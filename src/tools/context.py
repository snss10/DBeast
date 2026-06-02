"""Shared context and state for MCP tools.

This module provides the ToolContext class which maintains shared state
across all MCP tools, including database connections, analyzers, and formatters.

Architecture Note:
    The ToolContext follows a singleton-like pattern where a single instance
    is created during server initialization and shared across all tools.
    This is intentional for MCP servers where:
    1. All tools share the same database connection pool
    2. The lifespan context manages startup/shutdown
    3. Tools are registered before the server starts

    The context is NOT truly global - it's created explicitly in server.py
    and passed to tool registration functions via dependency injection.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from db import DatabasePool, SchemaDiscovery
from query import BatchQueryAnalyzer, ImpactAnalyzer, QueryAnalyzer, QueryExecutor
from utils import MarkdownFormatter

if TYPE_CHECKING:
    pass

# Lazy logger import to avoid circular dependencies
_logger: logging.Logger | None = None


def _get_logger():
    global _logger
    if _logger is None:
        try:
            from core.logging import get_logger

            _logger = get_logger("tools.context")
        except ImportError:
            import logging

            _logger = logging.getLogger("dbeast.tools.context")
    return _logger


# Module-level context holder for controlled singleton access
_context_instance: "ToolContext | None" = None


def get_tool_context() -> "ToolContext":
    """Get the shared ToolContext instance.

    This provides controlled access to the singleton context.
    The context must be created first via create_tool_context().

    Returns:
        The shared ToolContext instance

    Raises:
        RuntimeError: If context hasn't been created yet
    """
    if _context_instance is None:
        raise RuntimeError("ToolContext not initialized. Call create_tool_context() first.")
    return _context_instance


def create_tool_context() -> "ToolContext":
    """Create and register the singleton ToolContext.

    This should be called once during server initialization.
    Subsequent calls return the existing instance.

    Returns:
        The ToolContext instance (newly created or existing)
    """
    global _context_instance
    if _context_instance is None:
        _context_instance = ToolContext()
    return _context_instance


@dataclass
class ToolContext:
    """Shared context for all MCP tools."""

    db_pool: DatabasePool = field(default_factory=DatabasePool)
    schema_discovery: SchemaDiscovery | None = None
    query_executor: QueryExecutor | None = None
    impact_analyzer: ImpactAnalyzer | None = None
    query_analyzer: QueryAnalyzer = field(default_factory=lambda: QueryAnalyzer(dialect="postgres"))
    batch_analyzer: BatchQueryAnalyzer | None = None
    formatter: MarkdownFormatter = field(default_factory=MarkdownFormatter)

    auto_connected: bool = False
    auto_connect_error: str | None = None

    def init_components(self) -> None:
        """Initialize components after connection."""
        self.schema_discovery = SchemaDiscovery(self.db_pool)
        self.query_executor = QueryExecutor(self.db_pool)
        self.impact_analyzer = ImpactAnalyzer(self.db_pool, self.schema_discovery)
        self.batch_analyzer = BatchQueryAnalyzer(self.db_pool, self.schema_discovery, dialect="postgres")

    def has_env_credentials(self) -> bool:
        """Check if environment has database credentials."""
        try:
            from core.config import get_settings

            settings = get_settings()
            return settings.has_database_credentials()
        except Exception:
            # Fallback if settings fail to load
            return bool(
                os.getenv("DATABASE_URL")
                or (os.getenv("DB_HOST") and os.getenv("DB_USER"))
                or os.getenv("AWS_SECRET_NAME")
            )

    async def try_auto_connect(self) -> None:
        """Attempt auto-connection from environment variables with retry logic.

        Supports:
        - DATABASE_URL: Full connection URL
        - DB_HOST + DB_USER + DB_PASSWORD + DB_NAME: Individual params
        - AWS_SECRET_NAME + AWS_REGION: AWS Secrets Manager

        Uses exponential backoff retry for production resilience.
        """
        if not self.has_env_credentials():
            return
        try:
            from core.config import get_settings

            settings = get_settings()
            aws_secret = settings.aws_secret_name
            aws_region = settings.aws_region

            if aws_secret:
                # Allow host/port override for SSH tunnel scenarios
                # Check if DB_HOST is explicitly set in environment (not just default)
                explicit_host = os.getenv("DB_HOST")
                explicit_port = os.getenv("DB_PORT")
                host_override = settings.db_host if explicit_host else None
                port_override = settings.db_port if explicit_port else None
                # Use ssl_verify setting for SSH tunnel scenarios
                ssl_verify = settings.ssl_verify
                result = await self.db_pool.connect_with_retry(
                    aws_secret_name=aws_secret,
                    aws_region=aws_region,
                    host=host_override,
                    port=port_override,
                    ssl_verify=ssl_verify,
                )
            else:
                result = await self.db_pool.connect_with_retry(
                    ssl_verify=settings.ssl_verify,
                )

            self.init_components()
            self.auto_connected = True
            _get_logger().info(
                "Auto-connected to database",
                extra={
                    "host": result.get("host"),
                    "port": result.get("port"),
                    "database": result.get("database"),
                },
            )
        except Exception as e:
            self.auto_connect_error = str(e)
            _get_logger().warning("Auto-connect failed", extra={"error": str(e)})

    async def ensure_connected(self, url: str | None = None) -> str | None:
        """Ensure database connection exists.

        Args:
            url: Optional connection URL to connect with

        Returns:
            None if connected successfully, or an error message string if not.

        This method:
        1. If URL provided, attempts connection with that URL
        2. If already connected, returns None (success)
        3. If not connected and auto-connect hasn't been tried, attempts auto-connect
        4. Returns appropriate error message if connection fails
        """
        # If explicit URL provided, try connecting with it
        if url:
            try:
                await self.db_pool.connect(url=url)
                self.init_components()
                return None
            except Exception as e:
                return f"Connection failed: {str(e)}"

        # Already connected
        if self.db_pool.is_connected:
            return None

        # Try auto-connect if not already attempted (and not done by lifespan)
        if not self.auto_connected and self.auto_connect_error is None:
            await self.try_auto_connect()

        # Check if auto-connect succeeded
        if self.db_pool.is_connected:
            return None

        # Return appropriate error message
        if self.auto_connect_error:
            return (
                f"Not connected. Auto-connect failed: {self.auto_connect_error}. Pass 'url' parameter or use connect()."
            )
        elif self.has_env_credentials():
            return "Not connected. Use connect() or pass 'url' parameter."
        else:
            return "Not connected. Pass 'url' parameter (postgresql://user:pass@host:port/db) or use connect()."
