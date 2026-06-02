"""Audit log management tools for DBeast MCP server.

Provides tools to view and manage MCP request/response audit logs.
"""

from pydantic import Field

from models.responses import Response


def register_audit_tools(mcp):
    """Register audit management tools with the MCP server."""

    @mcp.tool()
    async def get_audit_logs(
        date: str | None = Field(default=None, description="Date in YYYY-MM-DD format (default: today)"),
        limit: int = Field(default=50, ge=1, le=500, description="Max entries to return"),
        format: str = Field(default="markdown", description="Output format: 'markdown' or 'json'"),
    ) -> str:
        """Retrieve MCP audit logs for accountability and debugging.

        USE FOR: viewing tool call history, debugging issues, compliance audits.

        Examples:
            get_audit_logs() - Today's logs
            get_audit_logs(date='2026-05-29') - Specific date
            get_audit_logs(limit=10) - Last 10 entries
        """
        try:
            from middleware.audit import get_audit_logger

            logger = get_audit_logger()

            if format == "json":
                files = logger.list_log_files()
                if date:
                    # Filter to specific date
                    files = [f for f in files if f["date"] == date]
                return Response.ok(
                    {
                        "log_files": files[:10],
                        "logs": logger.get_logs(date, limit),
                    },
                    connected=True,
                )
            else:
                return Response.formatted(logger.get_logs(date, limit), "markdown", connected=True)

        except ImportError:
            return Response.error(
                "AUDIT_DISABLED",
                "Audit logging module not available",
                hint="Ensure middleware.audit is properly installed",
            )
        except Exception as e:
            return Response.error(
                "INTERNAL_ERROR",
                f"Failed to retrieve audit logs: {str(e)}",
            )

    @mcp.tool()
    async def list_audit_files() -> str:
        """List available audit log files.

        USE FOR: finding available log dates, checking log sizes.

        Returns list of log files with date, size, and entry count.
        """
        try:
            from middleware.audit import get_audit_logger

            logger = get_audit_logger()
            files = logger.list_log_files()

            if not files:
                return Response.ok(
                    {
                        "message": "No audit logs found",
                        "log_dir": str(logger.log_dir),
                        "enabled": logger.enabled,
                    },
                    connected=True,
                )

            return Response.ok(
                {
                    "log_files": files,
                    "total_files": len(files),
                    "log_dir": str(logger.log_dir),
                },
                connected=True,
            )

        except ImportError:
            return Response.error(
                "AUDIT_DISABLED",
                "Audit logging module not available",
            )
        except Exception as e:
            return Response.error(
                "INTERNAL_ERROR",
                f"Failed to list audit files: {str(e)}",
            )
