"""Caching utilities for expensive database operations.

Provides TTL-based caching for schema discovery and other database metadata
that doesn't change frequently. Reduces database load and improves response time.

Usage:
    from utils.cache import schema_cache, get_cached_schema, set_cached_schema

    # Check cache first
    cached = get_cached_schema("public")
    if cached:
        return cached

    # Fetch from DB and cache
    schema_data = await fetch_schema_from_db("public")
    set_cached_schema("public", schema_data)
"""

from typing import Any

from cachetools import TTLCache

# Lazy-initialized caches to avoid locking TTL at import time
_schema_cache: TTLCache[str, dict[str, Any]] | None = None
_health_cache: TTLCache[str, dict[str, Any]] | None = None
_last_schema_ttl: int = -1
_last_health_ttl: int = 10


def _get_cache_ttl() -> int:
    """Get cache TTL from settings."""
    try:
        from core.config import get_settings

        return get_settings().schema_cache_ttl
    except Exception:
        return 60  # Default 60 seconds


def _get_schema_cache() -> TTLCache[str, dict[str, Any]]:
    """Get or create the schema cache with current TTL settings.

    If TTL has changed in settings, the cache is recreated with the new TTL.
    """
    global _schema_cache, _last_schema_ttl

    current_ttl = _get_cache_ttl()

    # Create cache if it doesn't exist or if TTL has changed
    if _schema_cache is None or _last_schema_ttl != current_ttl:
        # Use max(1, ttl) to avoid zero TTL which would cause issues
        effective_ttl = max(1, current_ttl) if current_ttl > 0 else 1
        _schema_cache = TTLCache(maxsize=100, ttl=effective_ttl)
        _last_schema_ttl = current_ttl

    return _schema_cache


def _get_health_cache() -> TTLCache[str, dict[str, Any]]:
    """Get or create the health cache (fixed 10 second TTL)."""
    global _health_cache

    if _health_cache is None:
        _health_cache = TTLCache(maxsize=10, ttl=10)

    return _health_cache


def _get_cache_key(schema_name: str | None) -> str:
    """Generate cache key for schema data."""
    return f"schema:{schema_name or '__all__'}"


def get_cached_schema(schema_name: str | None = None) -> dict[str, Any] | None:
    """Get cached schema data if available and not expired.

    Args:
        schema_name: Schema name or None for all schemas

    Returns:
        Cached schema data dict or None if not cached/expired
    """
    if _get_cache_ttl() <= 0:
        return None  # Caching disabled

    key = _get_cache_key(schema_name)
    return _get_schema_cache().get(key)


def set_cached_schema(schema_name: str | None, data: dict[str, Any]) -> None:
    """Cache schema data for future requests.

    Args:
        schema_name: Schema name or None for all schemas
        data: Schema data to cache
    """
    if _get_cache_ttl() <= 0:
        return  # Caching disabled

    key = _get_cache_key(schema_name)
    _get_schema_cache()[key] = data


def invalidate_schema_cache(schema_name: str | None = None) -> None:
    """Invalidate cached schema data.

    Args:
        schema_name: Schema name to invalidate, or None to clear all
    """
    cache = _get_schema_cache()
    if schema_name is None:
        cache.clear()
    else:
        key = _get_cache_key(schema_name)
        cache.pop(key, None)
        # Also invalidate the "all schemas" cache
        cache.pop(_get_cache_key(None), None)


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics for monitoring.

    Returns:
        Dict with cache stats
    """
    ttl = _get_cache_ttl()
    cache = _get_schema_cache()
    return {
        "size": len(cache),
        "maxsize": cache.maxsize,
        "ttl_seconds": ttl,
        "enabled": ttl > 0,
    }


def get_cached_health() -> dict[str, Any] | None:
    """Get cached health check data."""
    return _get_health_cache().get("health")


def set_cached_health(data: dict[str, Any]) -> None:
    """Cache health check data."""
    _get_health_cache()["health"] = data


def invalidate_health_cache() -> None:
    """Invalidate health cache."""
    _get_health_cache().pop("health", None)


def reset_caches() -> None:
    """Reset all caches. Useful for testing or when settings change."""
    global _schema_cache, _health_cache, _last_schema_ttl
    _schema_cache = None
    _health_cache = None
    _last_schema_ttl = -1
