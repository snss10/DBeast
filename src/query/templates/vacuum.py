"""Vacuum analysis query templates.

All methods that accept schema parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class VacuumQueries:
    """Queries for vacuum analysis."""

    RUNNING_VACUUMS = """
        SELECT
            p.pid,
            a.usename,
            p.datname,
            p.relid::regclass::text as table_name,
            p.phase,
            p.heap_blks_total,
            p.heap_blks_scanned,
            p.heap_blks_vacuumed,
            CASE WHEN p.heap_blks_total > 0
                THEN round((100.0 * p.heap_blks_vacuumed / p.heap_blks_total)::numeric, 2)
                ELSE 0 END as progress_pct,
            p.index_vacuum_count,
            p.max_dead_tuples,
            p.num_dead_tuples
        FROM pg_stat_progress_vacuum p
        JOIN pg_stat_activity a ON p.pid = a.pid
        WHERE p.datname = current_database()
    """

    AUTOVACUUM_SETTINGS = """
        SELECT name, setting, unit, short_desc
        FROM pg_settings
        WHERE name LIKE 'autovacuum%'
        ORDER BY name
    """

    @staticmethod
    def bloated_tables(schema: str) -> str:
        """Get tables with high dead tuple counts.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                n_live_tup as live_tuples,
                n_dead_tup as dead_tuples,
                CASE WHEN n_live_tup > 0
                    THEN round((100.0 * n_dead_tup / n_live_tup)::numeric, 2)
                    ELSE 0 END as dead_pct,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) as table_size,
                last_vacuum,
                last_autovacuum,
                vacuum_count,
                autovacuum_count,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
                AND (n_dead_tup > 10000 OR (n_live_tup > 0 AND n_dead_tup::float / n_live_tup > 0.1))
            ORDER BY n_dead_tup DESC
            LIMIT 25
        """

    @staticmethod
    def never_vacuumed(schema: str) -> str:
        """Get tables that have never been vacuumed.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                n_live_tup as live_tuples,
                n_dead_tup as dead_tuples,
                n_tup_ins + n_tup_upd + n_tup_del as total_modifications,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) as table_size
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
                AND last_vacuum IS NULL
                AND last_autovacuum IS NULL
                AND n_live_tup > 1000
            ORDER BY n_dead_tup DESC
            LIMIT 20
        """

    @staticmethod
    def approaching_threshold(schema: str) -> str:
        """Get tables approaching autovacuum threshold.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            WITH av_threshold AS (
                SELECT
                    (SELECT setting::int FROM pg_settings WHERE name = 'autovacuum_vacuum_threshold') as base_threshold,
                    (SELECT setting::float FROM pg_settings WHERE name = 'autovacuum_vacuum_scale_factor') as scale_factor
            )
            SELECT
                s.schemaname,
                s.relname as table_name,
                s.n_live_tup as live_tuples,
                s.n_dead_tup as dead_tuples,
                (av.base_threshold + av.scale_factor * s.n_live_tup)::int as vacuum_threshold,
                CASE WHEN (av.base_threshold + av.scale_factor * s.n_live_tup) > 0
                    THEN round((100.0 * s.n_dead_tup / (av.base_threshold + av.scale_factor * s.n_live_tup))::numeric, 2)
                    ELSE 0 END as pct_to_threshold,
                s.last_autovacuum
            FROM pg_stat_user_tables s
            CROSS JOIN av_threshold av
            WHERE s.schemaname = '{schema}'
                AND s.n_dead_tup > 0
            ORDER BY (s.n_dead_tup::float / NULLIF(av.base_threshold + av.scale_factor * s.n_live_tup, 0)) DESC
            LIMIT 20
        """

    @staticmethod
    def stale_statistics(schema: str) -> str:
        """Get tables with stale statistics.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                schemaname,
                relname as table_name,
                n_live_tup as live_tuples,
                n_mod_since_analyze as modifications_since_analyze,
                CASE WHEN n_live_tup > 0
                    THEN round((100.0 * n_mod_since_analyze / n_live_tup)::numeric, 2)
                    ELSE 0 END as mod_pct_since_analyze,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE schemaname = '{schema}'
                AND n_live_tup > 1000
                AND n_mod_since_analyze > n_live_tup * 0.1
            ORDER BY n_mod_since_analyze DESC
            LIMIT 20
        """

    @staticmethod
    def tables_needing_freeze(schema: str) -> str:
        """Get tables approaching transaction ID wraparound.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                n.nspname as schema_name,
                c.relname as table_name,
                age(c.relfrozenxid) as xid_age,
                round((100.0 * age(c.relfrozenxid) / 2147483647)::numeric, 4) as pct_to_wraparound,
                pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
                s.last_autovacuum
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_stat_user_tables s ON c.oid = s.relid
            WHERE c.relkind = 'r'
                AND n.nspname = '{schema}'
                AND age(c.relfrozenxid) > 500000000
            ORDER BY age(c.relfrozenxid) DESC
            LIMIT 15
        """
