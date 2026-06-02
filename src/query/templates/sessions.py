"""Session analysis query templates."""


class SessionQueries:
    """Queries for session analysis."""

    SESSION_SUMMARY = """
        SELECT
            count(*) as total_connections,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction,
            count(*) FILTER (WHERE state = 'idle in transaction (aborted)') as idle_in_transaction_aborted,
            count(*) FILTER (WHERE wait_event_type IS NOT NULL AND state = 'active') as waiting,
            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
        FROM pg_stat_activity
        WHERE datname = current_database()
    """

    BY_APPLICATION = """
        SELECT
            COALESCE(NULLIF(application_name, ''), 'unknown') as application,
            count(*) as total,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_txn,
            max(EXTRACT(EPOCH FROM (now() - backend_start)))::int as oldest_conn_sec,
            avg(EXTRACT(EPOCH FROM (now() - backend_start)))::int as avg_conn_age_sec
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY application_name
        ORDER BY count(*) DESC
    """

    BY_USER = """
        SELECT
            usename as username,
            count(*) as total,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_txn
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY usename
        ORDER BY count(*) DESC
    """

    BY_CLIENT_HOST = """
        SELECT
            COALESCE(client_addr::text, 'local') as client_host,
            count(*) as total,
            count(*) FILTER (WHERE state = 'active') as active
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY client_addr
        ORDER BY count(*) DESC
        LIMIT 20
    """

    AGE_DISTRIBUTION = """
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 60 THEN '< 1 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 300 THEN '1-5 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 1800 THEN '5-30 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 3600 THEN '30-60 min'
                WHEN EXTRACT(EPOCH FROM (now() - backend_start)) < 86400 THEN '1-24 hours'
                ELSE '> 24 hours'
            END as age_bucket,
            count(*) as count
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY 1
        ORDER BY min(EXTRACT(EPOCH FROM (now() - backend_start)))
    """

    LONG_LIVED_CONNECTIONS = """
        SELECT
            pid,
            usename,
            application_name,
            state,
            EXTRACT(EPOCH FROM (now() - backend_start))::int as connection_age_sec,
            client_addr::text as client_host
        FROM pg_stat_activity
        WHERE datname = current_database()
            AND backend_start < now() - interval '24 hours'
        ORDER BY backend_start
        LIMIT 20
    """

    BACKEND_TYPES = """
        SELECT
            backend_type,
            count(*) as count
        FROM pg_stat_activity
        GROUP BY backend_type
        ORDER BY count DESC
    """

    @staticmethod
    def idle_in_transaction_sessions(threshold_sec: int) -> str:
        return f"""
            SELECT
                pid,
                usename,
                application_name,
                client_addr::text as client_host,
                state,
                EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_duration_sec,
                EXTRACT(EPOCH FROM (now() - state_change))::int as idle_duration_sec,
                EXTRACT(EPOCH FROM (now() - backend_start))::int as connection_age_sec,
                LEFT(query, 200) as last_query
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND state LIKE 'idle in transaction%'
                AND EXTRACT(EPOCH FROM (now() - xact_start)) > {threshold_sec}
            ORDER BY xact_start
        """

    @staticmethod
    def active_sessions() -> str:
        return """
            SELECT
                pid,
                usename,
                application_name,
                client_addr::text as client_host,
                state,
                wait_event_type,
                wait_event,
                EXTRACT(EPOCH FROM (now() - query_start))::int as query_duration_sec,
                EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_duration_sec,
                LEFT(query, 300) as query
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND state = 'active'
                AND pid != pg_backend_pid()
            ORDER BY query_start
            LIMIT 25
        """
