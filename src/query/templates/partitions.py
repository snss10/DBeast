"""Partition analysis query templates.

All methods that accept schema/table parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class PartitionQueries:
    """Queries for partition analysis."""

    PARTITIONED_TABLES = """
        SELECT
            n.nspname as schema_name,
            c.relname as table_name,
            pg_get_userbyid(c.relowner) as owner,
            CASE p.partstrat
                WHEN 'r' THEN 'RANGE'
                WHEN 'l' THEN 'LIST'
                WHEN 'h' THEN 'HASH'
            END as partition_strategy,
            pg_get_partkeydef(c.oid) as partition_key,
            (
                SELECT COUNT(*)
                FROM pg_inherits i
                WHERE i.inhparent = c.oid
            ) as partition_count,
            pg_size_pretty(pg_total_relation_size(c.oid)) as total_size
        FROM pg_partitioned_table p
        JOIN pg_class c ON p.partrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, c.relname
    """

    @staticmethod
    def partition_details(schema: str, table: str) -> str:
        """Get details of all partitions for a table.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                child_ns.nspname as partition_schema,
                child.relname as partition_name,
                pg_get_expr(child.relpartbound, child.oid) as partition_bound,
                pg_size_pretty(pg_relation_size(child.oid)) as data_size,
                pg_size_pretty(pg_indexes_size(child.oid)) as index_size,
                pg_size_pretty(pg_total_relation_size(child.oid)) as total_size,
                s.n_live_tup as row_count,
                s.n_dead_tup as dead_rows,
                s.last_vacuum,
                s.last_analyze
            FROM pg_inherits i
            JOIN pg_class parent ON i.inhparent = parent.oid
            JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
            JOIN pg_class child ON i.inhrelid = child.oid
            JOIN pg_namespace child_ns ON child.relnamespace = child_ns.oid
            LEFT JOIN pg_stat_user_tables s ON s.relid = child.oid
            WHERE parent_ns.nspname = '{schema}'
                AND parent.relname = '{table}'
            ORDER BY child.relname
        """

    @staticmethod
    def partition_size_distribution(schema: str, table: str) -> str:
        """Analyze size distribution across partitions.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            WITH partition_sizes AS (
                SELECT
                    child.relname as partition_name,
                    pg_total_relation_size(child.oid) as size_bytes,
                    s.n_live_tup as row_count
                FROM pg_inherits i
                JOIN pg_class parent ON i.inhparent = parent.oid
                JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
                JOIN pg_class child ON i.inhrelid = child.oid
                LEFT JOIN pg_stat_user_tables s ON s.relid = child.oid
                WHERE parent_ns.nspname = '{schema}'
                    AND parent.relname = '{table}'
            )
            SELECT
                partition_name,
                pg_size_pretty(size_bytes) as size,
                row_count,
                round((100.0 * size_bytes / NULLIF(SUM(size_bytes) OVER (), 0))::numeric, 2) as size_pct,
                round((100.0 * row_count / NULLIF(SUM(row_count) OVER (), 0))::numeric, 2) as rows_pct
            FROM partition_sizes
            ORDER BY size_bytes DESC
        """

    INHERITANCE_HIERARCHY = """
        WITH RECURSIVE inheritance_tree AS (
            SELECT
                c.oid,
                n.nspname as schema_name,
                c.relname as table_name,
                0 as level,
                ARRAY[c.oid] as path,
                c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE NOT EXISTS (
                SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid
            )
            AND c.relkind IN ('r', 'p')
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')

            UNION ALL

            SELECT
                child.oid,
                child_ns.nspname,
                child.relname,
                it.level + 1,
                it.path || child.oid,
                child.relkind
            FROM pg_inherits i
            JOIN inheritance_tree it ON i.inhparent = it.oid
            JOIN pg_class child ON i.inhrelid = child.oid
            JOIN pg_namespace child_ns ON child.relnamespace = child_ns.oid
            WHERE it.level < 10
        )
        SELECT
            level,
            schema_name,
            table_name,
            CASE relkind
                WHEN 'r' THEN 'table'
                WHEN 'p' THEN 'partitioned table'
            END as type,
            pg_size_pretty(pg_total_relation_size(oid)) as total_size
        FROM inheritance_tree
        WHERE level > 0 OR EXISTS (
            SELECT 1 FROM pg_inherits i WHERE i.inhparent = oid
        )
        ORDER BY path
    """

    @staticmethod
    def partition_activity(schema: str, table: str) -> str:
        """Get activity statistics for partitions.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                child.relname as partition_name,
                s.seq_scan,
                s.seq_tup_read,
                s.idx_scan,
                s.idx_tup_fetch,
                s.n_tup_ins as inserts,
                s.n_tup_upd as updates,
                s.n_tup_del as deletes,
                s.n_tup_hot_upd as hot_updates,
                s.n_live_tup as live_rows,
                s.n_dead_tup as dead_rows
            FROM pg_inherits i
            JOIN pg_class parent ON i.inhparent = parent.oid
            JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
            JOIN pg_class child ON i.inhrelid = child.oid
            JOIN pg_stat_user_tables s ON s.relid = child.oid
            WHERE parent_ns.nspname = '{schema}'
                AND parent.relname = '{table}'
            ORDER BY s.n_tup_ins + s.n_tup_upd + s.n_tup_del DESC
        """

    @staticmethod
    def partition_indexes(schema: str, table: str) -> str:
        """Get indexes on partitioned table and partitions.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                child.relname as partition_name,
                i.indexrelname as index_name,
                pg_size_pretty(pg_relation_size(i.indexrelid)) as index_size,
                i.idx_scan as scans,
                i.idx_tup_read as tuples_read,
                i.idx_tup_fetch as tuples_fetched
            FROM pg_inherits inh
            JOIN pg_class parent ON inh.inhparent = parent.oid
            JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
            JOIN pg_class child ON inh.inhrelid = child.oid
            JOIN pg_stat_user_indexes i ON i.relid = child.oid
            WHERE parent_ns.nspname = '{schema}'
                AND parent.relname = '{table}'
            ORDER BY child.relname, i.indexrelname
        """

    PARTITION_CONSTRAINTS = """
        SELECT
            n.nspname as schema_name,
            c.relname as table_name,
            pg_get_expr(c.relpartbound, c.oid) as partition_constraint,
            parent.relname as parent_table
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class parent ON i.inhparent = parent.oid
        WHERE c.relispartition = true
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY parent.relname, c.relname
    """

    @staticmethod
    def empty_partitions(schema: str, table: str) -> str:
        """Find empty partitions.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                child.relname as partition_name,
                pg_get_expr(child.relpartbound, child.oid) as partition_bound,
                pg_size_pretty(pg_total_relation_size(child.oid)) as total_size
            FROM pg_inherits i
            JOIN pg_class parent ON i.inhparent = parent.oid
            JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
            JOIN pg_class child ON i.inhrelid = child.oid
            LEFT JOIN pg_stat_user_tables s ON s.relid = child.oid
            WHERE parent_ns.nspname = '{schema}'
                AND parent.relname = '{table}'
                AND COALESCE(s.n_live_tup, 0) = 0
            ORDER BY child.relname
        """

    @staticmethod
    def partition_pruning_check(schema: str, table: str, partition_column: str, value: str) -> str:
        """Generate a query to test partition pruning.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
            partition_column: Partition column name (validated)
            value: Value to check (used in WHERE clause, validated)

        Note: The value parameter is validated using validate_where_clause for
        additional security since it appears in the WHERE clause.
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        SQLSanitizer.validate_identifier(partition_column, "partition_column")
        # Validate value to prevent injection
        SQLSanitizer.validate_where_clause(value)
        return f"""
            SELECT * FROM "{schema}"."{table}"
            WHERE "{partition_column}" = {value}
            LIMIT 1
        """

    DEFAULT_PARTITION = """
        SELECT
            parent_ns.nspname as parent_schema,
            parent.relname as parent_table,
            child_ns.nspname as default_partition_schema,
            child.relname as default_partition_name,
            pg_size_pretty(pg_total_relation_size(child.oid)) as size,
            s.n_live_tup as row_count
        FROM pg_class child
        JOIN pg_namespace child_ns ON child.relnamespace = child_ns.oid
        JOIN pg_inherits i ON child.oid = i.inhrelid
        JOIN pg_class parent ON i.inhparent = parent.oid
        JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
        LEFT JOIN pg_stat_user_tables s ON s.relid = child.oid
        WHERE child.relispartition = true
            AND pg_get_expr(child.relpartbound, child.oid) = 'DEFAULT'
            AND parent_ns.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY parent.relname
    """

    PARTITION_MAINTENANCE_CANDIDATES = """
        SELECT
            parent_ns.nspname as schema_name,
            parent.relname as table_name,
            child.relname as partition_name,
            pg_get_expr(child.relpartbound, child.oid) as partition_bound,
            s.n_live_tup as row_count,
            s.n_dead_tup as dead_rows,
            CASE WHEN s.n_live_tup > 0
                THEN round((100.0 * s.n_dead_tup / s.n_live_tup)::numeric, 2)
                ELSE 0 END as dead_pct,
            s.last_vacuum,
            s.last_autovacuum,
            pg_size_pretty(pg_total_relation_size(child.oid)) as size
        FROM pg_inherits i
        JOIN pg_class parent ON i.inhparent = parent.oid
        JOIN pg_namespace parent_ns ON parent.relnamespace = parent_ns.oid
        JOIN pg_class child ON i.inhrelid = child.oid
        LEFT JOIN pg_stat_user_tables s ON s.relid = child.oid
        WHERE parent_ns.nspname NOT IN ('pg_catalog', 'information_schema')
            AND (
                s.n_dead_tup > 10000
                OR (s.n_live_tup > 0 AND s.n_dead_tup::float / s.n_live_tup > 0.1)
                OR s.last_vacuum IS NULL
            )
        ORDER BY s.n_dead_tup DESC NULLS LAST
        LIMIT 30
    """
