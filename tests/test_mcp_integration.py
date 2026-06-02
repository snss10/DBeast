"""Integration tests for MCP protocol compliance.

Tests that verify:
1. Tool registration and discoverability
2. Response format consistency
3. Error response format compliance
4. Resource return formats
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestToolRegistration:
    """Test that tools are properly registered with MCP."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock FastMCP that tracks registered tools."""
        tools = {}
        resources = {}

        def tool_decorator():
            def decorator(func):
                tools[func.__name__] = {
                    "name": func.__name__,
                    "description": func.__doc__,
                    "function": func,
                }
                return func

            return decorator

        def resource_decorator(uri):
            def decorator(func):
                resources[uri] = {
                    "uri": uri,
                    "description": func.__doc__,
                    "function": func,
                }
                return func

            return decorator

        mcp = MagicMock()
        mcp.tool = tool_decorator
        mcp.resource = resource_decorator
        mcp._registered_tools = tools
        mcp._registered_resources = resources
        return mcp

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock tool context."""
        ctx = MagicMock()
        ctx.db_pool = MagicMock()
        ctx.db_pool.is_connected = False
        ctx.auto_connected = False
        ctx.auto_connect_error = None
        ctx.ensure_connected = AsyncMock(return_value=None)
        return ctx

    def test_connection_tools_registered(self, mock_mcp, mock_ctx):
        """Test connection tools are registered with proper names."""
        from tools.connection import register_connection_tools

        register_connection_tools(mock_mcp, mock_ctx)

        assert "connect" in mock_mcp._registered_tools
        assert "disconnect" in mock_mcp._registered_tools
        assert "health_check" in mock_mcp._registered_tools

    def test_schema_tools_registered(self, mock_mcp, mock_ctx):
        """Test schema tools are registered."""
        from tools.schema import register_schema_tools

        register_schema_tools(mock_mcp, mock_ctx)

        assert "get_schema" in mock_mcp._registered_tools

    def test_query_tools_registered(self, mock_mcp, mock_ctx):
        """Test query tools are registered."""
        from tools.query import register_query_tools

        register_query_tools(mock_mcp, mock_ctx)

        assert "execute_query" in mock_mcp._registered_tools
        assert "analyze_query" in mock_mcp._registered_tools
        assert "analyze_impact" in mock_mcp._registered_tools
        assert "query_optimizer" in mock_mcp._registered_tools

    def test_health_tools_registered(self, mock_mcp, mock_ctx):
        """Test health tools are registered."""
        from tools.health import register_health_tools

        register_health_tools(mock_mcp, mock_ctx)

        assert "database_health" in mock_mcp._registered_tools

    def test_maintenance_tools_registered(self, mock_mcp, mock_ctx):
        """Test maintenance tools are registered."""
        from tools.maintenance import register_maintenance_tools

        register_maintenance_tools(mock_mcp, mock_ctx)

        assert "maintenance_analysis" in mock_mcp._registered_tools

    def test_tool_docstrings_present(self, mock_mcp, mock_ctx):
        """Test all tools have docstrings for LLM discoverability."""
        from tools.connection import register_connection_tools
        from tools.query import register_query_tools
        from tools.schema import register_schema_tools

        register_connection_tools(mock_mcp, mock_ctx)
        register_schema_tools(mock_mcp, mock_ctx)
        register_query_tools(mock_mcp, mock_ctx)

        for name, tool in mock_mcp._registered_tools.items():
            assert tool["description"] is not None, f"Tool {name} missing docstring"
            assert len(tool["description"]) > 20, f"Tool {name} has too short docstring"


class TestResourceFormats:
    """Test that resources return proper formats."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock FastMCP for resources."""
        resources = {}

        def resource_decorator(uri):
            def decorator(func):
                resources[uri] = func
                return func

            return decorator

        mcp = MagicMock()
        mcp.resource = resource_decorator
        mcp._resources = resources
        return mcp

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock tool context."""
        ctx = MagicMock()
        ctx.db_pool = MagicMock()
        ctx.db_pool.is_connected = False
        ctx.db_pool.config = None
        ctx.auto_connected = False
        ctx.auto_connect_error = None
        return ctx

    def test_config_resource_returns_json(self, mock_mcp, mock_ctx):
        """Test config resource returns valid JSON (not Response wrapper)."""
        from resources.config import register_config_resources

        register_config_resources(mock_mcp, mock_ctx)

        config_func = mock_mcp._resources["db://config"]
        result = config_func()

        # Should be valid JSON
        parsed = json.loads(result)

        # Should NOT be wrapped in Response envelope
        assert "status" not in parsed, "Resources should return raw JSON, not Response wrapper"

        # Should have expected structure
        assert "pool" in parsed
        assert "query" in parsed

    @pytest.mark.asyncio
    async def test_connection_status_resource_returns_json(self, mock_mcp, mock_ctx):
        """Test connection status resource returns valid JSON."""
        from resources.connection import register_connection_resources

        register_connection_resources(mock_mcp, mock_ctx)

        status_func = mock_mcp._resources["db://connection/status"]
        result = await status_func()

        # Should be valid JSON
        parsed = json.loads(result)

        # Should NOT be wrapped in Response envelope
        assert "status" not in parsed or parsed.get("status") != "success", (
            "Resources should return raw JSON, not Response wrapper"
        )

        # Should have connection info
        assert "connected" in parsed


class TestErrorRecoveryHints:
    """Test that tool docstrings contain error recovery hints."""

    def test_connect_has_error_hints(self):
        """Test connect tool has error recovery hints in docstring."""
        from unittest.mock import MagicMock

        from tools.connection import register_connection_tools

        mcp = MagicMock()
        tools = {}

        def tool_decorator():
            def decorator(func):
                tools[func.__name__] = func
                return func

            return decorator

        mcp.tool = tool_decorator

        ctx = MagicMock()
        register_connection_tools(mcp, ctx)

        assert "connect" in tools
        docstring = tools["connect"].__doc__
        assert "ERROR RECOVERY" in docstring, "connect tool should have ERROR RECOVERY section"

    def test_execute_query_has_error_hints(self):
        """Test execute_query tool has error recovery hints."""
        from unittest.mock import MagicMock

        from tools.query import register_query_tools

        mcp = MagicMock()
        tools = {}

        def tool_decorator():
            def decorator(func):
                tools[func.__name__] = func
                return func

            return decorator

        mcp.tool = tool_decorator

        ctx = MagicMock()
        register_query_tools(mcp, ctx)

        assert "execute_query" in tools
        docstring = tools["execute_query"].__doc__
        assert "ERROR RECOVERY" in docstring, "execute_query tool should have ERROR RECOVERY section"
