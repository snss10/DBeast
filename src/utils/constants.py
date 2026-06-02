"""Centralized constants for dbeast.

This module contains all magic numbers and configurable thresholds
used throughout the application, making them easy to find and modify.
"""

import os


class TimeoutDefaults:
    """Default timeout values in various units."""

    # Query timeout in seconds
    QUERY_TIMEOUT_SEC = float(os.getenv("DBEAST_QUERY_TIMEOUT", "30"))

    # Query timeout in milliseconds (for tool parameters)
    QUERY_TIMEOUT_MS = int(QUERY_TIMEOUT_SEC * 1000)

    # Connection timeout
    CONNECTION_TIMEOUT_SEC = 10

    # Socket check timeout
    SOCKET_CHECK_TIMEOUT_SEC = 0.5

    # Subprocess timeout for Docker checks
    SUBPROCESS_TIMEOUT_SEC = 5


class QueryLimits:
    """Default limits for query results."""

    # Default row limit for SELECT queries
    DEFAULT_ROW_LIMIT = 100

    # Default sample limit for impact analysis
    DEFAULT_SAMPLE_LIMIT = 10

    # Maximum rows to show in impact preview
    MAX_IMPACT_SAMPLE_ROWS = 100


class HealthThresholds:
    """Thresholds for health checks and warnings."""

    # Cache hit ratio below this triggers warning
    CACHE_HIT_RATIO_WARNING = 95

    # Connection utilization percentage for warning
    CONNECTION_UTILIZATION_WARNING = 80

    # Idle in transaction timeout (seconds)
    IDLE_IN_TRANSACTION_WARNING_SEC = 300

    # Lock wait time (seconds) for warning
    LOCK_WAIT_WARNING_SEC = 60

    # Lock wait time (seconds) for critical
    LOCK_WAIT_CRITICAL_SEC = 300

    # XID wraparound percentage for warning
    XID_WRAPAROUND_WARNING_PCT = 30

    # XID wraparound percentage for critical
    XID_WRAPAROUND_CRITICAL_PCT = 50

    # Long running query threshold (seconds)
    LONG_RUNNING_QUERY_SEC = 60

    # Long running transaction threshold (minutes)
    LONG_RUNNING_TRANSACTION_MIN = 10


class MaintenanceThresholds:
    """Thresholds for maintenance analysis."""

    # Index usage percentage below this triggers warning
    INDEX_USAGE_WARNING_PCT = 80

    # Sequential scan count above this triggers warning
    SEQ_SCAN_WARNING_COUNT = 100

    # Dead row ratio percentage for vacuum recommendation
    DEAD_ROW_RATIO_WARNING_PCT = 20

    # Table bloat percentage for high priority
    TABLE_BLOAT_HIGH_PCT = 50

    # Minimum rows for index recommendation
    MIN_ROWS_FOR_INDEX = 1000

    # Large table threshold for performance warnings
    LARGE_TABLE_ROW_THRESHOLD = 10000


class QueryAnalysisThresholds:
    """Thresholds for query analysis."""

    # Sequential scan row threshold
    SEQ_SCAN_ROW_WARNING = 1000

    # Nested loop row threshold for warning
    NESTED_LOOP_ROW_WARNING = 10000

    # Row estimate accuracy ratio for warning
    ROW_ESTIMATE_RATIO_WARNING = 10

    # Buffer cache hit ratio percentage for warning
    BUFFER_HIT_RATIO_WARNING = 90


class RiskScoring:
    """Risk scoring constants for impact analysis."""

    # Base scores for risk factors
    NO_WHERE_CLAUSE_SCORE = 50
    CRITICAL_PERCENT_SCORE = 40
    DANGEROUS_PERCENT_SCORE = 25
    MASS_DELETE_SCORE = 15
    MASS_UPDATE_SCORE = 10

    # Risk level thresholds
    CRITICAL_RISK_THRESHOLD = 70
    DANGEROUS_RISK_THRESHOLD = 40
    CAUTIOUS_RISK_THRESHOLD = 20

    # Maximum risk score
    MAX_RISK_SCORE = 100


class PoolDefaults:
    """Connection pool default settings."""

    MIN_SIZE = int(os.getenv("DBEAST_POOL_MIN_SIZE", "1"))
    MAX_SIZE = int(os.getenv("DBEAST_POOL_MAX_SIZE", "5"))
    COMMAND_TIMEOUT = int(os.getenv("DBEAST_COMMAND_TIMEOUT", "30"))


class AWSDefaults:
    """AWS integration defaults."""

    # Default AWS region for Secrets Manager
    DEFAULT_REGION = os.getenv("AWS_REGION", "us-west-1")
