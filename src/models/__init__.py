"""Pydantic models and response utilities for dbeast.

This module exports all data models and response helpers used throughout the application:

Models:
    - Connection: ConnectionConfig, ConnectionResult
    - Schema: Column, ForeignKey, Index, Table
    - Query: QueryResult, ImpactPreview, JoinInfo, QueryAnalysis
    - Analysis: QueryInput, IndexRecommendation, ExecutionPlanInfo, EnhancedQueryAnalysis
    - Batch: DuplicateGroup, NPlusOneCandidate, CrossQueryInsights, BatchAnalysisSummary, BatchAnalysisResult
    - Inputs: ExecuteQueryInput, AnalyzeQueryInput, AnalyzeImpactInput, etc.

Response System:
    - Response: Factory class for creating standardized responses
    - McpResponse: Pydantic model for response structure
    - ErrorCode: Enum of standard error codes
    - ErrorDetail, ResponseMeta: Supporting models

Helper Functions:
    - error(), connection_error(), timeout_error(), validation_error()
    - not_found_error(), extension_required_error(), internal_error(), parse_error()
    - success(), success_with_issues()

Usage:
    from models import Response, ConnectionConfig, Table
    return Response.ok({"tables": tables})
    return Response.not_connected()
"""

from models.analysis import (
    EnhancedQueryAnalysis,
    ExecutionPlanInfo,
    IndexRecommendation,
    QueryInput,
)
from models.batch import (
    BatchAnalysisResult,
    BatchAnalysisSummary,
    CrossQueryInsights,
    DuplicateGroup,
    NPlusOneCandidate,
)
from models.connection import ConnectionConfig, ConnectionResult
from models.inputs import (
    AnalyzeImpactInput,
    AnalyzeQueryInput,
    ConfigurationReviewInput,
    ConnectInput,
    DatabaseHealthInput,
    DataQualityInput,
    DependencyAnalysisInput,
    DuplicateDetectionInput,
    ExecuteQueryInput,
    MaintenanceAnalysisInput,
    PartitionAnalysisInput,
    QueryOptimizerInput,
    QueryPerformanceInput,
    ReplicationStatusInput,
    SchemaInput,
    SecurityAuditInput,
)
from models.query import ImpactPreview, JoinInfo, QueryAnalysis, QueryResult

# Unified response system and helper functions
from models.responses import (
    ErrorCode,
    ErrorDetail,
    McpResponse,
    Response,
    ResponseMeta,
    connection_error,
    error,
    extension_required_error,
    internal_error,
    not_found_error,
    parse_error,
    success,
    success_with_issues,
    timeout_error,
    validation_error,
)
from models.schema import Column, ForeignKey, Index, Table

__all__ = [
    # Connection
    "ConnectionConfig",
    "ConnectionResult",
    # Schema
    "Column",
    "ForeignKey",
    "Index",
    "Table",
    # Query
    "QueryResult",
    "ImpactPreview",
    "JoinInfo",
    "QueryAnalysis",
    # Analysis
    "QueryInput",
    "IndexRecommendation",
    "ExecutionPlanInfo",
    "EnhancedQueryAnalysis",
    # Batch
    "DuplicateGroup",
    "NPlusOneCandidate",
    "CrossQueryInsights",
    "BatchAnalysisSummary",
    "BatchAnalysisResult",
    # Input Validation Models
    "ExecuteQueryInput",
    "AnalyzeQueryInput",
    "AnalyzeImpactInput",
    "QueryOptimizerInput",
    "SchemaInput",
    "MaintenanceAnalysisInput",
    "SecurityAuditInput",
    "DataQualityInput",
    "DuplicateDetectionInput",
    "DatabaseHealthInput",
    "ReplicationStatusInput",
    "ConfigurationReviewInput",
    "PartitionAnalysisInput",
    "DependencyAnalysisInput",
    "QueryPerformanceInput",
    "ConnectInput",
    # Unified Response System
    "Response",
    "McpResponse",
    "ErrorCode",
    "ErrorDetail",
    "ResponseMeta",
    # Helper functions
    "error",
    "connection_error",
    "timeout_error",
    "validation_error",
    "not_found_error",
    "extension_required_error",
    "internal_error",
    "parse_error",
    "success",
    "success_with_issues",
]
