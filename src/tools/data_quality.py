"""Data quality analysis MCP tools.

This module provides tools for data quality analysis:
- data_quality_report: Nulls, cardinality, empty tables, outliers
- duplicate_detection: Find duplicate rows by columns
"""

import asyncio
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import DataQualityQueries
from tools.context import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
DataQualityIncludeType = Literal["all", "nulls", "cardinality", "empty", "outliers", "soft_delete", "types"]
FormatType = Literal["json", "markdown"]


def register_data_quality_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register data quality MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def duplicate_detection(
        table: str = Field(description="Table name to check"),
        columns: str = Field(description="Comma-separated column names (e.g., 'email,name')"),
        schema: str | None = Field(
            default=None,
            description="Schema containing the table. REQUIRED. Use get_schema() to list available schemas.",
        ),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
    ) -> str:
        """Detect duplicate rows in a table based on specified columns.

        LEVEL: Table ↔ Column (requires table and columns parameters)

        USE FOR: finding duplicates, duplicate rows, "are there duplicate emails?",
        detecting duplicate records, data deduplication analysis.
        DO NOT USE FOR: general data quality (use data_quality_report), schema structure (use get_schema),
        null analysis (use data_quality_report with include='nulls').

        Examples:
            duplicate_detection(table='users', columns='email', schema='public')
            duplicate_detection(table='orders', columns='customer_id,product_id', schema='shipment')
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        # If schema not specified, prompt to provide it
        if schema is None:
            schemas = await ctx.schema_discovery.get_schemas()
            schema_list = [s["schema_name"] for s in schemas if s["table_count"] > 0][:20]
            return Response.ok(
                {
                    "action_required": "specify_schema",
                    "message": "Please specify the schema parameter for the table. Use get_schema() to see all available schemas.",
                    "available_schemas": schema_list,
                    "example": f"duplicate_detection(table='{table}', columns='{columns}', schema='public')",
                },
                connected=True,
            )

        query = DataQualityQueries.duplicate_detection(schema, table, columns)
        try:
            rows = await ctx.db_pool.fetch(query)
        except Exception as e:
            return internal_error(e, context="duplicate_detection")

        result = {
            "table": f"{schema}.{table}",
            "columns_checked": columns,
            "duplicate_groups": len(rows),
            "duplicates": rows[:50],
        }

        if format == "json":
            return Response.ok(result, connected=True)

        lines = [f"# Duplicate Detection: {schema}.{table}", ""]
        lines.append(f"**Columns checked:** {columns}")
        lines.append(f"**Duplicate groups found:** {len(rows)}")
        lines.append("")
        if rows:
            lines.append("| " + " | ".join(columns.split(",")) + " | Count |")
            lines.append("|" + "---|" * (len(columns.split(",")) + 1))
            for r in rows[:20]:
                vals = [str(r.get(c.strip(), "N/A")) for c in columns.split(",")]
                lines.append(f"| {' | '.join(vals)} | {r.get('duplicate_count', 'N/A')} |")
        else:
            lines.append("No duplicates found.")
        return Response.formatted("\n".join(lines), "markdown", connected=True)

    async def _analyze_schema_quality(
        schema_name: str, include: str, table: str | None, outlier_column: str | None
    ) -> dict:
        """Analyze data quality for a single schema.

        Args:
            schema_name: Name of the schema to analyze
            include: What to include ('all', 'nulls', 'cardinality', etc.)
            table: Optional specific table to analyze
            outlier_column: Optional column for outlier detection

        Returns:
            Dictionary containing quality analysis results and issues
        """
        include_all = include == "all"
        result = {"schema": schema_name}
        issues = []

        if include_all or include == "nulls":
            result["null_analysis"] = await ctx.db_pool.fetch(DataQualityQueries.null_analysis(schema_name, table))
            high_null = [r for r in result["null_analysis"] if r.get("null_severity") == "high"]
            if high_null:
                issues.append(f"[{schema_name}] {len(high_null)} columns with >50% NULL values")

        if include_all or include == "cardinality":
            result["cardinality"] = await ctx.db_pool.fetch(DataQualityQueries.cardinality_analysis(schema_name, table))

        if include_all or include == "empty":
            result["empty_tables"] = await ctx.db_pool.fetch(DataQualityQueries.empty_tables(schema_name))
            if result["empty_tables"]:
                issues.append(f"[{schema_name}] {len(result['empty_tables'])} empty tables")

        if include_all or include == "types":
            result["data_types"] = await ctx.db_pool.fetch(DataQualityQueries.data_type_consistency(schema_name, table))
            type_issues = [r for r in result["data_types"] if r.get("type_recommendation") != "ok"]
            if type_issues:
                issues.append(f"[{schema_name}] {len(type_issues)} columns with data type recommendations")

        if include_all or include == "soft_delete":
            result["soft_deletes"] = await ctx.db_pool.fetch(DataQualityQueries.soft_delete_detection(schema_name))
            if result["soft_deletes"]:
                tables = {s["table_name"] for s in result["soft_deletes"]}
                issues.append(f"[{schema_name}] {len(tables)} tables with soft delete patterns")

        if (include_all or include == "outliers") and table and outlier_column:
            try:
                stats = await ctx.db_pool.fetchrow(
                    DataQualityQueries.outlier_detection(schema_name, table, outlier_column)
                )
                counts = await ctx.db_pool.fetchrow(
                    DataQualityQueries.count_outliers(schema_name, table, outlier_column)
                )
                result["outlier_analysis"] = {
                    "column": outlier_column,
                    "statistics": dict(stats) if stats else {},
                    "counts": dict(counts) if counts else {},
                }
                if counts and (counts.get("below_lower", 0) + counts.get("above_upper", 0)) > 0:
                    issues.append(f"[{schema_name}] Outliers detected in {table}.{outlier_column}")
            except Exception as e:
                result["outlier_error"] = str(e)

        result["issues"] = issues
        return result

    @mcp.tool()
    @audited()
    async def data_quality_report(
        schema: str | None = Field(
            default=None,
            description="Schema to analyze. Omit for all schemas, or specify one. Use get_schema() to list available.",
        ),
        table: str | None = Field(default=None, description="Optional table name"),
        include: DataQualityIncludeType = Field(
            default="all",
            description="What to include: 'all', 'nulls', 'cardinality', 'empty', 'outliers', 'soft_delete', 'types'",
        ),
        outlier_column: str | None = Field(default=None, description="For outlier detection: column name"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        summary_only: bool = Field(
            default=False, description="Return only summary counts and issues, not detailed lists"
        ),
    ) -> str:
        """Comprehensive data quality analysis - nulls, types, empty tables, outliers, soft deletes.

        LEVEL: Database ↔ Schema ↔ Table ↔ Column (multi-level tool)
          - schema='all': Database level - quality analysis for ALL schemas
          - schema='<name>': Schema level - all tables in that schema
            (supports ANY schema name: 'sales', 'billing', 'auth', 'analytics', etc.)
          - table='users': Table level - specific table analysis
          - outlier_column='age': Column level - outlier detection for specific column

        REQUIRED: Specify schema explicitly - use 'all' for all schemas or a specific schema name.

        USE FOR: data quality, data profiling, finding nulls, empty tables, outliers, soft deletes,
        cardinality analysis, "which columns have too many nulls?", data validation.
        DO NOT USE FOR: finding duplicates (use duplicate_detection), security/PII scan (use sensitive_data_scan),
        schema structure (use get_schema).

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'nulls': Null analysis - columns with high NULL percentages
          - 'cardinality': Cardinality analysis - unique value counts
          - 'empty': Empty tables - tables with zero rows
          - 'outliers': Outlier detection (requires table and outlier_column params)
          - 'soft_delete': Soft delete patterns - finds deleted_at, is_deleted columns
          - 'types': Data type consistency recommendations

        Examples:
            data_quality_report() - All tables in public schema (default)
            data_quality_report(schema='all') - Database-wide analysis
            data_quality_report(schema='billing') - All tables in billing schema
            data_quality_report(include='nulls') - Only null analysis
            data_quality_report(include='empty') - Only empty tables
            data_quality_report(include='soft_delete') - Find soft delete patterns
            data_quality_report(table='users', include='outliers', outlier_column='age') - Outlier detection
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            # If schema not specified, prompt the LLM to choose
            if schema is None:
                schemas = await ctx.schema_discovery.get_schemas()
                schema_list = [s["schema_name"] for s in schemas if s["table_count"] > 0][:20]
                return Response.ok(
                    {
                        "action_required": "specify_schema",
                        "message": "Please specify a schema to analyze. Use 'all' for comprehensive analysis or choose a specific schema.",
                        "available_schemas": schema_list,
                        "example": "data_quality_report(schema='public') or data_quality_report(schema='all')",
                    },
                    connected=True,
                )

            # Handle schema="all" - analyze all schemas
            if schema.lower() == "all":
                schemas = await ctx.schema_discovery.get_schemas()
                schema_names = [s["schema_name"] for s in schemas if s["table_count"] > 0]

                if not schema_names:
                    return Response.ok({"message": "No schemas with tables found"}, connected=True)

                all_results = {"schemas_analyzed": schema_names, "by_schema": {}}
                all_issues = []

                # Parallelize schema analysis for better performance
                schema_results = await asyncio.gather(
                    *[
                        _analyze_schema_quality(schema_name, include, table, outlier_column)
                        for schema_name in schema_names
                    ]
                )

                for schema_name, schema_result in zip(schema_names, schema_results, strict=False):
                    all_results["by_schema"][schema_name] = schema_result
                    all_issues.extend(schema_result.get("issues", []))

                all_results["issues"] = all_issues
                all_results["issue_count"] = len(all_issues)

                if format == "json":
                    if summary_only:
                        summary = {
                            "schemas_analyzed": all_results["schemas_analyzed"],
                            "issue_count": len(all_issues),
                            "issues": all_issues[:10],  # Top 10 issues only
                            "summary_by_schema": {
                                name: {"issue_count": len(data.get("issues", []))}
                                for name, data in all_results.get("by_schema", {}).items()
                            },
                        }
                        return Response.ok(summary, connected=True)
                    return Response.ok(all_results, connected=True)

                lines = ["# Data Quality Report (All Schemas)", ""]
                lines.append(f"**Schemas analyzed:** {', '.join(schema_names)}")
                lines.append(f"**Total issues:** {len(all_issues)}")
                lines.append("")

                if all_issues:
                    lines.append("## Issues by Schema")
                    for issue in all_issues:
                        lines.append(f"- {issue}")
                    lines.append("")

                return Response.formatted("\n".join(lines), "markdown", connected=True)

            # Single schema analysis
            include_all = include == "all"
            result = {"schema": schema}
            issues = []

            if include_all or include == "nulls":
                result["null_analysis"] = await ctx.db_pool.fetch(DataQualityQueries.null_analysis(schema, table))
                high_null = [r for r in result["null_analysis"] if r.get("null_severity") == "high"]
                if high_null:
                    issues.append(f"{len(high_null)} columns with >50% NULL values")

            if include_all or include == "cardinality":
                result["cardinality"] = await ctx.db_pool.fetch(DataQualityQueries.cardinality_analysis(schema, table))

            if include_all or include == "empty":
                result["empty_tables"] = await ctx.db_pool.fetch(DataQualityQueries.empty_tables(schema))
                if result["empty_tables"]:
                    issues.append(f"{len(result['empty_tables'])} empty tables")

            if include_all or include == "types":
                result["data_types"] = await ctx.db_pool.fetch(DataQualityQueries.data_type_consistency(schema, table))
                type_issues = [r for r in result["data_types"] if r.get("type_recommendation") != "ok"]
                if type_issues:
                    issues.append(f"{len(type_issues)} columns with data type recommendations")

            if include_all or include == "soft_delete":
                result["soft_deletes"] = await ctx.db_pool.fetch(DataQualityQueries.soft_delete_detection(schema))
                if result["soft_deletes"]:
                    tables = {s["table_name"] for s in result["soft_deletes"]}
                    issues.append(f"{len(tables)} tables with soft delete patterns")

            if (include_all or include == "outliers") and table and outlier_column:
                try:
                    stats = await ctx.db_pool.fetchrow(
                        DataQualityQueries.outlier_detection(schema, table, outlier_column)
                    )
                    counts = await ctx.db_pool.fetchrow(
                        DataQualityQueries.count_outliers(schema, table, outlier_column)
                    )
                    result["outlier_analysis"] = {
                        "column": outlier_column,
                        "statistics": dict(stats) if stats else {},
                        "counts": dict(counts) if counts else {},
                    }
                    if counts and (counts.get("below_lower", 0) + counts.get("above_upper", 0)) > 0:
                        issues.append(f"Outliers detected in {table}.{outlier_column}")
                except Exception as e:
                    result["outlier_error"] = str(e)

            result["issues"] = issues
            result["issue_count"] = len(issues)

            if format == "json":
                if summary_only:
                    summary = {
                        "schema": schema,
                        "issue_count": len(issues),
                        "issues": issues[:10],  # Top 10 issues only
                        "null_columns_high": len(
                            [r for r in result.get("null_analysis", []) if r.get("null_severity") == "high"]
                        ),
                        "empty_tables": len(result.get("empty_tables", [])),
                        "soft_delete_tables": len(result.get("soft_delete", [])),
                    }
                    return Response.ok(summary, connected=True)
                return Response.ok(result, connected=True)

            lines = [f"# Data Quality Report: {schema}", ""]
            lines.append(f"**Issues Found:** {len(issues)}")
            lines.append("")

            if issues:
                lines.append("## Issues")
                for issue in issues:
                    lines.append(f"- {issue}")
                lines.append("")

            if "null_analysis" in result:
                high_null = [r for r in result["null_analysis"] if r.get("null_severity") == "high"]
                if high_null:
                    lines.append("## High NULL Columns (>50%)")
                    for r in high_null[:10]:
                        lines.append(f"- `{r['table_name']}.{r['column_name']}`: {r['null_pct']}%")
                    lines.append("")

            if "empty_tables" in result and result["empty_tables"]:
                lines.append(f"## Empty Tables ({len(result['empty_tables'])})")
                for t in result["empty_tables"][:10]:
                    lines.append(f"- `{t['table_name']}`")
                lines.append("")

            if "soft_deletes" in result and result["soft_deletes"]:
                lines.append("## Soft Delete Patterns")
                seen = set()
                for s in result["soft_deletes"]:
                    if s["table_name"] not in seen:
                        seen.add(s["table_name"])
                        lines.append(f"- `{s['table_name']}`: {s['column_name']} ({s['delete_pattern']})")
                lines.append("")

            if "outlier_analysis" in result:
                oa = result["outlier_analysis"]
                c = oa.get("counts", {})
                lines.append(f"## Outliers: {oa['column']}")
                lines.append(f"- Below lower bound: {c.get('below_lower', 0)}")
                lines.append(f"- Above upper bound: {c.get('above_upper', 0)}")
                lines.append("")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="data_quality_report")
