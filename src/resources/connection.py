"""Connection status MCP resources.

Provides read-only access to database connection information.
"""

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tools.context import ToolContext


def register_connection_resources(mcp: "FastMCP", ctx: "ToolContext") -> None:
    """Register connection-related MCP resources.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.resource("db://connection/status")
    async def connection_status() -> str:
        """Current database connection status.

        Returns connection state, host, database, and basic pool info.
        Use this resource to check if connected before calling tools.
        For detailed pool stats, use health_check() tool.
        """
        if not ctx.db_pool.is_connected:
            return json.dumps(
                {
                    "connected": False,
                    "auto_connected": ctx.auto_connected,
                    "auto_connect_error": ctx.auto_connect_error,
                    "message": "Not connected. Use connect() tool to establish connection.",
                },
                indent=2,
            )

        config = ctx.db_pool.config
        pool = ctx.db_pool.get_pool()

        return json.dumps(
            {
                "connected": True,
                "host": config.host if config else None,
                "port": config.port if config else None,
                "database": config.database if config else None,
                "user": config.user if config else None,
                "pg_version": ctx.db_pool.pg_version,
                "extensions": list(ctx.db_pool.extensions.keys()),
                "pool_size": pool.get_size() if pool else 0,
                "pool_available": pool.get_idle_size() if pool else 0,
                "auto_connected": ctx.auto_connected,
            },
            indent=2,
        )
