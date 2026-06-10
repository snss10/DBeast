"""Dbeast - Expert PostgreSQL Database Analysis MCP Server.

This is the main MCP server entry point following official FastMCP patterns.
All tool implementations are organized in the tools/ package for maintainability.

Usage:
    python -m server          # Direct execution
    dbeast                    # Console script (from pyproject.toml)
    mcp dev src/server.py     # Development mode with inspector
"""


def _use_project_venv() -> None:
    """Re-exec with the uv-created virtualenv when launched by plain python."""
    import os
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    if not venv_python.exists():
        return

    current_python = Path(sys.executable).resolve()
    target_python = venv_python.resolve()
    if current_python == target_python:
        return

    os.execv(str(target_python), [str(target_python), *sys.argv])


_use_project_venv()

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment before other imports
load_dotenv()

# Initialize logging early
from core.logging import setup_logging

setup_logging()

from lifespan import create_lifespan
from resources import register_all_resources
from tools import create_tool_context, register_all_tools

# Initialize shared context for all tools using factory function
# This follows the controlled singleton pattern for MCP servers
ctx = create_tool_context()


# Initialize MCP server with official FastMCP configuration
mcp = FastMCP(
    name="dbeast",
    instructions="""Dbeast is an expert PostgreSQL database analysis MCP server.

CAPABILITIES:
- Schema discovery and exploration
- Query execution (read-only) and analysis
- Write operation impact preview (DELETE/UPDATE/DROP)
- Database health monitoring and diagnostics
- Performance analysis and optimization recommendations
- Security auditing and sensitive data detection
- Replication and configuration review

GETTING STARTED:
1. Call connect() to check connection status or auto-connect
2. Call get_schema() to explore database structure
3. Use specific analysis tools based on your needs

TOOL CATEGORIES:
- Connection: connect, disconnect, health_check
- Schema: get_schema
- Query: analyze_query, execute_query, analyze_impact, query_optimizer
- Health: database_health
- Maintenance: maintenance_analysis
- Performance: query_performance
- Infrastructure: replication_status, configuration_review
- Security: security_audit, sensitive_data_scan
- Data Quality: data_quality_report, duplicate_detection
- Dependencies: dependency_analysis
- Partitions: partition_analysis
- Audit: get_audit_logs, list_audit_files

RESOURCES (read-only status):
- db://connection/status - Connection state, host, pool stats
- db://config - Server configuration settings""",
    lifespan=create_lifespan(ctx),
)

# Register all MCP tools and resources with the server
register_all_tools(mcp, ctx)
register_all_resources(mcp, ctx)


def main() -> None:
    """Entry point used by the `dbeast` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
