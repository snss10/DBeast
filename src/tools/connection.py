"""Connection management MCP tools.

This module provides tools for managing PostgreSQL database connections:
- connect: Connect to database, check status, or discover databases
- disconnect: Disconnect from current database
- health_check: Check database connection health
"""

import os
import re
import socket
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from core.config import get_settings
from middleware.audit import audited
from models import Response
from tools.context import ToolContext
from utils import AWSDefaults

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
FormatType = Literal["json", "markdown"]


def _check_port(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a port is accepting connections."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _find_docker_postgres() -> list[dict]:
    """Find PostgreSQL containers running in Docker.

    Security note: Uses subprocess with explicit command list (no shell=True)
    and validates docker executable exists before calling.

    Can be disabled via DBEAST_ENABLE_DOCKER_DISCOVERY=false setting.
    """
    import shutil

    containers: list[dict] = []

    # Check if Docker discovery is disabled via settings
    try:
        settings = get_settings()
        if not settings.enable_docker_discovery:
            return containers
    except Exception:
        pass  # Continue if settings fail to load

    # Security: verify docker command exists before invoking
    docker_path = shutil.which("docker")
    if docker_path is None:
        return containers

    try:
        # Security: explicit command list prevents shell injection
        # Timeout prevents hanging on unresponsive docker daemon
        result = subprocess.run(
            [docker_path, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,  # Don't raise on non-zero exit
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    name, image = parts[0], parts[1]
                    ports = parts[2] if len(parts) > 2 else ""
                    if "postgres" in image.lower() or "pg" in image.lower():
                        port_match = re.search(r"0\.0\.0\.0:(\d+)->5432", ports)
                        exposed_port = int(port_match.group(1)) if port_match else None
                        containers.append(
                            {
                                "source": "docker",
                                "container": name,
                                "image": image,
                                "port": exposed_port,
                                "accessible": _check_port("localhost", exposed_port) if exposed_port else False,
                            }
                        )
    except subprocess.TimeoutExpired:
        # Docker daemon may be slow or unresponsive
        pass
    except (FileNotFoundError, PermissionError, OSError):
        # Docker not available or permission denied
        pass
    return containers


def _scan_env_files(workspace: Path = None) -> list[dict]:
    """Scan for .env files with database URLs."""
    found = []
    search_paths = []

    if workspace:
        search_paths.append(workspace)
    search_paths.append(Path.cwd())
    search_paths.append(Path.home())

    for base in search_paths:
        for env_file in [".env", ".env.local", ".env.development"]:
            env_path = base / env_file
            if env_path.exists():
                try:
                    content = env_path.read_text()
                    for line in content.split("\n"):
                        if "DATABASE_URL" in line or "DB_HOST" in line:
                            if "localhost" in line.lower() or "127.0.0.1" in line:
                                match = re.search(r"postgresql://[^@]+@([^:/]+):?(\d+)?/(\w+)", line)
                                if match:
                                    host = match.group(1)
                                    port = int(match.group(2)) if match.group(2) else 5432
                                    db = match.group(3)
                                    found.append(
                                        {
                                            "source": "env_file",
                                            "file": str(env_path),
                                            "host": host,
                                            "port": port,
                                            "database": db,
                                            "accessible": _check_port(host, port),
                                        }
                                    )
                except (OSError, UnicodeDecodeError):
                    # Skip files that can't be read
                    pass
    return found


def register_connection_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register connection-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def connect(
        url: str | None = Field(default=None, description="PostgreSQL URL"),
        host: str | None = Field(default=None, description="Database host"),
        port: int | None = Field(default=None, ge=1, le=65535, description="Port (1-65535)"),
        user: str | None = Field(default=None, description="Username"),
        password: str | None = Field(default=None, description="Password"),
        database: str | None = Field(default=None, description="Database name"),
        use_ssl: bool | None = Field(default=None, description="Use SSL"),
        ssl_verify: bool | None = Field(
            default=None, description="Verify SSL certificates (set False for SSH tunnels)"
        ),
        aws_secret_name: str | None = Field(default=None, description="AWS Secrets Manager secret"),
        aws_region: str = Field(default=AWSDefaults.DEFAULT_REGION, description="AWS region"),
        discover: bool = Field(default=False, description="Auto-discover PostgreSQL instances"),
        format: FormatType = Field(default="json", description="Output format"),
    ) -> str:
        """Connect to PostgreSQL or check connection status.

        LEVEL: Server (connection management)

        USE FOR: connecting, checking status, discovering databases.
        DO NOT USE FOR: health metrics (database_health), queries (execute_query).

        ERROR RECOVERY:
        - "connection refused": Check host/port, ensure PostgreSQL is running
        - "authentication failed": Verify user/password credentials
        - "database does not exist": List available databases with discover=True
        - "SSL required": Add use_ssl=True or check server SSL config
        - "certificate verify failed": Set ssl_verify=False for SSH tunnels

        Examples:
            connect() - Check status
            connect(discover=True) - Find databases
            connect(url='postgresql://user:pass@localhost:5432/mydb')
        """
        has_connection_params = any([url, host, user, password, database, aws_secret_name])

        if discover:
            result = {"discovered": [], "recommendations": [], "quick_connect": None}

            common_ports = [5432, 5433, 5434, 5435, 15432, 25432, 54320]
            for p in common_ports:
                if _check_port("localhost", p):
                    result["discovered"].append(
                        {
                            "source": "localhost",
                            "host": "localhost",
                            "port": p,
                            "accessible": True,
                        }
                    )

            docker_containers = _find_docker_postgres()
            result["discovered"].extend(docker_containers)

            env_dbs = _scan_env_files()
            result["discovered"].extend(env_dbs)

            accessible = [d for d in result["discovered"] if d.get("accessible")]

            if accessible:
                best = accessible[0]
                h = best.get("host", "localhost")
                p = best.get("port", 5432)
                result["quick_connect"] = (
                    f"connect(host='{h}', port={p}, user='YOUR_USER', password='YOUR_PASS', database='YOUR_DB')"
                )
                result["recommendations"].append(f"Found {len(accessible)} accessible instance(s). Try {h}:{p}")
            else:
                result["recommendations"].append("No accessible PostgreSQL found on localhost.")

            result["summary"] = {"total_found": len(result["discovered"]), "accessible": len(accessible)}
            return Response.ok(result, connected=ctx.db_pool.is_connected)

        if not has_connection_params:
            # Gather all detected env vars
            env_vars = {
                "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
                "DB_HOST": os.getenv("DB_HOST"),
                "DB_PORT": os.getenv("DB_PORT"),
                "DB_USER": bool(os.getenv("DB_USER")),
                "DB_PASSWORD": bool(os.getenv("DB_PASSWORD")),
                "DB_NAME": os.getenv("DB_NAME"),
                "AWS_SECRET_NAME": os.getenv("AWS_SECRET_NAME"),
                "AWS_REGION": os.getenv("AWS_REGION"),
            }

            # Determine connection method available
            can_connect_via = []
            if env_vars["DATABASE_URL"]:
                can_connect_via.append("DATABASE_URL")
            if env_vars["AWS_SECRET_NAME"]:
                can_connect_via.append(f"AWS_SECRET_NAME ({env_vars['AWS_SECRET_NAME']})")
            if env_vars["DB_HOST"] and env_vars["DB_USER"]:
                can_connect_via.append(f"DB_HOST ({env_vars['DB_HOST']}:{env_vars['DB_PORT'] or '5432'})")

            result = {
                "connected": ctx.db_pool.is_connected,
                "auto_connect_attempted": ctx.auto_connected or ctx.auto_connect_error is not None,
                "auto_connect_error": ctx.auto_connect_error,
                "env_detected": {
                    k: (v if isinstance(v, str) else ("set" if v else "not set")) for k, v in env_vars.items()
                },
                "can_connect_via": can_connect_via,
            }

            if ctx.db_pool.is_connected and ctx.db_pool.config:
                result["connection"] = {
                    "host": ctx.db_pool.config.host,
                    "port": ctx.db_pool.config.port,
                    "database": ctx.db_pool.config.database,
                    "user": ctx.db_pool.config.user,
                }
                result["extensions"] = list(ctx.db_pool.extensions.keys())
                result["pg_version"] = ctx.db_pool.pg_version
            elif can_connect_via:
                result["action"] = (
                    "Credentials detected. Call any tool requiring connection (e.g. get_schema()) to auto-connect."
                )
            else:
                result["action"] = (
                    "No credentials found. Use connect(url='...') or connect(discover=True) to find databases."
                )

            return Response.ok(result, connected=ctx.db_pool.is_connected)

        try:
            result = await ctx.db_pool.connect(
                url=url,
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                use_ssl=use_ssl,
                ssl_verify=ssl_verify,
                aws_secret_name=aws_secret_name,
                aws_region=aws_region,
            )
            ctx.init_components()
            if format == "markdown":
                return Response.formatted(ctx.formatter.connection_status(result), "markdown", connected=True)
            return Response.ok(result, connected=True)
        except Exception as e:
            if format == "markdown":
                return Response.formatted(
                    ctx.formatter.connection_status({"status": "error", "error": str(e)}),
                    "markdown",
                    connected=False,
                )
            return Response.internal(e, context="connect")

    @mcp.tool()
    @audited()
    async def disconnect() -> str:
        """Close the database connection and release pool resources.

        LEVEL: Server (connection management)

        USE FOR: ending session, cleanup, releasing connections.
        DO NOT USE FOR: checking status (use connect() or health_check).
        """
        result = await ctx.db_pool.disconnect()
        return Response.ok(result, connected=False)

    @mcp.tool()
    @audited()
    async def health_check(
        format: FormatType = Field(default="json", description="Output format"),
    ) -> str:
        """Check connection health - pool stats, version, extensions.

        LEVEL: Server (connection management)

        USE FOR: connection status, pool health, "is database reachable?".
        DO NOT USE FOR: database metrics (database_health), query stats (query_performance).
        """
        health = await ctx.db_pool.health_check()

        # Add additional context
        health["auto_connected"] = ctx.auto_connected
        health["auto_connect_error"] = ctx.auto_connect_error

        if format == "markdown":
            lines = ["# Database Health Check", ""]

            status_emoji = "✅" if health.get("healthy") else "❌"
            lines.append(f"**Status:** {status_emoji} {health.get('status', 'unknown').upper()}")
            lines.append("")

            if health.get("healthy"):
                lines.append("## Connection Info")
                lines.append(f"- **Host:** {health.get('host')}")
                lines.append(f"- **Database:** {health.get('database')}")
                lines.append(f"- **PostgreSQL Version:** {health.get('pg_version')}")
                lines.append("")

                lines.append("## Connection Pool")
                lines.append(f"- **Total Connections:** {health.get('pool_size', 0)}")
                lines.append(f"- **In Use:** {health.get('pool_used', 0)}")
                lines.append(f"- **Available:** {health.get('pool_free', 0)}")
                lines.append("")

                if health.get("extensions"):
                    lines.append("## Extensions")
                    for ext in health["extensions"]:
                        lines.append(f"- {ext}")
            else:
                lines.append(f"**Message:** {health.get('message', 'Unknown error')}")
                if health.get("auto_connect_error"):
                    lines.append(f"**Auto-connect Error:** {health['auto_connect_error']}")

            return Response.formatted("\n".join(lines), "markdown", connected=health.get("healthy", False))

        return Response.ok(health, connected=health.get("healthy", False))
