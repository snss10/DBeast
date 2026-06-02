"""Query execution and analysis MCP tools.

This module provides tools for SQL query operations:
- analyze_query: Static SQL analysis (syntax, anti-patterns, N+1 detection)
- execute_query: Execute read-only SELECT queries
- analyze_impact: Preview DELETE/UPDATE/DROP impact without executing
- query_optimizer: Deep analysis with execution plans and index recommendations
"""

import json
from typing import TYPE_CHECKING, Literal

import asyncpg.exceptions
from pydantic import Field

from middleware.audit import audited
from models import (
    QueryInput,
    Response,
    connection_error,
    internal_error,
    timeout_error,
    validation_error,
)
from query import BatchQueryAnalyzer, SmartAnalyzeQueries
from tools.context import ToolContext
from utils import MaintenanceThresholds

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

# Type aliases for Literal types
FormatType = Literal["json", "markdown"]


def register_query_tools(mcp: "FastMCP", ctx: ToolContext) -> None:
    """Register query-related MCP tools.

    Args:
        mcp: FastMCP server instance
        ctx: Shared tool context
    """

    @mcp.tool()
    @audited()
    async def analyze_query(
        query: str = Field(description='SQL string or JSON array [{"id":"q1","sql":"..."}]'),
        detect_duplicates: bool = Field(default=True, description="Detect duplicates in batch"),
        include_explain: bool = Field(default=False, description="Include EXPLAIN plan"),
        schema: str | None = Field(
            default=None,
            description="Schema name for batch analysis context. Required for EXPLAIN. Use get_schema() to list available schemas.",
        ),
        format: FormatType = Field(default="json", description="Output format"),
    ) -> str:
        """Validate SQL syntax, detect anti-patterns, N+1, duplicates.

        LEVEL: Query (SQL statement analysis - no DB connection needed for basic parsing)

        USE FOR: SQL validation, N+1 detection, batch analysis.
        DO NOT USE FOR: running queries (execute_query), write impact (analyze_impact).

        Examples:
            analyze_query(query='SELECT * FROM users')
            analyze_query(query='SELECT * FROM users', schema='shipment', include_explain=True)
        """
        queries_list = None

        # Auto-detect format: try JSON first, fallback to plain SQL
        query_stripped = query.strip()
        if query_stripped.startswith("["):
            try:
                queries_list = json.loads(query)
                if not isinstance(queries_list, list):
                    queries_list = None
            except json.JSONDecodeError:
                queries_list = None

        # Plain SQL string - single query mode
        if queries_list is None:
            result = ctx.query_analyzer.analyze(query)
            if format == "markdown":
                return Response.formatted(
                    ctx.formatter.query_analysis(result.model_dump()), "markdown", connected=False
                )
            return Response.ok(result.model_dump(), connected=False)

        # JSON array mode
        if not queries_list:
            return validation_error("Empty query array", field="query")

        # Single item in array - simple static analysis
        if len(queries_list) == 1:
            q = queries_list[0]
            sql = q.get("sql") if isinstance(q, dict) else str(q)
            if not sql:
                return validation_error("Query must have 'sql' field", field="query[0].sql")

            result = ctx.query_analyzer.analyze(sql)
            if format == "markdown":
                return Response.formatted(
                    ctx.formatter.query_analysis(result.model_dump()), "markdown", connected=False
                )
            return Response.ok(result.model_dump(), connected=False)

        # Batch mode - multiple queries with pattern detection
        query_inputs = [
            QueryInput(id=q.get("id", f"q{i}"), sql=q.get("sql", ""), source=q.get("source"), name=q.get("name"))
            for i, q in enumerate(queries_list)
            if isinstance(q, dict) and q.get("sql")
        ]

        if not query_inputs:
            return validation_error("No valid queries found. Each item needs a 'sql' field.", field="query")

        analyzer = ctx.batch_analyzer or BatchQueryAnalyzer(
            pool=ctx.db_pool if ctx.db_pool and ctx.db_pool.is_connected else None,
            schema_discovery=ctx.schema_discovery,
            dialect="postgres",
        )

        try:
            result = await analyzer.analyze_batch(
                queries=query_inputs,
                include_explain=include_explain and ctx.db_pool and ctx.db_pool.is_connected,
                detect_duplicates=detect_duplicates,
                schema_name=schema,
            )
            return Response.ok(result.model_dump(), connected=bool(ctx.db_pool and ctx.db_pool.is_connected))
        except Exception as e:
            return internal_error(e, context="batch query analysis")

    @mcp.tool()
    @audited()
    async def execute_query(
        query: str = Field(description="SQL SELECT query"),
        limit: int = Field(default=100, ge=1, le=50000, description="Max rows (1-50000)"),
        timeout_ms: int = Field(default=300000, ge=100, le=600000, description="Timeout in ms (5 min default)"),
        format: FormatType = Field(default="json", description="Output format"),
        url: str | None = Field(default=None, description="Database URL"),
    ) -> str:
        """Execute read-only SELECT queries. Writes are blocked.

        LEVEL: Data (actual table data retrieval)

        USE FOR: fetching data, counting rows, aggregations, joins.
        DO NOT USE FOR: INSERT/UPDATE/DELETE (use analyze_impact first).

        ERROR RECOVERY:
        - "relation does not exist": Verify table name with get_schema()
        - "permission denied": User lacks SELECT privilege on table
        - "query timeout": Reduce limit, add WHERE clause, or increase timeout_ms
        - "not connected": Call connect() first

        Examples:
            execute_query(query='SELECT * FROM users LIMIT 10')
            execute_query(query='SELECT COUNT(*) FROM orders')
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)
        try:
            result = await ctx.query_executor.execute_read(query, limit, timeout_ms=timeout_ms)
            if format == "markdown":
                return Response.formatted(ctx.formatter.query_result(result.model_dump()), "markdown", connected=True)
            return Response.ok(result.model_dump(), connected=True)
        except asyncpg.exceptions.QueryCanceledError:
            return timeout_error(timeout_ms, query)
        except ValueError as e:
            return validation_error(str(e), field="query")
        except Exception as e:
            return internal_error(e, context="execute_query")

    @mcp.tool()
    @audited()
    async def analyze_impact(
        query: str = Field(description="SQL DELETE/UPDATE/DROP query to preview"),
        sample_limit: int = Field(default=10, ge=1, le=1000, description="Sample rows to show"),
        timeout_ms: int = Field(default=300000, ge=100, le=600000, description="Timeout in ms (5 min default)"),
        schema: str | None = Field(
            default=None,
            description="Schema containing the table. REQUIRED. Use get_schema() to list available schemas.",
        ),
        format: FormatType = Field(default="json", description="Output format"),
        url: str | None = Field(default=None, description="Database URL"),
    ) -> str:
        """Preview DELETE/UPDATE/DROP impact WITHOUT executing. Shows affected rows and rollback SQL.

        LEVEL: Query (write operation preview - never executes)

        USE FOR: previewing write impact, cascade effects, risk assessment.
        DO NOT USE FOR: reading data (execute_query), INSERT operations.

        Examples:
            analyze_impact(query="DELETE FROM users WHERE status='inactive'", schema='public')
            analyze_impact(query="UPDATE orders SET status='cancelled' WHERE id=1", schema='shipment')
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        # If schema not specified, prompt to provide it
        if schema is None:
            schemas = await ctx.schema_discovery.get_schemas()
            schema_list = [s["schema_name"] for s in schemas if s["table_count"] > 0][:20]
            return Response.ok(
                {
                    "action_required": "specify_schema",
                    "message": "Please specify the schema parameter for the table. Use get_schema() to see all available schemas.",
                    "available_schemas": schema_list,
                    "example": "analyze_impact(query='DELETE FROM users WHERE id=1', schema='public')",
                },
                connected=True,
            )

        try:
            result = await ctx.impact_analyzer.analyze_impact(query, sample_limit, schema, timeout_ms=timeout_ms)
            if format == "markdown":
                return Response.formatted(ctx.formatter.impact_preview(result.model_dump()), "markdown", connected=True)
            return Response.ok(result.model_dump(), connected=True)
        except asyncpg.exceptions.QueryCanceledError:
            return timeout_error(timeout_ms, query)
        except ValueError as e:
            return validation_error(str(e), field="query")
        except Exception as e:
            return internal_error(e, context="analyze_impact")

    @mcp.tool()
    @audited()
    async def query_optimizer(
        query: str = Field(description="SQL query to optimize"),
        run_explain: bool = Field(default=False, description="Run EXPLAIN ANALYZE (executes in rollback)"),
        timeout_ms: int = Field(default=300000, ge=100, le=600000, description="Timeout in ms (5 min default)"),
        schema: str | None = Field(
            default=None,
            description="Schema for table stats lookup. REQUIRED. Use get_schema() to list available schemas.",
        ),
        url: str | None = Field(default=None, description="Database URL"),
    ) -> str:
        """Optimize slow queries - EXPLAIN plan, table stats, index recommendations.

        LEVEL: Query (single query optimization)

        USE FOR: slow query diagnosis, CREATE INDEX suggestions, execution plans.
        DO NOT USE FOR: running queries (execute_query), syntax validation (analyze_query).

        Examples:
            query_optimizer(query='SELECT * FROM orders WHERE customer_id=123', schema='shipment')
            query_optimizer(query='SELECT * FROM users', schema='public', run_explain=True)
        """
        if err := await ctx.ensure_connected(url):
            return connection_error(err)

        # If schema not specified, prompt to provide it
        if schema is None:
            schemas = await ctx.schema_discovery.get_schemas()
            schema_list = [s["schema_name"] for s in schemas if s["table_count"] > 0][:20]
            return Response.ok(
                {
                    "action_required": "specify_schema",
                    "message": "Please specify the schema parameter for table stats. Use get_schema() to see all available schemas.",
                    "available_schemas": schema_list,
                    "example": "query_optimizer(query='SELECT * FROM users', schema='public')",
                },
                connected=True,
            )

        # Convert ms to seconds for asyncpg
        timeout_sec = timeout_ms / 1000

        try:
            result = {
                "query": query,
                "static_analysis": None,
                "execution_plan": None,
                "table_context": {},
                "expert_recommendations": [],
                "severity": "info",
            }

            static = ctx.query_analyzer.analyze(query)
            result["static_analysis"] = static.model_dump()

            tables = static.tables or []

            for table in tables:
                try:
                    stats = await ctx.db_pool.fetch(SmartAnalyzeQueries.table_stats(schema, table), timeout=timeout_sec)
                    if stats:
                        result["table_context"][table] = dict(stats[0])

                    idx = await ctx.db_pool.fetch(SmartAnalyzeQueries.table_indexes(schema, table), timeout=timeout_sec)
                    result["table_context"][table] = result["table_context"].get(table, {})
                    result["table_context"][table]["indexes"] = [dict(i) for i in idx]
                except Exception as e:
                    # Record that we couldn't fetch stats for this table
                    result["table_context"][table] = {
                        "error": f"Could not fetch stats: {type(e).__name__}: {str(e)[:100]}"
                    }

            if run_explain:
                try:
                    plan_result = await ctx.query_executor.explain(
                        query, analyze=True, buffers=True, timeout_ms=timeout_ms
                    )
                    result["execution_plan"] = plan_result
                except asyncpg.exceptions.QueryCanceledError:
                    result["execution_plan"] = {"error": f"EXPLAIN timed out after {timeout_ms}ms"}
                except Exception as e:
                    result["execution_plan"] = {"error": str(e)}

            recommendations = []
            severity = "info"

            for warning in static.warnings or []:
                if "CRITICAL" in warning or "DANGER" in warning:
                    severity = "critical"
                    recommendations.append({"type": "critical", "source": "static", "message": warning})
                else:
                    recommendations.append({"type": "warning", "source": "static", "message": warning})

            if result["execution_plan"] and isinstance(result["execution_plan"], dict):
                for issue in result["execution_plan"].get("issues", []):
                    if "disk" in issue.lower() or "spill" in issue.lower():
                        if severity != "critical":
                            severity = "warning"
                    recommendations.append({"type": "performance", "source": "execution", "message": issue})
                for rec in result["execution_plan"].get("recommendations", []):
                    recommendations.append({"type": "suggestion", "source": "execution", "message": rec})

            for table, table_ctx in result["table_context"].items():
                rows = table_ctx.get("rows", 0)
                idx_usage = table_ctx.get("index_usage_pct", 100)
                existing_indexes = table_ctx.get("indexes", [])
                existing_index_names = [idx.get("indexrelname", "").lower() for idx in existing_indexes]

                if rows > MaintenanceThresholds.LARGE_TABLE_ROW_THRESHOLD and idx_usage < 50:
                    severity = "warning"
                    recommendations.append(
                        {
                            "type": "index_needed",
                            "source": "table_stats",
                            "table": table,
                            "message": f"Table '{table}' ({rows} rows) has {idx_usage}% index usage - add indexes on WHERE columns",
                        }
                    )

                where_cols = [c.split(".")[-1] for c in (static.columns or []) if c.lower() not in ["*", "id"]]
                unique_cols = list(dict.fromkeys(where_cols))[:3]

                if unique_cols and rows > MaintenanceThresholds.MIN_ROWS_FOR_INDEX:
                    col_suffix = "_".join(unique_cols)
                    index_name = f"idx_{table}_{col_suffix}"

                    index_exists = any(index_name.lower() in idx_name for idx_name in existing_index_names)

                    if not index_exists:
                        col_list = ", ".join(unique_cols)
                        ddl = f"CREATE INDEX {index_name} ON {schema}.{table} ({col_list});"
                        recommendations.append(
                            {
                                "type": "index_suggestion",
                                "source": "query_analysis",
                                "table": table,
                                "columns": unique_cols,
                                "message": f"Consider index on '{table}' columns: {col_list}",
                                "ddl": ddl,
                            }
                        )

            if "= ?" in query.lower() or "= $" in query.lower() or "= :" in query.lower():
                if any(
                    table_ctx.get("rows", 0) > MaintenanceThresholds.MIN_ROWS_FOR_INDEX
                    for table_ctx in result["table_context"].values()
                ):
                    recommendations.append(
                        {
                            "type": "pattern",
                            "source": "analysis",
                            "message": "Query uses parameterized lookup - verify it's not called in a loop (N+1 pattern)",
                        }
                    )

            result["expert_recommendations"] = recommendations
            result["severity"] = severity

            index_recs = [r for r in recommendations if r.get("ddl")]
            result["index_recommendations"] = index_recs
            result["create_index_statements"] = [r["ddl"] for r in index_recs]

            result["summary"] = {
                "total_issues": len(recommendations),
                "critical": len([r for r in recommendations if r["type"] == "critical"]),
                "warnings": len([r for r in recommendations if r["type"] in ("warning", "performance")]),
                "suggestions": len(
                    [r for r in recommendations if r["type"] in ("suggestion", "index_suggestion", "pattern")]
                ),
                "index_recommendations": len(index_recs),
            }

            return Response.ok(result, connected=True)
        except Exception as e:
            return internal_error(e, context="query_optimizer")
