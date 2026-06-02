"""Batch query analysis with cross-query detection and enhanced metrics."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from models import (
    BatchAnalysisResult,
    BatchAnalysisSummary,
    CrossQueryInsights,
    DuplicateGroup,
    EnhancedQueryAnalysis,
    ExecutionPlanInfo,
    IndexRecommendation,
    JoinInfo,
    NPlusOneCandidate,
    QueryInput,
)
from query.parsing_utils import ParsedExpr, QueryParserMixin

if TYPE_CHECKING:
    from db import DatabasePool, SchemaDiscovery


class BatchQueryAnalyzer(QueryParserMixin):
    """Analyzes multiple SQL queries with cross-query insights.

    Provides enhanced analysis beyond single-query parsing:
    - Duplicate/similar query detection
    - N+1 query pattern detection
    - Cross-query table access patterns
    - Optimization opportunities across query batches
    - Index recommendations based on schema

    Inherits common parsing methods from QueryParserMixin:
    - _get_query_type(), _extract_tables(), _extract_columns()
    - _extract_joins(), _extract_where()
    - _has_aggregation(), _has_subquery(), _has_limit()

    Attributes:
        dialect: SQL dialect for parsing (default: "postgres")
    """

    def __init__(
        self,
        pool: Optional["DatabasePool"] = None,
        schema_discovery: Optional["SchemaDiscovery"] = None,
        dialect: str = "postgres",
    ):
        self._pool = pool
        self._schema = schema_discovery
        self.dialect = dialect

    async def analyze_batch(
        self,
        queries: list[QueryInput],
        include_explain: bool = False,
        detect_duplicates: bool = True,
        schema_name: str = "public",
    ) -> BatchAnalysisResult:
        """
        Analyze a batch of queries with enhanced metrics and cross-query insights.
        """
        results: list[EnhancedQueryAnalysis] = []

        # Analyze each query individually
        for query_input in queries:
            try:
                analysis = await self._analyze_single(query_input, include_explain, schema_name)
                results.append(analysis)
            except Exception as e:
                # Create error result
                results.append(
                    EnhancedQueryAnalysis(
                        id=query_input.id,
                        name=query_input.name,
                        source=query_input.source,
                        sql=query_input.sql,
                        valid=False,
                        query_type="UNKNOWN",
                        tables=[],
                        columns=[],
                        joins=[],
                        where_conditions=[],
                        has_aggregation=False,
                        has_subquery=False,
                        has_limit=False,
                        complexity_score=0,
                        risk_level="unknown",
                        purpose="unknown",
                        error=str(e),
                    )
                )

        # Cross-query analysis
        cross_insights = CrossQueryInsights()
        if detect_duplicates and len(results) > 1:
            cross_insights = self._analyze_cross_query(results)
            # Update similar_to fields
            for dup_group in cross_insights.duplicates:
                for qid in dup_group.query_ids:
                    for result in results:
                        if result.id == qid:
                            result.similar_to = [other_id for other_id in dup_group.query_ids if other_id != qid]

        # Generate summary
        summary = self._generate_summary(results)

        return BatchAnalysisResult(
            summary=summary,
            queries=results,
            cross_query_insights=cross_insights,
            generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    async def _analyze_single(
        self,
        query_input: QueryInput,
        include_explain: bool,
        schema_name: str,
    ) -> EnhancedQueryAnalysis:
        """Analyze a single query with enhanced metrics."""
        sql = query_input.sql

        try:
            parsed = sqlglot.parse_one(sql, dialect=self.dialect)
        except ParseError as e:
            return EnhancedQueryAnalysis(
                id=query_input.id,
                name=query_input.name,
                source=query_input.source,
                sql=sql,
                valid=False,
                query_type="UNKNOWN",
                tables=[],
                columns=[],
                joins=[],
                where_conditions=[],
                has_aggregation=False,
                has_subquery=False,
                has_limit=False,
                complexity_score=0,
                risk_level="unknown",
                purpose="unknown",
                error=f"SQL syntax error: {str(e)}",
            )

        # Extract basic info
        query_type = self._get_query_type(parsed)
        tables = self._extract_tables(parsed)
        columns = self._extract_columns(parsed)
        joins = self._extract_joins(parsed)
        where_conditions = self._extract_where(parsed)
        has_aggregation = self._has_aggregation(parsed)
        has_subquery = self._has_subquery(parsed)
        has_limit = self._has_limit(parsed)

        # Enhanced metrics
        complexity = self._calculate_complexity(parsed, tables, joins, has_subquery)
        risk = self._assess_risk(query_type, where_conditions, tables, complexity)
        purpose = self._detect_purpose(query_type, has_aggregation, tables)

        # Generate warnings, optimizations, info
        warnings = self._generate_warnings(query_type, where_conditions, has_limit, parsed)
        optimizations = self._generate_optimizations(parsed, tables, joins, has_limit)
        info = self._generate_info(query_type, tables, columns)

        # Index recommendations
        index_recs = []
        if self._schema:
            index_recs = await self._generate_index_recommendations(
                tables, columns, where_conditions, joins, schema_name
            )

        # Execution plan
        exec_plan = None
        if include_explain and self._pool and self._pool.is_connected:
            exec_plan = await self._get_execution_plan(sql)

        # Format query
        try:
            formatted = parsed.sql(dialect=self.dialect, pretty=True)
        except Exception:
            formatted = sql

        return EnhancedQueryAnalysis(
            id=query_input.id,
            name=query_input.name,
            source=query_input.source,
            sql=sql,
            valid=True,
            query_type=query_type,
            tables=tables,
            columns=columns,
            joins=joins,
            where_conditions=where_conditions,
            has_aggregation=has_aggregation,
            has_subquery=has_subquery,
            has_limit=has_limit,
            complexity_score=complexity,
            risk_level=risk,
            purpose=purpose,
            index_recommendations=index_recs,
            execution_plan=exec_plan,
            warnings=warnings,
            optimizations=optimizations,
            info=info,
            formatted_query=formatted,
        )

    # Note: Common parsing methods (_get_query_type, _extract_tables, _extract_columns,
    # _extract_joins, _extract_where, _has_aggregation, _has_subquery, _has_limit)
    # are inherited from QueryParserMixin

    def _calculate_complexity(
        self, parsed: ParsedExpr, tables: list[str], joins: list[JoinInfo], has_subquery: bool
    ) -> int:
        """Calculate complexity score (1-10)."""
        score = 1

        # Tables
        score += min(len(tables) - 1, 3)  # +1 per table, max +3

        # Joins
        score += min(len(joins), 3)  # +1 per join, max +3

        # Subqueries
        if has_subquery:
            subquery_count = len(list(parsed.find_all(exp.Subquery)))
            score += min(subquery_count * 2, 4)  # +2 per subquery, max +4

        # Aggregations with GROUP BY
        if parsed.find(exp.Group):
            score += 1

        # HAVING clause
        if parsed.find(exp.Having):
            score += 1

        # UNION/INTERSECT/EXCEPT
        if parsed.find(exp.Union) or parsed.find(exp.Intersect) or parsed.find(exp.Except):
            score += 2

        # Window functions
        if parsed.find(exp.Window):
            score += 2

        # CTEs
        if parsed.find(exp.With):
            score += 2

        return min(score, 10)

    def _assess_risk(self, query_type: str, where_conditions: list[str], tables: list[str], complexity: int) -> str:
        """Assess risk level."""
        # Critical: DELETE/UPDATE without WHERE
        if query_type in ("DELETE", "UPDATE") and not where_conditions:
            return "critical"

        # High: DROP, TRUNCATE, or high complexity writes
        if query_type in ("DROP", "TRUNCATE"):
            return "high"

        if query_type in ("DELETE", "UPDATE") and complexity >= 7:
            return "high"

        # Medium: writes with WHERE, or complex reads
        if query_type in ("DELETE", "UPDATE", "INSERT"):
            return "medium"

        if complexity >= 7:
            return "medium"

        # Low: simple reads
        return "low"

    def _detect_purpose(self, query_type: str, has_aggregation: bool, tables: list[str]) -> str:
        """Detect query purpose."""
        if query_type in ("CREATE", "DROP", "ALTER", "TRUNCATE"):
            return "admin"

        if query_type in ("INSERT", "UPDATE", "DELETE"):
            return "write"

        if has_aggregation:
            return "analytics"

        return "read"

    def _generate_warnings(
        self, query_type: str, where_conditions: list[str], has_limit: bool, parsed: ParsedExpr
    ) -> list[str]:
        """Generate warning messages for anti-patterns."""
        warnings = []

        # CRITICAL: DELETE/UPDATE without WHERE
        if query_type in ("UPDATE", "DELETE") and not where_conditions:
            warnings.append(f"CRITICAL: {query_type} without WHERE clause will affect ALL rows!")

        # SELECT * over-fetching
        if any(parsed.find_all(exp.Star)):
            warnings.append("SELECT * returns all columns - consider selecting specific columns")

        # No LIMIT on SELECT
        if query_type == "SELECT" and not has_limit and not self._has_aggregation(parsed):
            warnings.append("No LIMIT clause - query may return many rows")

        # Anti-patterns in WHERE clause
        for where in parsed.find_all(exp.Where):
            # Function on column prevents index usage (exclude logical operators)
            for func in where.find_all(exp.Func):
                if hasattr(func, "key") and func.key and func.key.upper() not in ("AND", "OR", "NOT"):
                    func_sql = func.sql(dialect=self.dialect)
                    warnings.append(f"Function in WHERE prevents index: {func_sql}")

            # OR conditions can prevent index usage
            or_count = len(list(where.find_all(exp.Or)))
            if or_count > 0:
                warnings.append(f"OR condition in WHERE ({or_count}x) may prevent index usage - consider UNION")

            # LIKE with leading wildcard
            for like in where.find_all(exp.Like):
                if like.expression:
                    pattern_node = like.expression
                    pattern = ""
                    if hasattr(pattern_node, "this"):
                        pattern = str(pattern_node.this)
                    elif hasattr(pattern_node, "name"):
                        pattern = str(pattern_node.name)
                    else:
                        pattern = str(pattern_node)
                    if pattern.startswith("%") or pattern.startswith("'%") or pattern.startswith('"%'):
                        warnings.append("LIKE with leading wildcard cannot use index")

            # NOT IN with subquery - NULL handling issues
            for not_node in where.find_all(exp.Not):
                for in_node in not_node.find_all(exp.In):
                    if in_node.find(exp.Subquery):
                        warnings.append("NOT IN with subquery - returns no rows if subquery has NULL values")

            # IN with large list
            for in_node in where.find_all(exp.In):
                if hasattr(in_node, "expressions") and in_node.expressions:
                    if len(in_node.expressions) > 100:
                        warnings.append(
                            f"IN clause with {len(in_node.expressions)} values - consider temp table or ANY(array)"
                        )

        # Correlated subquery detection
        subqueries = list(parsed.find_all(exp.Subquery))
        for subq in subqueries:
            # Check if subquery references outer table
            outer_tables = {t.name for t in parsed.find_all(exp.Table) if t not in subq.find_all(exp.Table)}
            inner_cols = {c.table for c in subq.find_all(exp.Column) if c.table}
            if outer_tables & inner_cols:
                warnings.append("Correlated subquery detected - executes once per outer row, consider JOIN")

        # Multiple tables without JOIN (cartesian product)
        tables = list(parsed.find_all(exp.Table))
        joins = list(parsed.find_all(exp.Join))
        if len(tables) > 1:
            if not joins and not where_conditions:
                warnings.append("DANGER: Multiple tables without JOIN or WHERE = cartesian product!")
            elif joins and not where_conditions:
                unconditioned = [j for j in joins if not j.args.get("on")]
                if unconditioned:
                    warnings.append("DANGER: Implicit cross join (comma-separated tables) = cartesian product!")

        # DISTINCT might hide join issues
        if parsed.find(exp.Distinct) and joins:
            warnings.append("DISTINCT with JOINs often indicates incorrect join - verify logic")

        # ORDER BY on expression
        for order in parsed.find_all(exp.Order):
            for expr in order.find_all(exp.Func):
                warnings.append(f"ORDER BY on expression '{expr.sql()}' - cannot use index")

        # OFFSET without ORDER BY (non-deterministic)
        if parsed.find(exp.Offset) and not parsed.find(exp.Order):
            warnings.append("OFFSET without ORDER BY - results are non-deterministic")

        # Large OFFSET performance
        for offset in parsed.find_all(exp.Offset):
            if hasattr(offset, "expression") and offset.expression:
                try:
                    offset_val = int(str(offset.expression.this))
                    if offset_val > 1000:
                        warnings.append(f"Large OFFSET ({offset_val}) - consider keyset pagination")
                except (ValueError, AttributeError):
                    pass

        return warnings

    def _generate_optimizations(
        self, parsed: ParsedExpr, tables: list[str], joins: list[JoinInfo], has_limit: bool
    ) -> list[str]:
        """Generate optimization suggestions."""
        optimizations = []

        # Add LIMIT
        if not has_limit and not self._has_aggregation(parsed):
            optimizations.append("Add LIMIT to prevent large result sets")

        # Use explicit JOIN
        if len(tables) > 1 and not joins:
            optimizations.append("Use explicit JOIN syntax instead of comma-separated tables")

        # SELECT * with JOINs
        if any(parsed.find_all(exp.Star)) and joins:
            optimizations.append("SELECT * with JOINs returns duplicate column names - list columns explicitly")

        # DISTINCT optimization
        if parsed.find(exp.Distinct):
            if not parsed.find(exp.Order):
                optimizations.append("Add ORDER BY with DISTINCT for consistent results")
            if joins:
                optimizations.append("Replace DISTINCT with proper JOIN conditions or GROUP BY")

        # Subquery to JOIN conversion
        subqueries = list(parsed.find_all(exp.Subquery))
        if subqueries:
            for subq in subqueries:
                # IN subquery can often be JOIN
                parent = subq.parent
                if parent and isinstance(parent, exp.In):
                    optimizations.append("IN (subquery) can often be rewritten as JOIN for better performance")
                    break

        # EXISTS vs IN
        for in_node in parsed.find_all(exp.In):
            if in_node.find(exp.Subquery):
                optimizations.append("Consider EXISTS instead of IN for subqueries - often faster")
                break

        # COUNT(*) vs COUNT(1) vs COUNT(column)
        for count in parsed.find_all(exp.Count):
            if count.find(exp.Star):
                pass  # COUNT(*) is fine
            elif count.this and hasattr(count.this, "name"):
                optimizations.append("COUNT(column) excludes NULLs - use COUNT(*) if you want all rows")
                break

        # UNION vs UNION ALL
        for union in parsed.find_all(exp.Union):
            if union.args.get("distinct") is not False:
                optimizations.append("UNION removes duplicates (slow) - use UNION ALL if duplicates are acceptable")
                break

        # ORDER BY in subquery
        for subq in parsed.find_all(exp.Subquery):
            if subq.find(exp.Order) and not subq.find(exp.Limit):
                optimizations.append("ORDER BY in subquery without LIMIT is ignored - remove for clarity")
                break

        # Multiple OR on same column - use IN
        for where in parsed.find_all(exp.Where):
            or_nodes = list(where.find_all(exp.Or))
            if len(or_nodes) >= 2:
                optimizations.append("Multiple OR conditions - consider using IN clause instead")
                break

        # SELECT with no columns used
        for select in parsed.find_all(exp.Select):
            if select.find(exp.Count) and select.find(exp.Star):
                # COUNT(*) is fine
                pass
            elif len(list(select.find_all(exp.Column))) > 10:
                optimizations.append("Query selects many columns - ensure all are needed")
                break

        return optimizations

    def _generate_info(self, query_type: str, tables: list[str], columns: list[str]) -> list[str]:
        """Generate informational messages."""
        info = []

        info.append(f"Query type: {query_type}")
        info.append(f"Tables accessed: {len(tables)}")
        info.append(f"Columns referenced: {len(columns)}")

        return info

    async def _generate_index_recommendations(
        self,
        tables: list[str],
        columns: list[str],
        where_conditions: list[str],
        joins: list[JoinInfo],
        schema_name: str,
    ) -> list[IndexRecommendation]:
        """Generate index recommendations based on query and schema."""
        recommendations: list[IndexRecommendation] = []

        if not self._schema:
            return recommendations

        # Get existing indexes for comparison
        try:
            schema_tables = await self._schema.get_full_schema(schema_name)
            existing_indexes = {}
            for table in schema_tables:
                existing_indexes[table.name] = [set(idx.columns) for idx in table.indexes]
        except Exception:
            return recommendations

        # Extract columns used in WHERE clauses
        where_columns = []
        for cond in where_conditions:
            # Simple extraction - look for column names
            for col in columns:
                if "." in col:
                    _, col_name = col.rsplit(".", 1)
                else:
                    col_name = col
                if col_name in cond:
                    where_columns.append(col)

        # Check if WHERE columns have indexes
        for col in where_columns:
            table_name: str | None
            if "." in col:
                table_name, col_name = col.rsplit(".", 1)
            else:
                col_name = col
                table_name = tables[0] if tables else None

            if table_name and table_name in existing_indexes:
                # Check if column is indexed
                has_index = any(col_name in idx_cols for idx_cols in existing_indexes[table_name])
                if not has_index:
                    recommendations.append(
                        IndexRecommendation(
                            table=table_name,
                            columns=[col_name],
                            reason=f"Column '{col_name}' used in WHERE clause but not indexed",
                            impact="medium",
                        )
                    )

        # Check JOIN columns
        for join in joins:
            if join.condition:
                # Simple check for unindexed join columns
                for col in columns:
                    if "." in col and col in join.condition:
                        table_name, col_name = col.rsplit(".", 1)
                        if table_name in existing_indexes:
                            has_index = any(col_name in idx_cols for idx_cols in existing_indexes[table_name])
                            if not has_index:
                                recommendations.append(
                                    IndexRecommendation(
                                        table=table_name,
                                        columns=[col_name],
                                        reason=f"Column '{col_name}' used in JOIN but not indexed",
                                        impact="high",
                                    )
                                )

        return recommendations

    async def _get_execution_plan(self, sql: str) -> ExecutionPlanInfo | None:
        """Get execution plan from database."""
        if not self._pool:
            return None

        try:
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            rows = await self._pool.fetch(explain_sql)

            if not rows:
                return None

            plan_data = rows[0].get("QUERY PLAN", [])
            if not plan_data:
                return None

            plan = plan_data[0].get("Plan", {}) if plan_data else {}

            warnings = []
            scan_type = plan.get("Node Type", "")

            # Detect potential issues
            if "Seq Scan" in scan_type:
                warnings.append("Sequential scan detected - consider adding index")

            return ExecutionPlanInfo(
                plan_type=scan_type,
                estimated_cost=plan.get("Total Cost"),
                estimated_rows=plan.get("Plan Rows"),
                scan_type=scan_type,
                index_used=plan.get("Index Name"),
                warnings=warnings,
                raw_plan=plan,
            )
        except Exception:
            # Execution plan retrieval failed - non-critical, query analysis can proceed without it
            # Common causes: syntax error in query, permission denied, connection issues
            return None

    def _analyze_cross_query(self, results: list[EnhancedQueryAnalysis]) -> CrossQueryInsights:
        """Analyze queries together for patterns."""
        insights = CrossQueryInsights()

        # Detect duplicates
        insights.duplicates = self._detect_duplicates(results)

        # Detect N+1 patterns
        insights.n_plus_one_candidates = self._detect_n_plus_one(results)

        # Calculate table access patterns
        table_counts: dict[str, int] = defaultdict(int)
        for result in results:
            for table in result.tables:
                table_counts[table] += 1
        insights.table_access_patterns = dict(table_counts)

        # Generate optimization opportunities
        insights.optimization_opportunities = self._find_optimization_opportunities(results)

        return insights

    def _detect_duplicates(self, results: list[EnhancedQueryAnalysis]) -> list[DuplicateGroup]:
        """Detect duplicate or similar queries."""
        duplicates = []

        # Group by normalized SQL hash
        sql_hashes = defaultdict(list)
        structural_hashes = defaultdict(list)

        for result in results:
            if not result.valid:
                continue

            # Exact duplicates (normalized SQL)
            sql_hash = hashlib.md5(result.sql.strip().lower().encode()).hexdigest()
            sql_hashes[sql_hash].append(result.id)

            # Structural duplicates (same tables, joins, columns pattern)
            struct_key = (
                tuple(sorted(result.tables)),
                tuple(sorted(j.table for j in result.joins)),
                result.query_type,
            )
            structural_hashes[struct_key].append(result.id)

        # Report exact duplicates
        for _sql_hash, query_ids in sql_hashes.items():
            if len(query_ids) > 1:
                duplicates.append(
                    DuplicateGroup(
                        query_ids=query_ids, similarity_type="exact", description="Identical queries detected"
                    )
                )

        # Report structural duplicates (not already in exact)
        exact_ids = set()
        for group in duplicates:
            exact_ids.update(group.query_ids)

        for struct_key, query_ids in structural_hashes.items():
            if len(query_ids) > 1:
                # Filter out exact duplicates
                non_exact = [qid for qid in query_ids if qid not in exact_ids]
                if len(non_exact) > 1:
                    duplicates.append(
                        DuplicateGroup(
                            query_ids=non_exact,
                            similarity_type="structural",
                            description=f"Queries with same structure: tables={struct_key[0]}",
                        )
                    )

        return duplicates

    def _detect_n_plus_one(self, results: list[EnhancedQueryAnalysis]) -> list[NPlusOneCandidate]:
        """Detect potential N+1 query patterns."""
        candidates = []

        # Group queries by table access
        table_queries = defaultdict(list)
        for result in results:
            if result.valid and result.query_type == "SELECT":
                for table in result.tables:
                    table_queries[table].append(result)

        # Look for patterns where one query gets IDs and many queries use those IDs
        for table, queries in table_queries.items():
            if len(queries) >= 3:
                # Check if queries have similar WHERE patterns
                where_patterns = defaultdict(list)
                for q in queries:
                    for cond in q.where_conditions:
                        # Simple pattern: look for id = or id IN
                        if "id" in cond.lower() or "= " in cond:
                            where_patterns[cond[:20]].append(q.id)

                for _pattern, qids in where_patterns.items():
                    if len(qids) >= 3:
                        candidates.append(
                            NPlusOneCandidate(
                                loop_query_id=qids[0],
                                related_query_ids=qids[1:],
                                pattern=f"Multiple queries on {table} with similar WHERE",
                                suggestion="Consider using JOIN or IN clause to batch these queries",
                            )
                        )

        return candidates

    def _find_optimization_opportunities(self, results: list[EnhancedQueryAnalysis]) -> list[str]:
        """Find cross-query optimization opportunities."""
        opportunities = []

        # Check for queries that could be combined
        table_groups = defaultdict(list)
        for result in results:
            if result.valid and result.query_type == "SELECT":
                tables_key = tuple(sorted(result.tables))
                table_groups[tables_key].append(result)

        for tables, queries in table_groups.items():
            if len(queries) >= 3:
                opportunities.append(
                    f"Multiple queries ({len(queries)}) access same tables {tables} - "
                    "consider combining with UNION or CTE"
                )

        # Check for high complexity queries
        high_complexity = [r for r in results if r.complexity_score >= 8]
        if high_complexity:
            opportunities.append(
                f"{len(high_complexity)} queries have high complexity (8+) - "
                "consider breaking into smaller queries or using views"
            )

        return opportunities

    def _generate_summary(self, results: list[EnhancedQueryAnalysis]) -> BatchAnalysisSummary:
        """Generate summary statistics."""
        successful = [r for r in results if r.valid]
        failed = [r for r in results if not r.valid]

        total_warnings = sum(len(r.warnings) for r in results)
        total_optimizations = sum(len(r.optimizations) for r in results)
        high_risk = len([r for r in results if r.risk_level in ("high", "critical")])

        avg_complexity = 0.0
        if successful:
            avg_complexity = sum(r.complexity_score for r in successful) / len(successful)

        return BatchAnalysisSummary(
            total_queries=len(results),
            successful=len(successful),
            failed=len(failed),
            warnings_count=total_warnings,
            optimizations_count=total_optimizations,
            high_risk_count=high_risk,
            avg_complexity=round(avg_complexity, 1),
        )
