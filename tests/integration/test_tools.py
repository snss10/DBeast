"""Integration tests for MCP tools.

These tests require a running PostgreSQL database.
Set DATABASE_URL environment variable to run them.
"""

import os

import pytest

# Skip all tests in this module if DATABASE_URL is not set
pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL environment variable not set")


@pytest.fixture
def database_url():
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL")


@pytest.fixture
async def connected_context():
    """Create a connected ToolContext for testing."""
    from tools.context import ToolContext

    ctx = ToolContext()
    await ctx.db_pool.connect(url=os.getenv("DATABASE_URL"))
    ctx.init_components()

    yield ctx

    # Cleanup
    await ctx.db_pool.disconnect()


class TestConnectionTools:
    """Test connection-related tools."""

    @pytest.mark.asyncio
    async def test_health_check_connected(self, connected_context):
        """Test health_check when connected."""
        health = await connected_context.db_pool.health_check()

        assert health["healthy"] is True
        assert health["status"] == "connected"

    @pytest.mark.asyncio
    async def test_ensure_connected_already_connected(self, connected_context):
        """Test ensure_connected when already connected."""
        result = await connected_context.ensure_connected()

        assert result is None  # None means connected


class TestQueryTools:
    """Test query-related tools."""

    @pytest.mark.asyncio
    async def test_query_executor_read(self, connected_context):
        """Test QueryExecutor execute_read."""
        result = await connected_context.query_executor.execute_read("SELECT 1 as value", limit=10)

        assert result.success is True
        assert len(result.rows) == 1
        assert result.rows[0]["value"] == 1

    @pytest.mark.asyncio
    async def test_query_analyzer_parse(self, connected_context):
        """Test QueryAnalyzer analyze."""
        analysis = connected_context.query_analyzer.analyze("SELECT id, name FROM users WHERE status = 'active'")

        assert analysis.valid is True
        assert analysis.query_type == "SELECT"
        assert "users" in analysis.tables

    @pytest.mark.asyncio
    async def test_query_executor_rejects_write(self, connected_context):
        """Test that write queries are rejected."""
        with pytest.raises(ValueError, match="write"):
            await connected_context.query_executor.execute_read("DELETE FROM users WHERE id = 1")


class TestSchemaDiscovery:
    """Test schema discovery functionality."""

    @pytest.mark.asyncio
    async def test_get_schemas(self, connected_context):
        """Test listing schemas."""
        schemas = await connected_context.schema_discovery.get_schemas()

        # Should have at least public schema
        schema_names = [s["schema_name"] for s in schemas]
        assert "public" in schema_names

    @pytest.mark.asyncio
    async def test_get_tables(self, connected_context):
        """Test listing tables."""
        tables = await connected_context.schema_discovery.get_tables("public")

        # Should return a list (may be empty)
        assert isinstance(tables, list)


class TestImpactAnalyzer:
    """Test impact analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_delete_without_where(self, connected_context):
        """Test impact analysis for DELETE without WHERE."""
        # This should return warnings without executing
        analysis = connected_context.query_analyzer.analyze("DELETE FROM users")

        assert analysis.valid is True
        assert any("CRITICAL" in w for w in analysis.warnings)

    @pytest.mark.asyncio
    async def test_analyze_update_without_where(self, connected_context):
        """Test impact analysis for UPDATE without WHERE."""
        analysis = connected_context.query_analyzer.analyze("UPDATE users SET status = 'inactive'")

        assert analysis.valid is True
        assert any("CRITICAL" in w for w in analysis.warnings)
