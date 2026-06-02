"""SQL query templates organized by domain."""

from query.templates.config import ConfigQueries
from query.templates.data_quality import DataQualityQueries
from query.templates.dependencies import DependencyQueries
from query.templates.health import HealthQueries
from query.templates.indexes import (
    IndexQueries,
    SmartAnalyzeQueries,
    TableStatsQueries,
)
from query.templates.locks import LockQueries
from query.templates.partitions import PartitionQueries
from query.templates.performance import PerformanceQueries
from query.templates.replication import ReplicationQueries
from query.templates.schema import (
    AnalyzerQueries,
    SchemaQueries,
    SQLSanitizer,
    SystemQueries,
    build_count_query,
    build_select_query,
)
from query.templates.security import SecurityQueries
from query.templates.sessions import SessionQueries
from query.templates.transactions import TransactionQueries
from query.templates.vacuum import VacuumQueries

__all__ = [
    # Schema
    "SchemaQueries",
    "AnalyzerQueries",
    "SystemQueries",
    "SQLSanitizer",
    "build_count_query",
    "build_select_query",
    # Health
    "HealthQueries",
    # Sessions
    "SessionQueries",
    # Locks
    "LockQueries",
    # Transactions
    "TransactionQueries",
    # Vacuum
    "VacuumQueries",
    # Performance
    "PerformanceQueries",
    # Replication
    "ReplicationQueries",
    # Config
    "ConfigQueries",
    # Indexes
    "SmartAnalyzeQueries",
    "IndexQueries",
    "TableStatsQueries",
    # Data Quality
    "DataQualityQueries",
    # Security
    "SecurityQueries",
    # Dependencies
    "DependencyQueries",
    # Partitions
    "PartitionQueries",
]
