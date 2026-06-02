"""Dbeast - Expert PostgreSQL database analysis MCP server."""

__version__ = "0.1.0"

from db import DatabasePool, SchemaDiscovery
from models import (
    BatchAnalysisResult,
    BatchAnalysisSummary,
    Column,
    # Base models
    ConnectionConfig,
    ConnectionResult,
    CrossQueryInsights,
    DuplicateGroup,
    EnhancedQueryAnalysis,
    ExecutionPlanInfo,
    ForeignKey,
    ImpactPreview,
    Index,
    IndexRecommendation,
    JoinInfo,
    NPlusOneCandidate,
    QueryAnalysis,
    # Batch analysis models
    QueryInput,
    QueryResult,
    Table,
)
from query import BatchQueryAnalyzer, ImpactAnalyzer, QueryAnalyzer, QueryExecutor

__all__ = [
    # Version
    "__version__",
    # Database
    "DatabasePool",
    "SchemaDiscovery",
    # Query
    "QueryExecutor",
    "ImpactAnalyzer",
    "QueryAnalyzer",
    "BatchQueryAnalyzer",
    # Base Models
    "ConnectionConfig",
    "Column",
    "ForeignKey",
    "Index",
    "Table",
    "QueryResult",
    "ImpactPreview",
    "ConnectionResult",
    "JoinInfo",
    "QueryAnalysis",
    # Batch Analysis Models
    "QueryInput",
    "IndexRecommendation",
    "ExecutionPlanInfo",
    "EnhancedQueryAnalysis",
    "DuplicateGroup",
    "NPlusOneCandidate",
    "CrossQueryInsights",
    "BatchAnalysisSummary",
    "BatchAnalysisResult",
]
