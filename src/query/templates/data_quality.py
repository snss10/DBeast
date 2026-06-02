"""Data quality analysis query templates.

All methods that accept schema/table/column parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class DataQualityQueries:
    """Queries for data quality analysis."""

    @staticmethod
    def null_analysis(schema: str, table_name: str | None = None) -> str:
        """Analyze null values across columns.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND c.table_name = '{table_name}'"
        return f"""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                s.null_frac as null_fraction,
                round((s.null_frac * 100)::numeric, 2) as null_pct,
                CASE
                    WHEN s.null_frac > 0.5 THEN 'high'
                    WHEN s.null_frac > 0.1 THEN 'medium'
                    WHEN s.null_frac > 0 THEN 'low'
                    ELSE 'none'
                END as null_severity
            FROM information_schema.columns c
            LEFT JOIN pg_stats s ON
                s.schemaname = c.table_schema
                AND s.tablename = c.table_name
                AND s.attname = c.column_name
            WHERE c.table_schema = '{schema}'
                {table_filter}
            ORDER BY s.null_frac DESC NULLS LAST, c.table_name, c.ordinal_position
        """

    @staticmethod
    def column_null_counts(schema: str, table: str) -> str:
        """Get column metadata for null count analysis.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                a.attname as column_name,
                format_type(a.atttypid, a.atttypmod) as data_type,
                NOT a.attnotnull as is_nullable
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = '{schema}'
                AND c.relname = '{table}'
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY a.attnum
        """

    @staticmethod
    def duplicate_detection(schema: str, table: str, columns: str) -> str:
        """Detect duplicate rows based on specified columns.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
            columns: Comma-separated column names (each validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        # Validate each column in the comma-separated list
        for col in columns.split(","):
            col_stripped = col.strip()
            if col_stripped:
                SQLSanitizer.validate_identifier(col_stripped, "column")
        return f"""
            SELECT
                {columns},
                COUNT(*) as duplicate_count
            FROM "{schema}"."{table}"
            GROUP BY {columns}
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 100
        """

    @staticmethod
    def potential_duplicate_columns(schema: str, table_name: str | None = None) -> str:
        """Find columns that might have duplicates.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND tablename = '{table_name}'"
        return f"""
            SELECT
                tablename as table_name,
                attname as column_name,
                n_distinct,
                CASE
                    WHEN n_distinct < 0 THEN round((-n_distinct * 100)::numeric, 2)
                    ELSE NULL
                END as unique_ratio_pct,
                null_frac,
                avg_width
            FROM pg_stats
            WHERE schemaname = '{schema}'
                {table_filter}
                AND n_distinct > 0
                AND n_distinct < 100
            ORDER BY n_distinct ASC
        """

    @staticmethod
    def orphaned_records(schema: str) -> str:
        """Find potential orphaned records.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            WITH fk_info AS (
                SELECT
                    tc.table_name as child_table,
                    kcu.column_name as child_column,
                    ccu.table_name as parent_table,
                    ccu.column_name as parent_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                    AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = '{schema}'
            )
            SELECT
                child_table,
                child_column,
                parent_table,
                parent_column
            FROM fk_info
            ORDER BY child_table, child_column
        """

    @staticmethod
    def check_orphans_query(schema: str, child_table: str, child_col: str, parent_table: str, parent_col: str) -> str:
        """Generate query to check for orphaned records.

        Args:
            schema: Schema name (validated against SQL injection)
            child_table: Child table name (validated)
            child_col: Child column name (validated)
            parent_table: Parent table name (validated)
            parent_col: Parent column name (validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(child_table, "child_table")
        SQLSanitizer.validate_identifier(child_col, "child_column")
        SQLSanitizer.validate_identifier(parent_table, "parent_table")
        SQLSanitizer.validate_identifier(parent_col, "parent_column")
        return f"""
            SELECT
                c."{child_col}" as orphaned_value,
                COUNT(*) as orphan_count
            FROM "{schema}"."{child_table}" c
            LEFT JOIN "{schema}"."{parent_table}" p ON c."{child_col}" = p."{parent_col}"
            WHERE c."{child_col}" IS NOT NULL
                AND p."{parent_col}" IS NULL
            GROUP BY c."{child_col}"
            ORDER BY COUNT(*) DESC
            LIMIT 50
        """

    @staticmethod
    def cardinality_analysis(schema: str, table_name: str | None = None) -> str:
        """Analyze column cardinality.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND tablename = '{table_name}'"
        return f"""
            SELECT
                tablename as table_name,
                attname as column_name,
                n_distinct,
                CASE
                    WHEN n_distinct < 0 THEN 'ratio: ' || round((-n_distinct * 100)::numeric, 2) || '%'
                    WHEN n_distinct = 1 THEN 'constant (1 value)'
                    WHEN n_distinct < 10 THEN 'very low (' || n_distinct::int || ' values)'
                    WHEN n_distinct < 100 THEN 'low (' || n_distinct::int || ' values)'
                    WHEN n_distinct < 1000 THEN 'medium (' || n_distinct::int || ' values)'
                    ELSE 'high (' || n_distinct::int || '+ values)'
                END as cardinality_level,
                correlation,
                most_common_vals::text as most_common_values,
                most_common_freqs::text as most_common_frequencies
            FROM pg_stats
            WHERE schemaname = '{schema}'
                {table_filter}
            ORDER BY tablename,
                CASE WHEN n_distinct < 0 THEN -n_distinct ELSE 1.0 / NULLIF(n_distinct, 0) END DESC
        """

    @staticmethod
    def outlier_detection(schema: str, table: str, column: str) -> str:
        """Detect statistical outliers in a numeric column.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated)
            column: Column name (validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        SQLSanitizer.validate_identifier(column, "column")
        return f"""
            WITH stats AS (
                SELECT
                    AVG("{column}") as mean,
                    STDDEV("{column}") as stddev,
                    MIN("{column}") as min_val,
                    MAX("{column}") as max_val,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{column}") as q1,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY "{column}") as median,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{column}") as q3
                FROM "{schema}"."{table}"
                WHERE "{column}" IS NOT NULL
            ),
            iqr AS (
                SELECT
                    *,
                    q3 - q1 as iqr_value,
                    q1 - 1.5 * (q3 - q1) as lower_bound,
                    q3 + 1.5 * (q3 - q1) as upper_bound
                FROM stats
            )
            SELECT
                round(mean::numeric, 4) as mean,
                round(stddev::numeric, 4) as stddev,
                round(min_val::numeric, 4) as min_value,
                round(max_val::numeric, 4) as max_value,
                round(q1::numeric, 4) as q1,
                round(median::numeric, 4) as median,
                round(q3::numeric, 4) as q3,
                round(iqr_value::numeric, 4) as iqr,
                round(lower_bound::numeric, 4) as outlier_lower_bound,
                round(upper_bound::numeric, 4) as outlier_upper_bound,
                round((mean - 3 * stddev)::numeric, 4) as zscore_lower_3sd,
                round((mean + 3 * stddev)::numeric, 4) as zscore_upper_3sd
            FROM iqr
        """

    @staticmethod
    def count_outliers(schema: str, table: str, column: str) -> str:
        """Count outliers using IQR method.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated)
            column: Column name (validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        SQLSanitizer.validate_identifier(column, "column")
        return f"""
            WITH stats AS (
                SELECT
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{column}") as q1,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{column}") as q3,
                    COUNT(*) as total_count
                FROM "{schema}"."{table}"
                WHERE "{column}" IS NOT NULL
            ),
            bounds AS (
                SELECT
                    q1 - 1.5 * (q3 - q1) as lower_bound,
                    q3 + 1.5 * (q3 - q1) as upper_bound,
                    total_count
                FROM stats
            )
            SELECT
                total_count,
                (SELECT COUNT(*) FROM "{schema}"."{table}" WHERE "{column}" < lower_bound) as below_lower,
                (SELECT COUNT(*) FROM "{schema}"."{table}" WHERE "{column}" > upper_bound) as above_upper,
                round(lower_bound::numeric, 4) as lower_bound,
                round(upper_bound::numeric, 4) as upper_bound
            FROM bounds
        """

    @staticmethod
    def data_type_consistency(schema: str, table_name: str | None = None) -> str:
        """Check for potential data type issues.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND c.table_name = '{table_name}'"
        return f"""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                CASE
                    WHEN c.data_type = 'character varying' AND c.character_maximum_length IS NULL
                        THEN 'unbounded varchar - consider limit'
                    WHEN c.data_type = 'text'
                        THEN 'text type - consider varchar with limit'
                    WHEN c.data_type = 'double precision'
                        THEN 'float - consider numeric for money'
                    WHEN c.data_type = 'real'
                        THEN 'real - low precision float'
                    WHEN c.data_type = 'integer' AND c.column_name LIKE '%id%'
                        THEN 'integer ID - consider bigint for scale'
                    ELSE 'ok'
                END as type_recommendation
            FROM information_schema.columns c
            WHERE c.table_schema = '{schema}'
                {table_filter}
                AND c.table_name NOT LIKE 'pg_%'
            ORDER BY
                CASE WHEN c.data_type IN ('text', 'double precision', 'real') THEN 0 ELSE 1 END,
                c.table_name,
                c.ordinal_position
        """

    @staticmethod
    def format_validation_patterns(schema: str) -> str:
        """Identify columns that might need format validation.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                CASE
                    WHEN c.column_name ~* 'email' THEN 'email format'
                    WHEN c.column_name ~* 'phone|tel|mobile' THEN 'phone format'
                    WHEN c.column_name ~* 'url|link|website' THEN 'URL format'
                    WHEN c.column_name ~* 'zip|postal' THEN 'postal code format'
                    WHEN c.column_name ~* 'ip_?addr' THEN 'IP address format'
                    WHEN c.column_name ~* 'uuid|guid' THEN 'UUID format'
                    WHEN c.column_name ~* 'ssn|social' THEN 'SSN format (sensitive)'
                    WHEN c.column_name ~* 'credit|card' THEN 'credit card format (sensitive)'
                    ELSE NULL
                END as suggested_validation
            FROM information_schema.columns c
            WHERE c.table_schema = '{schema}'
                AND c.data_type IN ('character varying', 'text', 'character')
                AND c.column_name ~* 'email|phone|tel|mobile|url|link|website|zip|postal|ip|uuid|guid|ssn|social|credit|card'
            ORDER BY c.table_name, c.ordinal_position
        """

    @staticmethod
    def soft_delete_detection(schema: str) -> str:
        """Detect tables with soft delete patterns.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                CASE
                    WHEN c.column_name ~* '^(is_)?deleted$' THEN 'boolean soft delete'
                    WHEN c.column_name ~* 'deleted_at|deleted_on|deletion_date' THEN 'timestamp soft delete'
                    WHEN c.column_name ~* '^(is_)?active$' THEN 'active flag (inverse delete)'
                    WHEN c.column_name ~* '^(is_)?archived$' THEN 'archive flag'
                    WHEN c.column_name ~* 'status' AND c.data_type IN ('character varying', 'text')
                        THEN 'status field (possible soft delete)'
                    ELSE 'other pattern'
                END as delete_pattern
            FROM information_schema.columns c
            WHERE c.table_schema = '{schema}'
                AND c.column_name ~* 'deleted|active|archived|status'
            ORDER BY c.table_name, c.column_name
        """

    @staticmethod
    def empty_tables(schema: str) -> str:
        """Find tables with no data.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                n_live_tup as row_count,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) as table_size,
                last_vacuum,
                last_analyze
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
                AND n_live_tup = 0
            ORDER BY relname
        """

    @staticmethod
    def temporal_data_spread(schema: str, table: str, date_column: str) -> str:
        """Analyze temporal distribution of data.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated)
            date_column: Date column name (validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        SQLSanitizer.validate_identifier(date_column, "date_column")
        return f"""
            SELECT
                MIN("{date_column}") as earliest_date,
                MAX("{date_column}") as latest_date,
                MAX("{date_column}") - MIN("{date_column}") as date_range,
                COUNT(*) as total_records,
                COUNT(DISTINCT DATE("{date_column}")) as distinct_days,
                COUNT(*) / NULLIF(COUNT(DISTINCT DATE("{date_column}")), 0) as avg_records_per_day
            FROM "{schema}"."{table}"
            WHERE "{date_column}" IS NOT NULL
        """

    @staticmethod
    def temporal_distribution(schema: str, table: str, date_column: str) -> str:
        """Get monthly distribution of data.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated)
            date_column: Date column name (validated)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        SQLSanitizer.validate_identifier(date_column, "date_column")
        return f"""
            SELECT
                DATE_TRUNC('month', "{date_column}") as month,
                COUNT(*) as record_count,
                MIN("{date_column}") as first_record,
                MAX("{date_column}") as last_record
            FROM "{schema}"."{table}"
            WHERE "{date_column}" IS NOT NULL
            GROUP BY DATE_TRUNC('month', "{date_column}")
            ORDER BY month DESC
            LIMIT 24
        """
