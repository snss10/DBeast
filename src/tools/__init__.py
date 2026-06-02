"""MCP tool implementations for dbeast.

This module provides the tool registration system for the dbeast MCP server.
Tools are organized by domain (connection, schema, query, health, etc.) and
registered with the FastMCP server instance.

Tool Categories:
    - connection: Database connection management (connect, disconnect, health_check)
    - schema: Schema discovery and exploration (get_schema)
    - query: Query execution and analysis (analyze_query, execute_query, analyze_impact, query_optimizer)
    - health: Database health monitoring (database_health)
    - maintenance: Index and vacuum analysis (maintenance_analysis)
    - performance: Query performance analysis (query_performance)
    - replication: Replication status monitoring (replication_status)
    - config: PostgreSQL configuration review (configuration_review)
    - data_quality: Data quality analysis (data_quality_report, duplicate_detection)
    - security: Security auditing (security_audit, sensitive_data_scan)
    - dependencies: Object dependency analysis (dependency_analysis)
    - partitions: Partition analysis (partition_analysis)
    - audit: Audit log management (get_audit_logs, list_audit_files)
"""

from typing import TYPE_CHECKING

from tools.audit import register_audit_tools
from tools.config import register_config_tools
from tools.connection import register_connection_tools
from tools.context import ToolContext, create_tool_context, get_tool_context
from tools.data_quality import register_data_quality_tools
from tools.dependencies import register_dependency_tools
from tools.health import register_health_tools
from tools.maintenance import register_maintenance_tools
from tools.partitions import register_partition_tools
from tools.performance import register_performance_tools
from tools.query import register_query_tools
from tools.replication import register_replication_tools
from tools.schema import register_schema_tools
from tools.security import register_security_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = [
    "ToolContext",
    "create_tool_context",
    "get_tool_context",
    "register_connection_tools",
    "register_schema_tools",
    "register_query_tools",
    "register_health_tools",
    "register_maintenance_tools",
    "register_performance_tools",
    "register_replication_tools",
    "register_config_tools",
    "register_data_quality_tools",
    "register_security_tools",
    "register_dependency_tools",
    "register_partition_tools",
    "register_audit_tools",
    "register_all_tools",
]


def register_all_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register all MCP tools with the server.

    Args:
        mcp: The FastMCP server instance
        ctx: Shared tool context with database connections and utilities

    This function registers all tool categories in a specific order:
    1. Connection tools (must be first for connect/disconnect)
    2. Schema tools (for database exploration)
    3. Query tools (for query execution and analysis)
    4. Monitoring tools (health, maintenance, performance)
    5. Specialized tools (replication, security, data quality)
    """
    # Core tools
    register_connection_tools(mcp, ctx)
    register_schema_tools(mcp, ctx)
    register_query_tools(mcp, ctx)

    # Monitoring tools
    register_health_tools(mcp, ctx)
    register_maintenance_tools(mcp, ctx)
    register_performance_tools(mcp, ctx)

    # Infrastructure tools
    register_replication_tools(mcp, ctx)
    register_config_tools(mcp, ctx)

    # Analysis tools
    register_data_quality_tools(mcp, ctx)
    register_security_tools(mcp, ctx)
    register_dependency_tools(mcp, ctx)
    register_partition_tools(mcp, ctx)

    # Audit tools
    register_audit_tools(mcp)
