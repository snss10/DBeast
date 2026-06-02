"""Database health monitoring query templates."""


class HealthQueries:
    """Queries for database health monitoring."""

    DATABASE_STATS = """
        SELECT
            pg_database.datname,
            pg_database_size(pg_database.datname) as size_bytes,
            pg_size_pretty(pg_database_size(pg_database.datname)) as size,
            numbackends as connections,
            xact_commit as commits,
            xact_rollback as rollbacks,
            blks_read,
            blks_hit,
            CASE WHEN blks_hit + blks_read > 0
                THEN round((100.0 * blks_hit / (blks_hit + blks_read))::numeric, 2)
                ELSE 100 END as cache_hit_ratio,
            tup_returned,
            tup_fetched,
            tup_inserted,
            tup_updated,
            tup_deleted,
            deadlocks,
            temp_files,
            temp_bytes,
            pg_size_pretty(temp_bytes) as temp_size
        FROM pg_stat_database
        JOIN pg_database ON pg_database.datname = pg_stat_database.datname
        WHERE pg_database.datname = current_database()
    """

    CONNECTIONS_BY_STATE = """
        SELECT
            state,
            count(*) as count,
            max(EXTRACT(EPOCH FROM (now() - state_change)))::int as max_duration_sec
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY state
    """

    CONNECTIONS_BY_APPLICATION = """
        SELECT
            COALESCE(application_name, 'unknown') as application,
            count(*) as count,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY application_name
        ORDER BY count DESC
        LIMIT 15
    """

    CONNECTION_AGE_DISTRIBUTION = """
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 60 THEN '<1 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 300 THEN '1-5 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 1800 THEN '5-30 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 3600 THEN '30-60 min'
                ELSE '>1 hour'
            END as age_bucket,
            count(*) as count
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY 1
        ORDER BY min(EXTRACT(EPOCH FROM (now() - backend_start)))
    """

    IDLE_IN_TRANSACTION = """
        SELECT
            pid,
            usename,
            application_name,
            EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_duration_sec,
            EXTRACT(EPOCH FROM (now() - state_change))::int as idle_duration_sec,
            LEFT(query, 150) as last_query
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND state = 'idle in transaction'
            AND xact_start < now() - interval '5 minutes'
        ORDER BY xact_start
        LIMIT 10
    """

    WAIT_EVENTS = """
        SELECT
            COALESCE(wait_event_type, 'CPU/Running') as wait_type,
            COALESCE(wait_event, 'Active') as wait_event,
            count(*) as count
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND state = 'active'
            AND pid != pg_backend_pid()
        GROUP BY wait_event_type, wait_event
        ORDER BY count DESC
        LIMIT 15
    """

    XID_WRAPAROUND = """
        SELECT
            datname,
            age(datfrozenxid) as xid_age,
            round((100.0 * age(datfrozenxid) / 2147483647)::numeric, 2) as pct_to_wraparound,
            2147483647 - age(datfrozenxid) as xids_remaining
        FROM pg_database
        WHERE datname = current_database()
    """

    LONG_RUNNING_TRANSACTIONS = """
        SELECT
            pid,
            usename,
            application_name,
            state,
            EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_duration_sec,
            LEFT(query, 150) as current_query
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND xact_start IS NOT NULL
            AND xact_start < now() - interval '10 minutes'
            AND pid != pg_backend_pid()
        ORDER BY xact_start
        LIMIT 10
    """

    OLDEST_TRANSACTION = """
        SELECT
            pid,
            usename,
            state,
            EXTRACT(EPOCH FROM (now() - xact_start))::int as age_sec,
            LEFT(query, 100) as query
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND xact_start IS NOT NULL
            AND pid != pg_backend_pid()
        ORDER BY xact_start
        LIMIT 1
    """

    PREPARED_TRANSACTIONS = """
        SELECT
            gid,
            owner,
            database,
            EXTRACT(EPOCH FROM (now() - prepared))::int as age_sec
        FROM pg_prepared_xacts
        WHERE database = current_database()
        ORDER BY prepared
    """

    CHECKPOINT_STATS = """
        SELECT
            checkpoints_timed,
            checkpoints_req,
            checkpoint_write_time,
            checkpoint_sync_time,
            buffers_checkpoint,
            buffers_clean,
            buffers_backend,
            buffers_alloc
        FROM pg_stat_bgwriter
    """

    ACTIVE_QUERIES = """
        SELECT
            pid,
            usename,
            state,
            EXTRACT(EPOCH FROM (now() - query_start))::int as duration_sec,
            wait_event_type,
            wait_event,
            LEFT(query, 200) as query_preview
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND state != 'idle'
            AND pid != pg_backend_pid()
        ORDER BY query_start
        LIMIT 20
    """

    LONG_RUNNING_QUERIES = """
        SELECT
            pid,
            usename,
            EXTRACT(EPOCH FROM (now() - query_start))::int as duration_sec,
            LEFT(query, 300) as query
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND state = 'active'
            AND query_start < now() - interval '1 minute'
            AND pid != pg_backend_pid()
        ORDER BY query_start
        LIMIT 10
    """

    TABLES_NEEDING_VACUUM = """
        SELECT
            schemaname,
            relname as table_name,
            n_live_tup as live_rows,
            n_dead_tup as dead_rows,
            CASE WHEN n_live_tup > 0
                THEN round((100.0 * n_dead_tup / n_live_tup)::numeric, 2)
                ELSE 0 END as dead_ratio_pct,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            vacuum_count,
            autovacuum_count
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 1000
            OR (n_live_tup > 0 AND n_dead_tup::float / n_live_tup > 0.1)
        ORDER BY n_dead_tup DESC
        LIMIT 20
    """
