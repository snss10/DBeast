"""Configuration MCP resources.

Provides read-only access to server configuration settings.
"""

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tools.context import ToolContext


def register_config_resources(mcp: "FastMCP", ctx: "ToolContext") -> None:
    """Register configuration-related MCP resources.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context (unused but kept for consistency)
    """

    @mcp.resource("db://config")
    def server_config() -> str:
        """Dbeast server configuration.

        Shows current configuration settings (without sensitive values).
        Useful for understanding server behavior, timeouts, and pool limits.
        """
        return json.dumps(
            {
                "pool": {
                    "min_size": int(os.getenv("DBEAST_POOL_MIN_SIZE", "1")),
                    "max_size": int(os.getenv("DBEAST_POOL_MAX_SIZE", "5")),
                    "command_timeout_sec": int(os.getenv("DBEAST_COMMAND_TIMEOUT", "300")),
                    "connection_timeout_sec": int(float(os.getenv("DBEAST_POOL_CONNECTION_TIMEOUT", "300"))),
                },
                "query": {
                    "default_timeout_sec": int(float(os.getenv("DBEAST_QUERY_TIMEOUT", "300"))),
                    "default_row_limit": int(os.getenv("DBEAST_DEFAULT_ROW_LIMIT", "100")),
                },
                "retry": {
                    "max_retries": int(os.getenv("DBEAST_CONNECTION_MAX_RETRIES", "5")),
                    "retry_delay_base": float(os.getenv("DBEAST_CONNECTION_RETRY_DELAY", "1.0")),
                },
                "ssl": {
                    "verify": os.getenv("DBEAST_SSL_VERIFY", "true").lower() in ("true", "1", "yes"),
                },
                "cache": {
                    "schema_cache_ttl_sec": int(os.getenv("DBEAST_SCHEMA_CACHE_TTL", "60")),
                },
                "audit": {
                    "enabled": os.getenv("DBEAST_AUDIT_ENABLED", "true").lower() in ("true", "1", "yes"),
                    "log_dir": os.getenv("DBEAST_AUDIT_DIR", "logs/mcp_audit"),
                    "max_response_size": int(os.getenv("DBEAST_AUDIT_MAX_RESPONSE_SIZE", "10000")),
                },
                "credentials_configured": {
                    "database_url": bool(os.getenv("DATABASE_URL")),
                    "db_host": bool(os.getenv("DB_HOST")),
                    "aws_secret": bool(os.getenv("AWS_SECRET_NAME")),
                },
            },
            indent=2,
        )
