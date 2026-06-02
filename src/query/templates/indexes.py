"""Index and table statistics query templates.

All methods that accept schema/table parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class SmartAnalyzeQueries:
    """Queries for smart query analysis."""

    @staticmethod
    def table_stats(schema: str, table: str) -> str:
        """Get table statistics for smart analysis.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                relname,
                n_live_tup as rows,
                seq_scan,
                idx_scan,
                CASE WHEN seq_scan + idx_scan > 0
                    THEN round((100.0 * idx_scan / (seq_scan + idx_scan))::numeric, 2)
                    ELSE 100 END as index_usage_pct
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}' AND relname = '{table}'
        """

    @staticmethod
    def table_indexes(schema: str, table: str) -> str:
        """Get indexes for a table.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT indexrelname, idx_scan
            FROM pg_stat_user_indexes
            WHERE schemaname = '{schema}' AND relname = '{table}'
        """


class IndexQueries:
    """Queries for index analysis."""

    @staticmethod
    def all_indexes(schema: str, table_name: str | None = None) -> str:
        """Get all indexes in a schema.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND relname = '{table_name}'"
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                indexrelname as index_name,
                pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
                pg_relation_size(indexrelid) as index_size_bytes,
                idx_scan as scans,
                idx_tup_read as rows_read,
                idx_tup_fetch as rows_fetched
            FROM pg_stat_user_indexes
            WHERE schemaname = '{schema}' {table_filter}
            ORDER BY idx_scan DESC
        """

    @staticmethod
    def unused_indexes(schema: str, table_name: str | None = None) -> str:
        """Get unused indexes.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND s.relname = '{table_name}'"
        return f"""
            SELECT
                s.schemaname,
                s.relname as table_name,
                s.indexrelname as index_name,
                pg_size_pretty(pg_relation_size(s.indexrelid)) as wasted_space,
                pg_relation_size(s.indexrelid) as wasted_bytes,
                i.indisunique as is_unique,
                i.indisprimary as is_primary
            FROM pg_stat_user_indexes s
            JOIN pg_index i ON s.indexrelid = i.indexrelid
            WHERE s.idx_scan = 0
                AND s.schemaname = '{schema}'
                AND NOT i.indisprimary
                {table_filter}
            ORDER BY pg_relation_size(s.indexrelid) DESC
        """

    @staticmethod
    def duplicate_indexes(schema: str, table_name: str | None = None) -> str:
        """Find duplicate/overlapping indexes.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND t.relname = '{table_name}'"
        return f"""
            WITH index_cols AS (
                SELECT
                    n.nspname as schema_name,
                    t.relname as table_name,
                    i.relname as index_name,
                    pg_get_indexdef(ix.indexrelid) as definition,
                    array_to_string(array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)), ', ') as columns,
                    pg_relation_size(ix.indexrelid) as size_bytes
                FROM pg_index ix
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                WHERE n.nspname = '{schema}'
                    {table_filter}
                GROUP BY n.nspname, t.relname, i.relname, ix.indexrelid
            )
            SELECT
                ic1.table_name,
                ic1.index_name as index1,
                ic2.index_name as index2,
                ic1.columns as index1_cols,
                ic2.columns as index2_cols,
                pg_size_pretty(ic1.size_bytes + ic2.size_bytes) as combined_size
            FROM index_cols ic1
            JOIN index_cols ic2 ON ic1.table_name = ic2.table_name
                AND ic1.index_name < ic2.index_name
                AND (ic1.columns LIKE ic2.columns || '%' OR ic2.columns LIKE ic1.columns || '%')
        """

    @staticmethod
    def tables_needing_indexes(schema: str, table_name: str | None = None) -> str:
        """Find tables that would benefit from indexes.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND relname = '{table_name}'"
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                seq_scan,
                seq_tup_read,
                idx_scan,
                n_live_tup as rows,
                CASE WHEN seq_scan > 0 THEN seq_tup_read / seq_scan ELSE 0 END as avg_rows_per_seq_scan
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
                AND seq_scan > 50
                AND n_live_tup > 1000
                AND (idx_scan = 0 OR seq_scan > idx_scan * 10)
                {table_filter}
            ORDER BY seq_tup_read DESC
            LIMIT 20
        """

    @staticmethod
    def largest_indexes(schema: str, table_name: str | None = None) -> str:
        """Get largest indexes.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND relname = '{table_name}'"
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                indexrelname as index_name,
                pg_size_pretty(pg_relation_size(indexrelid)) as current_size,
                idx_scan as usage_count
            FROM pg_stat_user_indexes
            WHERE schemaname = '{schema}'
                {table_filter}
            ORDER BY pg_relation_size(indexrelid) DESC
            LIMIT 20
        """

    @staticmethod
    def fk_missing_indexes(schema: str) -> str:
        """Find foreign keys without supporting indexes.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            WITH fk_columns AS (
                SELECT
                    c.conrelid,
                    c.conname AS fk_name,
                    c.confrelid,
                    c.conkey AS fk_cols,
                    n.nspname AS schema_name,
                    t.relname AS table_name,
                    rn.nspname AS ref_schema,
                    rt.relname AS ref_table
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_class rt ON rt.oid = c.confrelid
                JOIN pg_namespace rn ON rn.oid = rt.relnamespace
                WHERE c.contype = 'f'
                    AND n.nspname = '{schema}'
            ),
            fk_with_indexes AS (
                SELECT
                    fk.fk_name,
                    fk.table_name,
                    fk.ref_schema,
                    fk.ref_table,
                    fk.fk_cols,
                    (
                        SELECT string_agg(a.attname, ', ' ORDER BY array_position(fk.fk_cols, a.attnum))
                        FROM pg_attribute a
                        WHERE a.attrelid = fk.conrelid AND a.attnum = ANY(fk.fk_cols)
                    ) AS fk_columns,
                    EXISTS (
                        SELECT 1 FROM pg_index i
                        WHERE i.indrelid = fk.conrelid
                            AND fk.fk_cols::int[] <@ i.indkey::int[]
                            AND (
                                i.indkey[0] = fk.fk_cols[1]
                                OR array_length(fk.fk_cols, 1) = 1
                            )
                    ) AS has_index
                FROM fk_columns fk
            )
            SELECT
                table_name,
                fk_name,
                fk_columns,
                ref_schema || '.' || ref_table AS references_table,
                CASE WHEN has_index THEN 'EXISTS' ELSE 'MISSING' END AS index_status,
                CASE WHEN NOT has_index
                    THEN 'CREATE INDEX idx_' || table_name || '_' || replace(fk_columns, ', ', '_') || ' ON {schema}.' || table_name || ' (' || fk_columns || ')'
                    ELSE NULL
                END AS suggested_index
            FROM fk_with_indexes
            WHERE NOT has_index
            ORDER BY table_name, fk_name
        """


class TableStatsQueries:
    """Queries for table statistics."""

    @staticmethod
    def table_statistics(schema: str, table_name: str | None = None) -> str:
        """Get comprehensive table statistics.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        table_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            table_filter = f"AND relname = '{table_name}'"
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) as total_size,
                pg_total_relation_size(schemaname || '.' || relname) as total_size_bytes,
                pg_size_pretty(pg_relation_size(schemaname || '.' || relname)) as table_size,
                pg_size_pretty(pg_indexes_size((schemaname || '.' || relname)::regclass)) as index_size,
                n_live_tup as live_rows,
                n_dead_tup as dead_rows,
                n_tup_ins as inserts,
                n_tup_upd as updates,
                n_tup_del as deletes,
                n_tup_hot_upd as hot_updates,
                seq_scan,
                seq_tup_read,
                idx_scan,
                idx_tup_fetch,
                CASE WHEN seq_scan + idx_scan > 0
                    THEN round((100.0 * idx_scan / (seq_scan + idx_scan))::numeric, 2)
                    ELSE 100 END as index_usage_pct,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}' {table_filter}
            ORDER BY pg_total_relation_size(schemaname || '.' || relname) DESC
            LIMIT 50
        """

    @staticmethod
    def column_statistics(schema: str, table_name: str | None = None) -> str:
        """Get column statistics.

        Args:
            schema: Schema name (validated against SQL injection)
            table_name: Optional table name filter (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        col_filter = ""
        if table_name:
            SQLSanitizer.validate_identifier(table_name, "table")
            col_filter = f"AND tablename = '{table_name}'"
        return f"""
            SELECT
                tablename,
                attname as column_name,
                n_distinct,
                CASE
                    WHEN n_distinct < 0 THEN 'unique ratio: ' || round((-n_distinct * 100)::numeric, 2) || '%'
                    WHEN n_distinct > 0 THEN n_distinct || ' distinct values'
                    ELSE 'unknown'
                END as distinctness,
                null_frac as null_fraction,
                avg_width,
                correlation
            FROM pg_stats
            WHERE schemaname = '{schema}' {col_filter}
            ORDER BY tablename, attnum
        """

    @staticmethod
    def hot_tables(schema: str) -> str:
        """Get tables with high activity.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                relname as table_name,
                seq_scan + idx_scan as total_scans,
                n_tup_ins + n_tup_upd + n_tup_del as total_writes
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
            ORDER BY (seq_scan + idx_scan + n_tup_ins + n_tup_upd + n_tup_del) DESC
            LIMIT 10
        """

    @staticmethod
    def toast_sizes(schema: str) -> str:
        """Get TOAST table sizes.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                n.nspname AS schema_name,
                c.relname AS table_name,
                t.relname AS toast_table,
                pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
                pg_relation_size(c.oid) AS table_size_bytes,
                pg_size_pretty(pg_relation_size(t.oid)) AS toast_size,
                pg_relation_size(t.oid) AS toast_size_bytes,
                pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                CASE WHEN pg_total_relation_size(c.oid) > 0
                    THEN round((100.0 * pg_relation_size(t.oid) / pg_total_relation_size(c.oid))::numeric, 2)
                    ELSE 0
                END AS toast_pct
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            JOIN pg_class t ON c.reltoastrelid = t.oid
            WHERE n.nspname = '{schema}'
                AND c.relkind = 'r'
                AND pg_relation_size(t.oid) > 0
            ORDER BY pg_relation_size(t.oid) DESC
            LIMIT 25
        """
