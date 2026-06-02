"""PostgreSQL configuration review MCP tools.

This module provides tools for PostgreSQL configuration review:
- configuration_review: Memory, connections, autovacuum, logging settings
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import ConfigQueries
from tools.context import ToolContext
from utils import HealthThresholds

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
ConfigIncludeType = Literal["all", "memory", "connections", "logging", "autovacuum", "extensions"]
FormatType = Literal["json", "markdown"]


def register_config_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register configuration-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def configuration_review(
        include: ConfigIncludeType = Field(
            default="all",
            description="What to include: 'all', 'memory', 'connections', 'logging', 'autovacuum', 'extensions'",
        ),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
    ) -> str:
        """Reviews PostgreSQL configuration settings and provides tuning observations.

        LEVEL: Server (PostgreSQL instance configuration)

        USE FOR: configuration, settings, postgresql.conf, parameters, tuning, memory, extensions,
        "why is DB slow globally?", "is autovacuum configured correctly?", server tuning review.
        DO NOT USE FOR: database-level health (use database_health), query optimization (use query_optimizer),
        replication settings (use replication_status), table-specific issues (use maintenance_analysis).

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'memory': shared_buffers, effective_cache_size, work_mem analysis
          - 'connections': max_connections, current utilization, pooling recommendations
          - 'logging': log_min_duration_statement, log_checkpoints, statement_timeout
          - 'autovacuum': autovacuum enabled, workers, thresholds
          - 'extensions': Installed extensions, recommended extensions not installed

        Examples:
            configuration_review() - Full configuration review
            configuration_review(include='memory') - Memory settings only
            configuration_review(include='connections') - Connection limits only
            configuration_review(include='autovacuum') - Autovacuum settings only
            configuration_review(include='logging') - Logging configuration
            configuration_review(include='extensions') - Installed extensions
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            include_all = include == "all"
            result = {}
            observations = []

            key_settings = await ctx.db_pool.fetch(ConfigQueries.KEY_SETTINGS)
            settings_dict = {s["name"]: s for s in key_settings}

            if include_all or include == "memory":
                shared_buffers_bytes = await ctx.db_pool.fetchval(
                    "SELECT setting::bigint * 8192 FROM pg_settings WHERE name = 'shared_buffers'"
                )
                effective_cache_bytes = await ctx.db_pool.fetchval(
                    "SELECT setting::bigint * 8192 FROM pg_settings WHERE name = 'effective_cache_size'"
                )
                work_mem_bytes = await ctx.db_pool.fetchval(
                    "SELECT pg_size_bytes(setting || unit) FROM pg_settings WHERE name = 'work_mem'"
                )

                result["memory"] = {
                    "shared_buffers_bytes": shared_buffers_bytes,
                    "effective_cache_bytes": effective_cache_bytes,
                    "work_mem_bytes": work_mem_bytes,
                }

                system_mem_estimate = effective_cache_bytes * 1.5 if effective_cache_bytes else None
                if shared_buffers_bytes and system_mem_estimate:
                    sb_pct = 100.0 * shared_buffers_bytes / system_mem_estimate
                    if sb_pct < 15:
                        observations.append(
                            f"shared_buffers may be low ({sb_pct:.1f}% of estimated RAM) - consider 25% of RAM"
                        )
                    elif sb_pct > 40:
                        observations.append(
                            f"shared_buffers is high ({sb_pct:.1f}% of estimated RAM) - may cause memory pressure"
                        )

            if include_all or include == "connections":
                max_conn = int(settings_dict.get("max_connections", {}).get("setting", 100))
                current_conn = await ctx.db_pool.fetchval(ConfigQueries.CONNECTION_COUNT)
                conn_pct = 100.0 * current_conn / max_conn if max_conn else 0

                result["connections"] = {
                    "current": current_conn,
                    "max": max_conn,
                    "utilization_pct": round(conn_pct, 2),
                }

                if conn_pct > HealthThresholds.CONNECTION_UTILIZATION_WARNING:
                    observations.append(f"Connection utilization high: {conn_pct:.1f}% - consider connection pooling")

            if include_all or include == "autovacuum":
                av_enabled = settings_dict.get("autovacuum", {}).get("setting") == "on"
                if not av_enabled:
                    observations.append("CRITICAL: Autovacuum is disabled - enable immediately")

                av_workers = int(settings_dict.get("autovacuum_max_workers", {}).get("setting", 3))
                if av_workers < 3:
                    observations.append(f"autovacuum_max_workers is low ({av_workers})")

            if include_all or include == "logging":
                log_duration = settings_dict.get("log_min_duration_statement", {}).get("setting", "-1")
                if log_duration == "-1":
                    observations.append("Slow query logging disabled - consider enabling")

                log_checkpoints = settings_dict.get("log_checkpoints", {}).get("setting") == "on"
                if not log_checkpoints:
                    observations.append("Checkpoint logging disabled")

                statement_timeout = settings_dict.get("statement_timeout", {}).get("setting", "0")
                if statement_timeout == "0":
                    observations.append("No statement_timeout set - queries can run indefinitely")

            if include_all or include == "extensions":
                extensions = await ctx.db_pool.fetch(ConfigQueries.EXTENSIONS)
                result["extensions"] = [dict(e) for e in extensions]

                recommended_ext = ["pg_stat_statements", "pgstattuple", "pg_buffercache"]
                installed_ext = [e["extname"] for e in extensions]
                missing_ext = [e for e in recommended_ext if e not in installed_ext]
                if missing_ext:
                    result["recommended_extensions_not_installed"] = missing_ext

            settings_by_category = {}
            for s in key_settings:
                cat = s["category"]
                if cat not in settings_by_category:
                    settings_by_category[cat] = []
                settings_by_category[cat].append(
                    {
                        "name": s["name"],
                        "value": f"{s['setting']}{' ' + s['unit'] if s['unit'] else ''}",
                        "source": s["source"],
                        "pending_restart": s["pending_restart"],
                    }
                )
            result["settings_by_category"] = settings_by_category

            pending = [s["name"] for s in key_settings if s["pending_restart"]]
            if pending:
                observations.append(f"Settings pending restart: {', '.join(pending)}")

            result["observations"] = observations
            result["observation_count"] = len(observations)

            if format == "json":
                return Response.ok(result, connected=True)

            lines = ["# Configuration Review", ""]

            if "memory" in result:
                mem = result["memory"]
                lines.append("## Memory Settings")
                if mem.get("shared_buffers_bytes"):
                    lines.append(f"- shared_buffers: {mem['shared_buffers_bytes'] / (1024 * 1024 * 1024):.2f} GB")
                if mem.get("effective_cache_bytes"):
                    lines.append(
                        f"- effective_cache_size: {mem['effective_cache_bytes'] / (1024 * 1024 * 1024):.2f} GB"
                    )
                if mem.get("work_mem_bytes"):
                    lines.append(f"- work_mem: {mem['work_mem_bytes'] / (1024 * 1024):.0f} MB")
                lines.append("")

            if "connections" in result:
                conn = result["connections"]
                lines.append("## Connections")
                lines.append(f"- Current: {conn['current']} / {conn['max']} ({conn['utilization_pct']}%)")
                lines.append("")

            if "extensions" in result:
                lines.append(f"## Extensions ({len(result['extensions'])})")
                for e in result["extensions"][:10]:
                    lines.append(f"- {e['extname']} v{e['extversion']}")
                if result.get("recommended_extensions_not_installed"):
                    lines.append("")
                    lines.append("**Recommended but not installed:**")
                    for e in result["recommended_extensions_not_installed"]:
                        lines.append(f"- {e}")
                lines.append("")

            if observations:
                lines.append("## Observations")
                for obs in observations:
                    lines.append(f"- {obs}")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="configuration_review")
