"""MCP resources for dbeast.

Resources provide read-only, stateless data that LLMs can retrieve
without side effects. They are ideal for:
- Connection status and metadata
- Configuration overview

Resources use URI templates like:
- db://connection/status - Connection state, host, database, pool info
- db://config - Server settings (timeouts, pool, SSL, audit)
"""

from typing import TYPE_CHECKING

from resources.config import register_config_resources
from resources.connection import register_connection_resources

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tools.context import ToolContext

__all__ = [
    "register_connection_resources",
    "register_config_resources",
    "register_all_resources",
]


def register_all_resources(mcp: "FastMCP", ctx: "ToolContext") -> None:
    """Register all MCP resources with the server.

    Args:
        mcp: The FastMCP server instance
        ctx: Shared tool context with database connections
    """
    register_connection_resources(mcp, ctx)
    register_config_resources(mcp, ctx)
