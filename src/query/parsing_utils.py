"""Shared SQL parsing utilities using sqlglot.

This module provides common parsing methods used by both QueryAnalyzer
and BatchQueryAnalyzer to avoid code duplication.

Classes:
    QueryParserMixin: Mixin class providing core SQL parsing methods

Type Aliases:
    ParsedExpr: Union type for sqlglot parsed expressions

The mixin provides these methods:
    - _get_query_type(): Determine query type (SELECT, INSERT, UPDATE, etc.)
    - _extract_tables(): Extract all table names from query
    - _extract_columns(): Extract column references
    - _extract_joins(): Extract JOIN clauses with conditions
    - _extract_where(): Extract WHERE conditions
    - _has_aggregation(): Check for COUNT, SUM, AVG, MIN, MAX
    - _has_subquery(): Check for subqueries
    - _has_limit(): Check for LIMIT clause

Usage:
    class MyAnalyzer(QueryParserMixin):
        def __init__(self, dialect: str = "postgres"):
            self.dialect = dialect

        def analyze(self, query: str):
            parsed = sqlglot.parse_one(query, dialect=self.dialect)
            tables = self._extract_tables(parsed)
            # ... use other mixin methods
"""

from sqlglot import exp

from models import JoinInfo

# Type alias for parsed SQL expressions
ParsedExpr = exp.Expression | exp.Expr


class QueryParserMixin:
    """Mixin providing common SQL parsing methods.

    Both QueryAnalyzer and BatchQueryAnalyzer inherit from this to share
    the core parsing logic without code duplication.
    """

    dialect: str = "postgres"

    def _get_query_type(self, parsed: ParsedExpr) -> str:
        """Determine the SQL query type."""
        type_map = {
            exp.Select: "SELECT",
            exp.Insert: "INSERT",
            exp.Update: "UPDATE",
            exp.Delete: "DELETE",
            exp.Create: "CREATE",
            exp.Drop: "DROP",
            exp.Alter: "ALTER",
        }
        for cls, name in type_map.items():
            if isinstance(parsed, cls):
                return name

        class_name = parsed.__class__.__name__.upper()
        if class_name == "COMMAND":
            sql_upper = parsed.sql().upper().strip()
            if sql_upper.startswith("TRUNCATE"):
                return "TRUNCATE"
            elif sql_upper.startswith("GRANT"):
                return "GRANT"
            elif sql_upper.startswith("REVOKE"):
                return "REVOKE"
        return class_name

    def _extract_tables(self, parsed: ParsedExpr) -> list[str]:
        """Extract all table names from the query."""
        tables: list[str] = []
        for table in parsed.find_all(exp.Table):
            name = f"{table.db}.{table.name}" if table.db else table.name
            if name and name not in tables:
                tables.append(name)
        return tables

    def _extract_columns(self, parsed: ParsedExpr) -> list[str]:
        """Extract all column references from the query."""
        columns: list[str] = []
        for col in parsed.find_all(exp.Column):
            name = f"{col.table}.{col.name}" if col.table else col.name
            if name and name not in columns and name != "*":
                columns.append(name)
        if any(parsed.find_all(exp.Star)) and "*" not in columns:
            columns.insert(0, "*")
        return columns

    def _extract_joins(self, parsed: ParsedExpr) -> list[JoinInfo]:
        """Extract JOIN information from the query."""
        joins: list[JoinInfo] = []
        for join in parsed.find_all(exp.Join):
            join_type = " ".join(filter(None, [join.side, join.kind, "JOIN"])).upper()
            table_expr = join.this
            table_name = table_expr.name if isinstance(table_expr, exp.Table) else ""
            alias = table_expr.alias if isinstance(table_expr, exp.Table) else None
            condition = join.args["on"].sql(dialect=self.dialect) if join.args.get("on") else None
            joins.append(
                JoinInfo(
                    join_type=join_type,
                    table=table_name,
                    alias=alias,
                    condition=condition,
                )
            )
        return joins

    def _extract_where(self, parsed: ParsedExpr) -> list[str]:
        """Extract WHERE clause conditions from the query."""
        return [w.this.sql(dialect=self.dialect) for w in parsed.find_all(exp.Where) if w.this]

    def _has_aggregation(self, parsed: ParsedExpr) -> bool:
        """Check if the query has aggregation functions."""
        return any(parsed.find_all(exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max))

    def _has_subquery(self, parsed: ParsedExpr) -> bool:
        """Check if the query has subqueries."""
        return len(list(parsed.find_all(exp.Subquery))) > 0

    def _has_limit(self, parsed: ParsedExpr) -> bool:
        """Check if the query has a LIMIT clause."""
        return parsed.find(exp.Limit) is not None
