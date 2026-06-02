"""Query execution with safety checks."""

import re
import time
from typing import TYPE_CHECKING

from core.exceptions import DbConnectionError
from models import QueryResult

if TYPE_CHECKING:
    from db import DatabasePool


def _get_default_timeout() -> float:
    """Get default timeout from settings."""
    try:
        from core.config import get_settings

        return get_settings().query_timeout
    except Exception:
        return 30.0  # Fallback default


class QueryExecutor:
    """Executes SQL queries with safety checks."""

    WRITE_PATTERNS = [
        r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE)",
    ]

    def __init__(self, pool: "DatabasePool", default_timeout: float | None = None):
        self._pool = pool
        self.default_timeout = default_timeout or _get_default_timeout()

    def is_write_query(self, query: str) -> bool:
        """Check if query is a write operation."""
        query_upper = query.upper().strip()
        for pattern in self.WRITE_PATTERNS:
            if re.match(pattern, query_upper, re.IGNORECASE):
                return True
        return False

    def is_safe_read_query(self, query: str) -> bool:
        """Check if query is a safe read operation."""
        return not self.is_write_query(query)

    async def execute_read(
        self,
        query: str,
        limit: int = 100,
        timeout_ms: int | None = None,
    ) -> QueryResult:
        """
        Execute a read-only SQL query.

        Args:
            query: SQL SELECT query
            limit: Max rows to return
            timeout_ms: Query timeout in milliseconds (default from DBEAST_QUERY_TIMEOUT env or 30000)

        Raises:
            ValueError: If query is a write operation
            asyncpg.exceptions.QueryCanceledError: If query times out
        """
        if self.is_write_query(query):
            raise ValueError(
                "Write queries (INSERT, UPDATE, DELETE, etc.) are not allowed. "
                "Use analyze_impact to preview affected rows."
            )

        query_with_limit = self._add_limit_if_needed(query, limit)

        # Convert ms to seconds for asyncpg
        timeout_sec = (timeout_ms / 1000) if timeout_ms else self.default_timeout

        start = time.perf_counter()
        rows = await self._pool.fetch(query_with_limit, timeout=timeout_sec)
        elapsed = (time.perf_counter() - start) * 1000

        columns = list(rows[0].keys()) if rows else []

        return QueryResult(
            query=query_with_limit,
            rows=rows,
            row_count=len(rows),
            columns=columns,
            execution_time_ms=round(elapsed, 2),
        )

    def _add_limit_if_needed(self, query: str, limit: int) -> str:
        """Add LIMIT clause if not present."""
        query_upper = query.upper().strip()

        if "LIMIT" in query_upper:
            return query

        query = query.rstrip().rstrip(";")
        return f"{query} LIMIT {limit}"

    async def explain(
        self,
        query: str,
        analyze: bool = False,
        buffers: bool = False,
        timeout_ms: int | None = None,
    ) -> dict:
        """
        Get execution plan with optional actual runtime stats.

        For write queries (INSERT, UPDATE, DELETE, etc.) with analyze=True,
        the query is wrapped in a transaction that is rolled back to prevent
        actual data modification while still getting real execution timing.

        Args:
            query: SQL query to explain
            analyze: Run ANALYZE for actual timing (executes the query)
            buffers: Include buffer usage stats
            timeout_ms: Query timeout in milliseconds
        """
        options = ["FORMAT JSON"]
        if analyze:
            options.append("ANALYZE true")
            if buffers:
                options.append("BUFFERS true")
        else:
            options.append("ANALYZE false")

        explain_query = f"EXPLAIN ({', '.join(options)}) {query}"

        # Convert ms to seconds for asyncpg
        timeout_sec = (timeout_ms / 1000) if timeout_ms else self.default_timeout

        # Safety: wrap write queries in a rolled-back transaction
        is_write = analyze and self.is_write_query(query)
        rolled_back = False

        if is_write:
            # Execute within a transaction that we rollback
            rows = await self._execute_with_rollback(explain_query, timeout_sec)
            rolled_back = True
        else:
            rows = await self._pool.fetch(explain_query, timeout=timeout_sec)

        if not rows:
            return {"query": query, "plan": None, "issues": [], "recommendations": []}

        plan_data = rows[0].get("QUERY PLAN", rows)
        plan = plan_data[0] if isinstance(plan_data, list) and plan_data else plan_data

        issues, recommendations = self._analyze_plan(plan, analyze)

        result = {
            "query": query,
            "plan": plan,
            "issues": issues,
            "recommendations": recommendations,
        }

        if analyze and isinstance(plan, dict) and "Plan" in plan:
            result["execution_summary"] = self._extract_execution_summary(plan)

        # Indicate that the query was safely rolled back
        if rolled_back:
            result["safety_note"] = "Write query was executed in a rolled-back transaction - no data was modified"

        return result

    async def _execute_with_rollback(self, query: str, timeout: float | None = None) -> list[dict]:
        """
        Execute a query within a transaction that is always rolled back.
        Used for safely running EXPLAIN ANALYZE on write queries.

        Args:
            query: SQL query to execute
            timeout: Query timeout in seconds
        """
        pool = self._pool.get_pool()
        if not pool:
            raise DbConnectionError("Not connected to database")

        async with pool.acquire() as conn:
            # Start transaction
            tr = conn.transaction()
            await tr.start()
            try:
                # Execute the query with timeout
                rows = await conn.fetch(query, timeout=timeout)
                return [dict(row) for row in rows]
            finally:
                # Always rollback - never commit write queries
                await tr.rollback()

    def _analyze_plan(self, plan: dict, has_actual_times: bool) -> tuple[list[str], list[str]]:
        """Analyze execution plan for issues."""
        issues: list[str] = []
        recommendations: list[str] = []

        if not isinstance(plan, dict):
            return issues, recommendations

        root_plan = plan.get("Plan", plan)
        self._traverse_plan(root_plan, issues, recommendations, has_actual_times, depth=0)

        # Check for planning vs execution time ratio
        if has_actual_times:
            planning_time = plan.get("Planning Time", 0)
            exec_time = plan.get("Execution Time", 0)
            if planning_time > exec_time and exec_time > 0:
                issues.append(
                    f"Planning time ({planning_time:.1f}ms) exceeds execution ({exec_time:.1f}ms) - query may be over-optimized"
                )

        return issues, recommendations

    def _traverse_plan(self, node: dict, issues: list, recs: list, has_actual: bool, depth: int):
        """Recursively analyze plan nodes."""
        if not isinstance(node, dict):
            return

        node_type = node.get("Node Type", "")

        # Sequential Scan issues
        if node_type == "Seq Scan":
            table = node.get("Relation Name", "unknown")
            rows = node.get("Actual Rows", node.get("Plan Rows", 0))
            if rows > 1000:
                issues.append(f"Sequential scan on '{table}' ({rows} rows) - consider adding index")
                filter_cond = node.get("Filter")
                if filter_cond:
                    recs.append(f"Add index on '{table}' for filter: {filter_cond}")

        # Nested Loop with high row count
        if node_type == "Nested Loop":
            actual_rows = node.get("Actual Rows", 0)
            loops = node.get("Actual Loops", 1)
            if has_actual and actual_rows * loops > 10000:
                issues.append(f"Nested Loop scanned {actual_rows * loops} rows - consider JOIN rewrite")

        # Sort operations
        if node_type == "Sort":
            sort_method = node.get("Sort Method", "")
            if "external" in sort_method.lower() or "disk" in sort_method.lower():
                issues.append(f"Sort spilled to disk ({sort_method}) - increase work_mem or add index")
                recs.append("Consider: SET work_mem = '256MB' or add index on sort columns")

        # Hash operations
        if node_type in ("Hash", "Hash Join"):
            batches = node.get("Hash Batches", 1)
            if batches > 1:
                issues.append(f"Hash operation used {batches} batches (spilled to disk)")
                recs.append("Increase work_mem to keep hash in memory")

        # Bitmap Heap Scan with lossy pages
        if node_type == "Bitmap Heap Scan":
            lossy = node.get("Lossy Heap Blocks", 0)
            if lossy > 0:
                issues.append(f"Bitmap scan lost precision ({lossy} lossy blocks) - increase work_mem")

        # Row estimate accuracy
        if has_actual:
            estimated = node.get("Plan Rows", 1)
            actual = node.get("Actual Rows", 1)
            if estimated > 0 and actual > 0:
                ratio = max(actual / estimated, estimated / actual)
                if ratio > 10:
                    issues.append(
                        f"Row estimate off by {ratio:.0f}x for {node_type} (est: {estimated}, actual: {actual}) - run ANALYZE on table"
                    )

        # Buffer analysis
        shared_hit = node.get("Shared Hit Blocks", 0)
        shared_read = node.get("Shared Read Blocks", 0)
        if shared_read > 0 and shared_hit + shared_read > 0:
            hit_ratio = shared_hit / (shared_hit + shared_read) * 100
            if hit_ratio < 90:
                issues.append(f"Low buffer cache hit ratio ({hit_ratio:.0f}%) for {node_type}")

        # Index-related issues
        if node_type == "Index Scan":
            idx_cond = node.get("Index Cond")
            filter_cond = node.get("Filter")
            if filter_cond and not idx_cond:
                issues.append(f"Index scan with filter (not in index): {filter_cond}")
                recs.append("Consider covering index that includes filter columns")

        # Recurse into child plans
        for child_key in ("Plans", "Plan"):
            children = node.get(child_key, [])
            if isinstance(children, dict):
                children = [children]
            for child in children:
                self._traverse_plan(child, issues, recs, has_actual, depth + 1)

    def _extract_execution_summary(self, plan: dict) -> dict:
        """Extract key execution metrics."""
        root = plan.get("Plan", {})
        return {
            "total_time_ms": plan.get("Execution Time", 0),
            "planning_time_ms": plan.get("Planning Time", 0),
            "rows_returned": root.get("Actual Rows", 0),
            "total_cost": root.get("Total Cost", 0),
            "startup_cost": root.get("Startup Cost", 0),
            "shared_hit_blocks": root.get("Shared Hit Blocks", 0),
            "shared_read_blocks": root.get("Shared Read Blocks", 0),
            "temp_read_blocks": root.get("Temp Read Blocks", 0),
            "temp_written_blocks": root.get("Temp Written Blocks", 0),
        }
