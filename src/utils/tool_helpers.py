"""Shared helper functions for MCP tools.

Provides common patterns used across multiple tool modules to reduce code duplication.
"""

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from db import SchemaDiscovery

T = TypeVar("T")


async def get_user_schemas(schema_discovery: "SchemaDiscovery") -> list[str]:
    """Get list of user schema names that have tables.

    Args:
        schema_discovery: SchemaDiscovery instance

    Returns:
        List of schema names with at least one table
    """
    schemas = await schema_discovery.get_schemas()
    return [s["schema_name"] for s in schemas if s["table_count"] > 0]


async def analyze_all_schemas(
    schema_discovery: "SchemaDiscovery",
    analyze_fn: Callable[[str], Coroutine[Any, Any, dict]],
    result_key: str = "by_schema",
) -> tuple[list[str], dict[str, dict]]:
    """Analyze all user schemas using a provided analysis function.

    This is a common pattern used by maintenance_analysis, dependency_analysis,
    data_quality_report, etc. when schema='all' is specified.

    Args:
        schema_discovery: SchemaDiscovery instance to get schema list
        analyze_fn: Async function that takes a schema name and returns analysis dict
        result_key: Key name for the by-schema results dict

    Returns:
        Tuple of (schema_names, results_by_schema)

    Example:
        schema_names, by_schema = await analyze_all_schemas(
            ctx.schema_discovery,
            lambda s: _analyze_schema_maintenance(s, include, table)
        )
    """
    schema_names = await get_user_schemas(schema_discovery)

    results: dict[str, dict] = {}
    for schema_name in schema_names:
        results[schema_name] = await analyze_fn(schema_name)

    return schema_names, results


def aggregate_issues(
    by_schema: dict[str, dict],
    issue_key: str = "issues",
) -> tuple[list[str], str]:
    """Aggregate issues from multiple schema analyses and determine overall severity.

    Args:
        by_schema: Dict mapping schema names to their analysis results
        issue_key: Key name for issues list in each schema result

    Returns:
        Tuple of (all_issues, overall_severity)
    """
    all_issues: list[str] = []
    overall_severity = "healthy"

    for schema_result in by_schema.values():
        all_issues.extend(schema_result.get(issue_key, []))

        schema_severity = schema_result.get("severity", "healthy")
        if schema_severity == "critical":
            overall_severity = "critical"
        elif schema_severity == "warning" and overall_severity != "critical":
            overall_severity = "warning"

    return all_issues, overall_severity


def build_all_schemas_result(
    schema_names: list[str],
    by_schema: dict[str, dict],
    all_issues: list[str],
    overall_severity: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard result structure for schema='all' analyses.

    Args:
        schema_names: List of schema names analyzed
        by_schema: Dict mapping schema names to their results
        all_issues: Aggregated list of all issues
        overall_severity: Overall severity level
        extra_fields: Additional fields to include in the result

    Returns:
        Standardized result dict
    """
    result: dict[str, Any] = {
        "schemas_analyzed": schema_names,
        "by_schema": by_schema,
        "severity": overall_severity,
        "issues": all_issues,
        "issue_count": len(all_issues),
        "healthy": len(all_issues) == 0,
    }

    if extra_fields:
        result.update(extra_fields)

    return result
