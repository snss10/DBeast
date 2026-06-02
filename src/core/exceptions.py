"""Custom exceptions for dbeast.

Provides a hierarchy of exceptions for different error scenarios,
enabling precise error handling and meaningful error messages.
"""

from typing import Any


class DbeastError(Exception):
    """Base exception for all dbeast errors.

    Attributes:
        message: Human-readable error message
        code: Machine-readable error code
        details: Additional error context
    """

    code: str = "DBEAST_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        if code:
            self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        result = {
            "error": True,
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class DbConnectionError(DbeastError, ConnectionError):
    """Raised when database connection fails.

    Named DbConnectionError to avoid shadowing Python's built-in ConnectionError.
    Also subclasses ConnectionError so callers can catch the standard Python
    connection exception type when they do not need DBeast-specific details.
    """

    code = "CONNECTION_ERROR"

    def __init__(
        self,
        message: str = "Failed to connect to database",
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        original_error: Exception | None = None,
    ):
        details: dict[str, Any] = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        if database:
            details["database"] = database
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, details=details)
        self.original_error = original_error


class QueryError(DbeastError):
    """Raised when query execution fails."""

    code = "QUERY_ERROR"

    def __init__(
        self,
        message: str = "Query execution failed",
        query: str | None = None,
        original_error: Exception | None = None,
    ):
        details = {}
        if query:
            # Truncate long queries
            details["query"] = query[:500] + "..." if len(query) > 500 else query
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(message, details=details)
        self.query = query
        self.original_error = original_error


class ValidationError(DbeastError):
    """Raised when input validation fails."""

    code = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str = "Validation failed",
        field: str | None = None,
        value: Any | None = None,
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]
        super().__init__(message, details=details)
        self.field = field
        self.value = value


class DbTimeoutError(DbeastError):
    """Raised when operation times out.

    Named DbTimeoutError to avoid shadowing Python's built-in TimeoutError.
    """

    code = "TIMEOUT_ERROR"

    def __init__(
        self,
        message: str = "Operation timed out",
        timeout_ms: int | None = None,
        operation: str | None = None,
    ):
        details: dict[str, Any] = {}
        if timeout_ms:
            details["timeout_ms"] = timeout_ms
        if operation:
            details["operation"] = operation
        super().__init__(message, details=details)
        self.timeout_ms = timeout_ms
        self.operation = operation


class NotFoundError(DbeastError):
    """Raised when a resource is not found."""

    code = "NOT_FOUND"

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: str | None = None,
        resource_name: str | None = None,
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_name:
            details["resource_name"] = resource_name
        super().__init__(message, details=details)
        self.resource_type = resource_type
        self.resource_name = resource_name


class SecurityError(DbeastError):
    """Raised when a security check fails."""

    code = "SECURITY_ERROR"

    def __init__(
        self,
        message: str = "Security check failed",
        reason: str | None = None,
    ):
        details = {}
        if reason:
            details["reason"] = reason
        super().__init__(message, details=details)
        self.reason = reason
