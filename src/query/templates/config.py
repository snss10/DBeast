"""Configuration review query templates."""


class ConfigQueries:
    """Queries for configuration review."""

    KEY_SETTINGS = """
        SELECT
            name,
            setting,
            unit,
            category,
            short_desc,
            boot_val,
            reset_val,
            source,
            pending_restart
        FROM pg_settings
        WHERE name IN (
            'shared_buffers', 'effective_cache_size', 'work_mem', 'maintenance_work_mem',
            'max_connections', 'max_worker_processes', 'max_parallel_workers', 'max_parallel_workers_per_gather',
            'random_page_cost', 'effective_io_concurrency', 'seq_page_cost',
            'checkpoint_completion_target', 'wal_buffers', 'min_wal_size', 'max_wal_size',
            'autovacuum', 'autovacuum_max_workers', 'autovacuum_vacuum_threshold', 'autovacuum_vacuum_scale_factor',
            'autovacuum_analyze_threshold', 'autovacuum_analyze_scale_factor',
            'log_min_duration_statement', 'log_checkpoints', 'log_lock_waits', 'log_temp_files',
            'statement_timeout', 'idle_in_transaction_session_timeout', 'lock_timeout',
            'default_statistics_target', 'track_activities', 'track_counts'
        )
        ORDER BY category, name
    """

    MEMORY_SETTINGS = """
        SELECT
            name,
            setting,
            unit,
            pg_size_bytes(setting || COALESCE(unit, '')) as bytes
        FROM pg_settings
        WHERE name IN ('shared_buffers', 'effective_cache_size', 'work_mem', 'maintenance_work_mem')
    """

    CONNECTION_COUNT = """
        SELECT count(*) FROM pg_stat_activity
    """

    EXTENSIONS = """
        SELECT extname, extversion
        FROM pg_extension
        ORDER BY extname
    """
