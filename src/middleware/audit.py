"""MCP Audit Logger for accountability and debugging.

Logs all MCP tool requests and responses to markdown files for:
- Accountability and compliance
- Debugging and troubleshooting
- Usage analytics
- Audit trails

Usage:
    from middleware.audit import get_audit_logger, create_audited_tool

    # Method 1: Manual logging
    logger = get_audit_logger()
    await logger.log_tool_call("execute_query", {"query": "SELECT 1"}, response, duration_ms)

    # Method 2: Use audited tool factory (recommended)
    @mcp.tool()
    async def my_tool(param: str) -> str:
        ...

    # Register with auditing:
    register_audited_tool(mcp, my_tool_impl, "my_tool")
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

# Module-level logger instance
_audit_logger: "McpAuditLogger | None" = None
_logger = logging.getLogger("dbeast.audit")

F = TypeVar("F", bound=Callable[..., Any])


def get_audit_logger() -> "McpAuditLogger":
    """Get or create the singleton audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = McpAuditLogger()
    return _audit_logger


class McpAuditLogger:
    """Logs MCP tool calls to markdown files for accountability.

    Features:
    - Daily log files in markdown format
    - Structured request/response logging
    - Configurable via environment variables
    - Automatic log rotation by date
    - Sensitive data masking (passwords, secrets)
    - Handles both JSON and markdown responses
    """

    # Fields to mask in logs
    SENSITIVE_FIELDS = {"password", "secret", "token", "api_key", "apikey", "credential", "aws_secret"}

    def __init__(
        self,
        log_dir: str | None = None,
        enabled: bool | None = None,
        max_response_size: int | None = None,
    ):
        """Initialize the audit logger.

        Args:
            log_dir: Directory for log files (default: logs/mcp_audit)
            enabled: Enable/disable logging (default: from env DBEAST_AUDIT_ENABLED)
            max_response_size: Max chars for response in log (truncates if larger)
        """
        # Load from environment if not specified
        self.enabled = enabled if enabled is not None else os.getenv("DBEAST_AUDIT_ENABLED", "true").lower() == "true"
        log_dir_value = log_dir or os.getenv("DBEAST_AUDIT_DIR") or "logs/mcp_audit"
        self.log_dir = Path(log_dir_value)
        self.max_response_size = max_response_size or int(os.getenv("DBEAST_AUDIT_MAX_RESPONSE_SIZE", "10000"))

        # Create log directory if enabled
        if self.enabled:
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                _logger.warning(f"Failed to create audit log directory: {e}")
                self.enabled = False

    def _get_log_file(self) -> Path:
        """Get the log file path for today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.md"

    def _mask_sensitive(self, data: Any) -> Any:
        """Mask sensitive fields in data recursively."""
        if isinstance(data, dict):
            masked = {}
            for key, value in data.items():
                if any(s in key.lower() for s in self.SENSITIVE_FIELDS):
                    masked[key] = "***MASKED***"
                else:
                    masked[key] = self._mask_sensitive(value)
            return masked
        elif isinstance(data, list):
            return [self._mask_sensitive(item) for item in data]
        elif isinstance(data, str):
            # Mask connection strings with passwords
            if "://" in data and "@" in data:
                return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", data)
        return data

    def _parse_response(self, response: Any) -> tuple[Any, str]:
        """Parse response to extract data and determine format.

        Returns:
            Tuple of (parsed_data, format_type)
            format_type is 'json', 'markdown', or 'text'
        """
        if response is None:
            return None, "json"

        # If it's already a dict/list, return as-is
        if isinstance(response, (dict, list)):
            return response, "json"

        # If it's a string, try to parse as JSON
        if isinstance(response, str):
            response_stripped = response.strip()
            # Check if it looks like JSON
            if response_stripped.startswith(("{", "[")):
                try:
                    return json.loads(response), "json"
                except json.JSONDecodeError:
                    pass
            # Check if it looks like markdown
            if response_stripped.startswith("#") or "\n## " in response_stripped:
                return {"_markdown": response[:500] + "..." if len(response) > 500 else response}, "markdown"
            # Plain text
            return {"_text": response[:500] + "..." if len(response) > 500 else response}, "text"

        # Fallback
        return {"_raw": str(response)[:500]}, "text"

    def _truncate_response(self, response: Any) -> Any:
        """Truncate large responses for logging."""
        try:
            response_str = json.dumps(response, default=str, indent=2)
        except (TypeError, ValueError):
            response_str = str(response)

        if len(response_str) > self.max_response_size:
            return {
                "_truncated": True,
                "_original_size": len(response_str),
                "_preview": response_str[: self.max_response_size] + "...",
            }
        return response

    def _write_header_if_needed(self, file_path: Path) -> None:
        """Write the header if this is a new file."""
        if not file_path.exists():
            header = f"""# MCP Audit Log

**Date:** {datetime.now().strftime("%Y-%m-%d")}
**Server:** DBeast PostgreSQL MCP Server

---

"""
            file_path.write_text(header, encoding="utf-8")

    async def log_tool_call(
        self,
        tool_name: str,
        params: dict[str, Any],
        response: Any,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Log a tool call to the audit file.

        Args:
            tool_name: Name of the MCP tool called
            params: Input parameters (will be masked for sensitive data)
            response: Tool response (string or dict - will be parsed and truncated)
            duration_ms: Execution time in milliseconds
            error: Error message if the call failed
        """
        if not self.enabled:
            return

        try:
            file_path = self._get_log_file()
            self._write_header_if_needed(file_path)

            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
            status = "ERROR" if error else "SUCCESS"
            status_icon = "❌" if error else "✅"

            # Mask sensitive data in params
            masked_params = self._mask_sensitive(params)

            # Parse and truncate response
            parsed_response, response_format = self._parse_response(response)
            truncated_response = self._truncate_response(parsed_response) if parsed_response else None

            # Format the log entry
            entry = f"""
## {timestamp} | `{tool_name}` | {status_icon} {status}

**Duration:** {duration_ms:.0f}ms

### Request Parameters
```json
{json.dumps(masked_params, indent=2, default=str)}
```

### Response ({response_format})
```json
{json.dumps(truncated_response, indent=2, default=str) if truncated_response else "null"}
```
"""
            if error:
                entry += f"""
### Error Details
```
{error[:1000]}
```
"""
            entry += "\n---\n"

            # Append to file (synchronous write is fine for audit logs)
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry)

        except Exception as e:
            # Don't let logging errors break the tool
            _logger.warning(f"Audit log failed for {tool_name}: {e}")

    def get_logs(self, date: str | None = None, limit: int = 100) -> str:
        """Retrieve logs for a specific date.

        Args:
            date: Date in YYYY-MM-DD format (default: today)
            limit: Max number of entries to return

        Returns:
            Log content as string
        """
        if not self.enabled:
            return "Audit logging is disabled."

        target_date = date or datetime.now().strftime("%Y-%m-%d")
        file_path = self.log_dir / f"{target_date}.md"

        if not file_path.exists():
            return f"No logs found for {target_date}"

        content = file_path.read_text(encoding="utf-8")

        # If limit specified, return only last N entries
        if limit and limit > 0:
            entries = content.split("\n---\n")
            if len(entries) > limit + 1:  # +1 for header
                # Keep header + last N entries
                header = entries[0]
                last_entries = entries[-(limit):]
                content = header + "\n---\n" + "\n---\n".join(last_entries)

        return content

    def list_log_files(self) -> list[dict[str, Any]]:
        """List available log files.

        Returns:
            List of log file info dicts with date, size, path
        """
        if not self.enabled or not self.log_dir.exists():
            return []

        files = []
        for f in sorted(self.log_dir.glob("*.md"), reverse=True):
            try:
                stat = f.stat()
                content = f.read_text(encoding="utf-8")
                files.append(
                    {
                        "date": f.stem,
                        "size_kb": round(stat.st_size / 1024, 2),
                        "path": str(f),
                        "entries": content.count("\n---\n") - 1,
                    }
                )
            except OSError:
                continue
        return files


def create_audited_tool(tool_name: str | None = None) -> Callable[[F], F]:
    """Create a decorator that wraps an async tool function with audit logging.

    This decorator should be applied BEFORE @mcp.tool() so it wraps the inner function.

    Args:
        tool_name: Override tool name (default: function name)

    Usage:
        @mcp.tool()
        @create_audited_tool()
        async def my_tool(param: str) -> str:
            ...

        # Or with custom name:
        @mcp.tool()
        @create_audited_tool("custom_name")
        async def another_tool() -> str:
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_audit_logger()
            name = tool_name or func.__name__
            start_time = time.time()
            error = None
            response = None

            try:
                response = await func(*args, **kwargs)
                return response
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                # Extract params from kwargs (exclude internal params)
                params = {k: v for k, v in kwargs.items() if not k.startswith("_")}
                await logger.log_tool_call(name, params, response, duration_ms, error)

        return wrapper  # type: ignore

    return decorator


# Convenience alias
audited = create_audited_tool
