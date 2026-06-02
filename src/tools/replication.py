"""Replication status and monitoring MCP tools.

This module provides tools for replication monitoring:
- replication_status: Physical, logical, slots, WAL, archiving
"""

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from middleware.audit import audited
from models import Response, connection_error, internal_error
from query import ReplicationQueries
from tools.context import ToolContext

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
ReplicationIncludeType = Literal["all", "physical", "logical", "slots", "wal", "archiving"]
FormatType = Literal["json", "markdown"]


def register_replication_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register replication-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def replication_status(
        include: ReplicationIncludeType = Field(
            default="all", description="What to include: 'all', 'physical', 'logical', 'slots', 'wal', 'archiving'"
        ),
        url: str | None = Field(default=None, description="Database URL for auto-connection"),
        format: FormatType = Field(default="json", description="Output format: 'json' or 'markdown'"),
    ) -> str:
        """Comprehensive replication health - physical, logical, CDC, slots, WAL, archiving.

        LEVEL: Server (PostgreSQL instance level)

        USE FOR: replication status, replica lag, standby, streaming replication, replication slots,
        CDC, logical replication, publications, subscriptions, WAL archiving, backup progress,
        "is replication healthy?", "how far behind is the replica?".
        DO NOT USE FOR: database-level health (use database_health), query performance (use query_performance),
        PostgreSQL settings (use configuration_review).

        INCLUDE OPTIONS:
          - 'all': Everything (default)
          - 'physical': Standbys, streaming replication, replay lag
          - 'logical': CDC status, wal_level, publications, subscriptions, logical slots
          - 'slots': All replication slots (physical and logical), inactive slot warnings
          - 'wal': WAL info, WAL settings
          - 'archiving': Archive mode, archiver status, failed archives, active basebackups

        Examples:
            replication_status() - Full replication report
            replication_status(include='physical') - Physical replication only
            replication_status(include='logical') - Logical replication/CDC only
            replication_status(include='slots') - Replication slots only
            replication_status(include='wal') - WAL status only
            replication_status(include='archiving') - WAL archiving status
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        try:
            include_all = include == "all"
            result: dict[str, Any] = {"replication_configured": False}
            issues: list[str] = []

            if include_all or include == "physical":
                standbys = await ctx.db_pool.fetch(ReplicationQueries.STANDBYS)
                if standbys:
                    result["replication_configured"] = True
                    result["role"] = "primary"
                    result["standbys"] = [dict(r) for r in standbys]

                    lagging = [s for s in result["standbys"] if s.get("replay_lag_bytes", 0) > 1073741824]
                    if lagging:
                        issues.append(f"{len(lagging)} replica(s) lagging >1GB behind primary")

                recovery_status = await ctx.db_pool.fetch(ReplicationQueries.IS_STANDBY)
                if recovery_status and recovery_status[0]["is_standby"]:
                    result["replication_configured"] = True
                    result["role"] = "standby"

                    recovery_info = await ctx.db_pool.fetch(ReplicationQueries.STANDBY_STATUS)
                    result["standby_status"] = dict(recovery_info[0]) if recovery_info else {}

                    lag_sec = result.get("standby_status", {}).get("replay_lag_seconds", 0)
                    if lag_sec and lag_sec > 60:
                        issues.append(f"Standby lagging {lag_sec} seconds behind primary")

            if include_all or include == "logical":
                cdc_config = await ctx.db_pool.fetch(ReplicationQueries.CDC_STATUS)
                wal_level = next((c["setting"] for c in cdc_config if c["name"] == "wal_level"), "unknown")
                result["cdc_enabled"] = wal_level == "logical"
                result["wal_level"] = wal_level

                if wal_level == "logical":
                    result["replication_configured"] = True

                    publications = await ctx.db_pool.fetch(ReplicationQueries.PUBLICATIONS)
                    result["publications"] = [dict(p) for p in publications]

                    subscriptions = await ctx.db_pool.fetch(ReplicationQueries.SUBSCRIPTIONS)
                    result["subscriptions"] = [dict(s) for s in subscriptions]

                    logical_slots = await ctx.db_pool.fetch(ReplicationQueries.LOGICAL_REPLICATION_SLOTS)
                    result["logical_slots"] = [dict(s) for s in logical_slots]

                    inactive_logical = [s for s in logical_slots if not s["active"]]
                    if inactive_logical:
                        issues.append(f"{len(inactive_logical)} inactive logical slot(s)")

            if include_all or include == "slots":
                slots = await ctx.db_pool.fetch(ReplicationQueries.REPLICATION_SLOTS)
                result["replication_slots"] = [dict(r) for r in slots]

                if slots:
                    result["replication_configured"] = True
                    inactive_slots = [s for s in slots if not s["active"]]
                    if inactive_slots:
                        issues.append(f"{len(inactive_slots)} inactive replication slot(s) retaining WAL")

                inactive_detail = await ctx.db_pool.fetch(ReplicationQueries.INACTIVE_REPLICATION_SLOTS)
                for slot in inactive_detail:
                    if "CRITICAL" in slot.get("severity", ""):
                        issues.append(f"CRITICAL: Slot '{slot['slot_name']}' retaining {slot['retained_wal']}")

            if include_all or include == "wal":
                wal_info = await ctx.db_pool.fetch(ReplicationQueries.WAL_INFO)
                result["wal_info"] = dict(wal_info[0]) if wal_info else {}

                wal_settings = await ctx.db_pool.fetch(ReplicationQueries.WAL_SETTINGS)
                result["wal_settings"] = {s["name"]: f"{s['setting']} {s['unit'] or ''}".strip() for s in wal_settings}

            if include_all or include == "archiving":
                archiver_status = await ctx.db_pool.fetch(ReplicationQueries.WAL_ARCHIVER_STATUS)
                if archiver_status:
                    result["archiver_status"] = dict(archiver_status[0])
                    archive_health = result["archiver_status"].get("health_status", "unknown")
                    if "CRITICAL" in archive_health:
                        issues.append(f"Archive failure: {result['archiver_status'].get('last_failed_wal', 'unknown')}")
                    elif "WARNING" in archive_health:
                        issues.append("No WAL archive in >1 hour")

                archive_settings = await ctx.db_pool.fetch(ReplicationQueries.ARCHIVE_SETTINGS)
                result["archive_settings"] = [dict(s) for s in archive_settings]
                archive_mode = next((s["setting"] for s in archive_settings if s["name"] == "archive_mode"), "off")
                result["archive_enabled"] = archive_mode in ("on", "always")

                basebackup_progress = await ctx.db_pool.fetch(ReplicationQueries.BASEBACKUP_PROGRESS)
                if basebackup_progress:
                    result["active_backups"] = [dict(b) for b in basebackup_progress]

            result["issues"] = issues

            if not result["replication_configured"]:
                result["message"] = "No replication configured on this database"

            if format == "json":
                return Response.ok(result, connected=True)

            lines = ["# Replication Status", ""]

            if not result["replication_configured"]:
                return Response.formatted("No replication configured on this database.", "text", connected=True)

            lines.append("## Overview")
            lines.append(f"- Role: {result.get('role', 'unknown')}")
            lines.append(f"- WAL level: {result.get('wal_level', 'unknown')}")
            lines.append(f"- CDC enabled: {'Yes' if result.get('cdc_enabled') else 'No'}")
            lines.append("")

            if result.get("standbys"):
                lines.append("## Physical Replication")
                lines.append("| Application | Client | State | Lag |")
                lines.append("|-------------|--------|-------|-----|")
                for s in result["standbys"]:
                    lines.append(
                        f"| {s.get('application_name', 'N/A')} | {s.get('client_host', 'N/A')} | {s.get('state', 'N/A')} | {s.get('replay_lag', 'N/A')} |"
                    )
                lines.append("")

            if result.get("standby_status"):
                ss = result["standby_status"]
                lines.append("## Standby Status")
                lines.append(f"- Replay lag: {ss.get('replay_lag_seconds', 0)} seconds")
                lines.append(f"- Last replay: {ss.get('last_replay_time', 'N/A')}")
                lines.append("")

            if result.get("publications"):
                lines.append("## Publications")
                for p in result["publications"]:
                    tables = (
                        p.get("tables", "all tables") if p.get("all_tables") else p.get("tables", "specific tables")
                    )
                    lines.append(f"- **{p['publication_name']}**: {tables}")
                lines.append("")

            if result.get("subscriptions"):
                lines.append("## Subscriptions")
                for s in result["subscriptions"]:
                    status = "enabled" if s.get("enabled") else "disabled"
                    lines.append(f"- **{s['subscription_name']}**: {status}")
                lines.append("")

            if result.get("replication_slots"):
                lines.append("## Replication Slots")
                lines.append("| Slot | Type | Active | Retained WAL |")
                lines.append("|------|------|--------|--------------|")
                for s in result["replication_slots"]:
                    lines.append(
                        f"| {s['slot_name']} | {s['slot_type']} | {s['active']} | {s.get('retained_wal', 'N/A')} |"
                    )
                lines.append("")

            if result.get("archiver_status") or result.get("archive_settings"):
                lines.append("## WAL Archiving")
                if result.get("archive_enabled"):
                    lines.append("- Archive mode: enabled")
                    if result.get("archiver_status"):
                        arch = result["archiver_status"]
                        lines.append(f"- Archives completed: {arch.get('archived_count', 0)}")
                        lines.append(f"- Last archive: {arch.get('last_archived_wal', 'N/A')}")
                        lines.append(f"- Failed archives: {arch.get('failed_count', 0)}")
                        if arch.get("health_status"):
                            lines.append(f"- Status: {arch['health_status']}")
                else:
                    lines.append("- Archive mode: **disabled**")
                lines.append("")

            if result.get("active_backups"):
                lines.append("## Active Basebackups")
                for b in result["active_backups"]:
                    lines.append(
                        f"- **{b.get('application_name', 'backup')}**: {b.get('progress_pct', 0)}% ({b.get('streamed', 'N/A')} / {b.get('total_size', 'N/A')})"
                    )
                lines.append("")

            if issues:
                lines.append("## Issues")
                for issue in issues:
                    lines.append(f"- {issue}")

            return Response.formatted("\n".join(lines), "markdown", connected=True)
        except Exception as e:
            return internal_error(e, context="replication_status")
