"""Input validation models for MCP tool parameters.

These Pydantic models provide schema validation and constraints for tool inputs,
ensuring type safety and providing clear error messages for invalid inputs.

Usage:
    from models.inputs import ExecuteQueryInput

    # Validation happens automatically
    input_data = ExecuteQueryInput(query="SELECT * FROM users", limit=50)
"""

import warnings
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Suppress Pydantic warning about 'schema' field name shadowing BaseModel.schema()
# This is intentional - we use 'schema' as it's the standard PostgreSQL term
warnings.filterwarnings(
    "ignore",
    message='Field name "schema" in .* shadows an attribute in parent',
    category=UserWarning,
)


class ExecuteQueryInput(BaseModel):
    """Input validation for execute_query tool."""

    query: str = Field(
        min_length=1,
        max_length=100000,  # 100KB - allows for complex queries with CTEs/subqueries
        description="SQL SELECT query to execute",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=50000,  # Increased to allow larger exports
        description="Maximum rows to return (1-50000)",
    )
    timeout_ms: int = Field(
        default=300000,
        ge=100,
        le=600000,
        description="Query timeout in milliseconds (default: 5 min)",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v


class AnalyzeQueryInput(BaseModel):
    """Input validation for analyze_query tool."""

    query: str = Field(
        min_length=1,
        max_length=100000,  # 100KB - allows for batch analysis with multiple queries
        description="SQL query or JSON array of queries to analyze",
    )
    detect_duplicates: bool = Field(
        default=True,
        description="Detect duplicate/similar queries in batch mode",
    )
    include_explain: bool = Field(
        default=False,
        description="Include EXPLAIN plan (requires database connection)",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. REQUIRED - use get_schema() to list available schemas.",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class AnalyzeImpactInput(BaseModel):
    """Input validation for analyze_impact tool."""

    query: str = Field(
        min_length=1,
        max_length=100000,  # 100KB - write queries can be large with many conditions
        description="SQL write query to analyze (DELETE, UPDATE, DROP)",
    )
    sample_limit: int = Field(
        default=10,
        ge=1,
        le=1000,  # Increased for larger previews
        description="Number of sample rows to show (1-1000)",
    )
    timeout_ms: int = Field(
        default=300000,
        ge=100,
        le=600000,
        description="Query timeout in milliseconds (default: 5 min)",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. REQUIRED - use get_schema() to list available schemas.",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class QueryOptimizerInput(BaseModel):
    """Input validation for query_optimizer tool."""

    query: str = Field(
        min_length=1,
        max_length=100000,  # 100KB for large queries
        description="SQL query to optimize",
    )
    run_explain: bool = Field(
        default=False,
        description="Run EXPLAIN ANALYZE for actual execution timing",
    )
    timeout_ms: int = Field(
        default=300000,
        ge=100,
        le=600000,
        description="Query timeout in milliseconds (default: 5 min)",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. REQUIRED - use get_schema() to list available schemas.",
    )


class SchemaInput(BaseModel):
    """Input validation for get_schema tool."""

    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name or 'all' to list all schemas",
    )
    format: Literal["json", "text", "markdown", "mermaid"] = Field(
        default="json",
        description="Output format (mermaid generates ERD diagrams)",
    )

    @field_validator("schema")
    @classmethod
    def validate_schema_name(cls, v: str | None) -> str | None:
        """Validate schema name if provided."""
        if v is None or v.lower() == "all":
            return v
        if not v.strip():
            return None
        # Basic identifier validation
        import re

        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(f"Invalid schema name: '{v}'. Use alphanumeric characters and underscores.")
        return v


class MaintenanceAnalysisInput(BaseModel):
    """Input validation for maintenance_analysis tool."""

    include: Literal["all", "indexes", "tables", "vacuum", "fk_indexes", "toast"] = Field(
        default="all",
        description="What to include in analysis",
    )
    table: str | None = Field(
        default=None,
        max_length=128,
        description="Specific table to analyze",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. Required - use 'all' for all schemas or specify one. Use get_schema() to list.",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class SecurityAuditInput(BaseModel):
    """Input validation for security_audit tool."""

    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. Required - use 'all' for all schemas or specify one. Use get_schema() to list.",
    )
    include: Literal["all", "roles", "privileges", "rls", "ssl", "sensitive", "functions"] = Field(
        default="all",
        description="What to include in audit",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class DataQualityInput(BaseModel):
    """Input validation for data_quality_report tool."""

    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. Required - use 'all' for all schemas or specify one. Use get_schema() to list.",
    )
    table: str | None = Field(
        default=None,
        max_length=128,
        description="Optional specific table to analyze",
    )
    include: Literal["all", "nulls", "cardinality", "empty", "outliers", "soft_delete", "types"] = Field(
        default="all",
        description="What to include in analysis",
    )
    outlier_column: str | None = Field(
        default=None,
        max_length=128,
        description="Column name for outlier detection",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class DuplicateDetectionInput(BaseModel):
    """Input validation for duplicate_detection tool."""

    table: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$",
        description="Table name to check for duplicates",
    )
    columns: str = Field(
        min_length=1,
        max_length=5000,  # Increased to allow many columns (up to ~75 columns at 63 chars each + commas)
        description="Comma-separated column names (e.g., 'email,name')",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. REQUIRED - use get_schema() to list available schemas.",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, v: str) -> str:
        """Validate column names."""
        import re

        cols = [c.strip() for c in v.split(",")]
        for col in cols:
            if not col:
                raise ValueError("Column names cannot be empty")
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
                raise ValueError(f"Invalid column name: '{col}'")
        return v


class DatabaseHealthInput(BaseModel):
    """Input validation for database_health tool."""

    include: Literal["all", "summary", "sessions", "locks", "transactions", "queries", "bloat"] = Field(
        default="all",
        description="What to include in health check",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class ReplicationStatusInput(BaseModel):
    """Input validation for replication_status tool."""

    include: Literal["all", "physical", "logical", "slots", "wal", "archiving"] = Field(
        default="all",
        description="What to include in replication status",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class ConfigurationReviewInput(BaseModel):
    """Input validation for configuration_review tool."""

    include: Literal["all", "memory", "connections", "logging", "autovacuum", "extensions"] = Field(
        default="all",
        description="What to include in configuration review",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class PartitionAnalysisInput(BaseModel):
    """Input validation for partition_analysis tool."""

    table: str | None = Field(
        default=None,
        max_length=128,
        description="Partitioned table name (omit to list all)",
    )
    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. REQUIRED when table specified - use get_schema() to list available schemas.",
    )
    include: Literal["all", "details", "size", "activity", "indexes", "maintenance"] = Field(
        default="all",
        description="What to include in partition analysis",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class DependencyAnalysisInput(BaseModel):
    """Input validation for dependency_analysis tool."""

    schema: str | None = Field(
        default=None,
        max_length=128,
        description="Schema name. Required - use 'all' for all schemas or specify one. Use get_schema() to list.",
    )
    include: Literal["all", "views", "functions", "triggers", "sequences", "extensions", "fdw"] = Field(
        default="all",
        description="What to include in dependency analysis",
    )
    table: str | None = Field(
        default=None,
        max_length=128,
        description="Optional specific table for dependency analysis",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )


class QueryPerformanceInput(BaseModel):
    """Input validation for query_performance tool."""

    limit: int = Field(
        default=20,
        ge=1,
        le=500,  # Increased for larger performance reports
        description="Number of queries to return (1-500)",
    )
    order_by: Literal["total_time", "calls", "mean_time", "rows", "shared_blks_hit", "shared_blks_read"] = Field(
        default="total_time",
        description="Sort order for query results",
    )
    min_calls: int = Field(
        default=1,
        ge=1,
        le=1000000,  # Allow filtering for high-frequency queries
        description="Minimum call count filter (1-1000000)",
    )


class ConnectInput(BaseModel):
    """Input validation for connect tool."""

    url: str | None = Field(
        default=None,
        max_length=2000,
        description="Full PostgreSQL URL",
    )
    host: str | None = Field(
        default=None,
        max_length=255,
        description="Database host",
    )
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Database port (1-65535)",
    )
    user: str | None = Field(
        default=None,
        max_length=128,
        description="Database username",
    )
    password: str | None = Field(
        default=None,
        max_length=1000,
        description="Database password",
    )
    database: str | None = Field(
        default=None,
        max_length=128,
        description="Database name",
    )
    use_ssl: bool | None = Field(
        default=None,
        description="Use SSL encryption",
    )
    aws_secret_name: str | None = Field(
        default=None,
        max_length=512,
        description="AWS Secrets Manager secret name",
    )
    aws_region: str = Field(
        default="us-west-1",
        max_length=64,
        description="AWS region",
    )
    discover: bool = Field(
        default=False,
        description="Auto-discover accessible PostgreSQL instances",
    )
    format: Literal["json", "markdown"] = Field(
        default="json",
        description="Output format",
    )
