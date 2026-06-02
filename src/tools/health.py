"""Database health and monitoring MCP tools.

This module provides tools for monitoring database health:
- database_health: Comprehensive health check (connections, locks, transactions)
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import HealthQueries, LockQueries, SessionQueries, TransactionQueries
from tools.context import ToolContext
from utils import HealthThresholds

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
HealthIncludeType = Literal["all", "summary", "sessions", "locks", "transactions", "queries", "bloat"]
FormatType = Literal["json", "markdown"]


def register_health_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register health monitoring MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def database_health(
        include: HealthIncludeType = Field(
            default="all",
            description="What to include: 'all', 'summary', 'sessions', 'locks', 'transactions', 'queries', 'bloat'",
        ),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
        summary_only: bool = Field(
            default=False, description="Return only summary counts and critical issues, not detailed lists"
        ),
    ) -> str:
        """Live database health - monitors active connections, sessions, locks, transactions.

        LEVEL: Database (single database monitoring)

        USE FOR: "is database healthy?", connection issues, lock problems, blocked queries,
        idle transactions, deadlock detection, XID wraparound check, "why is DB slow right now?".
        DO NOT USE FOR: index analysis (use maintenance_analysis), slow query history (use query_performance),
        table sizes/stats (use maintenance_analysis), query optimization (use query_optimizer),
        PostgreSQL server config (use configuration_review), replication (use replication_status).
        REAL-TIME: Shows current state of database activity.

        ERROR RECOVERY:
        - "not connected": Call connect() first or pass url parameter
        - "permission denied on pg_stat_*": User needs pg_monitor role or superuser
        - Use summary_only=True for large/busy databases to reduce payload size

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'summary': Database stats, connections by state, checkpoint stats
          - 'sessions': Session summary, by app/user/host, idle in transaction, active sessions
          - 'locks': Lock summary, waiting locks, blocking tree, table lock hotspots, deadlocks
          - 'transactions': XID wraparound status, transaction stats, long-running transactions
          - 'queries': Active queries, long-running queries, wait events
          - 'bloat': Tables needing vacuum

        Examples:
            database_health() - Full health report
            database_health(include='locks') - Only lock information
            database_health(include='sessions') - Only session information
            database_health(include='transactions') - XID status and long transactions
            database_health(format='markdown') - Human-readable output
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            include_all = include == "all"
            include_summary = include_all or include == "summary"
            health = {"severity": "healthy"}
            issues = []

            if include_summary or include_all:
                db_stats = await ctx.db_pool.fetch(HealthQueries.DATABASE_STATS)
                health["database"] = dict(db_stats[0]) if db_stats else {}

                conn_stats = await ctx.db_pool.fetch(HealthQueries.CONNECTIONS_BY_STATE)
                health["connections_by_state"] = [dict(r) for r in conn_stats]

                checkpoint_stats = await ctx.db_pool.fetch(HealthQueries.CHECKPOINT_STATS)
                health["checkpoint_stats"] = dict(checkpoint_stats[0]) if checkpoint_stats else {}

                if health.get("database", {}).get("cache_hit_ratio", 100) < HealthThresholds.CACHE_HIT_RATIO_WARNING:
                    issues.append(f"Low cache hit ratio: {health['database'].get('cache_hit_ratio')}%")
                    health["severity"] = "warning"

                if health.get("database", {}).get("deadlocks", 0) > 0:
                    issues.append(f"Deadlocks detected: {health['database']['deadlocks']}")

            if include_all or include == "sessions":
                summary = await ctx.db_pool.fetch(SessionQueries.SESSION_SUMMARY)
                health["session_summary"] = dict(summary[0]) if summary else {}

                if health.get("session_summary"):
                    s = health["session_summary"]
                    utilization = 100.0 * s.get("total_connections", 0) / s.get("max_connections", 1)
                    health["session_summary"]["utilization_pct"] = round(utilization, 2)
                    if utilization > HealthThresholds.CONNECTION_UTILIZATION_WARNING:
                        issues.append(f"High connection utilization: {utilization:.1f}%")
                        health["severity"] = "warning"

                by_app = await ctx.db_pool.fetch(SessionQueries.BY_APPLICATION)
                health["sessions_by_application"] = [dict(r) for r in by_app]

                by_user = await ctx.db_pool.fetch(SessionQueries.BY_USER)
                health["sessions_by_user"] = [dict(r) for r in by_user]

                by_host = await ctx.db_pool.fetch(SessionQueries.BY_CLIENT_HOST)
                health["sessions_by_host"] = [dict(r) for r in by_host]

                age_dist = await ctx.db_pool.fetch(SessionQueries.AGE_DISTRIBUTION)
                health["connection_age_distribution"] = [dict(r) for r in age_dist]

                idle_threshold_sec = HealthThresholds.IDLE_IN_TRANSACTION_WARNING_SEC
                idle_in_txn = await ctx.db_pool.fetch(SessionQueries.idle_in_transaction_sessions(idle_threshold_sec))
                health["idle_in_transaction"] = [dict(r) for r in idle_in_txn]
                if idle_in_txn:
                    idle_threshold_min = idle_threshold_sec // 60
                    issues.append(f"{len(idle_in_txn)} sessions idle in transaction >{idle_threshold_min} min")
                    health["severity"] = "warning"

                active = await ctx.db_pool.fetch(SessionQueries.active_sessions())
                health["active_sessions"] = [dict(r) for r in active]

            if include_all or include == "locks":
                lock_summary = await ctx.db_pool.fetch(LockQueries.LOCK_SUMMARY)
                health["lock_summary"] = [dict(r) for r in lock_summary]

                waiting = await ctx.db_pool.fetch(LockQueries.waiting_locks(0))
                health["waiting_locks"] = [dict(r) for r in waiting]
                if waiting:
                    max_wait = max(w.get("wait_duration_sec", 0) for w in health["waiting_locks"])
                    issues.append(f"{len(waiting)} queries waiting for locks (max: {max_wait}s)")
                    if max_wait > HealthThresholds.LOCK_WAIT_WARNING_SEC:
                        health["severity"] = "warning"
                    if max_wait > HealthThresholds.LOCK_WAIT_CRITICAL_SEC:
                        health["severity"] = "critical"

                blocking_tree = await ctx.db_pool.fetch(LockQueries.BLOCKING_TREE)
                health["blocking_tree"] = [dict(r) for r in blocking_tree]

                table_locks = await ctx.db_pool.fetch(LockQueries.TABLE_LOCK_HOTSPOTS)
                health["table_lock_hotspots"] = [dict(r) for r in table_locks]

                deadlock_stats = await ctx.db_pool.fetch(LockQueries.DEADLOCK_COUNT)
                health["cumulative_deadlocks"] = deadlock_stats[0]["deadlocks"] if deadlock_stats else 0

            if include_all or include == "transactions":
                xid_age = await ctx.db_pool.fetch(TransactionQueries.DATABASE_XID)
                health["xid_status"] = dict(xid_age[0]) if xid_age else {}

                xid_pct = health.get("xid_status", {}).get("pct_to_wraparound", 0)
                if xid_pct > HealthThresholds.XID_WRAPAROUND_CRITICAL_PCT:
                    issues.append(f"CRITICAL: XID wraparound at {xid_pct}%")
                    health["severity"] = "critical"
                elif xid_pct > HealthThresholds.XID_WRAPAROUND_WARNING_PCT:
                    issues.append(f"XID age warning: {xid_pct}%")
                    if health["severity"] != "critical":
                        health["severity"] = "warning"

                txn_stats = await ctx.db_pool.fetch(TransactionQueries.TRANSACTION_STATS)
                health["transaction_stats"] = dict(txn_stats[0]) if txn_stats else {}

                long_txn = await ctx.db_pool.fetch(
                    TransactionQueries.long_running_transactions(HealthThresholds.LONG_RUNNING_TRANSACTION_MIN)
                )
                health["long_running_transactions"] = [dict(r) for r in long_txn]
                if long_txn:
                    issues.append(f"{len(long_txn)} transactions running >10 minutes")

                prepared_txn = await ctx.db_pool.fetch(TransactionQueries.PREPARED_TRANSACTIONS)
                health["prepared_transactions"] = [dict(r) for r in prepared_txn]

                oldest = await ctx.db_pool.fetch(TransactionQueries.oldest_transaction())
                health["oldest_transaction"] = dict(oldest[0]) if oldest else None

            if include_all or include == "queries":
                active = await ctx.db_pool.fetch(HealthQueries.ACTIVE_QUERIES)
                health["active_queries"] = [dict(r) for r in active]

                long_running = await ctx.db_pool.fetch(HealthQueries.LONG_RUNNING_QUERIES)
                health["long_running_queries"] = [dict(r) for r in long_running]
                if long_running:
                    issues.append(f"{len(long_running)} queries running >1 minute")

                wait_events = await ctx.db_pool.fetch(HealthQueries.WAIT_EVENTS)
                health["wait_events"] = [dict(r) for r in wait_events]

            if include_all or include == "bloat":
                bloat = await ctx.db_pool.fetch(HealthQueries.TABLES_NEEDING_VACUUM)
                health["tables_needing_vacuum"] = [dict(r) for r in bloat]
                if bloat:
                    issues.append(f"{len(bloat)} tables need vacuum")

            health["issues"] = issues
            health["issue_count"] = len(issues)
            health["healthy"] = len(issues) == 0

            if format == "json":
                if summary_only:
                    summary = {
                        "severity": health.get("severity", "unknown"),
                        "issue_count": len(issues),
                        "issues": issues,  # Issues are already a summary list
                        "healthy": len(issues) == 0,
                        "database": health.get("database"),
                        "session_summary": health.get("session_summary"),
                        "lock_summary": health.get("lock_summary"),
                        "xid_status": health.get("xid_status"),
                    }
                    return Response.ok(summary, connected=True)
                return Response.ok(health, connected=True)

            lines = ["# Database Health Report", ""]
            lines.append(f"**Status:** {health['severity'].upper()}")
            lines.append(f"**Issues:** {len(issues)}")
            lines.append("")

            if issues:
                lines.append("## Issues")
                for issue in issues:
                    lines.append(f"- {issue}")
                lines.append("")

            if "database" in health:
                db = health["database"]
                lines.append("## Overview")
                lines.append(f"- Size: {db.get('size', 'N/A')}")
                lines.append(f"- Connections: {db.get('connections', 'N/A')}")
                lines.append(f"- Cache hit ratio: {db.get('cache_hit_ratio', 'N/A')}%")
                lines.append("")

            if "session_summary" in health:
                ss = health["session_summary"]
                lines.append("## Sessions")
                lines.append(f"- Total: {ss.get('total_connections', 0)} / {ss.get('max_connections', 0)}")
                lines.append(f"- Active: {ss.get('active', 0)}, Idle: {ss.get('idle', 0)}")
                lines.append(f"- Idle in transaction: {ss.get('idle_in_transaction', 0)}")
                lines.append("")

            if "lock_summary" in health and health["lock_summary"]:
                lines.append("## Locks")
                lines.append(f"- Waiting queries: {len(health.get('waiting_locks', []))}")
                lines.append(f"- Deadlocks (cumulative): {health.get('cumulative_deadlocks', 0)}")
                lines.append("")

            if "xid_status" in health:
                xid = health["xid_status"]
                lines.append("## Transaction ID Status")
                lines.append(f"- XID age: {xid.get('xid_age', 'N/A')}")
                lines.append(f"- % to wraparound: {xid.get('pct_to_wraparound', 0)}%")
                lines.append("")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="database_health")
