"""Transaction health query templates."""


class TransactionQueries:
    """Queries for transaction health analysis."""

    DATABASE_XID = """
        SELECT
            datname,
            age(datfrozenxid) as xid_age,
            datfrozenxid::text as frozen_xid,
            round((100.0 * age(datfrozenxid) / 2147483647)::numeric, 4) as pct_to_wraparound,
            2147483647 - age(datfrozenxid) as xids_remaining,
            pg_size_pretty(pg_database_size(datname)) as db_size
        FROM pg_database
        WHERE datname = current_database()
    """

    TRANSACTION_STATS = """
        SELECT
            xact_commit as commits,
            xact_rollback as rollbacks,
            CASE WHEN xact_commit + xact_rollback > 0
                THEN round((100.0 * xact_rollback / (xact_commit + xact_rollback))::numeric, 2)
                ELSE 0 END as rollback_pct
        FROM pg_stat_database
        WHERE datname = current_database()
    """

    PREPARED_TRANSACTIONS = """
        SELECT
            gid as transaction_id,
            owner,
            database,
            EXTRACT(EPOCH FROM (now() - prepared))::int as age_sec,
            prepared as prepared_at
        FROM pg_prepared_xacts
        WHERE database = current_database()
        ORDER BY prepared
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
        LIMIT 15
    """

    @staticmethod
    def tables_by_xid_age() -> str:
        return """
            SELECT
                n.nspname as schema_name,
                c.relname as table_name,
                age(c.relfrozenxid) as xid_age,
                round((100.0 * age(c.relfrozenxid) / 2147483647)::numeric, 4) as pct_to_wraparound,
                pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
                s.last_autovacuum,
                s.autovacuum_count
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_stat_user_tables s ON c.oid = s.relid
            WHERE c.relkind = 'r'
                AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY age(c.relfrozenxid) DESC
            LIMIT 20
        """

    @staticmethod
    def long_running_transactions(threshold_min: int) -> str:
        return f"""
            SELECT
                pid,
                usename,
                application_name,
                client_addr::text as client_host,
                state,
                EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_duration_sec,
                EXTRACT(EPOCH FROM (now() - query_start))::int as current_query_duration_sec,
                wait_event_type,
                wait_event,
                LEFT(query, 250) as current_query
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND xact_start IS NOT NULL
                AND xact_start < now() - interval '{threshold_min} minutes'
                AND pid != pg_backend_pid()
            ORDER BY xact_start
        """

    @staticmethod
    def oldest_transaction() -> str:
        return """
            SELECT
                pid,
                usename,
                application_name,
                state,
                EXTRACT(EPOCH FROM (now() - xact_start))::int as transaction_age_sec,
                EXTRACT(EPOCH FROM (now() - backend_start))::int as connection_age_sec,
                LEFT(query, 200) as query
            FROM pg_stat_activity
            WHERE datname = current_database()
                AND xact_start IS NOT NULL
                AND pid != pg_backend_pid()
            ORDER BY xact_start
            LIMIT 1
        """
