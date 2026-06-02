"""Query performance analysis templates (requires pg_stat_statements)."""


class PerformanceQueries:
    """Queries for query performance analysis (requires pg_stat_statements)."""

    SUMMARY = """
        SELECT
            count(*) as total_unique_queries,
            sum(calls) as total_calls,
            round(sum({time_col})::numeric, 2) as total_time_ms,
            round(avg({mean_time_col})::numeric, 2) as avg_mean_time_ms,
            sum(rows) as total_rows,
            sum(shared_blks_hit) as total_cache_hits,
            sum(shared_blks_read) as total_disk_reads,
            round((100.0 * sum(shared_blks_hit) / NULLIF(sum(shared_blks_hit) + sum(shared_blks_read), 0))::numeric, 2) as overall_cache_hit_pct
        FROM pg_stat_statements
        WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
    """

    @staticmethod
    def top_queries(
        order_col: str, time_col: str, mean_time_col: str, limit: int, min_calls: int, pg_version: int = 14
    ) -> str:
        stddev_col = (
            "round(stddev_exec_time::numeric, 2) as stddev_time_ms," if pg_version >= 13 else "NULL as stddev_time_ms,"
        )
        return f"""
            SELECT
                queryid,
                LEFT(query, 500) as query,
                calls,
                round({time_col}::numeric, 2) as total_time_ms,
                round({mean_time_col}::numeric, 2) as mean_time_ms,
                {stddev_col}
                rows,
                round((100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0))::numeric, 2) as cache_hit_pct,
                shared_blks_hit,
                shared_blks_read,
                shared_blks_dirtied,
                shared_blks_written,
                temp_blks_read,
                temp_blks_written
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND calls >= {min_calls}
            ORDER BY {order_col} DESC
            LIMIT {limit}
        """

    @staticmethod
    def variable_queries(mean_time_col: str, pg_version: int = 14) -> str:
        if pg_version < 13:
            return """
                SELECT NULL as queryid, 'stddev_exec_time not available in PostgreSQL < 13' as query,
                       0 as calls, 0 as mean_time_ms, 0 as stddev_time_ms, 0 as cv_pct
                WHERE false
            """
        return f"""
            SELECT
                queryid,
                LEFT(query, 300) as query,
                calls,
                round({mean_time_col}::numeric, 2) as mean_time_ms,
                round(stddev_exec_time::numeric, 2) as stddev_time_ms,
                round((stddev_exec_time / NULLIF({mean_time_col}, 0) * 100)::numeric, 2) as cv_pct
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND calls >= 10
                AND {mean_time_col} > 1
            ORDER BY stddev_exec_time / NULLIF({mean_time_col}, 0) DESC
            LIMIT 10
        """

    @staticmethod
    def temp_heavy_queries(mean_time_col: str) -> str:
        return f"""
            SELECT
                queryid,
                LEFT(query, 300) as query,
                calls,
                temp_blks_read,
                temp_blks_written,
                round({mean_time_col}::numeric, 2) as mean_time_ms
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND (temp_blks_read > 0 OR temp_blks_written > 0)
            ORDER BY temp_blks_read + temp_blks_written DESC
            LIMIT 10
        """

    @staticmethod
    def low_cache_hit_queries(mean_time_col: str) -> str:
        return f"""
            SELECT
                queryid,
                LEFT(query, 300) as query,
                calls,
                shared_blks_hit,
                shared_blks_read,
                round((100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0))::numeric, 2) as cache_hit_pct,
                round({mean_time_col}::numeric, 2) as mean_time_ms
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND shared_blks_hit + shared_blks_read > 1000
                AND shared_blks_hit::float / NULLIF(shared_blks_hit + shared_blks_read, 0) < 0.9
            ORDER BY shared_blks_read DESC
            LIMIT 10
        """
