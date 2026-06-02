"""Query execution and analysis models with validation constraints."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    """Result of query execution with validated fields."""

    query: str = Field(
        min_length=1,
        max_length=100000,
        description="The executed SQL query",
    )
    rows: list[dict] = Field(
        default_factory=list,
        description="Returned data rows as list of dictionaries",
    )
    row_count: int = Field(
        ge=0,
        description="Number of rows returned",
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Column names in result set",
    )
    execution_time_ms: float | None = Field(
        default=None,
        ge=0,
        description="Query execution time in milliseconds",
    )


class ImpactPreview(BaseModel):
    """Preview of write query impact with risk assessment."""

    query_type: str = Field(
        min_length=1,
        max_length=50,
        description="Type of write operation (DELETE, UPDATE, DROP, etc.)",
    )
    target_table: str = Field(
        min_length=1,
        max_length=256,
        description="Fully qualified table name (schema.table)",
    )
    affected_rows: int = Field(
        ge=0,
        description="Estimated number of rows affected",
    )
    sample_rows: list[dict] = Field(
        default_factory=list,
        max_length=100,
        description="Sample of rows that would be affected",
    )
    cascade_info: list[dict] = Field(
        default_factory=list,
        description="Foreign key cascade impact information",
    )
    warning: str | None = Field(
        default=None,
        max_length=1000,
        description="Warning message if applicable",
    )

    # Risk assessment fields
    risk_level: Literal["safe", "cautious", "dangerous", "critical"] = Field(
        default="safe",
        description="Risk level classification",
    )
    risk_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Risk score from 0-100",
    )
    should_block: bool = Field(
        default=False,
        description="Whether execution should be blocked",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="List of identified risk factors",
    )

    # Rollback support
    rollback_sql: str | None = Field(
        default=None,
        max_length=1000000,
        description="Generated SQL to rollback the operation",
    )
    rollback_row_count: int = Field(
        default=0,
        ge=0,
        description="Number of rows in rollback statement",
    )
    rollback_warning: str | None = Field(
        default=None,
        max_length=1000,
        description="Warning about rollback limitations",
    )


class JoinInfo(BaseModel):
    """JOIN clause information with validation."""

    join_type: str = Field(
        min_length=1,
        max_length=50,
        description="Type of join (INNER, LEFT, RIGHT, FULL, CROSS)",
    )
    table: str = Field(
        min_length=1,
        max_length=256,
        description="Joined table name",
    )
    alias: str | None = Field(
        default=None,
        max_length=128,
        description="Table alias if used",
    )
    condition: str | None = Field(
        default=None,
        max_length=10000,
        description="Join condition (ON clause)",
    )


class QueryAnalysis(BaseModel):
    """Static query analysis result with validation."""

    valid: bool = Field(
        description="Whether the query is syntactically valid",
    )
    query_type: str = Field(
        max_length=50,
        description="Query type (SELECT, INSERT, UPDATE, DELETE, etc.)",
    )
    tables: list[str] = Field(
        default_factory=list,
        description="Tables referenced in the query",
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Columns referenced in the query",
    )
    joins: list[JoinInfo] = Field(
        default_factory=list,
        description="JOIN clause details",
    )
    where_conditions: list[str] = Field(
        default_factory=list,
        description="WHERE clause conditions",
    )
    has_aggregation: bool = Field(
        default=False,
        description="Whether query uses aggregate functions",
    )
    has_subquery: bool = Field(
        default=False,
        description="Whether query contains subqueries",
    )
    has_limit: bool = Field(
        default=False,
        description="Whether query has LIMIT clause",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Analysis warnings (e.g., missing indexes)",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Optimization suggestions",
    )
    formatted_query: str | None = Field(
        default=None,
        max_length=100000,
        description="Pretty-printed query",
    )
    error: str | None = Field(
        default=None,
        max_length=10000,
        description="Parse error if query is invalid",
    )
