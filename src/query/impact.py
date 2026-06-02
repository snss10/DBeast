"""Impact analysis for write queries with risk scoring and rollback generation."""

import re
from typing import TYPE_CHECKING, Literal

from models import ImpactPreview
from query.templates.schema import AnalyzerQueries, SQLSanitizer, build_count_query, build_select_query

if TYPE_CHECKING:
    from db import DatabasePool, SchemaDiscovery


def _load_thresholds() -> dict:
    """Load thresholds from centralized settings.

    Uses pydantic-settings for validated configuration with defaults.
    """
    try:
        from core.config import get_settings

        settings = get_settings()
        return {
            "mass_update_rows": settings.dbeast_mass_update_rows,
            "mass_delete_rows": settings.dbeast_mass_delete_rows,
            "dangerous_percent": settings.dbeast_dangerous_percent,
            "critical_percent": settings.dbeast_critical_percent,
        }
    except Exception:
        # Fallback defaults if settings fail to load
        return {
            "mass_update_rows": 1000,
            "mass_delete_rows": 100,
            "dangerous_percent": 50,
            "critical_percent": 90,
        }


def _get_default_timeout() -> float:
    """Get default query timeout from settings."""
    try:
        from core.config import get_settings

        return get_settings().query_timeout
    except Exception:
        return 30.0


class ImpactAnalyzer:
    """Analyzes the impact of write queries without executing them."""

    def __init__(
        self,
        pool: "DatabasePool",
        schema: "SchemaDiscovery",
        thresholds: dict | None = None,
        default_timeout: float | None = None,
    ):
        self._pool = pool
        self._schema = schema
        # Allow custom thresholds, fallback to settings, then defaults
        self.thresholds = thresholds or _load_thresholds()
        self._default_timeout = default_timeout or _get_default_timeout()
        self._current_timeout: float | None = None

    def _get_timeout(self) -> float | None:
        """Get the current timeout (set per-call or default)."""
        return self._current_timeout or self._default_timeout

    def parse_query_type(self, query: str) -> str:
        """Parse the type of SQL query."""
        query_upper = query.upper().strip()
        if query_upper.startswith("INSERT"):
            return "INSERT"
        elif query_upper.startswith("UPDATE"):
            return "UPDATE"
        elif query_upper.startswith("DELETE"):
            return "DELETE"
        elif query_upper.startswith("SELECT"):
            return "SELECT"
        elif query_upper.startswith("TRUNCATE"):
            return "TRUNCATE"
        elif query_upper.startswith("DROP"):
            return "DROP"
        return "UNKNOWN"

    def extract_table_name(self, query: str) -> str | None:
        """Extract the target table name from a query.

        Returns just the table name, stripping any schema prefix.
        Schema-qualified names like 'public.users' return 'users'.
        """
        query_upper = query.upper().strip()

        if query_upper.startswith("DELETE"):
            # Match schema.table or just table, with optional quotes
            match = re.search(r"DELETE\s+FROM\s+(?:[\"']?\w+[\"']?\.)?([\"']?\w+[\"']?)", query, re.IGNORECASE)
            if match:
                return match.group(1).strip("\"'")

        elif query_upper.startswith("UPDATE"):
            # Match schema.table or just table, with optional quotes
            match = re.search(r"UPDATE\s+(?:[\"']?\w+[\"']?\.)?([\"']?\w+[\"']?)", query, re.IGNORECASE)
            if match:
                return match.group(1).strip("\"'")

        elif query_upper.startswith("INSERT"):
            match = re.search(r"INSERT\s+INTO\s+([\"']?\w+[\"']?)", query, re.IGNORECASE)
            if match:
                return match.group(1).strip("\"'")

        elif query_upper.startswith("TRUNCATE"):
            match = re.search(r"TRUNCATE\s+(?:TABLE\s+)?([\"']?\w+[\"']?)", query, re.IGNORECASE)
            if match:
                return match.group(1).strip("\"'")

        return None

    def extract_where_clause(self, query: str) -> str | None:
        """Extract the WHERE clause from a query."""
        match = re.search(r"WHERE\s+(.+?)(?:ORDER BY|LIMIT|$)", query, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _calculate_risk(
        self,
        query_type: str,
        affected_rows: int,
        total_rows: int,
        has_where: bool,
        cascade_info: list[dict],
    ) -> tuple[Literal["safe", "cautious", "dangerous", "critical"], int, bool, list[str]]:
        """Calculate risk level, score, block decision, and risk factors."""
        risk_factors = []
        risk_score = 0

        # No WHERE clause
        if not has_where and query_type in ("UPDATE", "DELETE"):
            risk_factors.append(f"{query_type} without WHERE clause affects ALL rows")
            risk_score += 50

        # Calculate percentage of table affected
        pct_affected = (affected_rows / total_rows * 100) if total_rows > 0 else 0

        # High percentage of rows affected
        if pct_affected >= self.thresholds["critical_percent"]:
            risk_factors.append(f"Affects {pct_affected:.1f}% of table ({affected_rows:,} of {total_rows:,} rows)")
            risk_score += 40
        elif pct_affected >= self.thresholds["dangerous_percent"]:
            risk_factors.append(f"Affects {pct_affected:.1f}% of table ({affected_rows:,} of {total_rows:,} rows)")
            risk_score += 25

        # Mass operations
        if query_type == "DELETE" and affected_rows > self.thresholds["mass_delete_rows"]:
            risk_factors.append(f"Mass DELETE: {affected_rows:,} rows")
            risk_score += 15
        elif query_type == "UPDATE" and affected_rows > self.thresholds["mass_update_rows"]:
            risk_factors.append(f"Mass UPDATE: {affected_rows:,} rows")
            risk_score += 10

        # Cascade effects
        cascade_rows = sum(c.get("potential_cascade_rows", 0) for c in cascade_info if c.get("on_delete") == "CASCADE")
        if cascade_rows > 0:
            risk_factors.append(f"CASCADE will affect {cascade_rows:,} rows in dependent tables")
            risk_score += min(20, cascade_rows // 100)

        # Determine risk level
        risk_score = min(100, risk_score)

        risk_level: Literal["safe", "cautious", "dangerous", "critical"]
        if risk_score >= 70:
            risk_level = "critical"
            should_block = True
        elif risk_score >= 40:
            risk_level = "dangerous"
            should_block = True
        elif risk_score >= 20:
            risk_level = "cautious"
            should_block = False
        else:
            risk_level = "safe"
            should_block = False

        return risk_level, risk_score, should_block, risk_factors

    def _generate_rollback_sql(
        self,
        query_type: str,
        table: str,
        schema: str,
        sample_rows: list[dict],
    ) -> tuple[str | None, int]:
        """Generate rollback SQL for DELETE operations."""
        if query_type != "DELETE" or not sample_rows:
            return None, 0

        columns = list(sample_rows[0].keys())
        if not columns:
            return None, 0

        col_list = ", ".join(f'"{c}"' for c in columns)

        values_list = []
        for row in sample_rows:
            values = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    values.append("NULL")
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                elif isinstance(val, bool):
                    values.append("TRUE" if val else "FALSE")
                else:
                    escaped = str(val).replace("'", "''")
                    values.append(f"'{escaped}'")
            values_list.append(f"({', '.join(values)})")

        rollback_sql = f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES\n' + ",\n".join(values_list) + ";"

        return rollback_sql, len(sample_rows)

    async def analyze_delete(
        self,
        query: str,
        sample_limit: int = 10,
        schema: str = "public",
        generate_rollback: bool = True,
    ) -> ImpactPreview:
        """Analyze the impact of a DELETE query with risk scoring and rollback SQL."""
        table = self.extract_table_name(query)
        if not table:
            raise ValueError("Could not extract table name from DELETE query")

        where_clause = self.extract_where_clause(query)

        count_query = build_count_query(table, schema, where_clause)
        total_count_query = build_count_query(table, schema, None)
        sample_query = build_select_query(table, schema, where_clause, sample_limit)

        timeout = self._get_timeout()
        affected_count = await self._pool.fetchval(count_query, timeout=timeout) or 0
        total_count = await self._pool.fetchval(total_count_query, timeout=timeout) or 0
        sample_rows = await self._pool.fetch(sample_query, timeout=timeout)
        sample_rows_dict = [dict(r) for r in sample_rows]

        cascade_info = await self._get_cascade_info(table, schema)

        # Calculate risk
        risk_level, risk_score, should_block, risk_factors = self._calculate_risk(
            "DELETE", affected_count, total_count, bool(where_clause), cascade_info
        )

        # Generate rollback SQL
        rollback_sql, rollback_row_count = None, 0
        rollback_warning = None
        if generate_rollback and sample_rows_dict:
            rollback_sql, rollback_row_count = self._generate_rollback_sql("DELETE", table, schema, sample_rows_dict)
            # Warn if rollback is partial
            if rollback_row_count < affected_count:
                rollback_warning = (
                    f"PARTIAL ROLLBACK: Only {rollback_row_count} of {affected_count:,} rows captured. "
                    f"Increase sample_limit to capture more rows for full rollback."
                )

        # Generate warning message
        warning = None
        if not where_clause:
            warning = "CRITICAL: No WHERE clause - this will delete ALL rows!"
        elif risk_level in ("dangerous", "critical"):
            warning = f"WARNING: High-risk operation affecting {affected_count:,} rows ({affected_count / total_count * 100:.1f}% of table)"
        elif affected_count > 1000:
            warning = f"WARNING: This will affect {affected_count:,} rows"

        return ImpactPreview(
            query_type="DELETE",
            target_table=f"{schema}.{table}",
            affected_rows=affected_count,
            sample_rows=sample_rows_dict,
            cascade_info=cascade_info,
            warning=warning,
            risk_level=risk_level,
            risk_score=risk_score,
            should_block=should_block,
            risk_factors=risk_factors,
            rollback_sql=rollback_sql,
            rollback_row_count=rollback_row_count,
            rollback_warning=rollback_warning,
        )

    async def analyze_update(
        self,
        query: str,
        sample_limit: int = 10,
        schema: str = "public",
    ) -> ImpactPreview:
        """Analyze the impact of an UPDATE query with risk scoring."""
        table = self.extract_table_name(query)
        if not table:
            raise ValueError("Could not extract table name from UPDATE query")

        where_clause = self.extract_where_clause(query)

        count_query = build_count_query(table, schema, where_clause)
        total_count_query = build_count_query(table, schema, None)
        sample_query = build_select_query(table, schema, where_clause, sample_limit)

        timeout = self._get_timeout()
        affected_count = await self._pool.fetchval(count_query, timeout=timeout) or 0
        total_count = await self._pool.fetchval(total_count_query, timeout=timeout) or 0
        sample_rows = await self._pool.fetch(sample_query, timeout=timeout)
        sample_rows_dict = [dict(r) for r in sample_rows]

        # Calculate risk (no cascade for UPDATE typically)
        risk_level, risk_score, should_block, risk_factors = self._calculate_risk(
            "UPDATE", affected_count, total_count, bool(where_clause), []
        )

        # Generate warning message
        warning = None
        if not where_clause:
            warning = "CRITICAL: No WHERE clause - this will update ALL rows!"
        elif risk_level in ("dangerous", "critical"):
            warning = f"WARNING: High-risk operation affecting {affected_count:,} rows ({affected_count / total_count * 100:.1f}% of table)"
        elif affected_count > 1000:
            warning = f"WARNING: This will affect {affected_count:,} rows"

        return ImpactPreview(
            query_type="UPDATE",
            target_table=f"{schema}.{table}",
            affected_rows=affected_count,
            sample_rows=sample_rows_dict,
            cascade_info=[],
            warning=warning,
            risk_level=risk_level,
            risk_score=risk_score,
            should_block=should_block,
            risk_factors=risk_factors,
            rollback_sql=None,
            rollback_row_count=0,
        )

    async def _get_cascade_info(self, table: str, schema: str = "public") -> list[dict]:
        """Get information about cascade effects.

        Optimized to batch COUNT queries for CASCADE tables into a single query
        to avoid N+1 performance issues.
        """
        timeout = self._get_timeout()
        rows = await self._pool.fetch(AnalyzerQueries.GET_CASCADE_INFO, table, schema, timeout=timeout)

        if not rows:
            return []

        # Collect and validate tables that need row counts (only CASCADE deletes)
        cascade_tables = []
        for row in rows:
            if row["delete_rule"] == "CASCADE":
                tbl = row["dependent_table"]
                try:
                    # Validate table name to prevent SQL injection
                    SQLSanitizer.validate_identifier(tbl, "table")
                    cascade_tables.append(tbl)
                except ValueError:
                    # Skip tables with invalid names (shouldn't happen with real DB data)
                    continue

        # Validate schema name as well
        try:
            SQLSanitizer.validate_identifier(schema, "schema")
        except ValueError:
            # Invalid schema - return basic cascade info without counts
            return [
                {
                    "table": row["dependent_table"],
                    "column": row["dependent_column"],
                    "on_delete": row["delete_rule"],
                    "on_update": row["update_rule"],
                }
                for row in rows
            ]

        # Batch fetch row counts in a single query if there are cascade tables
        table_counts: dict[str, int] = {}
        if cascade_tables:
            # Build a single query to count all cascade tables at once
            # Using UNION ALL for efficiency (table names already validated above)
            count_parts = [
                f'SELECT \'{tbl}\' as table_name, COUNT(*) as cnt FROM "{schema}"."{tbl}"' for tbl in cascade_tables
            ]
            batch_count_query = " UNION ALL ".join(count_parts)

            try:
                count_rows = await self._pool.fetch(batch_count_query, timeout=timeout)
                table_counts = {row["table_name"]: row["cnt"] for row in count_rows}
            except Exception:
                # Continue with empty counts - counts are informational, not critical
                # Common causes: table doesn't exist, permission denied
                table_counts = {}

        # Build cascade info with pre-fetched counts
        cascade_info = []
        for row in rows:
            info = {
                "table": row["dependent_table"],
                "column": row["dependent_column"],
                "on_delete": row["delete_rule"],
                "on_update": row["update_rule"],
            }

            if row["delete_rule"] == "CASCADE":
                info["potential_cascade_rows"] = table_counts.get(row["dependent_table"], 0)

            cascade_info.append(info)

        return cascade_info

    async def analyze_impact(
        self,
        query: str,
        sample_limit: int = 10,
        schema: str = "public",
        generate_rollback: bool = True,
        timeout_ms: int | None = None,
    ) -> ImpactPreview:
        """Analyze the impact of any write query with risk scoring.

        Args:
            query: SQL write query to analyze
            sample_limit: Max sample rows to return
            schema: Schema name
            generate_rollback: Whether to generate rollback SQL
            timeout_ms: Query timeout in milliseconds (default 30000)
        """
        # Set timeout for this analysis run (convert ms to seconds)
        self._current_timeout = (timeout_ms / 1000) if timeout_ms else None
        try:
            query_type = self.parse_query_type(query)

            if query_type == "DELETE":
                return await self.analyze_delete(query, sample_limit, schema, generate_rollback)
            elif query_type == "UPDATE":
                return await self.analyze_update(query, sample_limit, schema)
            elif query_type == "INSERT":
                table = self.extract_table_name(query)
                return ImpactPreview(
                    query_type="INSERT",
                    target_table=f"{schema}.{table}" if table else "unknown",
                    affected_rows=1,
                    sample_rows=[],
                    cascade_info=[],
                    warning=None,
                    risk_level="safe",
                    risk_score=0,
                    should_block=False,
                    risk_factors=[],
                )
            elif query_type == "TRUNCATE":
                table = self.extract_table_name(query)
                return ImpactPreview(
                    query_type="TRUNCATE",
                    target_table=f"{schema}.{table}" if table else "unknown",
                    affected_rows=-1,
                    sample_rows=[],
                    cascade_info=[],
                    warning="CRITICAL: TRUNCATE will delete ALL rows instantly and cannot be easily rolled back!",
                    risk_level="critical",
                    risk_score=100,
                    should_block=True,
                    risk_factors=[
                        "TRUNCATE deletes all rows",
                        "Cannot be rolled back in a transaction",
                        "Resets sequences",
                    ],
                )
            elif query_type == "DROP":
                return ImpactPreview(
                    query_type="DROP",
                    target_table="unknown",
                    affected_rows=-1,
                    sample_rows=[],
                    cascade_info=[],
                    warning="CRITICAL: DROP will permanently delete the object and all its data!",
                    risk_level="critical",
                    risk_score=100,
                    should_block=True,
                    risk_factors=["DROP permanently deletes object", "All data will be lost", "Cannot be undone"],
                )
            else:
                raise ValueError(f"Cannot analyze impact for query type: {query_type}")
        finally:
            # Reset timeout after call
            self._current_timeout = None
