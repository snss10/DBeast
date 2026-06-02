"""Security audit MCP tools.

This module provides tools for security auditing:
- security_audit: Roles, privileges, RLS, SSL, sensitive data
- sensitive_data_scan: Find PII/PHI columns
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import SecurityQueries
from services import SecurityAuditService
from tools.context import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
SecurityIncludeType = Literal["all", "roles", "privileges", "rls", "ssl", "sensitive", "functions"]
FormatType = Literal["json", "markdown"]


def register_security_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register security audit MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def sensitive_data_scan(
        schema: str | None = Field(
            default=None, description="Schema name to scan. Omit or pass null to scan ALL schemas."
        ),
        format: FormatType = Field(default="json", description="Output format"),
        url: str | None = Field(default=None, description="Database URL"),
    ) -> str:
        """Find PII/PHI columns - passwords, credit cards, SSN, emails.

        LEVEL: Database (scans all schemas by default) or Schema (if specified)

        USE FOR: finding sensitive data, GDPR compliance, security review.
        DO NOT USE FOR: permissions (security_audit), data quality (data_quality_report).

        Examples:
            sensitive_data_scan() - Scan all schemas
            sensitive_data_scan(schema='public') - Public schema only
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            if schema:
                query = SecurityQueries.sensitive_columns_in_schema(schema)
            else:
                query = SecurityQueries.SENSITIVE_COLUMNS

            rows = await ctx.db_pool.fetch(query)

            if format == "json":
                return Response.ok({"sensitive_columns": rows, "count": len(rows)}, connected=True)

            if not rows:
                return Response.formatted("No sensitive columns detected.", "text", connected=True)

            lines = ["# Sensitive Data Scan", ""]
            lines.append("| Schema | Table | Column | Type | Category |")
            lines.append("|--------|-------|--------|------|----------|")

            for r in rows:
                schema_name = r.get("table_schema", schema or "N/A")
                category = r.get("category", r.get("sensitivity_type", "unknown"))
                lines.append(
                    f"| {schema_name} | {r['table_name']} | {r['column_name']} | {r['data_type']} | {category} |"
                )

            lines.append("")
            lines.append("**Recommendations:**")
            lines.append("- Ensure columns containing credentials are hashed (never plain text)")
            lines.append("- Consider encryption at rest for PII/PHI data")
            lines.append("- Implement RLS policies for multi-tenant access control")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="sensitive_data_scan")

    @mcp.tool()
    @audited()
    async def security_audit(
        schema: str | None = Field(
            default=None,
            description="Schema to audit. Omit for all schemas, or specify one. Use get_schema() to list available.",
        ),
        include: SecurityIncludeType = Field(default="all", description="What to audit"),
        format: FormatType = Field(default="json", description="Output format"),
        url: str | None = Field(default=None, description="Database URL"),
    ) -> str:
        """Audit roles, privileges, RLS, SSL, and security definer functions.

        LEVEL: Schema or Database (schema='all')
        REQUIRED: Specify schema explicitly - use 'all' for all schemas or a specific schema name.

        USE FOR: security audit, role permissions, RLS policies, SSL status.
        DO NOT USE FOR: PII detection (sensitive_data_scan), data quality.

        INCLUDE: all, roles, privileges, rls, ssl, sensitive, functions

        Examples:
            security_audit(schema='sales') - Audit sales schema
            security_audit(schema='all') - All schemas
            security_audit(schema='billing', include='roles') - Roles only in billing
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
                        "message": "Please specify a schema to audit. Use 'all' for full security audit or choose a specific schema.",
                        "available_schemas": schema_list,
                        "example": "security_audit(schema='public') or security_audit(schema='all')",
                    },
                    connected=True,
                )

            # Use the service layer for business logic
            service = SecurityAuditService(ctx.db_pool, ctx.schema_discovery)
            result = await service.full_audit(schema, include)

            if format == "json":
                return Response.ok(result, connected=True)

            return Response.formatted(service.format_audit_markdown(result, schema), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="security_audit")
