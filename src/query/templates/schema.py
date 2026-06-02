"""Schema discovery query templates."""

import re


class SQLSanitizer:
    """Sanitize SQL fragments to prevent injection attacks."""

    # Dangerous patterns that should not appear in WHERE clauses
    DANGEROUS_PATTERNS = [
        r";\s*(?:DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE|GRANT|REVOKE)",
        r"--",  # SQL comment
        r"/\*",  # Block comment start
        r"\*/",  # Block comment end
        r"'\s*;\s*",  # String followed by semicolon
        r"UNION\s+(?:ALL\s+)?SELECT",  # UNION injection
        r"INTO\s+(?:OUTFILE|DUMPFILE)",  # File write attempts
        r"LOAD_FILE",  # File read attempts
        r"pg_sleep",  # Time-based injection
        r"pg_read_file",  # PostgreSQL file read
        r"pg_write_file",  # PostgreSQL file write
        r"lo_import",  # Large object import
        r"lo_export",  # Large object export
    ]

    # Compile patterns for efficiency
    _compiled_patterns = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]

    @classmethod
    def validate_where_clause(cls, where: str | None) -> str | None:
        """Validate and return WHERE clause, or raise ValueError if dangerous.

        Args:
            where: The WHERE clause to validate (without the WHERE keyword)

        Returns:
            The validated WHERE clause, or None if input is None

        Raises:
            ValueError: If the WHERE clause contains dangerous patterns
        """
        if where is None:
            return None

        # Check for dangerous patterns
        for pattern in cls._compiled_patterns:
            if pattern.search(where):
                raise ValueError(
                    f"Potentially dangerous SQL pattern detected in WHERE clause. Pattern matched: {pattern.pattern}"
                )

        # Check for multiple statements (semicolons not in strings)
        # Simple check: if there's a semicolon followed by SQL keywords
        if re.search(r";\s*\w", where):
            raise ValueError("Multiple SQL statements not allowed in WHERE clause")

        return where

    @classmethod
    def validate_identifier(cls, identifier: str, identifier_type: str = "identifier") -> str:
        """Validate a SQL identifier (table name, schema name, column name).

        Args:
            identifier: The identifier to validate
            identifier_type: Type of identifier for error messages

        Returns:
            The validated identifier

        Raises:
            ValueError: If the identifier is invalid
        """
        if not identifier:
            raise ValueError(f"{identifier_type} cannot be empty")

        # Allow alphanumeric, underscore, and dollar sign (PostgreSQL allows these)
        # Also allow quoted identifiers
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_$]*$", identifier):
            # Check if it's a valid quoted identifier
            if not re.match(r'^"[^"]*"$', identifier):
                raise ValueError(
                    f"Invalid {identifier_type}: '{identifier}'. "
                    f"Must be alphanumeric with underscores or a quoted identifier."
                )

        return identifier


class SchemaQueries:
    """Queries for schema discovery."""

    LIST_SCHEMAS = """
        SELECT
            n.nspname as schema_name,
            COUNT(c.relname) as table_count,
            COALESCE(SUM(s.n_live_tup), 0) as total_rows,
            pg_size_pretty(SUM(pg_total_relation_size(c.oid))) as total_size
        FROM pg_namespace n
        LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind = 'r'
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            AND n.nspname NOT LIKE 'pg_temp%'
        GROUP BY n.nspname
        ORDER BY table_count DESC, n.nspname
    """

    LIST_TABLES = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1 AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """

    GET_COLUMNS = """
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
        FROM information_schema.columns c
        LEFT JOIN (
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = $1
                AND tc.table_schema = $2
        ) pk ON c.column_name = pk.column_name
        WHERE c.table_name = $1 AND c.table_schema = $2
        ORDER BY c.ordinal_position
    """

    GET_PRIMARY_KEYS = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_name = $1
            AND tc.table_schema = $2
        ORDER BY kcu.ordinal_position
    """

    GET_FOREIGN_KEYS = """
        SELECT
            kcu.column_name,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column,
            tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = $1
            AND tc.table_schema = $2
    """

    GET_INDEXES = """
        SELECT
            i.relname AS index_name,
            array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) AS columns,
            ix.indisunique AS is_unique,
            pg_get_indexdef(ix.indexrelid) AS definition
        FROM pg_index ix
        JOIN pg_class i ON ix.indexrelid = i.oid
        JOIN pg_class t ON ix.indrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE t.relname = $1 AND n.nspname = $2
        GROUP BY i.relname, ix.indisunique, ix.indexrelid
        ORDER BY i.relname
    """

    GET_RELATIONSHIPS = """
        SELECT
            tc.table_name AS from_table,
            kcu.column_name AS from_column,
            ccu.table_name AS to_table,
            ccu.column_name AS to_column,
            tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = $1
        ORDER BY tc.table_name, kcu.column_name
    """


class AnalyzerQueries:
    """Queries for impact analysis."""

    GET_CASCADE_INFO = """
        SELECT
            tc.table_name AS dependent_table,
            kcu.column_name AS dependent_column,
            rc.delete_rule,
            rc.update_rule
        FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc
            ON rc.constraint_name = tc.constraint_name
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON rc.unique_constraint_name = ccu.constraint_name
        WHERE ccu.table_name = $1
            AND ccu.table_schema = $2
    """


class SystemQueries:
    """System-level queries."""

    GET_VERSION = "SELECT version()"
    COUNT_ROWS = 'SELECT COUNT(*) FROM "{schema}"."{table}"'
    SELECT_ALL = 'SELECT * FROM "{schema}"."{table}"'
    SELECT_WITH_WHERE = 'SELECT * FROM "{schema}"."{table}" WHERE {where}'
    COUNT_WITH_WHERE = 'SELECT COUNT(*) FROM "{schema}"."{table}" WHERE {where}'


def build_count_query(
    table: str,
    schema: str = "public",
    where: str | None = None,
    validate: bool = True,
) -> str:
    """Build a COUNT query for a table.

    Args:
        table: Table name
        schema: Schema name
        where: Optional WHERE clause (without WHERE keyword)
        validate: Whether to validate inputs for SQL injection (default True)

    Returns:
        SQL COUNT query string

    Raises:
        ValueError: If validation is enabled and dangerous patterns are detected
    """
    if validate:
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        where = SQLSanitizer.validate_where_clause(where)

    if where:
        return f'SELECT COUNT(*) FROM "{schema}"."{table}" WHERE {where}'
    return f'SELECT COUNT(*) FROM "{schema}"."{table}"'


def build_select_query(
    table: str,
    schema: str = "public",
    where: str | None = None,
    limit: int | None = None,
    validate: bool = True,
) -> str:
    """Build a SELECT query for a table.

    Args:
        table: Table name
        schema: Schema name
        where: Optional WHERE clause (without WHERE keyword)
        limit: Optional row limit
        validate: Whether to validate inputs for SQL injection (default True)

    Returns:
        SQL SELECT query string

    Raises:
        ValueError: If validation is enabled and dangerous patterns are detected
    """
    if validate:
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        where = SQLSanitizer.validate_where_clause(where)

    query = f'SELECT * FROM "{schema}"."{table}"'
    if where:
        query += f" WHERE {where}"
    if limit is not None and isinstance(limit, int) and limit > 0:
        query += f" LIMIT {limit}"
    return query
