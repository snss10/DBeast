"""Lock analysis query templates."""


class LockQueries:
    """Queries for lock analysis."""

    LOCK_SUMMARY = """
        SELECT
            locktype,
            mode,
            count(*) as total,
            count(*) FILTER (WHERE granted) as granted,
            count(*) FILTER (WHERE NOT granted) as waiting
        FROM pg_locks
        WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
        GROUP BY locktype, mode
        ORDER BY count(*) DESC
    """

    TABLE_LOCK_HOTSPOTS = """
        SELECT
            c.relname as table_name,
            n.nspname as schema_name,
            count(*) as total_locks,
            count(*) FILTER (WHERE NOT l.granted) as waiting_locks,
            array_agg(DISTINCT l.mode) as lock_modes
        FROM pg_locks l
        JOIN pg_class c ON l.relation = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
            AND c.relkind = 'r'
        GROUP BY c.relname, n.nspname
        HAVING count(*) > 1
        ORDER BY count(*) FILTER (WHERE NOT l.granted) DESC, count(*) DESC
        LIMIT 20
    """

    ADVISORY_LOCKS = """
        SELECT
            l.classid,
            l.objid,
            l.mode,
            l.granted,
            a.usename,
            a.application_name,
            a.pid
        FROM pg_locks l
        JOIN pg_stat_activity a ON l.pid = a.pid
        WHERE l.locktype = 'advisory'
            AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
        ORDER BY l.classid, l.objid
        LIMIT 50
    """

    DEADLOCK_COUNT = """
        SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()
    """

    BLOCKING_TREE = """
        WITH RECURSIVE lock_tree AS (
            SELECT
                blocked.pid,
                blocking.pid as blocked_by,
                1 as depth,
                ARRAY[blocking.pid] as path
            FROM pg_locks blocked
            JOIN pg_locks blocking ON
                blocked.database = blocking.database
                AND blocked.relation = blocking.relation
                AND blocked.pid != blocking.pid
                AND blocking.granted
                AND NOT blocked.granted
            WHERE blocked.database = (SELECT oid FROM pg_database WHERE datname = current_database())

            UNION ALL

            SELECT
                lt.pid,
                blocking.pid,
                lt.depth + 1,
                lt.path || blocking.pid
            FROM lock_tree lt
            JOIN pg_locks blocked ON lt.blocked_by = blocked.pid AND NOT blocked.granted
            JOIN pg_locks blocking ON
                blocked.database = blocking.database
                AND blocked.relation = blocking.relation
                AND blocked.pid != blocking.pid
                AND blocking.granted
            WHERE lt.depth < 10
                AND NOT blocking.pid = ANY(lt.path)
        )
        SELECT DISTINCT
            a.pid,
            a.usename,
            a.application_name,
            a.state,
            EXTRACT(EPOCH FROM (now() - a.query_start))::int as query_duration_sec,
            array_length(lt.path, 1) as blocked_by_count,
            lt.path as blocked_by_pids,
            LEFT(a.query, 150) as query
        FROM lock_tree lt
        JOIN pg_stat_activity a ON lt.pid = a.pid
        ORDER BY array_length(lt.path, 1) DESC, query_duration_sec DESC
        LIMIT 20
    """

    @staticmethod
    def waiting_locks(min_wait_seconds: int = 0) -> str:
        return f"""
            SELECT
                blocked.pid as blocked_pid,
                blocked_activity.usename as blocked_user,
                blocked_activity.application_name as blocked_app,
                EXTRACT(EPOCH FROM (now() - blocked_activity.query_start))::int as wait_duration_sec,
                blocked.locktype,
                blocked.mode as requested_mode,
                blocked_activity.wait_event_type,
                blocked_activity.wait_event,
                c.relname as table_name,
                LEFT(blocked_activity.query, 200) as blocked_query,
                blocking.pid as blocking_pid,
                blocking_activity.usename as blocking_user,
                blocking_activity.state as blocking_state,
                LEFT(blocking_activity.query, 200) as blocking_query
            FROM pg_locks blocked
            JOIN pg_stat_activity blocked_activity ON blocked.pid = blocked_activity.pid
            JOIN pg_locks blocking ON
                blocked.database = blocking.database
                AND blocked.relation = blocking.relation
                AND blocked.pid != blocking.pid
                AND blocking.granted
            JOIN pg_stat_activity blocking_activity ON blocking.pid = blocking_activity.pid
            LEFT JOIN pg_class c ON blocked.relation = c.oid
            WHERE NOT blocked.granted
                AND blocked.database = (SELECT oid FROM pg_database WHERE datname = current_database())
                AND EXTRACT(EPOCH FROM (now() - blocked_activity.query_start)) >= {min_wait_seconds}
            ORDER BY blocked_activity.query_start
            LIMIT 30
        """
