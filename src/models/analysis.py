"""Query analysis models for enhanced analysis."""

from pydantic import BaseModel

from models.query import JoinInfo


class QueryInput(BaseModel):
    """Input for batch query analysis."""

    id: str
    sql: str
    source: str | None = None
    name: str | None = None


class IndexRecommendation(BaseModel):
    """Index recommendation from analysis."""

    table: str
    columns: list[str]
    reason: str
    impact: str


class ExecutionPlanInfo(BaseModel):
    """Execution plan information."""

    plan_type: str
    estimated_cost: float | None = None
    estimated_rows: int | None = None
    scan_type: str | None = None
    index_used: str | None = None
    warnings: list[str] = []
    raw_plan: dict | None = None


class EnhancedQueryAnalysis(BaseModel):
    """Enhanced query analysis with metrics and recommendations."""

    id: str
    name: str | None = None
    source: str | None = None
    sql: str
    valid: bool
    query_type: str
    tables: list[str]
    columns: list[str]
    joins: list[JoinInfo]
    where_conditions: list[str]
    has_aggregation: bool
    has_subquery: bool
    has_limit: bool
    complexity_score: int
    risk_level: str
    purpose: str
    index_recommendations: list[IndexRecommendation] = []
    execution_plan: ExecutionPlanInfo | None = None
    warnings: list[str] = []
    optimizations: list[str] = []
    info: list[str] = []
    similar_to: list[str] = []
    error: str | None = None
    formatted_query: str | None = None
