"""Dependency analysis MCP tools.

This module provides tools for database object dependency analysis:
- dependency_analysis: Views, functions, triggers, sequences, extensions
"""

import asyncio
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import DependencyQueries
from tools.context import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
DependencyIncludeType = Literal["all", "views", "functions", "triggers", "sequences", "extensions", "fdw"]
FormatType = Literal["json", "markdown"]


def register_dependency_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register dependency analysis MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    async def _analyze_schema_dependencies(schema_name: str, include: str, table: str | None) -> dict:
        """Analyze dependencies for a single schema.

        Args:
            schema_name: Name of the schema to analyze
            include: What to include ('all', 'functions', 'triggers', 'sequences')
            table: Optional specific table to analyze triggers for

        Returns:
            Dictionary containing dependency information and summary
        """
        include_all = include == "all"
        result = {"schema": schema_name}

        if include_all or include == "functions":
            result["functions"] = await ctx.db_pool.fetch(DependencyQueries.functions_in_schema(schema_name))
            result["trigger_functions"] = await ctx.db_pool.fetch(DependencyQueries.trigger_functions(schema_name))

        if include_all or include == "triggers":
            if table:
                result["triggers"] = await ctx.db_pool.fetch(DependencyQueries.triggers_for_table(schema_name, table))

        if include_all or include == "sequences":
            result["sequence_usage"] = await ctx.db_pool.fetch(DependencyQueries.sequence_usage(schema_name))

        result["summary"] = {
            "functions": len(result.get("functions", [])),
            "trigger_functions": len(result.get("trigger_functions", [])),
        }
        return result

    @mcp.tool()
    @audited()
    async def dependency_analysis(
        schema: str | None = Field(
            default=None,
            description="Schema to analyze. Omit for all schemas, or specify one. Use get_schema() to list available.",
        ),
        include: DependencyIncludeType = Field(
            default="all",
            description="What to include: 'all', 'views', 'functions', 'triggers', 'sequences', 'extensions', 'fdw'",
        ),
        table: str | None = Field(default=None, description="Optional: analyze dependencies for specific table"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        summary_only: bool = Field(default=False, description="Return only summary counts, not detailed object lists"),
    ) -> str:
        """Comprehensive dependency analysis - views, functions, triggers, sequences, FDW.

        LEVEL: Database ↔ Schema ↔ Table (multi-level tool)
          - schema='all': Database level - dependencies for ALL schemas
          - schema='<name>': Schema level - dependencies in that schema
            (supports ANY schema name: 'sales', 'billing', 'auth', 'analytics', etc.)
          - table='users': Table level - what depends on this specific table

        REQUIRED: Specify schema explicitly - use 'all' for all schemas or a specific schema name.

        USE FOR: dependencies, views, functions, triggers, sequences, extensions, FDW, lineage,
        "what depends on this table?", "what views exist?", impact analysis before DROP.
        DO NOT USE FOR: table structure (use get_schema), index analysis (use maintenance_analysis),
        security permissions (use security_audit).

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'views': Views, materialized views, view dependencies
          - 'functions': User-defined functions, trigger functions
          - 'triggers': Triggers on tables
          - 'sequences': Sequences and their usage
          - 'extensions': Installed PostgreSQL extensions
          - 'fdw': Foreign data wrappers, foreign servers, foreign tables

        Examples:
            dependency_analysis() - All dependencies in public schema (default)
            dependency_analysis(schema='all') - Database-wide analysis
            dependency_analysis(schema='billing') - Dependencies in billing schema
            dependency_analysis(table='users') - What depends on users table
            dependency_analysis(include='views') - Only view dependencies
            dependency_analysis(include='functions') - Only functions
            dependency_analysis(include='triggers') - Only triggers
            dependency_analysis(include='fdw') - Foreign data wrappers only
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            include_all = include == "all"

            # If schema not specified, prompt the LLM to choose
            if schema is None:
                schemas = await ctx.schema_discovery.get_schemas()
                schema_list = [s["schema_name"] for s in schemas if s["table_count"] > 0][:20]
                return Response.ok(
                    {
                        "action_required": "specify_schema",
                        "message": "Please specify a schema to analyze. Use 'all' for full dependency map or choose a specific schema.",
                        "available_schemas": schema_list,
                        "example": "dependency_analysis(schema='public') or dependency_analysis(schema='all')",
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

                # Global dependencies (database-wide, only fetch once)
                if include_all or include == "views":
                    all_results["views"] = await ctx.db_pool.fetch(DependencyQueries.ALL_VIEWS)
                    all_results["materialized_views"] = await ctx.db_pool.fetch(DependencyQueries.MATERIALIZED_VIEWS)
                    all_results["view_dependencies"] = await ctx.db_pool.fetch(DependencyQueries.VIEW_DEPENDENCIES)

                if include_all or include == "triggers":
                    all_results["triggers"] = await ctx.db_pool.fetch(DependencyQueries.TRIGGERS)

                if include_all or include == "sequences":
                    all_results["sequences"] = await ctx.db_pool.fetch(DependencyQueries.SEQUENCES)

                if include_all or include == "extensions":
                    all_results["extensions"] = await ctx.db_pool.fetch(DependencyQueries.EXTENSIONS)

                if include_all or include == "fdw":
                    all_results["foreign_data_wrappers"] = await ctx.db_pool.fetch(
                        DependencyQueries.FOREIGN_DATA_WRAPPERS
                    )
                    all_results["foreign_servers"] = await ctx.db_pool.fetch(DependencyQueries.FOREIGN_SERVERS)
                    all_results["foreign_tables"] = await ctx.db_pool.fetch(DependencyQueries.FOREIGN_TABLES)

                # Per-schema dependencies - parallelize for better performance
                schema_results = await asyncio.gather(
                    *[_analyze_schema_dependencies(schema_name, include, table) for schema_name in schema_names]
                )

                total_functions = 0
                for schema_name, schema_result in zip(schema_names, schema_results, strict=False):
                    all_results["by_schema"][schema_name] = schema_result
                    total_functions += schema_result["summary"].get("functions", 0)

                all_results["summary"] = {
                    "schemas_analyzed": len(schema_names),
                    "views": len(all_results.get("views", [])),
                    "materialized_views": len(all_results.get("materialized_views", [])),
                    "functions_total": total_functions,
                    "triggers": len(all_results.get("triggers", [])),
                    "sequences": len(all_results.get("sequences", [])),
                    "extensions": len(all_results.get("extensions", [])),
                    "foreign_tables": len(all_results.get("foreign_tables", [])),
                }

                if format == "json":
                    if summary_only:
                        # Return only the summary counts, not detailed object lists
                        return Response.ok(
                            {
                                "schemas_analyzed": all_results["schemas_analyzed"],
                                "summary": all_results["summary"],
                                "summary_by_schema": {
                                    name: data.get("summary", {})
                                    for name, data in all_results.get("by_schema", {}).items()
                                },
                            },
                            connected=True,
                        )
                    return Response.ok(all_results, connected=True)

                lines = ["# Dependency Analysis (All Schemas)", ""]
                lines.append(f"**Schemas analyzed:** {', '.join(schema_names)}")
                lines.append("")

                s = all_results["summary"]
                lines.append("## Summary")
                lines.append(f"- Views: {s['views']} (materialized: {s['materialized_views']})")
                lines.append(f"- Functions: {s['functions_total']} total across schemas")
                lines.append(f"- Triggers: {s['triggers']}")
                lines.append(f"- Sequences: {s['sequences']}")
                lines.append(f"- Extensions: {s['extensions']}")
                lines.append(f"- Foreign tables: {s['foreign_tables']}")
                lines.append("")

                # Per-schema function counts
                lines.append("## Functions by Schema")
                for schema_name in schema_names:
                    func_count = all_results["by_schema"][schema_name]["summary"].get("functions", 0)
                    if func_count > 0:
                        lines.append(f"- {schema_name}: {func_count}")
                lines.append("")

                return Response.formatted("\n".join(lines), "markdown", connected=True)

            # Single schema analysis (original logic)
            result = {"schema": schema}

            if include_all or include == "views":
                if table:
                    result["view_dependencies"] = await ctx.db_pool.fetch(
                        DependencyQueries.view_dependencies_for_table(schema, table)
                    )
                else:
                    result["views"] = await ctx.db_pool.fetch(DependencyQueries.ALL_VIEWS)
                    result["materialized_views"] = await ctx.db_pool.fetch(DependencyQueries.MATERIALIZED_VIEWS)
                    result["view_dependencies"] = await ctx.db_pool.fetch(DependencyQueries.VIEW_DEPENDENCIES)

            if include_all or include == "functions":
                result["functions"] = await ctx.db_pool.fetch(DependencyQueries.functions_in_schema(schema))
                result["trigger_functions"] = await ctx.db_pool.fetch(DependencyQueries.trigger_functions(schema))

            if include_all or include == "triggers":
                if table:
                    result["triggers"] = await ctx.db_pool.fetch(DependencyQueries.triggers_for_table(schema, table))
                else:
                    result["triggers"] = await ctx.db_pool.fetch(DependencyQueries.TRIGGERS)

            if include_all or include == "sequences":
                result["sequences"] = await ctx.db_pool.fetch(DependencyQueries.SEQUENCES)
                result["sequence_usage"] = await ctx.db_pool.fetch(DependencyQueries.sequence_usage(schema))

            if include_all or include == "extensions":
                result["extensions"] = await ctx.db_pool.fetch(DependencyQueries.EXTENSIONS)

            if include_all or include == "fdw":
                result["foreign_data_wrappers"] = await ctx.db_pool.fetch(DependencyQueries.FOREIGN_DATA_WRAPPERS)
                result["foreign_servers"] = await ctx.db_pool.fetch(DependencyQueries.FOREIGN_SERVERS)
                result["foreign_tables"] = await ctx.db_pool.fetch(DependencyQueries.FOREIGN_TABLES)

            result["summary"] = {
                "views": len(result.get("views", [])),
                "materialized_views": len(result.get("materialized_views", [])),
                "functions": len(result.get("functions", [])),
                "triggers": len(result.get("triggers", [])),
                "sequences": len(result.get("sequences", [])),
                "extensions": len(result.get("extensions", [])),
                "foreign_tables": len(result.get("foreign_tables", [])),
            }

            if format == "json":
                if summary_only:
                    # Return only the summary, not detailed object lists
                    return Response.ok(
                        {
                            "schema": schema,
                            "summary": result["summary"],
                        },
                        connected=True,
                    )
                return Response.ok(result, connected=True)

            lines = [f"# Dependency Analysis: {schema}", ""]

            lines.append("## Summary")
            s = result["summary"]
            lines.append(f"- Views: {s['views']} (materialized: {s['materialized_views']})")
            lines.append(f"- Functions: {s['functions']}")
            lines.append(f"- Triggers: {s['triggers']}")
            lines.append(f"- Sequences: {s['sequences']}")
            lines.append(f"- Extensions: {s['extensions']}")
            lines.append(f"- Foreign tables: {s['foreign_tables']}")
            lines.append("")

            if result.get("view_dependencies"):
                lines.append("## View Dependencies")
                deps = result["view_dependencies"][:10]
                for d in deps:
                    if "view_name" in d:
                        lines.append(f"- {d['view_schema']}.{d['view_name']}")
                    else:
                        lines.append(
                            f"- {d['dependent_schema']}.{d['dependent_view']} → {d['source_schema']}.{d['source_table']}"
                        )
                if len(result["view_dependencies"]) > 10:
                    lines.append(f"- ... ({len(result['view_dependencies']) - 10} more)")
                lines.append("")

            if result.get("functions"):
                funcs = result["functions"][:10]
                lines.append(f"## Functions ({len(result['functions'])})")
                for f in funcs:
                    lines.append(f"- {f['function_name']} → {f.get('return_type', 'void')} ({f['language']})")
                if len(result["functions"]) > 10:
                    lines.append(f"- ... ({len(result['functions']) - 10} more)")
                lines.append("")

            if result.get("triggers"):
                trigs = result["triggers"][:10]
                lines.append(f"## Triggers ({len(result['triggers'])})")
                for t in trigs:
                    lines.append(f"- {t.get('trigger_name', 'N/A')} on {t.get('table_name', 'N/A')}")
                lines.append("")

            if result.get("extensions"):
                lines.append(f"## Extensions ({len(result['extensions'])})")
                for e in result["extensions"]:
                    lines.append(f"- {e['extension_name']} v{e['version']}")
                lines.append("")

            if result.get("foreign_tables"):
                lines.append(f"## Foreign Data ({len(result['foreign_tables'])} tables)")
                for ft in result["foreign_tables"][:5]:
                    lines.append(f"- {ft.get('schema_name', 'public')}.{ft.get('table_name', 'N/A')}")
                lines.append("")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="dependency_analysis")
