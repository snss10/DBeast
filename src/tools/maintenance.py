"""Database maintenance MCP tools.

This module provides tools for database maintenance analysis:
- maintenance_analysis: Index usage, vacuum status, table statistics
"""

import asyncio
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import IndexQueries, TableStatsQueries, VacuumQueries
from tools.context import ToolContext
from utils import MaintenanceThresholds

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
MaintenanceIncludeType = Literal["all", "indexes", "tables", "vacuum", "fk_indexes", "toast"]
FormatType = Literal["json", "markdown"]


def register_maintenance_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register maintenance-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    async def _analyze_schema_maintenance(schema_name: str, include: str, table: str | None) -> dict:
        """Analyze maintenance status for a single schema.

        Args:
            schema_name: Name of the schema to analyze
            include: What to include ('all', 'indexes', 'tables', 'vacuum', etc.)
            table: Optional specific table to analyze

        Returns:
            Dictionary containing maintenance analysis, issues, and recommendations
        """
        include_all = include == "all"
        result = {"schema": schema_name, "severity": "healthy"}
        issues = []
        recommendations = []

        if include_all or include == "indexes":
            indexes = await ctx.db_pool.fetch(IndexQueries.all_indexes(schema_name, table))
            result["indexes"] = [dict(r) for r in indexes]

            unused = await ctx.db_pool.fetch(IndexQueries.unused_indexes(schema_name, table))
            result["unused_indexes"] = [dict(r) for r in unused]

            duplicates = await ctx.db_pool.fetch(IndexQueries.duplicate_indexes(schema_name, table))
            result["duplicate_indexes"] = [dict(r) for r in duplicates]

            missing = await ctx.db_pool.fetch(IndexQueries.tables_needing_indexes(schema_name, table))
            result["tables_needing_indexes"] = [dict(r) for r in missing]

            largest = await ctx.db_pool.fetch(IndexQueries.largest_indexes(schema_name, table))
            result["largest_indexes"] = [dict(r) for r in largest]

            total_wasted = sum(u.get("wasted_bytes", 0) for u in result["unused_indexes"])
            if result["unused_indexes"]:
                issues.append(
                    f"[{schema_name}] {len(result['unused_indexes'])} unused indexes wasting {total_wasted / 1024 / 1024:.1f} MB"
                )
                recommendations.append(
                    {
                        "type": "drop_unused",
                        "schema": schema_name,
                        "action": "Consider dropping unused non-unique indexes",
                        "indexes": [u["index_name"] for u in result["unused_indexes"][:5]],
                    }
                )

            if result["duplicate_indexes"]:
                issues.append(f"[{schema_name}] {len(result['duplicate_indexes'])} potentially redundant index pairs")
                recommendations.append(
                    {
                        "type": "remove_duplicates",
                        "schema": schema_name,
                        "action": "Review and remove redundant indexes",
                    }
                )

            for m in result["tables_needing_indexes"][:5]:
                recommendations.append(
                    {
                        "type": "add_index",
                        "schema": schema_name,
                        "table": m["table_name"],
                        "message": f"{m['seq_scan']} seq scans, {m['avg_rows_per_seq_scan']:.0f} rows/scan",
                    }
                )

            result["index_summary"] = {
                "total_indexes": len(result["indexes"]),
                "unused_indexes": len(result["unused_indexes"]),
                "duplicate_pairs": len(result["duplicate_indexes"]),
                "tables_needing_indexes": len(result["tables_needing_indexes"]),
                "wasted_space_mb": round(total_wasted / 1024 / 1024, 1),
            }

        if include_all or include == "tables":
            tables = await ctx.db_pool.fetch(TableStatsQueries.table_statistics(schema_name, table))
            result["tables"] = [dict(r) for r in tables]

            for t in result["tables"]:
                tbl = t["table_name"]
                if (
                    t["seq_scan"] > MaintenanceThresholds.SEQ_SCAN_WARNING_COUNT
                    and t.get("index_usage_pct", 100) < MaintenanceThresholds.INDEX_USAGE_WARNING_PCT
                ):
                    issues.append(
                        f"[{schema_name}] '{tbl}': {t['seq_scan']} seq scans ({t.get('index_usage_pct', 0)}% idx use)"
                    )
                if t["live_rows"] > 0:
                    dead_ratio = t["dead_rows"] / t["live_rows"] * 100
                    if dead_ratio > MaintenanceThresholds.DEAD_ROW_RATIO_WARNING_PCT:
                        issues.append(f"[{schema_name}] '{tbl}': {dead_ratio:.0f}% dead rows - needs VACUUM")

            hot = await ctx.db_pool.fetch(TableStatsQueries.hot_tables(schema_name))
            result["hot_tables"] = [dict(r) for r in hot]

            result["table_summary"] = {
                "total_tables": len(result["tables"]),
                "total_rows": sum(t.get("live_rows", 0) for t in result["tables"]),
                "total_dead_rows": sum(t.get("dead_rows", 0) for t in result["tables"]),
            }

        if include_all or include == "vacuum":
            bloated = await ctx.db_pool.fetch(VacuumQueries.bloated_tables(schema_name))
            result["bloated_tables"] = [dict(r) for r in bloated]
            if bloated:
                issues.append(f"[{schema_name}] {len(bloated)} tables with significant dead tuples")

            never_vacuumed = await ctx.db_pool.fetch(VacuumQueries.never_vacuumed(schema_name))
            result["never_vacuumed"] = [dict(r) for r in never_vacuumed]
            if never_vacuumed:
                issues.append(f"[{schema_name}] {len(never_vacuumed)} tables with >1000 rows never vacuumed")
                result["severity"] = "warning"

            need_freeze = await ctx.db_pool.fetch(VacuumQueries.tables_needing_freeze(schema_name))
            result["tables_needing_freeze"] = [dict(r) for r in need_freeze]
            if need_freeze:
                issues.append(f"[{schema_name}] {len(need_freeze)} tables need vacuum freeze (XID age > 500M)")
                result["severity"] = "critical"

            if result["never_vacuumed"]:
                recommendations.append(
                    {
                        "priority": "high",
                        "schema": schema_name,
                        "action": f"Run VACUUM ANALYZE on {len(result['never_vacuumed'])} tables",
                    }
                )

            high_bloat = [
                t for t in result["bloated_tables"] if t.get("dead_pct", 0) > MaintenanceThresholds.TABLE_BLOAT_HIGH_PCT
            ]
            if high_bloat:
                recommendations.append(
                    {
                        "priority": "high",
                        "schema": schema_name,
                        "action": f"VACUUM FULL or pg_repack for {len(high_bloat)} severely bloated tables",
                    }
                )

            result["vacuum_summary"] = {
                "bloated_tables": len(result["bloated_tables"]),
                "never_vacuumed": len(result["never_vacuumed"]),
                "needing_freeze": len(result["tables_needing_freeze"]),
            }

        if include_all or include == "fk_indexes":
            fk_missing = await ctx.db_pool.fetch(IndexQueries.fk_missing_indexes(schema_name))
            result["fk_missing_indexes"] = [dict(r) for r in fk_missing]
            if fk_missing:
                issues.append(f"[{schema_name}] {len(fk_missing)} foreign keys without supporting indexes")
                for fk in fk_missing[:3]:
                    recommendations.append(
                        {
                            "type": "add_fk_index",
                            "priority": "medium",
                            "schema": schema_name,
                            "table": fk["table_name"],
                            "fk_name": fk["fk_name"],
                            "action": fk.get("suggested_index", f"Add index on {fk['fk_columns']}"),
                        }
                    )
            result["fk_index_summary"] = {"missing_indexes": len(fk_missing)}

        if include_all or include == "toast":
            toast_tables = await ctx.db_pool.fetch(TableStatsQueries.toast_sizes(schema_name))
            result["toast_tables"] = [dict(r) for r in toast_tables]
            large_toast = [t for t in toast_tables if t.get("toast_pct", 0) > 50]
            if large_toast:
                issues.append(f"[{schema_name}] {len(large_toast)} tables with >50% TOAST storage")
            result["toast_summary"] = {"tables_with_toast": len(toast_tables), "large_toast_tables": len(large_toast)}

        result["issues"] = issues
        result["recommendations"] = recommendations
        return result

    @mcp.tool()
    @audited()
    async def maintenance_analysis(
        include: MaintenanceIncludeType = Field(
            default="all", description="What to include: 'all', 'indexes', 'tables', 'vacuum', 'fk_indexes', 'toast'"
        ),
        table: str | None = Field(default=None, description="Specific table (or all tables if not specified)"),
        schema: str | None = Field(
            default=None,
            description="Schema to analyze. Omit for all schemas, or specify one. Use get_schema() to list available.",
        ),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        summary_only: bool = Field(
            default=False, description="Return only summary counts and issues, not detailed lists"
        ),
    ) -> str:
        """Table and index maintenance - analyzes indexes, vacuum status, table bloat, FK indexes.

        LEVEL: Database ↔ Schema ↔ Table (multi-level tool)
          - schema='all': Database level - maintenance status for ALL schemas
          - schema='<name>': Schema level - all tables in that schema
            (supports ANY schema name: 'sales', 'billing', 'auth', 'analytics', etc.)
          - table='users': Table level - specific table analysis

        REQUIRED: Specify schema explicitly - use 'all' for all schemas or a specific schema name.

        USE FOR: finding unused indexes, duplicate indexes, tables needing vacuum, FK missing indexes,
        table sizes, TOAST analysis, autovacuum status, "which indexes should I drop?".
        DO NOT USE FOR: live connections/locks (use database_health), slow query history (use query_performance),
        specific query optimization (use query_optimizer), schema structure (use get_schema),
        partitioned tables (use partition_analysis).
        STATIC: Analyzes stored statistics, not real-time activity.

        ERROR RECOVERY:
        - "not connected": Call connect() first or pass url parameter
        - "schema not found": Verify schema exists with get_schema()
        - Large payload: Use summary_only=True or include='indexes' to filter results
        - "permission denied": User needs read access to pg_catalog views

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'indexes': All indexes, unused indexes, duplicate indexes, tables needing indexes, largest indexes
          - 'tables': Table statistics, hot tables (most active)
          - 'vacuum': Bloated tables, never vacuumed, tables needing freeze, autovacuum settings
          - 'fk_indexes': Foreign keys missing supporting indexes
          - 'toast': TOAST storage analysis (large object storage)

        Examples:
            maintenance_analysis() - All tables in public schema (default)
            maintenance_analysis(schema='all') - All schemas (database-wide)
            maintenance_analysis(schema='billing') - All tables in billing schema
            maintenance_analysis(schema='auth', table='users') - Specific table in auth schema
            maintenance_analysis(include='indexes') - Only index analysis
            maintenance_analysis(include='vacuum') - Only vacuum/bloat analysis
            maintenance_analysis(include='fk_indexes') - Only FK index analysis
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
                        "example": "maintenance_analysis(schema='public') or maintenance_analysis(schema='all')",
                    },
                    connected=True,
                )

            # Handle schema="all" - analyze all user schemas
            if schema.lower() == "all":
                schemas = await ctx.schema_discovery.get_schemas()
                schema_names = [s["schema_name"] for s in schemas if s["table_count"] > 0]

                if not schema_names:
                    return Response.ok({"message": "No schemas with tables found"}, connected=True)

                all_results = {"schemas_analyzed": schema_names, "by_schema": {}}
                all_issues = []
                all_recommendations = []
                overall_severity = "healthy"

                # Parallelize schema analysis for better performance
                schema_results = await asyncio.gather(
                    *[_analyze_schema_maintenance(schema_name, include, table) for schema_name in schema_names]
                )

                for schema_name, schema_result in zip(schema_names, schema_results, strict=False):
                    all_results["by_schema"][schema_name] = schema_result
                    all_issues.extend(schema_result.get("issues", []))
                    all_recommendations.extend(schema_result.get("recommendations", []))
                    if schema_result.get("severity") == "critical":
                        overall_severity = "critical"
                    elif schema_result.get("severity") == "warning" and overall_severity != "critical":
                        overall_severity = "warning"

                # Add global vacuum info (only once, not per-schema)
                if include == "all" or include == "vacuum":
                    running_vacuums = await ctx.db_pool.fetch(VacuumQueries.RUNNING_VACUUMS)
                    all_results["running_vacuums"] = [dict(r) for r in running_vacuums]
                    av_settings = await ctx.db_pool.fetch(VacuumQueries.AUTOVACUUM_SETTINGS)
                    all_results["autovacuum_settings"] = [dict(r) for r in av_settings]
                    av_enabled = next(
                        (s for s in all_results["autovacuum_settings"] if s["name"] == "autovacuum"), None
                    )
                    if av_enabled and av_enabled["setting"] != "on":
                        all_recommendations.insert(
                            0, {"priority": "critical", "action": "Enable autovacuum immediately"}
                        )

                all_results["severity"] = overall_severity
                all_results["issues"] = all_issues
                all_results["issue_count"] = len(all_issues)
                all_results["recommendations"] = all_recommendations
                all_results["healthy"] = len(all_issues) == 0

                if format == "json":
                    if summary_only:
                        # Return only summary counts, not detailed lists
                        summary = {
                            "schemas_analyzed": all_results["schemas_analyzed"],
                            "severity": overall_severity,
                            "issue_count": len(all_issues),
                            "issues": all_issues[:10],  # Top 10 issues only
                            "recommendations": all_recommendations[:5],  # Top 5 recommendations
                            "healthy": len(all_issues) == 0,
                            "summary_by_schema": {
                                name: {
                                    "severity": data.get("severity", "unknown"),
                                    "issue_count": len(data.get("issues", [])),
                                }
                                for name, data in all_results.get("by_schema", {}).items()
                            },
                        }
                        return Response.ok(summary, connected=True)
                    return Response.ok(all_results, connected=True)

                lines = ["# Maintenance Analysis (All Schemas)", ""]
                lines.append(f"**Schemas analyzed:** {', '.join(schema_names)}")
                lines.append(f"**Status:** {overall_severity.upper()}")
                lines.append(f"**Total issues:** {len(all_issues)}")
                lines.append("")

                if all_issues:
                    lines.append("## Issues by Schema")
                    for issue in all_issues:
                        lines.append(f"- {issue}")
                    lines.append("")

                if all_recommendations:
                    lines.append("## Recommendations")
                    for rec in all_recommendations[:10]:
                        schema_prefix = f"[{rec.get('schema', 'global')}] " if rec.get("schema") else ""
                        lines.append(
                            f"- [{rec.get('priority', 'info').upper()}] {schema_prefix}{rec.get('action', '')}"
                        )
                    lines.append("")

                return Response.formatted("\n".join(lines), "markdown", connected=True)

            # Single schema analysis - reuse the helper function
            result = await _analyze_schema_maintenance(schema, include, table)

            # Strip schema prefix from issues for single-schema output
            issues = [issue.replace(f"[{schema}] ", "") for issue in result.get("issues", [])]
            result["issues"] = issues
            result["issue_count"] = len(issues)

            # Strip schema from recommendations for single-schema output
            recommendations = result.get("recommendations", [])
            for rec in recommendations:
                rec.pop("schema", None)
            result["recommendations"] = recommendations
            result["healthy"] = len(issues) == 0

            # Add global vacuum info for single schema (running vacuums, autovacuum settings)
            include_all = include == "all"
            if include_all or include == "vacuum":
                running_vacuums = await ctx.db_pool.fetch(VacuumQueries.RUNNING_VACUUMS)
                result["running_vacuums"] = [dict(r) for r in running_vacuums]
                av_settings = await ctx.db_pool.fetch(VacuumQueries.AUTOVACUUM_SETTINGS)
                result["autovacuum_settings"] = [dict(r) for r in av_settings]
                av_enabled = next((s for s in result["autovacuum_settings"] if s["name"] == "autovacuum"), None)
                if av_enabled and av_enabled["setting"] != "on":
                    recommendations.insert(0, {"priority": "critical", "action": "Enable autovacuum immediately"})

                # Add running_vacuums count to vacuum_summary if it exists
                if "vacuum_summary" in result:
                    result["vacuum_summary"]["running_vacuums"] = len(result["running_vacuums"])

            if format == "json":
                if summary_only:
                    # Return only summary counts, not detailed lists
                    summary = {
                        "schema": schema,
                        "severity": result.get("severity", "unknown"),
                        "issue_count": len(issues),
                        "issues": issues[:10],  # Top 10 issues only
                        "recommendations": recommendations[:5],  # Top 5 recommendations
                        "healthy": len(issues) == 0,
                        "index_summary": result.get("index_summary"),
                        "vacuum_summary": result.get("vacuum_summary"),
                        "table_summary": result.get("table_summary"),
                    }
                    return Response.ok(summary, connected=True)
                return Response.ok(result, connected=True)

            lines = ["# Maintenance Analysis", ""]
            lines.append(f"**Status:** {result['severity'].upper()}")
            lines.append(f"**Issues:** {len(issues)}")
            lines.append("")

            if issues:
                lines.append("## Issues")
                for issue in issues:
                    lines.append(f"- {issue}")
                lines.append("")

            if recommendations:
                lines.append("## Recommendations")
                for rec in recommendations:
                    lines.append(f"- [{rec.get('priority', 'info').upper()}] {rec.get('action', '')}")
                lines.append("")

            if "index_summary" in result:
                s = result["index_summary"]
                lines.append("## Indexes")
                lines.append(f"- Total: {s['total_indexes']}, Unused: {s['unused_indexes']}")
                lines.append(f"- Wasted space: {s['wasted_space_mb']} MB")
                lines.append("")

            if "vacuum_summary" in result:
                s = result["vacuum_summary"]
                lines.append("## Vacuum Status")
                lines.append(f"- Bloated tables: {s['bloated_tables']}")
                lines.append(f"- Never vacuumed: {s['never_vacuumed']}")
                lines.append(f"- Needing freeze: {s['needing_freeze']}")
                lines.append("")

            if "fk_index_summary" in result:
                s = result["fk_index_summary"]
                lines.append("## Foreign Key Indexes")
                lines.append(f"- Missing indexes: {s['missing_indexes']}")
                if result.get("fk_missing_indexes"):
                    lines.append("")
                    for fk in result["fk_missing_indexes"][:5]:
                        lines.append(f"  - `{fk['table_name']}.{fk['fk_name']}` → {fk['references_table']}")
                lines.append("")

            if "toast_summary" in result:
                s = result["toast_summary"]
                lines.append("## TOAST Storage")
                lines.append(f"- Tables with TOAST: {s['tables_with_toast']}")
                lines.append(f"- Large TOAST (>50%): {s['large_toast_tables']}")
                if result.get("toast_tables"):
                    lines.append("")
                    for t in result["toast_tables"][:5]:
                        lines.append(f"  - `{t['table_name']}`: {t['toast_size']} ({t['toast_pct']}% of total)")
                lines.append("")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="maintenance_analysis")
