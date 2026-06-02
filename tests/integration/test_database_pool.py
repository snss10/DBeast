"""Integration tests for DatabasePool.

These tests require a running PostgreSQL database.
Set DATABASE_URL environment variable to run them.

Example:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/testdb pytest tests/integration/
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
async def pool():
    """Create a fresh database pool for each test."""
    from db import DatabasePool

    pool = DatabasePool()
    yield pool

    # Cleanup
    if pool.is_connected:
        await pool.disconnect()


class TestDatabasePoolConnection:
    """Test database connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_with_url(self, pool, database_url):
        """Test connection with DATABASE_URL."""
        result = await pool.connect(url=database_url)

        assert result["status"] == "connected"
        assert pool.is_connected
        assert pool.pg_version is not None

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, pool, database_url):
        """Test connect and disconnect cycle."""
        await pool.connect(url=database_url)
        assert pool.is_connected

        result = await pool.disconnect()
        assert result["status"] == "disconnected"
        assert not pool.is_connected

    @pytest.mark.asyncio
    async def test_health_check_connected(self, pool, database_url):
        """Test health check when connected."""
        await pool.connect(url=database_url)

        health = await pool.health_check()

        assert health["healthy"] is True
        assert health["status"] == "connected"
        assert "pool_size" in health
        assert "pool_free" in health

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, pool):
        """Test health check when not connected."""
        health = await pool.health_check()

        assert health["healthy"] is False
        assert health["status"] == "not_connected"

    @pytest.mark.asyncio
    async def test_reconnect(self, pool, database_url):
        """Test reconnecting after disconnect."""
        await pool.connect(url=database_url)
        await pool.disconnect()

        result = await pool.connect(url=database_url)
        assert result["status"] == "connected"


class TestDatabasePoolQueries:
    """Test query execution functionality."""

    @pytest.mark.asyncio
    async def test_fetch(self, pool, database_url):
        """Test fetching rows."""
        await pool.connect(url=database_url)

        rows = await pool.fetch("SELECT 1 as value, 'test' as name")

        assert len(rows) == 1
        assert rows[0]["value"] == 1
        assert rows[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_fetchrow(self, pool, database_url):
        """Test fetching single row."""
        await pool.connect(url=database_url)

        row = await pool.fetchrow("SELECT 42 as answer")

        assert row is not None
        assert row["answer"] == 42

    @pytest.mark.asyncio
    async def test_fetchval(self, pool, database_url):
        """Test fetching single value."""
        await pool.connect(url=database_url)

        value = await pool.fetchval("SELECT 'hello'")

        assert value == "hello"

    @pytest.mark.asyncio
    async def test_fetch_with_timeout(self, pool, database_url):
        """Test query with timeout."""
        await pool.connect(url=database_url)

        # Should complete within timeout
        rows = await pool.fetch("SELECT 1", timeout=5.0)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_fetch_not_connected(self, pool):
        """Test query when not connected raises error."""
        with pytest.raises(ConnectionError):
            await pool.fetch("SELECT 1")


class TestDatabasePoolRetry:
    """Test connection retry functionality."""

    @pytest.mark.asyncio
    async def test_connect_with_retry_success(self, pool, database_url):
        """Test successful connection with retry."""
        result = await pool.connect_with_retry(url=database_url)

        assert result["status"] == "connected"
        assert pool.is_connected

    @pytest.mark.asyncio
    async def test_connect_with_retry_invalid_url(self, pool):
        """Test retry with invalid URL eventually fails."""
        with pytest.raises(ConnectionError):
            await pool.connect_with_retry(url="postgresql://invalid:invalid@nonexistent:9999/nodb")


class TestDatabasePoolExtensions:
    """Test extension detection functionality."""

    @pytest.mark.asyncio
    async def test_extension_detection(self, pool, database_url):
        """Test that extensions are detected on connect."""
        await pool.connect(url=database_url)

        # Extensions dict should be populated (may be empty if none installed)
        assert isinstance(pool.extensions, dict)

    @pytest.mark.asyncio
    async def test_has_extension(self, pool, database_url):
        """Test has_extension method."""
        await pool.connect(url=database_url)

        # Should return False for non-existent extension
        assert pool.has_extension("nonexistent_extension") is False
