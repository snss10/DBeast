"""Partition analysis MCP tools.

This module provides tools for partitioned table analysis:
- partition_analysis: Partition details, sizes, activity, maintenance
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import PartitionQueries
from tools.context import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
PartitionIncludeType = Literal["all", "details", "size", "activity", "indexes", "maintenance"]
FormatType = Literal["json", "markdown"]


def register_partition_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register partition analysis MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def partition_analysis(
        table: str | None = Field(
            default=None, description="Partitioned table name (omit to list all partitioned tables)"
        ),
        schema: str | None = Field(
            default=None,
            description="Schema name. REQUIRED when table is specified. Use get_schema() to list available schemas.",
        ),
        include: PartitionIncludeType = Field(
            default="all", description="What to include: 'all', 'details', 'size', 'activity', 'indexes', 'maintenance'"
        ),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
    ) -> str:
        """Partition analysis - list all partitioned tables or analyze specific table.

        LEVEL: Schema ↔ Table (multi-level tool)
          - table=None (default): Lists all partitioned tables across ALL schemas
          - table='orders': Requires schema - detailed partition analysis for that table

        USE FOR: partitions, partition analysis, partition details, partition size, inheritance,
        "which tables are partitioned?", partition skew detection, empty partition identification.
        DO NOT USE FOR: non-partitioned table maintenance (use maintenance_analysis),
        schema structure (use get_schema), index health (use maintenance_analysis).

        INCLUDE OPTIONS (only when table is specified):
          - 'all': Everything (default)
          - 'details': Partition details - boundaries, row counts, dead rows
          - 'size': Size distribution - partition sizes, percentages, skew detection
          - 'activity': Partition activity - inserts, updates per partition
          - 'indexes': Partition indexes
          - 'maintenance': Empty partitions, maintenance candidates, default partitions

        Examples:
            partition_analysis() - List all partitioned tables across all schemas
            partition_analysis(table='events', schema='logs') - Detailed analysis of events table
            partition_analysis(table='orders', schema='shipment', include='size') - Size distribution
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            if not table:
                # List all partitioned tables across all schemas
                rows = await ctx.db_pool.fetch(PartitionQueries.PARTITIONED_TABLES)

                if format == "json":
                    return Response.ok({"partitioned_tables": rows, "count": len(rows)}, connected=True)

                if not rows:
                    return Response.formatted("No partitioned tables found.", "text", connected=True)

                lines = ["# Partitioned Tables", ""]
                lines.append("| Schema | Table | Strategy | Partition Key | Partitions | Size |")
                lines.append("|--------|-------|----------|---------------|------------|------|")
                for r in rows:
                    lines.append(
                        f"| {r['schema_name']} | {r['table_name']} | {r['partition_strategy']} | {r['partition_key']} | {r['partition_count']} | {r['total_size']} |"
                    )
                return Response.formatted("\n".join(lines), "markdown", connected=True)

            # If schema not specified when table is provided, prompt for it
            if schema is None:
                schemas = await ctx.db_pool.fetch(
                    "SELECT DISTINCT schemaname FROM pg_tables WHERE tablename = $1", table
                )
                if schemas:
                    schema_list = [s["schemaname"] for s in schemas]
                    return Response.ok(
                        {
                            "action_required": "specify_schema",
                            "message": f"Please specify the schema for table '{table}'. Use get_schema() to see all available schemas.",
                            "table_found_in_schemas": schema_list,
                            "example": f"partition_analysis(table='{table}', schema='{schema_list[0]}')",
                        },
                        connected=True,
                    )
                else:
                    return Response.ok(
                        {
                            "action_required": "specify_schema",
                            "message": f"Please specify the schema for table '{table}'. Table not found - verify the name.",
                            "example": f"partition_analysis(table='{table}', schema='public')",
                        },
                        connected=True,
                    )

            include_all = include == "all"
            result = {"table": f"{schema}.{table}"}

            if include_all or include == "details":
                result["details"] = await ctx.db_pool.fetch(PartitionQueries.partition_details(schema, table))

            if include_all or include == "size":
                result["size_distribution"] = await ctx.db_pool.fetch(
                    PartitionQueries.partition_size_distribution(schema, table)
                )

            if include_all or include == "activity":
                result["activity"] = await ctx.db_pool.fetch(PartitionQueries.partition_activity(schema, table))

            if include_all or include == "indexes":
                result["indexes"] = await ctx.db_pool.fetch(PartitionQueries.partition_indexes(schema, table))

            if include_all or include == "maintenance":
                result["empty_partitions"] = await ctx.db_pool.fetch(PartitionQueries.empty_partitions(schema, table))
                result["maintenance_candidates"] = await ctx.db_pool.fetch(
                    PartitionQueries.PARTITION_MAINTENANCE_CANDIDATES
                )
                result["default_partitions"] = await ctx.db_pool.fetch(PartitionQueries.DEFAULT_PARTITION)

            if format == "json":
                return Response.ok(result, connected=True)

            details = result.get("details", [])
            if not details:
                return Response.formatted(
                    f"Table `{schema}.{table}` is not partitioned or doesn't exist.",
                    "text",
                    connected=True,
                )

            lines = [f"# Partition Analysis: {schema}.{table}", ""]

            total_rows = sum(d.get("row_count", 0) or 0 for d in details)
            total_dead = sum(d.get("dead_rows", 0) or 0 for d in details)
            empty_count = len(result.get("empty_partitions", []))

            lines.append("## Summary")
            lines.append(f"- Total partitions: {len(details)}")
            lines.append(f"- Total rows: {total_rows:,}")
            lines.append(f"- Total dead rows: {total_dead:,}")
            lines.append(f"- Empty partitions: {empty_count}")
            lines.append("")

            if "size_distribution" in result and result["size_distribution"]:
                distribution = result["size_distribution"]
                max_pct = max((d.get("size_pct", 0) or 0) for d in distribution)
                min_pct = min((d.get("size_pct", 0) or 0) for d in distribution if d.get("size_pct"))

                lines.append("## Size Distribution")
                lines.append(f"- Largest: {max_pct}%, Smallest: {min_pct}%")
                if max_pct > 50:
                    lines.append("- **Warning:** Significant partition skew")
                lines.append("")

                lines.append("| Partition | Size | % | Rows |")
                lines.append("|-----------|------|---|------|")
                for d in distribution[:10]:
                    lines.append(
                        f"| {d['partition_name']} | {d['size']} | {d.get('size_pct', 'N/A')}% | {d.get('row_count', 'N/A')} |"
                    )
                lines.append("")

            if "activity" in result and result["activity"]:
                activity = result["activity"]
                lines.append("## Activity")
                for a in activity[:5]:
                    lines.append(
                        f"- {a['partition_name']}: {a.get('inserts', 0)} inserts, {a.get('updates', 0)} updates"
                    )
                lines.append("")

            if result.get("empty_partitions"):
                lines.append(f"## Empty Partitions ({len(result['empty_partitions'])})")
                for e in result["empty_partitions"][:5]:
                    lines.append(f"- {e['partition_name']}")
                lines.append("")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="partition_analysis")
