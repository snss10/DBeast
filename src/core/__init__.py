"""Core infrastructure for dbeast.

This module contains cross-cutting concerns like logging, configuration,
and custom exceptions.
"""

from core.config import Settings, get_settings
from core.exceptions import (
    DbConnectionError,
    DbeastError,
    DbTimeoutError,
    NotFoundError,
    QueryError,
    SecurityError,
    ValidationError,
)
from core.logging import LogLevel, get_logger, setup_logging

__all__ = [
    # Logging
    "get_logger",
    "setup_logging",
    "LogLevel",
    # Config
    "Settings",
    "get_settings",
    # Exceptions
    "DbeastError",
    "DbConnectionError",
    "QueryError",
    "ValidationError",
    "DbTimeoutError",
    "NotFoundError",
    "SecurityError",
]
