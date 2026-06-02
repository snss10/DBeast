"""MCP server lifecycle management.

Handles startup and shutdown of the dbeast MCP server, including:
- Auto-connecting to database if credentials are available (non-blocking)
- Graceful cleanup of database connections on shutdown

Usage:
    from lifespan import create_lifespan

    mcp = FastMCP(name="dbeast", lifespan=create_lifespan(ctx))
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tools.context import ToolContext

# Lazy logger import
_logger: logging.Logger | None = None

# Track background auto-connect task
_auto_connect_task: asyncio.Task | None = None


def _get_logger():
    """Get logger lazily to avoid circular imports."""
    global _logger
    if _logger is None:
        try:
            from core.logging import get_logger

            _logger = get_logger("lifespan")
        except ImportError:
            import logging

            _logger = logging.getLogger("dbeast.lifespan")
    return _logger


def create_lifespan(ctx: "ToolContext"):
    """Create a lifespan context manager for the MCP server.

    Args:
        ctx: The shared ToolContext instance

    Returns:
        An async context manager for server lifecycle
    """

    async def _background_auto_connect():
        """Run auto-connect in background so server starts immediately."""
        log = _get_logger()
        try:
            await ctx.try_auto_connect()
            if ctx.db_pool.is_connected:
                log.info(
                    "Auto-connected to database",
                    extra={
                        "host": ctx.db_pool.config.host if ctx.db_pool.config else None,
                        "database": ctx.db_pool.config.database if ctx.db_pool.config else None,
                    },
                )
            else:
                log.info(
                    "Auto-connect did not establish connection - use connect() tool",
                    extra={"error": ctx.auto_connect_error},
                )
        except Exception as e:
            log.warning("Auto-connect failed in background", extra={"error": str(e)})

    @asynccontextmanager
    async def lifespan(server: "FastMCP") -> AsyncIterator[None]:
        """Manage MCP server lifecycle - startup and shutdown.

        This follows the official FastMCP lifespan pattern for:
        - Auto-connecting to database on startup (non-blocking background task)
        - Graceful cleanup of database connections on shutdown
        """
        global _auto_connect_task
        log = _get_logger()
        log.info("Starting dbeast MCP server", extra={"server_name": server.name})

        # Startup: start auto-connect as background task (non-blocking)
        # This allows the server to start immediately and respond to MCP client
        if ctx.has_env_credentials():
            log.info("Starting background auto-connect...")
            _auto_connect_task = asyncio.create_task(_background_auto_connect())
        else:
            log.info("No database credentials configured - use connect() tool")

        yield  # Server runs here - starts immediately without waiting for DB

        # Shutdown: cancel background task if still running, cleanup connections
        log.info("Shutting down dbeast MCP server")

        if _auto_connect_task and not _auto_connect_task.done():
            log.info("Cancelling background auto-connect task...")
            _auto_connect_task.cancel()
            try:
                await _auto_connect_task
            except asyncio.CancelledError:
                pass

        if ctx.db_pool and ctx.db_pool.is_connected:
            log.info("Closing database connections...")
            await ctx.db_pool.disconnect()

        log.info("Shutdown complete")

    return lifespan
