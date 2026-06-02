"""Tests for MCP resources."""

import json
from unittest.mock import MagicMock

import pytest

from resources.config import register_config_resources
from resources.connection import register_connection_resources


class MockFastMCP:
    """Mock FastMCP for testing resource registration."""

    def __init__(self):
        self._resources = {}

    def resource(self, uri: str):
        def decorator(func):
            self._resources[uri] = func
            return func

        return decorator

    def get_resource(self, uri: str):
        return self._resources.get(uri)


class TestConnectionResources:
    """Tests for connection resources."""

    @pytest.fixture
    def mock_mcp(self):
        return MockFastMCP()

    @pytest.fixture
    def mock_ctx(self):
        ctx = MagicMock()
        ctx.db_pool = MagicMock()
        ctx.db_pool.is_connected = True
        ctx.db_pool.config = MagicMock()
        ctx.db_pool.config.host = "localhost"
        ctx.db_pool.config.port = 5432
        ctx.db_pool.config.database = "testdb"
        ctx.db_pool.config.user = "testuser"
        ctx.db_pool.pg_version = 15
        ctx.db_pool.extensions = {"pg_stat_statements": True}
        ctx.db_pool.get_pool = MagicMock()
        pool = MagicMock()
        pool.get_size = MagicMock(return_value=5)
        pool.get_idle_size = MagicMock(return_value=3)
        pool.get_min_size = MagicMock(return_value=1)
        pool.get_max_size = MagicMock(return_value=10)
        ctx.db_pool.get_pool.return_value = pool
        ctx.auto_connected = True
        ctx.auto_connect_error = None
        return ctx

    def test_resources_registered(self, mock_mcp, mock_ctx):
        """Connection resources should be registered."""
        register_connection_resources(mock_mcp, mock_ctx)

        # Only connection/status resource now (pool and extensions consolidated)
        assert "db://connection/status" in mock_mcp._resources

    @pytest.mark.asyncio
    async def test_connection_status_connected(self, mock_mcp, mock_ctx):
        """connection_status should return connected info with pool stats."""
        register_connection_resources(mock_mcp, mock_ctx)
        status = mock_mcp.get_resource("db://connection/status")

        result = await status()
        data = json.loads(result)

        # Resources return raw JSON (not Response wrapper)
        assert data["connected"] is True
        assert data["host"] == "localhost"
        assert data["database"] == "testdb"
        # Pool stats now included in connection/status
        assert data["pool_size"] == 5
        assert data["pool_available"] == 3
        assert "extensions" in data

    @pytest.mark.asyncio
    async def test_connection_status_not_connected(self, mock_mcp, mock_ctx):
        """connection_status should return not connected info."""
        mock_ctx.db_pool.is_connected = False
        register_connection_resources(mock_mcp, mock_ctx)
        status = mock_mcp.get_resource("db://connection/status")

        result = await status()
        data = json.loads(result)

        # Resources return raw JSON (not Response wrapper)
        assert data["connected"] is False
        assert "message" in data


class TestConfigResources:
    """Tests for config resources."""

    @pytest.fixture
    def mock_mcp(self):
        return MockFastMCP()

    @pytest.fixture
    def mock_ctx(self):
        return MagicMock()

    def test_resources_registered(self, mock_mcp, mock_ctx):
        """Config resources should be registered."""
        register_config_resources(mock_mcp, mock_ctx)

        assert "db://config" in mock_mcp._resources

    def test_server_config(self, mock_mcp, mock_ctx):
        """server_config should return configuration."""
        register_config_resources(mock_mcp, mock_ctx)
        config = mock_mcp.get_resource("db://config")

        result = config()
        data = json.loads(result)

        # Resources return raw JSON (not Response wrapper)
        assert "pool" in data
        assert "query" in data
        assert "retry" in data
        assert "ssl" in data
        assert "credentials_configured" in data
