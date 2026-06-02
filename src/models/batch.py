"""Batch analysis models."""

from pydantic import BaseModel

from models.analysis import EnhancedQueryAnalysis


class DuplicateGroup(BaseModel):
    """Group of duplicate/similar queries."""

    query_ids: list[str]
    similarity_type: str
    description: str


class NPlusOneCandidate(BaseModel):
    """Potential N+1 query pattern."""

    loop_query_id: str
    related_query_ids: list[str]
    pattern: str
    suggestion: str


class CrossQueryInsights(BaseModel):
    """Cross-query analysis insights."""

    duplicates: list[DuplicateGroup] = []
    n_plus_one_candidates: list[NPlusOneCandidate] = []
    optimization_opportunities: list[str] = []
    table_access_patterns: dict[str, int] = {}


class BatchAnalysisSummary(BaseModel):
    """Summary statistics for batch analysis."""

    total_queries: int
    successful: int
    failed: int
    warnings_count: int
    optimizations_count: int
    high_risk_count: int
    avg_complexity: float


class BatchAnalysisResult(BaseModel):
    """Complete batch analysis result."""

    summary: BatchAnalysisSummary
    queries: list[EnhancedQueryAnalysis]
    cross_query_insights: CrossQueryInsights
    generated_at: str
