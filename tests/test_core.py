"""Consolidated tests for core module (config, exceptions, logging)."""

import json
import logging
import os
from unittest.mock import patch

import pytest

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
from core.logging import JSONFormatter, get_logger, setup_logging


class TestSettings:
    """Essential configuration tests."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.db_host == "localhost"
            assert settings.db_port == 5432
            assert settings.pool_min_size == 1

    def test_env_override(self):
        """Test environment variable overrides."""
        env = {"DB_HOST": "testhost", "DB_PORT": "5433", "DBEAST_LOG_LEVEL": "DEBUG"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.db_host == "testhost"
            assert settings.db_port == 5433

    def test_database_url(self):
        """Test DATABASE_URL configuration."""
        env = {"DATABASE_URL": "postgresql://user:pass@host:5432/db"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.database_url == "postgresql://user:pass@host:5432/db"
            assert settings.has_database_credentials() is True

    def test_get_settings_cached(self):
        """Test settings caching."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestExceptions:
    """Essential exception tests."""

    def test_dbeast_error_basics(self):
        """Test base exception."""
        error = DbeastError("Test", code="TEST", details={"key": "val"})
        assert error.message == "Test"
        assert error.code == "TEST"
        result = error.to_dict()
        assert result["error"] is True

    def test_db_connection_error(self):
        """Test connection error with details."""
        error = DbConnectionError("Failed", host="localhost", port=5432)
        assert error.code == "CONNECTION_ERROR"
        assert error.details["host"] == "localhost"

    def test_query_error_truncates_long_query(self):
        """Test long query truncation."""
        long_query = "SELECT " + "x" * 600
        error = QueryError("Error", query=long_query)
        assert len(error.details["query"]) <= 503

    def test_exception_inheritance(self):
        """Test all exceptions inherit from DbeastError."""
        for exc_class in [DbConnectionError, QueryError, ValidationError, DbTimeoutError, NotFoundError, SecurityError]:
            assert issubclass(exc_class, DbeastError)

    def test_can_catch_as_base(self):
        """Test catching as base class."""
        with pytest.raises(DbeastError):
            raise DbConnectionError("Test")


class TestLogging:
    """Essential logging tests."""

    def test_json_formatter(self):
        """Test JSON log formatting."""
        formatter = JSONFormatter()
        record = logging.LogRecord("test", logging.INFO, "test.py", 10, "Message", (), None)
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "Message"

    def test_setup_logging(self):
        """Test logging setup."""
        logger = setup_logging(level="DEBUG")
        assert logger.name == "dbeast"
        assert logger.level == logging.DEBUG

    def test_get_child_logger(self):
        """Test child logger naming."""
        logger = get_logger("module")
        assert logger.name == "dbeast.module"
