"""Structured logging infrastructure for dbeast.

Provides JSON-formatted logging suitable for production environments
with support for log aggregation systems like ELK, CloudWatch, etc.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from typing import Any


class LogLevel(StrEnum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def __init__(self, include_timestamp: bool = True, include_extra: bool = True):
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_extra = include_extra
        self._skip_keys = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "message",
            "taskName",
        }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_obj: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if self.include_timestamp:
            log_obj["timestamp"] = datetime.now(UTC).isoformat()

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from record
        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in self._skip_keys and not key.startswith("_"):
                    try:
                        json.dumps(value)  # Check if serializable
                        log_obj[key] = value
                    except (TypeError, ValueError):
                        log_obj[key] = str(value)

        return json.dumps(log_obj, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with colors for development."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors."""
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        timestamp = datetime.now().strftime("%H:%M:%S")

        msg = f"{color}[{timestamp}] {record.levelname:8}{reset} "
        msg += f"{record.module}:{record.funcName}:{record.lineno} - "
        msg += record.getMessage()

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return msg


def setup_logging(
    level: str | None = None,
    json_format: bool | None = None,
    log_file: str | None = None,
) -> logging.Logger:
    """Set up logging for dbeast.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to DBEAST_LOG_LEVEL env var or INFO.
        json_format: Whether to use JSON format. Defaults to DBEAST_LOG_JSON env var
                    or True in production (no TTY), False in development (TTY).
        log_file: Optional file path to write logs to.

    Returns:
        Configured root logger for dbeast
    """
    # Determine log level
    if level is None:
        level = os.getenv("DBEAST_LOG_LEVEL", "INFO").upper()

    # Determine format
    if json_format is None:
        env_json = os.getenv("DBEAST_LOG_JSON", "").lower()
        if env_json in ("true", "1", "yes"):
            json_format = True
        elif env_json in ("false", "0", "no"):
            json_format = False
        else:
            # Auto-detect: JSON for production (no TTY), console for development
            json_format = not sys.stderr.isatty()

    # Get or create logger
    logger = logging.getLogger("dbeast")
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Choose formatter
    formatter: logging.Formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = ConsoleFormatter()

    # Add stderr handler
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())  # Always JSON for files
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


@lru_cache(maxsize=32)
def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance for the specified module.

    Args:
        name: Logger name (usually __name__). If None, returns root dbeast logger.

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing query", extra={"query_id": "abc123"})
    """
    if name is None:
        return logging.getLogger("dbeast")

    # Create child logger under dbeast namespace
    if name.startswith("dbeast."):
        return logging.getLogger(name)
    return logging.getLogger(f"dbeast.{name}")


# Initialize default logging on module import
_default_logger = setup_logging()
