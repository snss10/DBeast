"""Schema discovery MCP tools.

This module provides tools for exploring database schema structure:
- get_schema: List schemas, tables, columns, relationships, and indexes
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from tools.context import ToolContext
from utils import get_cached_schema, set_cached_schema

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
SchemaFormatType = Literal["json", "text", "markdown", "mermaid"]


def register_schema_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register schema-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def get_schema(
        schema: str | None = Field(
            default=None,
            description="Schema name. Omit or 'all' for all schemas; specific name for tables.",
        ),
        format: SchemaFormatType = Field(default="json", description="Output format"),
        limit: int = Field(default=100, ge=1, le=500, description="Max tables to return (1-500)"),
        offset: int = Field(default=0, ge=0, description="Skip first N tables (for pagination)"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
    ) -> str:
        """Discover database schema - tables, columns, relationships, indexes.

        LEVEL: Database (lists all schemas) or Schema (specific schema details)

        USE FOR: listing tables, columns, foreign keys, ERD generation.
        DO NOT USE FOR: table data (execute_query), index health (maintenance_analysis).

        ERROR RECOVERY:
        - "schema not found": Call get_schema() without params to list all schemas
        - "no tables found": Schema exists but is empty, verify with execute_query
        - "not connected": Call connect() first or pass url parameter

        PAGINATION: For large schemas (100+ tables), use limit/offset.

        Examples:
            get_schema() - List all schemas
            get_schema(schema='public') - Tables in public
            get_schema(schema='public', limit=50, offset=50) - Page 2
            get_schema(format='mermaid') - ERD diagram
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            # Check cache first (only for JSON format to avoid stale formatting)
            cache_key = schema.lower() if schema else None
            if format == "json":
                cached = get_cached_schema(cache_key)
                if cached is not None:
                    cached["_cached"] = True
                    return Response.ok(cached, connected=True)

            # If no schema specified or "all", return schema summary
            if schema is None or schema.lower() == "all":
                schemas = await ctx.schema_discovery.get_schemas()
                result = {"schemas": schemas, "total_schemas": len(schemas)}

                # Cache the result
                set_cached_schema(cache_key, result)

                if format == "json":
                    return Response.ok(result, connected=True)

                lines = ["# Database Schemas", ""]
                lines.append(f"Found **{len(schemas)}** user schemas:")
                lines.append("")
                lines.append("| Schema | Tables | Rows | Size |")
                lines.append("|--------|--------|------|------|")
                for s in schemas:
                    lines.append(
                        f"| {s['schema_name']} | {s['table_count']} | {s['total_rows']:,} | {s['total_size'] or 'N/A'} |"
                    )
                lines.append("")
                lines.append("---")
                lines.append('*Use `get_schema(schema="name")` for detailed table info.*')
                return Response.formatted("\n".join(lines), "markdown", connected=True)

            # Specific schema - return full table details
            all_tables = await ctx.schema_discovery.get_full_schema(schema)

            if not all_tables:
                return Response.ok(
                    {
                        "schema": schema,
                        "tables": [],
                        "total_tables": 0,
                        "message": f"No tables found in schema '{schema}'. Use get_schema() to list all schemas.",
                    },
                    connected=True,
                )

            # Apply pagination
            total_tables = len(all_tables)
            tables = all_tables[offset : offset + limit]

            # Cache the full table data (not paginated) for JSON responses
            table_dicts = [t.model_dump() for t in tables]
            all_table_dicts = [t.model_dump() for t in all_tables]
            schema_result = {"schema": schema, "tables": all_table_dicts, "table_count": total_tables}
            set_cached_schema(cache_key, schema_result)

            # Build pagination info
            pagination = {
                "total_tables": total_tables,
                "returned": len(table_dicts),
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total_tables,
            }

            if format == "json":
                result = {
                    "schema": schema,
                    "tables": table_dicts,
                    "pagination": pagination,
                }
                return Response.ok(result, connected=True)
            elif format == "markdown":
                header = f"# Schema: {schema}\n\n"
                if total_tables > limit:
                    header += f"*Showing {len(table_dicts)} of {total_tables} tables (offset={offset})*\n\n"
                return Response.formatted(
                    header + "\n".join(ctx.formatter.schema_table(t) for t in table_dicts),
                    "markdown",
                    connected=True,
                )
            elif format == "mermaid":
                return Response.formatted(str(ctx.formatter.mermaid_erd(table_dicts)), "mermaid", connected=True)
            return Response.formatted(str(ctx.schema_discovery.format_schema_as_text(tables)), "text", connected=True)
        except Exception as e:
            return internal_error(e, context="get_schema")
