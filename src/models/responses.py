"""Unified response system for all MCP outputs.

Provides a consistent response structure for both tools and resources:
- Success: {"success": true, "data": {...}, "meta": {...}}
- Error: {"success": false, "error": {...}, "meta": {...}}

This ensures LLMs always know how to parse responses regardless of
whether they came from a tool or resource.

Classes:
    ErrorCode: Enum of standard error codes (NOT_CONNECTED, QUERY_TIMEOUT, etc.)
    ErrorDetail: Pydantic model for structured error information
    ResponseMeta: Pydantic model for response metadata (connected, source)
    McpResponse: Pydantic model for the unified response structure
    Response: Factory class with static methods for creating responses

Helper Functions:
    error(): Create error response with custom code
    connection_error(): Database not connected error
    timeout_error(): Query timeout error
    validation_error(): Input validation error
    not_found_error(): Resource not found error
    extension_required_error(): Missing PostgreSQL extension error
    internal_error(): Unexpected internal error
    parse_error(): SQL syntax error
    success(): Create success response with optional enrichment
    success_with_issues(): Success response that includes warnings/issues

Usage:
    # Preferred - use Response factory directly
    return Response.ok({"data": data}, connected=True)
    return Response.not_connected()
    return Response.error(ErrorCode.VALIDATION_ERROR, "Invalid input")

    # Helper functions (shorthand for common cases)
    return connection_error()
    return success({"tables": tables})
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """Standard error codes for all MCP responses."""

    # Connection errors
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"

    # Query errors
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    QUERY_CANCELED = "QUERY_CANCELED"
    QUERY_INVALID = "QUERY_INVALID"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    MISSING_PARAMETER = "MISSING_PARAMETER"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    SCHEMA_NOT_FOUND = "SCHEMA_NOT_FOUND"

    # Permission errors
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # Feature errors
    EXTENSION_REQUIRED = "EXTENSION_REQUIRED"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    PARSE_ERROR = "PARSE_ERROR"


class ErrorDetail(BaseModel):
    """Structured error information for LLM-readable error responses."""

    code: str = Field(description="Machine-readable error code (e.g., NOT_CONNECTED, VALIDATION_ERROR)")
    message: str = Field(description="Human-readable error message explaining what went wrong")
    hint: str | None = Field(default=None, description="Actionable suggestion for how to fix the error")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional context like field names, values, or query snippets"
    )


class ResponseMeta(BaseModel):
    """Response metadata providing context about the response source and connection state."""

    connected: bool = Field(default=False, description="Whether database connection is active")
    source: Literal["tool", "resource"] = Field(
        default="tool", description="Whether response came from a 'tool' or 'resource'"
    )


class McpResponse(BaseModel):
    """Unified response model for all MCP outputs - consistent structure for LLM parsing."""

    success: bool = Field(description="True if operation succeeded, False if error occurred")
    data: Any | None = Field(default=None, description="Response payload on success (dict, list, or structured data)")
    error: ErrorDetail | None = Field(default=None, description="Error details when success=false")
    meta: ResponseMeta | None = Field(default=None, description="Metadata about connection state and response source")

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2, exclude_none=True)


class Response:
    """Factory for creating standardized MCP responses.

    Usage:
        # Success
        return Response.ok({"tables": tables}, connected=True)

        # Error
        return Response.not_connected()
        return Response.timeout(30000)
        return Response.error(ErrorCode.VALIDATION_ERROR, "Invalid query")
    """

    @staticmethod
    def ok(
        data: Any,
        connected: bool = True,
        source: Literal["tool", "resource"] = "tool",
        summary: str | None = None,
    ) -> str:
        """Create a success response.

        Args:
            data: The response payload (dict, list, or Pydantic model)
            connected: Whether database is connected
            source: "tool" or "resource"
            summary: Optional brief summary for LLM

        Returns:
            JSON string with success=true
        """
        # Handle Pydantic models
        if hasattr(data, "model_dump"):
            data = data.model_dump()

        # Add summary to data if provided
        if summary and isinstance(data, dict):
            data = {"summary": summary, **data}

        return McpResponse(success=True, data=data, meta=ResponseMeta(connected=connected, source=source)).to_json()

    @staticmethod
    def formatted(
        content: str,
        format: Literal["markdown", "text", "mermaid"],
        connected: bool = True,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Create a wrapped response for formatted string payloads."""
        return Response.ok(
            {"format": format, "content": content},
            connected=connected,
            source=source,
        )

    @staticmethod
    def error(
        code: ErrorCode | str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
        connected: bool = False,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Create an error response.

        Args:
            code: Error code (use ErrorCode enum)
            message: Human-readable error message
            hint: Suggestion for how to fix the error
            details: Additional error context
            connected: Whether database is connected
            source: "tool" or "resource"

        Returns:
            JSON string with success=false
        """
        return McpResponse(
            success=False,
            error=ErrorDetail(
                code=code.value if isinstance(code, ErrorCode) else code,
                message=message,
                hint=hint,
                details=details,
            ),
            meta=ResponseMeta(connected=connected, source=source),
        ).to_json()

    # =========================================================================
    # Convenience shortcuts for common errors
    # =========================================================================

    @staticmethod
    def not_connected(
        message: str = "Not connected to database",
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for connection errors."""
        return Response.error(
            ErrorCode.NOT_CONNECTED,
            message,
            hint="Call connect() first with credentials, or pass 'url' parameter to this tool. "
            "Example: connect(host='localhost', database='mydb', user='postgres')",
            details={
                "next_action": "connect",
                "required_params": ["host", "database", "user"],
                "optional_params": ["password", "port", "url", "aws_secret_name"],
            },
            connected=False,
            source=source,
        )

    @staticmethod
    def timeout(
        timeout_ms: int,
        query: str | None = None,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for timeout errors."""
        details: dict[str, Any] = {
            "timeout_ms": timeout_ms,
            "recommended_timeout_ms": timeout_ms * 2,
        }
        if query:
            details["query_preview"] = query[:200] + "..." if len(query) > 200 else query
        return Response.error(
            ErrorCode.QUERY_TIMEOUT,
            f"Query timed out after {timeout_ms}ms",
            hint=f"Options: 1) Retry with timeout_ms={timeout_ms * 2}, "
            "2) Use analyze_query() to check for missing indexes, "
            "3) Add LIMIT clause, or 4) Use query_optimizer() for optimization suggestions",
            details=details,
            connected=True,
            source=source,
        )

    @staticmethod
    def validation(
        message: str,
        field: str | None = None,
        value: Any = None,
        allowed_values: list[str] | None = None,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for validation errors."""
        details: dict[str, Any] = {}
        hint_parts = ["Correct the input parameter"]

        if field:
            details["field"] = field
            hint_parts = [f"Fix the '{field}' parameter"]
        if value is not None:
            details["provided_value"] = str(value)[:100]
        if allowed_values:
            details["allowed_values"] = allowed_values
            hint_parts.append(f"Allowed values: {', '.join(allowed_values)}")

        return Response.error(
            ErrorCode.VALIDATION_ERROR,
            message,
            hint=". ".join(hint_parts),
            details=details if details else None,
            connected=True,
            source=source,
        )

    @staticmethod
    def not_found(
        resource: str,
        name: str,
        suggestions: list[str] | None = None,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for not found errors."""
        code = (
            ErrorCode.TABLE_NOT_FOUND
            if resource == "table"
            else (ErrorCode.SCHEMA_NOT_FOUND if resource == "schema" else ErrorCode.NOT_FOUND)
        )
        details: dict[str, Any] = {"resource": resource, "name": name}
        hint_parts = []

        if resource == "table":
            hint_parts.append("Verify table exists with get_schema()")
            hint_parts.append("Check if schema prefix is needed (e.g., 'public.tablename')")
        elif resource == "schema":
            hint_parts.append("List available schemas with get_schema(schema='all')")
        else:
            hint_parts.append(f"Verify {resource} name is correct")

        if suggestions:
            details["similar_names"] = suggestions
            hint_parts.append(f"Did you mean: {', '.join(suggestions[:3])}?")

        return Response.error(
            code,
            f"{resource.capitalize()} '{name}' not found",
            hint=" ".join(hint_parts),
            details=details,
            connected=True,
            source=source,
        )

    @staticmethod
    def extension_required(
        extension: str,
        feature: str,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for missing extension errors."""
        return Response.error(
            ErrorCode.EXTENSION_REQUIRED,
            f"Extension '{extension}' is required for {feature}",
            hint=f"Run: CREATE EXTENSION IF NOT EXISTS {extension};",
            details={"extension": extension},
            connected=True,
            source=source,
        )

    @staticmethod
    def internal(
        exception: Exception,
        context: str | None = None,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for internal/unexpected errors."""
        exc_type = type(exception).__name__
        exc_msg = str(exception)
        details: dict[str, Any] = {"exception_type": exc_type}

        # Build helpful hints based on exception type
        hint_parts = ["This is an unexpected error"]
        if "permission" in exc_msg.lower() or "denied" in exc_msg.lower():
            hint_parts = ["Check database user permissions", "Verify the user has necessary grants"]
            details["likely_cause"] = "insufficient_permissions"
        elif "syntax" in exc_msg.lower():
            hint_parts = ["Check SQL syntax", "Use analyze_query() to validate query"]
            details["likely_cause"] = "sql_syntax_error"
        elif "does not exist" in exc_msg.lower():
            hint_parts = ["Verify object name spelling", "Check if schema prefix is needed"]
            details["likely_cause"] = "object_not_found"
        elif "connection" in exc_msg.lower() or "connect" in exc_msg.lower():
            hint_parts = ["Database connection may be lost", "Try reconnecting with connect()"]
            details["likely_cause"] = "connection_issue"
        else:
            hint_parts.append("Retry the operation or try with different parameters")

        if context:
            details["context"] = context

        return Response.error(
            ErrorCode.INTERNAL_ERROR,
            exc_msg,
            hint=". ".join(hint_parts),
            details=details,
            connected=True,
            source=source,
        )

    @staticmethod
    def parse_error(
        message: str,
        query: str | None = None,
        source: Literal["tool", "resource"] = "tool",
    ) -> str:
        """Shortcut for SQL parse errors."""
        details = {}
        if query:
            details["query"] = query[:200] + "..." if len(query) > 200 else query
        return Response.error(
            ErrorCode.PARSE_ERROR,
            message,
            hint="Check SQL syntax and ensure query is valid",
            details=details if details else None,
            connected=True,
            source=source,
        )


# =============================================================================
# CONVENIENCE HELPER FUNCTIONS
# =============================================================================
# These are shorthand functions that delegate to Response methods.
# Prefer using Response.ok() and Response.error() directly in new code.


def error(
    code: ErrorCode | str,
    message: str,
    details: dict[str, Any] | None = None,
    hint: str | None = None,
) -> str:
    """Create a standardized error response."""
    return Response.error(
        code=code,
        message=message,
        hint=hint,
        details=details,
        connected=True,
        source="tool",
    )


def connection_error(message: str = "Not connected to database") -> str:
    """Shorthand for connection errors."""
    return Response.not_connected(message, source="tool")


def timeout_error(timeout_ms: int, query: str | None = None) -> str:
    """Shorthand for query timeout errors."""
    return Response.timeout(timeout_ms, query, source="tool")


def validation_error(
    message: str, field: str | None = None, value: Any = None, allowed_values: list[str] | None = None
) -> str:
    """Shorthand for validation errors."""
    return Response.validation(message, field, value, allowed_values, source="tool")


def not_found_error(resource: str, name: str, suggestions: list[str] | None = None) -> str:
    """Shorthand for not found errors."""
    return Response.not_found(resource, name, suggestions, source="tool")


def extension_required_error(extension: str, feature: str) -> str:
    """Shorthand for missing extension errors."""
    return Response.extension_required(extension, feature, source="tool")


def internal_error(exception: Exception, context: str | None = None) -> str:
    """Shorthand for internal/unexpected errors."""
    return Response.internal(exception, context, source="tool")


def parse_error(message: str, query: str | None = None) -> str:
    """Shorthand for SQL parse errors."""
    return Response.parse_error(message, query, source="tool")


def success(
    data: Any,
    next_steps: list[str] | None = None,
    related_tools: list[str] | None = None,
    summary: str | None = None,
) -> str:
    """Create a standardized success response.

    Args:
        data: The actual result data (dict, list, or Pydantic model)
        next_steps: Suggested next actions for the AI agent
        related_tools: Other tools that might be useful
        summary: Brief summary of what was returned

    Returns:
        JSON string with success=true wrapper
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump()

    if isinstance(data, dict):
        if next_steps:
            data = {**data, "next_steps": next_steps}
        if related_tools:
            data = {**data, "related_tools": related_tools}

    return Response.ok(data, connected=True, source="tool", summary=summary)


def success_with_issues(
    data: Any,
    issues: list[str],
    severity: str = "info",
    next_steps: list[str] | None = None,
) -> str:
    """Create a success response that includes issues/warnings.

    Args:
        data: The actual result data
        issues: List of issues/warnings found
        severity: Overall severity - 'info', 'warning', 'critical'
        next_steps: Suggested actions to resolve issues
    """
    if hasattr(data, "model_dump"):
        data = data.model_dump()

    enriched_data = {
        **(data if isinstance(data, dict) else {"value": data}),
        "issues": issues,
        "issue_count": len(issues),
        "severity": severity,
        "healthy": len(issues) == 0,
    }

    if next_steps:
        enriched_data["next_steps"] = next_steps

    return Response.ok(enriched_data, connected=True, source="tool")
