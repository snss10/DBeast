"""Query performance analysis MCP tools.

This module provides tools for query performance analysis:
- query_performance: Top queries by time/calls (requires pg_stat_statements)
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, extension_required_error, internal_error
from query import PerformanceQueries
from tools.context import ToolContext
from utils import HealthThresholds

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
OrderByType = Literal["total_time", "calls", "mean_time", "rows", "shared_blks_hit", "shared_blks_read"]


def register_performance_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register performance-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def query_performance(
        limit: int = Field(default=20, ge=1, le=500, description="Number of queries to return (1-500)"),
        order_by: OrderByType = Field(
            default="total_time",
            description="Sort by: total_time, calls, mean_time, rows, shared_blks_hit, shared_blks_read",
        ),
        min_calls: int = Field(default=1, ge=1, description="Minimum call count filter"),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
    ) -> str:
        """Historical query stats - shows top queries by time/calls/IO from pg_stat_statements.

        LEVEL: Database (database-wide query statistics)

        USE FOR: "what queries are slowest?", finding high-frequency queries, cache hit analysis,
        queries using temp files, overall query patterns, "which queries consume most time?".
        DO NOT USE FOR: analyzing ONE specific query (use query_optimizer), live running queries (use database_health),
        index recommendations (use maintenance_analysis), query syntax validation (use analyze_query).
        REQUIRES: pg_stat_statements extension installed.

        Examples:
            query_performance() - Top 20 queries by total time
            query_performance(order_by='calls') - Most frequently called queries
            query_performance(order_by='mean_time') - Slowest average execution
            query_performance(limit=50, min_calls=100) - Top 50, only queries called 100+ times
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            result = {}

            if not ctx.db_pool.has_extension("pg_stat_statements"):
                ext_check = await ctx.db_pool.fetch("""
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
                """)
                if not ext_check:
                    return extension_required_error(
                        "pg_stat_statements", "query performance analysis (tracking SQL execution statistics)"
                    )

            valid_orders = [
                "total_time",
                "calls",
                "mean_time",
                "rows",
                "shared_blks_hit",
                "shared_blks_read",
                "shared_blks_dirtied",
                "temp_blks_read",
                "temp_blks_written",
            ]
            if order_by not in valid_orders:
                order_by = "total_time"

            pg_version = ctx.db_pool.pg_version or 14

            time_col = "total_exec_time" if pg_version >= 13 else "total_time"
            mean_time_col = "mean_exec_time" if pg_version >= 13 else "mean_time"

            order_col = order_by
            if order_by == "total_time":
                order_col = time_col
            elif order_by == "mean_time":
                order_col = mean_time_col

            top_queries = await ctx.db_pool.fetch(
                PerformanceQueries.top_queries(order_col, time_col, mean_time_col, limit, min_calls, pg_version)
            )
            result["top_queries"] = [dict(r) for r in top_queries]

            summary_query = PerformanceQueries.SUMMARY.format(time_col=time_col, mean_time_col=mean_time_col)
            summary = await ctx.db_pool.fetch(summary_query)
            result["summary"] = dict(summary[0]) if summary else {}

            variable_queries = await ctx.db_pool.fetch(PerformanceQueries.variable_queries(mean_time_col, pg_version))
            result["most_variable_queries"] = [dict(r) for r in variable_queries]

            temp_heavy = await ctx.db_pool.fetch(PerformanceQueries.temp_heavy_queries(mean_time_col))
            result["queries_using_temp"] = [dict(r) for r in temp_heavy]

            low_cache_hit = await ctx.db_pool.fetch(PerformanceQueries.low_cache_hit_queries(mean_time_col))
            result["low_cache_hit_queries"] = [dict(r) for r in low_cache_hit]

            issues = []
            healthy = True

            if result.get("queries_using_temp"):
                issues.append(
                    f"{len(result['queries_using_temp'])} queries using temp files (consider increasing work_mem)"
                )
                healthy = False
            if result.get("low_cache_hit_queries"):
                issues.append(f"{len(result['low_cache_hit_queries'])} queries with <90% cache hit rate")
                healthy = False
            if result.get("most_variable_queries"):
                high_cv = [q for q in result["most_variable_queries"] if q.get("cv_pct", 0) > 100]
                if high_cv:
                    issues.append(f"{len(high_cv)} queries with highly variable performance (CV >100%)")
                    healthy = False

            if result.get("summary", {}).get("overall_cache_hit_pct", 100) < HealthThresholds.CACHE_HIT_RATIO_WARNING:
                issues.append(
                    f"Overall cache hit ratio is {result['summary'].get('overall_cache_hit_pct', 0):.1f}% (target: >{HealthThresholds.CACHE_HIT_RATIO_WARNING}%)"
                )
                healthy = False

            result["issues"] = issues
            result["healthy"] = healthy

            return Response.ok(result, connected=True)
        except Exception as e:
            return internal_error(e, context="query_performance")
