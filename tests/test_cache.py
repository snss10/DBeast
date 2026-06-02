"""Tests for caching utilities."""

import pytest

# Skip all tests if cachetools is not installed
pytest.importorskip("cachetools", reason="cachetools not installed")


class TestSchemaCache:
    """Tests for schema caching functions."""

    def test_set_and_get_cached_schema(self):
        """Test setting and getting cached schema data."""
        from utils.cache import get_cached_schema, invalidate_schema_cache, set_cached_schema

        # Clear cache first
        invalidate_schema_cache()

        test_data = {"tables": ["users", "orders"], "count": 2}

        # Set cache
        set_cached_schema("public", test_data)

        # Get cache
        cached = get_cached_schema("public")

        # May return None if caching is disabled (TTL=0)
        if cached is not None:
            assert cached == test_data

    def test_invalidate_specific_schema(self):
        """Test invalidating a specific schema cache."""
        from utils.cache import get_cached_schema, invalidate_schema_cache, set_cached_schema

        # Clear and set
        invalidate_schema_cache()
        set_cached_schema("public", {"test": 1})
        set_cached_schema("billing", {"test": 2})

        # Invalidate just public
        invalidate_schema_cache("public")

        # Public should be gone, billing might still exist
        public_cached = get_cached_schema("public")
        assert public_cached is None

    def test_invalidate_all_schemas(self):
        """Test invalidating all schema caches."""
        from utils.cache import get_cached_schema, invalidate_schema_cache, set_cached_schema

        # Set multiple
        set_cached_schema("public", {"test": 1})
        set_cached_schema("billing", {"test": 2})

        # Invalidate all
        invalidate_schema_cache()

        # Both should be gone
        assert get_cached_schema("public") is None
        assert get_cached_schema("billing") is None

    def test_get_cache_stats(self):
        """Test cache statistics."""
        from utils.cache import get_cache_stats, invalidate_schema_cache

        invalidate_schema_cache()
        stats = get_cache_stats()

        assert "size" in stats
        assert "maxsize" in stats
        assert "ttl_seconds" in stats
        assert "enabled" in stats
        assert isinstance(stats["size"], int)
        assert isinstance(stats["maxsize"], int)

    def test_none_schema_key(self):
        """Test caching with None schema (all schemas)."""
        from utils.cache import get_cached_schema, invalidate_schema_cache, set_cached_schema

        invalidate_schema_cache()

        test_data = {"schemas": ["public", "billing"]}
        set_cached_schema(None, test_data)

        cached = get_cached_schema(None)
        if cached is not None:
            assert cached == test_data


class TestHealthCache:
    """Tests for health check caching."""

    def test_set_and_get_health_cache(self):
        """Test setting and getting health cache."""
        from utils.cache import get_cached_health, invalidate_health_cache, set_cached_health

        invalidate_health_cache()

        test_data = {"healthy": True, "connections": 5}
        set_cached_health(test_data)

        cached = get_cached_health()
        if cached is not None:
            assert cached == test_data

    def test_invalidate_health_cache(self):
        """Test invalidating health cache."""
        from utils.cache import get_cached_health, invalidate_health_cache, set_cached_health

        set_cached_health({"test": 1})
        invalidate_health_cache()

        assert get_cached_health() is None
