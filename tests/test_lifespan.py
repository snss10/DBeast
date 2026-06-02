"""Tests for MCP server lifespan management."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestLifespanBehavior:
    """Tests for lifespan behavior."""

    @pytest.mark.asyncio
    async def test_lifespan_calls_auto_connect(self):
        """Test that lifespan attempts auto-connect on startup (background task)."""
        import asyncio

        from lifespan import create_lifespan

        mock_ctx = MagicMock()
        mock_ctx.db_pool = MagicMock()
        mock_ctx.db_pool.is_connected = False
        mock_ctx.db_pool.config = None
        mock_ctx.db_pool.disconnect = AsyncMock()
        mock_ctx.try_auto_connect = AsyncMock()
        mock_ctx.has_env_credentials = MagicMock(return_value=True)
        mock_ctx.auto_connect_error = None

        mock_server = MagicMock()
        mock_server.name = "test_server"

        lifespan = create_lifespan(mock_ctx)

        async with lifespan(mock_server):
            # Give background task time to start and run
            await asyncio.sleep(0.1)

        # Should have tried to auto-connect in background
        mock_ctx.try_auto_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_disconnects_on_shutdown(self):
        """Test that lifespan disconnects on shutdown when connected."""
        from lifespan import create_lifespan

        mock_ctx = MagicMock()
        mock_ctx.db_pool = MagicMock()
        mock_ctx.db_pool.is_connected = True
        mock_ctx.db_pool.disconnect = AsyncMock()
        mock_ctx.try_auto_connect = AsyncMock()
        mock_ctx.has_env_credentials = MagicMock(return_value=False)

        mock_server = MagicMock()
        mock_server.name = "test_server"

        lifespan = create_lifespan(mock_ctx)

        async with lifespan(mock_server):
            # Simulate connected state after startup
            mock_ctx.db_pool.is_connected = True

        # Should have disconnected
        mock_ctx.db_pool.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_handles_auto_connect_failure(self):
        """Test that lifespan handles auto-connect failure gracefully."""
        import asyncio

        from lifespan import create_lifespan

        mock_ctx = MagicMock()
        mock_ctx.db_pool = MagicMock()
        mock_ctx.db_pool.is_connected = False
        mock_ctx.db_pool.config = None
        mock_ctx.db_pool.disconnect = AsyncMock()
        mock_ctx.try_auto_connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_ctx.has_env_credentials = MagicMock(return_value=True)
        mock_ctx.auto_connect_error = None

        mock_server = MagicMock()
        mock_server.name = "test_server"

        lifespan = create_lifespan(mock_ctx)

        # Should not raise - failure is logged but not propagated
        async with lifespan(mock_server):
            await asyncio.sleep(0.1)  # Let background task run

    @pytest.mark.asyncio
    async def test_lifespan_skips_disconnect_when_not_connected(self):
        """Test that lifespan skips disconnect when not connected."""
        from lifespan import create_lifespan

        mock_ctx = MagicMock()
        mock_ctx.db_pool = MagicMock()
        mock_ctx.db_pool.is_connected = False
        mock_ctx.db_pool.disconnect = AsyncMock()
        mock_ctx.try_auto_connect = AsyncMock()
        mock_ctx.has_env_credentials = MagicMock(return_value=False)

        mock_server = MagicMock()
        mock_server.name = "test_server"

        lifespan = create_lifespan(mock_ctx)

        async with lifespan(mock_server):
            pass

        # Should NOT have disconnected since not connected
        mock_ctx.db_pool.disconnect.assert_not_called()
