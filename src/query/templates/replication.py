"""Replication status query templates."""


class ReplicationQueries:
    """Queries for replication status."""

    STANDBYS = """
        SELECT
            pid,
            usename,
            application_name,
            client_addr::text as client_host,
            state,
            sent_lsn,
            write_lsn,
            flush_lsn,
            replay_lsn,
            pg_wal_lsn_diff(sent_lsn, replay_lsn) as replay_lag_bytes,
            pg_size_pretty(pg_wal_lsn_diff(sent_lsn, replay_lsn)) as replay_lag,
            sync_state,
            reply_time
        FROM pg_stat_replication
    """

    IS_STANDBY = """
        SELECT pg_is_in_recovery() as is_standby
    """

    STANDBY_STATUS = """
        SELECT
            pg_last_wal_receive_lsn() as receive_lsn,
            pg_last_wal_replay_lsn() as replay_lsn,
            pg_last_xact_replay_timestamp() as last_replay_time,
            EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::int as replay_lag_seconds
    """

    REPLICATION_SLOTS = """
        SELECT
            slot_name,
            plugin,
            slot_type,
            database,
            active,
            xmin,
            catalog_xmin,
            restart_lsn,
            confirmed_flush_lsn,
            pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained_wal
        FROM pg_replication_slots
    """

    WAL_INFO = """
        SELECT
            pg_current_wal_lsn() as current_lsn,
            pg_walfile_name(pg_current_wal_lsn()) as current_wal_file
    """

    WAL_SETTINGS = """
        SELECT name, setting, unit
        FROM pg_settings
        WHERE name IN ('max_wal_size', 'min_wal_size', 'wal_keep_size', 'max_replication_slots', 'max_wal_senders')
    """

    CDC_STATUS = """
        SELECT
            name,
            setting,
            CASE
                WHEN name = 'wal_level' AND setting = 'logical' THEN 'CDC enabled'
                WHEN name = 'wal_level' AND setting = 'replica' THEN 'streaming only'
                WHEN name = 'wal_level' AND setting = 'minimal' THEN 'no replication'
                ELSE setting
            END as status_description
        FROM pg_settings
        WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders', 'max_logical_replication_workers')
    """

    LOGICAL_REPLICATION_SLOTS = """
        SELECT
            slot_name,
            plugin,
            slot_type,
            database,
            active,
            xmin,
            catalog_xmin,
            restart_lsn,
            confirmed_flush_lsn,
            pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained_wal,
            CASE
                WHEN NOT active AND pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) > 1073741824
                THEN 'WARNING: inactive slot retaining >1GB WAL'
                WHEN NOT active THEN 'inactive'
                ELSE 'active'
            END as health_status
        FROM pg_replication_slots
        WHERE slot_type = 'logical'
        ORDER BY slot_name
    """

    PUBLICATIONS = """
        SELECT
            p.pubname as publication_name,
            pg_get_userbyid(p.pubowner) as owner,
            p.puballtables as all_tables,
            p.pubinsert as publishes_insert,
            p.pubupdate as publishes_update,
            p.pubdelete as publishes_delete,
            p.pubtruncate as publishes_truncate,
            (
                SELECT array_agg(pt.tablename)
                FROM pg_publication_tables pt
                WHERE pt.pubname = p.pubname
            ) as tables
        FROM pg_publication p
        ORDER BY p.pubname
    """

    @staticmethod
    def publication_tables(publication_name: str) -> str:
        """Get tables in a publication."""
        return f"""
            SELECT
                schemaname as schema_name,
                tablename as table_name
            FROM pg_publication_tables
            WHERE pubname = '{publication_name}'
            ORDER BY schemaname, tablename
        """

    SUBSCRIPTIONS = """
        SELECT
            s.subname as subscription_name,
            pg_get_userbyid(s.subowner) as owner,
            s.subenabled as enabled,
            s.subconninfo as connection_info,
            s.subslotname as slot_name,
            s.subsynccommit as sync_commit,
            s.subpublications as publications
        FROM pg_subscription s
        ORDER BY s.subname
    """

    SUBSCRIPTION_STATUS = """
        SELECT
            sr.subname as subscription_name,
            sr.pid,
            sr.relid::regclass as table_name,
            sr.received_lsn,
            sr.last_msg_send_time,
            sr.last_msg_receipt_time,
            sr.latest_end_lsn,
            sr.latest_end_time
        FROM pg_stat_subscription sr
        ORDER BY sr.subname
    """

    REPLICATION_ORIGIN = """
        SELECT
            roname as origin_name,
            roident as origin_id
        FROM pg_replication_origin
        ORDER BY roname
    """

    REPLICATION_ORIGIN_STATUS = """
        SELECT
            ro.roname as origin_name,
            ros.external_id,
            ros.remote_lsn,
            ros.local_lsn
        FROM pg_replication_origin ro
        LEFT JOIN pg_replication_origin_status ros ON ro.roident = ros.local_id
        ORDER BY ro.roname
    """

    WAL_RECEIVER = """
        SELECT
            pid,
            status,
            receive_start_lsn,
            receive_start_tli,
            written_lsn,
            flushed_lsn,
            received_tli,
            last_msg_send_time,
            last_msg_receipt_time,
            latest_end_lsn,
            latest_end_time,
            slot_name,
            sender_host,
            sender_port,
            conninfo
        FROM pg_stat_wal_receiver
    """

    INACTIVE_REPLICATION_SLOTS = """
        SELECT
            slot_name,
            plugin,
            slot_type,
            database,
            active,
            pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained_wal,
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) as retained_wal_bytes,
            CASE
                WHEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) > 5368709120 THEN 'CRITICAL: >5GB retained'
                WHEN pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) > 1073741824 THEN 'WARNING: >1GB retained'
                ELSE 'OK'
            END as severity
        FROM pg_replication_slots
        WHERE NOT active
        ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC
    """

    @staticmethod
    def table_replication_identity(schema: str) -> str:
        """Check replication identity settings for tables.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        from query.templates.schema import SQLSanitizer

        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                c.relname as table_name,
                CASE c.relreplident
                    WHEN 'd' THEN 'default (primary key)'
                    WHEN 'n' THEN 'nothing'
                    WHEN 'f' THEN 'full'
                    WHEN 'i' THEN 'index'
                END as replication_identity,
                CASE
                    WHEN c.relreplident = 'n' THEN 'WARNING: cannot replicate UPDATEs/DELETEs'
                    WHEN c.relreplident = 'f' THEN 'NOTE: full row comparison (slower)'
                    ELSE 'OK'
                END as status
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = '{schema}'
                AND c.relkind = 'r'
            ORDER BY c.relname
        """

    WAL_ARCHIVER_STATUS = """
        SELECT
            archived_count,
            last_archived_wal,
            last_archived_time,
            failed_count,
            last_failed_wal,
            last_failed_time,
            EXTRACT(EPOCH FROM (now() - last_archived_time))::int as seconds_since_last_archive,
            CASE
                WHEN failed_count > 0 AND last_failed_time > last_archived_time
                    THEN 'CRITICAL: recent archive failure'
                WHEN EXTRACT(EPOCH FROM (now() - last_archived_time)) > 3600
                    THEN 'WARNING: no archive in >1 hour'
                WHEN archived_count = 0
                    THEN 'INFO: no archives yet'
                ELSE 'OK'
            END as health_status,
            (SELECT setting FROM pg_settings WHERE name = 'archive_mode') as archive_mode,
            (SELECT setting FROM pg_settings WHERE name = 'archive_command') as archive_command
        FROM pg_stat_archiver
    """

    BASEBACKUP_PROGRESS = """
        SELECT
            p.pid,
            a.usename,
            a.application_name,
            p.phase,
            CASE p.backup_total
                WHEN 0 THEN 0
                ELSE round((100.0 * p.backup_streamed / p.backup_total)::numeric, 2)
            END as progress_pct,
            pg_size_pretty(p.backup_streamed) as streamed,
            pg_size_pretty(p.backup_total) as total_size,
            p.tablespaces_total,
            p.tablespaces_streamed,
            a.backend_start,
            EXTRACT(EPOCH FROM (now() - a.backend_start))::int as running_seconds
        FROM pg_stat_progress_basebackup p
        JOIN pg_stat_activity a ON p.pid = a.pid
    """

    ARCHIVE_SETTINGS = """
        SELECT
            name,
            setting,
            unit,
            CASE name
                WHEN 'archive_mode' THEN
                    CASE setting
                        WHEN 'on' THEN 'Archiving enabled'
                        WHEN 'always' THEN 'Archiving enabled (even on standby)'
                        ELSE 'Archiving DISABLED'
                    END
                WHEN 'archive_timeout' THEN
                    CASE WHEN setting::int = 0 THEN 'No forced switch'
                    ELSE 'Force switch every ' || setting || 's' END
                ELSE NULL
            END as description
        FROM pg_settings
        WHERE name IN ('archive_mode', 'archive_command', 'archive_timeout', 'archive_library')
        ORDER BY name
    """
