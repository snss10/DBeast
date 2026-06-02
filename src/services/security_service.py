"""Security audit business logic service.

Extracts security audit logic from tool definitions for better testability
and separation of concerns.
"""

import asyncio
from typing import TYPE_CHECKING, Any

from query import SecurityQueries

if TYPE_CHECKING:
    from db import DatabasePool, SchemaDiscovery


class SecurityAuditService:
    """Service for performing security audits on PostgreSQL databases."""

    def __init__(self, db_pool: "DatabasePool", schema_discovery: "SchemaDiscovery"):
        """Initialize the security audit service.

        Args:
            db_pool: Database connection pool
            schema_discovery: Schema discovery utility
        """
        self.db_pool = db_pool
        self.schema_discovery = schema_discovery

    async def audit_schema_security(self, schema_name: str, include: str) -> dict[str, Any]:
        """Audit security for a single schema.

        Args:
            schema_name: Name of the schema to audit
            include: What to include ('all', 'privileges', 'rls', 'sensitive')

        Returns:
            Dictionary containing audit results and issues
        """
        include_all = include == "all"
        result: dict[str, Any] = {"schema": schema_name}
        issues: list[str] = []

        if include_all or include == "privileges":
            result["table_privileges"] = await self.db_pool.fetch(SecurityQueries.table_privileges_summary(schema_name))

        if include_all or include == "rls":
            result["rls_coverage"] = await self.db_pool.fetch(SecurityQueries.rls_coverage(schema_name))
            rls_coverage = result["rls_coverage"]
            rls_enabled = len([r for r in rls_coverage if r.get("rls_enabled")])
            if rls_enabled == 0 and len(rls_coverage) > 0:
                issues.append(f"[{schema_name}] No tables have RLS enabled")

        if include_all or include == "sensitive":
            result["sensitive_columns"] = await self.db_pool.fetch(
                SecurityQueries.sensitive_columns_in_schema(schema_name)
            )
            if result["sensitive_columns"]:
                issues.append(f"[{schema_name}] {len(result['sensitive_columns'])} sensitive columns found")

        result["issues"] = issues
        return result

    async def get_global_security_info(self, include: str) -> tuple[dict[str, Any], list[str]]:
        """Get database-wide security information.

        Args:
            include: What to include ('all', 'roles', 'ssl', 'rls', 'privileges', 'functions')

        Returns:
            Tuple of (results dict, issues list)
        """
        include_all = include == "all"
        result: dict[str, Any] = {}
        issues: list[str] = []

        if include_all or include == "roles":
            # Parallel fetch for role queries
            superusers, login_roles, memberships, unused = await asyncio.gather(
                self.db_pool.fetch(SecurityQueries.SUPERUSERS),
                self.db_pool.fetch(SecurityQueries.LOGIN_ROLES),
                self.db_pool.fetch(SecurityQueries.ROLE_MEMBERSHIPS),
                self.db_pool.fetch(SecurityQueries.UNUSED_ROLES),
            )
            result["superusers"] = superusers
            result["login_roles"] = login_roles
            result["role_memberships"] = memberships
            result["unused_roles"] = unused

            if len(result["superusers"]) > 2:
                issues.append("[global] Consider reducing number of superusers")
            expired = [r for r in unused if r.get("status") == "expired"]
            if expired:
                issues.append(f"[global] {len(expired)} expired role(s) found")

        if include_all or include == "ssl":
            # Parallel fetch for SSL queries
            ssl_config, conn_security, audit = await asyncio.gather(
                self.db_pool.fetch(SecurityQueries.SSL_CONFIG),
                self.db_pool.fetch(SecurityQueries.CONNECTION_SECURITY),
                self.db_pool.fetch(SecurityQueries.AUDIT_SETTINGS),
            )
            result["ssl_config"] = ssl_config
            result["connection_security"] = conn_security
            result["audit_settings"] = audit
            ssl_enabled = any(s["name"] == "ssl" and s["setting"] == "on" for s in ssl_config)
            if not ssl_enabled:
                issues.append("[global] SSL not enabled - enable for encrypted connections")

        if include_all or include == "rls":
            result["rls_policies"] = await self.db_pool.fetch(SecurityQueries.RLS_POLICIES)

        if include_all or include == "privileges":
            # Parallel fetch for privilege queries
            schema_privs, default_privs = await asyncio.gather(
                self.db_pool.fetch(SecurityQueries.SCHEMA_PRIVILEGES),
                self.db_pool.fetch(SecurityQueries.DEFAULT_PRIVILEGES),
            )
            result["schema_privileges"] = schema_privs
            result["default_privileges"] = default_privs

        if include_all or include == "functions":
            result["security_definer_functions"] = await self.db_pool.fetch(
                SecurityQueries.FUNCTIONS_WITH_SECURITY_DEFINER
            )
            result["public_schema_objects"] = await self.db_pool.fetch(SecurityQueries.public_schema_objects("public"))
            if result["security_definer_functions"]:
                issues.append(f"[global] Audit {len(result['security_definer_functions'])} SECURITY DEFINER functions")

        return result, issues

    async def full_audit(self, schema: str, include: str) -> dict[str, Any]:
        """Perform a full security audit.

        Args:
            schema: Schema name or 'all' for all schemas
            include: What to include in the audit

        Returns:
            Complete audit results
        """
        if schema.lower() == "all":
            return await self._audit_all_schemas(include)
        return await self._audit_single_schema(schema, include)

    async def _audit_all_schemas(self, include: str) -> dict[str, Any]:
        """Audit all schemas in the database."""
        schemas = await self.schema_discovery.get_schemas()
        schema_names = [s["schema_name"] for s in schemas if s["table_count"] > 0]

        if not schema_names:
            return {"message": "No schemas with tables found"}

        result: dict[str, Any] = {
            "schemas_analyzed": schema_names,
            "by_schema": {},
        }

        # Get global security info
        global_result, global_issues = await self.get_global_security_info(include)
        result.update(global_result)

        all_issues = list(global_issues)

        # Per-schema security info
        for schema_name in schema_names:
            schema_result = await self.audit_schema_security(schema_name, include)
            result["by_schema"][schema_name] = schema_result
            all_issues.extend(schema_result.get("issues", []))

        result["issues"] = all_issues
        result["issue_count"] = len(all_issues)

        return result

    async def _audit_single_schema(self, schema: str, include: str) -> dict[str, Any]:
        """Audit a single schema."""
        include_all = include == "all"
        result: dict[str, Any] = {}

        if include_all or include == "roles":
            result["superusers"] = await self.db_pool.fetch(SecurityQueries.SUPERUSERS)
            result["login_roles"] = await self.db_pool.fetch(SecurityQueries.LOGIN_ROLES)
            result["role_memberships"] = await self.db_pool.fetch(SecurityQueries.ROLE_MEMBERSHIPS)
            result["unused_roles"] = await self.db_pool.fetch(SecurityQueries.UNUSED_ROLES)

        if include_all or include == "privileges":
            result["table_privileges"] = await self.db_pool.fetch(SecurityQueries.table_privileges_summary(schema))
            result["schema_privileges"] = await self.db_pool.fetch(SecurityQueries.SCHEMA_PRIVILEGES)
            result["default_privileges"] = await self.db_pool.fetch(SecurityQueries.DEFAULT_PRIVILEGES)

        if include_all or include == "rls":
            result["rls_policies"] = await self.db_pool.fetch(SecurityQueries.RLS_POLICIES)
            result["rls_coverage"] = await self.db_pool.fetch(SecurityQueries.rls_coverage(schema))

        if include_all or include == "ssl":
            result["ssl_config"] = await self.db_pool.fetch(SecurityQueries.SSL_CONFIG)
            result["connection_security"] = await self.db_pool.fetch(SecurityQueries.CONNECTION_SECURITY)
            result["audit_settings"] = await self.db_pool.fetch(SecurityQueries.AUDIT_SETTINGS)

        if include_all or include == "sensitive":
            result["sensitive_columns"] = await self.db_pool.fetch(SecurityQueries.sensitive_columns_in_schema(schema))

        if include_all or include == "functions":
            result["security_definer_functions"] = await self.db_pool.fetch(
                SecurityQueries.FUNCTIONS_WITH_SECURITY_DEFINER
            )
            result["public_schema_objects"] = await self.db_pool.fetch(SecurityQueries.public_schema_objects("public"))

        return result

    def format_audit_markdown(self, result: dict[str, Any], schema: str) -> str:
        """Format audit results as markdown.

        Args:
            result: Audit results dictionary
            schema: Schema that was audited ('all' or specific schema)

        Returns:
            Formatted markdown string
        """
        if schema.lower() == "all":
            return self._format_all_schemas_markdown(result)
        return self._format_single_schema_markdown(result)

    def _format_all_schemas_markdown(self, result: dict[str, Any]) -> str:
        """Format all-schemas audit as markdown."""
        issues = result.get("issues", [])
        schema_names = result.get("schemas_analyzed", [])

        lines = ["# Security Audit Report (All Schemas)", ""]
        lines.append(f"**Schemas analyzed:** {', '.join(schema_names)}")
        lines.append(f"**Total issues:** {len(issues)}")
        lines.append("")

        if issues:
            lines.append("## Security Issues")
            for issue in issues:
                lines.append(f"- {issue}")
            lines.append("")
        else:
            lines.append("No critical issues identified.")

        return "\n".join(lines)

    def _format_single_schema_markdown(self, result: dict[str, Any]) -> str:
        """Format single-schema audit as markdown."""
        lines = ["# Security Audit Report", ""]
        issues: list[str] = []

        if "superusers" in result:
            lines.append("## Roles & Access")
            lines.append(f"- Superusers: {len(result['superusers'])}")
            lines.append(f"- Login roles: {len(result.get('login_roles', []))}")
            expired = [r for r in result.get("unused_roles", []) if r.get("status") == "expired"]
            if expired:
                lines.append(f"- **Expired roles: {len(expired)}**")
                issues.append(f"- {len(expired)} expired role(s) found")
            if len(result["superusers"]) > 2:
                issues.append("- Consider reducing number of superusers")
            lines.append("")

        if "rls_coverage" in result:
            rls_coverage = result["rls_coverage"]
            rls_enabled = len([r for r in rls_coverage if r.get("rls_enabled")])
            lines.append("## Row-Level Security")
            lines.append(f"- Tables with RLS: {rls_enabled}/{len(rls_coverage)}")
            lines.append(f"- Active policies: {len(result.get('rls_policies', []))}")
            if rls_enabled == 0 and len(rls_coverage) > 0:
                issues.append("- Consider implementing RLS for multi-tenant security")
            lines.append("")

        if "ssl_config" in result:
            ssl_enabled = any(s["name"] == "ssl" and s["setting"] == "on" for s in result["ssl_config"])
            lines.append("## Connection Security")
            lines.append(f"- SSL enabled: {'Yes' if ssl_enabled else 'No'}")
            if not ssl_enabled:
                issues.append("- Enable SSL for encrypted connections")
            lines.append("")

        if "sensitive_columns" in result:
            sensitive = result["sensitive_columns"]
            lines.append("## Sensitive Data")
            lines.append(f"- Sensitive columns found: {len(sensitive)}")
            if sensitive:
                by_category: dict[str, int] = {}
                for s in sensitive:
                    cat = s.get("category", s.get("sensitivity_type", "other"))
                    by_category[cat] = by_category.get(cat, 0) + 1
                for cat, count in sorted(by_category.items()):
                    lines.append(f"  - {cat}: {count}")
                issues.append(f"- Review {len(sensitive)} sensitive columns for proper handling")
            lines.append("")

        if "security_definer_functions" in result:
            sec_definer = result["security_definer_functions"]
            lines.append("## Functions & Objects")
            lines.append(f"- SECURITY DEFINER functions: {len(sec_definer)}")
            lines.append(f"- Objects in public schema: {len(result.get('public_schema_objects', []))}")
            if sec_definer:
                issues.append(f"- Audit {len(sec_definer)} SECURITY DEFINER functions")
            lines.append("")

        lines.append("## Recommendations")
        if issues:
            for issue in issues:
                lines.append(issue)
        else:
            lines.append("No critical issues identified.")

        return "\n".join(lines)
