"""SQL query parsing and analysis using sqlglot.

This module provides single-query analysis for syntax validation,
anti-pattern detection, and optimization suggestions.

Classes:
    QueryAnalyzer: Analyzes individual SQL queries

The QueryAnalyzer inherits parsing methods from QueryParserMixin
and adds query-specific analysis:
    - Syntax validation
    - Anti-pattern warnings (SELECT *, missing WHERE, cartesian products)
    - Security warnings (DROP, TRUNCATE, GRANT/REVOKE)
    - Optimization suggestions

Usage:
    analyzer = QueryAnalyzer(dialect="postgres")
    result = analyzer.analyze("SELECT * FROM users WHERE id = 1")
    print(result.warnings)  # List of potential issues
    print(result.suggestions)  # Optimization suggestions
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from models import JoinInfo, QueryAnalysis
from query.parsing_utils import ParsedExpr, QueryParserMixin


class QueryAnalyzer(QueryParserMixin):
    """Analyzes single SQL queries for syntax, anti-patterns, and suggestions.

    Inherits common parsing methods from QueryParserMixin.
    """

    def __init__(self, dialect: str = "postgres"):
        self.dialect = dialect

    def analyze(self, query: str) -> QueryAnalysis:
        try:
            parsed = sqlglot.parse_one(query, dialect=self.dialect)
        except ParseError as e:
            return QueryAnalysis(
                valid=False,
                query_type="UNKNOWN",
                tables=[],
                columns=[],
                joins=[],
                where_conditions=[],
                has_aggregation=False,
                has_subquery=False,
                has_limit=False,
                warnings=[],
                suggestions=[],
                error=f"SQL syntax error: {str(e)}",
            )

        query_type = self._get_query_type(parsed)
        tables = self._extract_tables(parsed)
        columns = self._extract_columns(parsed)
        joins = self._extract_joins(parsed)
        where_conditions = self._extract_where(parsed)
        has_aggregation = self._has_aggregation(parsed)
        has_subquery = self._has_subquery(parsed)
        has_limit = self._has_limit(parsed)

        warnings = self._generate_warnings(query_type, tables, where_conditions, has_limit, parsed)
        suggestions = self._generate_suggestions(query_type, tables, columns, joins, has_aggregation, has_limit)

        try:
            formatted = parsed.sql(dialect=self.dialect, pretty=True)
        except Exception:
            formatted = query

        return QueryAnalysis(
            valid=True,
            query_type=query_type,
            tables=tables,
            columns=columns,
            joins=joins,
            where_conditions=where_conditions,
            has_aggregation=has_aggregation,
            has_subquery=has_subquery,
            has_limit=has_limit,
            warnings=warnings,
            suggestions=suggestions,
            formatted_query=formatted,
        )

    def _generate_warnings(
        self,
        query_type: str,
        tables: list[str],
        where_conditions: list[str],
        has_limit: bool,
        parsed: ParsedExpr,
    ) -> list[str]:
        """Generate warning messages for anti-patterns and dangerous queries."""
        warnings: list[str] = []

        # CRITICAL: DROP statement
        if query_type == "DROP":
            target = tables[0] if tables else "object"
            warnings.append(f"CRITICAL: DROP will permanently delete '{target}' and all its data!")

        # CRITICAL: TRUNCATE statement
        if query_type == "TRUNCATE":
            target = tables[0] if tables else "table"
            warnings.append(
                f"CRITICAL: TRUNCATE will instantly delete ALL rows from '{target}'! Cannot be rolled back easily."
            )

        # Security: GRANT/REVOKE
        if query_type == "GRANT":
            warnings.append("SECURITY: GRANT statement will modify database permissions")

        if query_type == "REVOKE":
            warnings.append("SECURITY: REVOKE statement will remove database permissions")

        # CRITICAL: DELETE/UPDATE without WHERE
        if query_type in ("UPDATE", "DELETE") and not where_conditions:
            warnings.append(f"CRITICAL: {query_type} without WHERE clause will affect ALL rows!")

        # SELECT * over-fetching
        if any(parsed.find_all(exp.Star)):
            warnings.append("SELECT * returns all columns - consider selecting specific columns")

        # No LIMIT
        if query_type == "SELECT" and not has_limit and not self._has_aggregation(parsed):
            warnings.append("No LIMIT clause - query may return many rows")

        # Cartesian product detection
        joins = list(parsed.find_all(exp.Join))
        if len(tables) > 1:
            if not joins and not where_conditions:
                warnings.append("DANGER: Multiple tables without JOIN or WHERE = cartesian product!")
            elif joins and not where_conditions:
                unconditioned_joins = [j for j in joins if not j.args.get("on")]
                if unconditioned_joins:
                    warnings.append("DANGER: Implicit cross join (comma-separated tables) = cartesian product!")

        # Anti-patterns in WHERE
        for where in parsed.find_all(exp.Where):
            for func in where.find_all(exp.Func):
                if hasattr(func, "key") and func.key and func.key.upper() not in ("AND", "OR", "NOT"):
                    warnings.append(f"Function in WHERE prevents index: {func.sql(dialect=self.dialect)}")

            if list(where.find_all(exp.Or)):
                warnings.append("OR in WHERE may prevent index usage - consider UNION")

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

            for not_node in where.find_all(exp.Not):
                if not_node.find(exp.In) and not_node.find(exp.Subquery):
                    warnings.append("NOT IN with subquery - NULL values cause empty results")

        # DISTINCT with JOINs
        if parsed.find(exp.Distinct) and joins:
            warnings.append("DISTINCT with JOINs often indicates incorrect join logic")

        # Large OFFSET
        for offset in parsed.find_all(exp.Offset):
            if hasattr(offset, "expression") and offset.expression:
                try:
                    val = int(str(getattr(offset.expression, "this", 0)))
                    if val > 1000:
                        warnings.append(f"Large OFFSET ({val}) - consider keyset pagination")
                except (ValueError, AttributeError):
                    pass

        return warnings

    def _generate_suggestions(
        self,
        query_type: str,
        tables: list[str],
        columns: list[str],
        joins: list[JoinInfo],
        has_aggregation: bool,
        has_limit: bool,
    ) -> list[str]:
        """Generate optimization suggestions."""
        suggestions: list[str] = []
        if query_type == "SELECT" and not has_limit and not has_aggregation:
            suggestions.append("Consider adding LIMIT to prevent large result sets")
        if len(tables) > 1 and not any("." in c for c in columns):
            suggestions.append("Consider using table aliases for clarity")
        return suggestions

    def validate(self, query: str) -> tuple[bool, str | None]:
        """Validate SQL syntax without full analysis."""
        try:
            sqlglot.parse_one(query, dialect=self.dialect)
            return True, None
        except ParseError as e:
            return False, str(e)

    def format_query(self, query: str) -> str:
        """Format/prettify a SQL query."""
        try:
            return sqlglot.parse_one(query, dialect=self.dialect).sql(dialect=self.dialect, pretty=True)
        except ParseError:
            return query

    def get_query_type(self, query: str) -> str:
        """Get the query type without full analysis."""
        try:
            return self._get_query_type(sqlglot.parse_one(query, dialect=self.dialect))
        except ParseError:
            return "UNKNOWN"
