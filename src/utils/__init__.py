"""Utility functions for dbeast."""

from utils.aws import AWSDbCredentials, get_db_credentials_from_secret, get_secret_value
from utils.constants import (
    AWSDefaults,
    HealthThresholds,
    MaintenanceThresholds,
    PoolDefaults,
    QueryAnalysisThresholds,
    QueryLimits,
    RiskScoring,
    TimeoutDefaults,
)
from utils.formatter import MarkdownFormatter
from utils.tool_helpers import (
    aggregate_issues,
    analyze_all_schemas,
    build_all_schemas_result,
    get_user_schemas,
)

# Cache utilities - optional dependency on cachetools
try:
    from utils.cache import (
        get_cache_stats,
        get_cached_health,
        get_cached_schema,
        invalidate_health_cache,
        invalidate_schema_cache,
        reset_caches,
        set_cached_health,
        set_cached_schema,
    )
except ImportError:
    # Provide no-op stubs if cachetools isn't installed
    def get_cached_schema(*args, **kwargs):
        return None

    def set_cached_schema(*args, **kwargs):
        pass

    def invalidate_schema_cache(*args, **kwargs):
        pass

    def get_cached_health(*args, **kwargs):
        return None

    def set_cached_health(*args, **kwargs):
        pass

    def invalidate_health_cache(*args, **kwargs):
        pass

    def get_cache_stats(*args, **kwargs):
        return {"enabled": False, "reason": "cachetools not installed"}

    def reset_caches(*args, **kwargs):
        pass


__all__ = [
    "AWSDbCredentials",
    "get_secret_value",
    "get_db_credentials_from_secret",
    "MarkdownFormatter",
    # Cache
    "get_cached_schema",
    "set_cached_schema",
    "invalidate_schema_cache",
    "get_cached_health",
    "set_cached_health",
    "invalidate_health_cache",
    "get_cache_stats",
    "reset_caches",
    # Constants
    "TimeoutDefaults",
    "QueryLimits",
    "HealthThresholds",
    "MaintenanceThresholds",
    "QueryAnalysisThresholds",
    "RiskScoring",
    "PoolDefaults",
    "AWSDefaults",
    # Tool helpers
    "get_user_schemas",
    "analyze_all_schemas",
    "aggregate_issues",
    "build_all_schemas_result",
]
