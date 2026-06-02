"""Dependency and lineage query templates.

All methods that accept schema/table/name parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class DependencyQueries:
    """Queries for analyzing database object dependencies."""

    VIEW_DEPENDENCIES = """
        SELECT DISTINCT
            dependent_ns.nspname as dependent_schema,
            dependent_view.relname as dependent_view,
            source_ns.nspname as source_schema,
            source_table.relname as source_table
        FROM pg_depend
        JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
        JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid
        JOIN pg_class as source_table ON pg_depend.refobjid = source_table.oid
        JOIN pg_namespace dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
        JOIN pg_namespace source_ns ON source_table.relnamespace = source_ns.oid
        WHERE dependent_ns.nspname NOT IN ('pg_catalog', 'information_schema')
            AND source_ns.nspname NOT IN ('pg_catalog', 'information_schema')
            AND source_table.relname != dependent_view.relname
            AND dependent_view.relkind = 'v'
        ORDER BY dependent_view.relname, source_table.relname
    """

    @staticmethod
    def view_dependencies_for_table(schema: str, table: str) -> str:
        """Find all views that depend on a specific table.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT DISTINCT
                dependent_ns.nspname as view_schema,
                dependent_view.relname as view_name,
                pg_get_viewdef(dependent_view.oid, true) as view_definition
            FROM pg_depend
            JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
            JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid
            JOIN pg_class as source_table ON pg_depend.refobjid = source_table.oid
            JOIN pg_namespace dependent_ns ON dependent_view.relnamespace = dependent_ns.oid
            JOIN pg_namespace source_ns ON source_table.relnamespace = source_ns.oid
            WHERE source_ns.nspname = '{schema}'
                AND source_table.relname = '{table}'
                AND dependent_view.relkind = 'v'
            ORDER BY dependent_view.relname
        """

    @staticmethod
    def view_definition(schema: str, view_name: str) -> str:
        """Get the definition of a view.

        Args:
            schema: Schema name (validated against SQL injection)
            view_name: View name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(view_name, "view_name")
        return f"""
            SELECT
                schemaname as schema_name,
                viewname as view_name,
                viewowner as owner,
                definition
            FROM pg_views
            WHERE schemaname = '{schema}'
                AND viewname = '{view_name}'
        """

    MATERIALIZED_VIEWS = """
        SELECT
            schemaname as schema_name,
            matviewname as view_name,
            matviewowner as owner,
            ispopulated as is_populated,
            pg_size_pretty(pg_total_relation_size(schemaname || '.' || matviewname)) as size,
            definition
        FROM pg_matviews
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, matviewname
    """

    ALL_VIEWS = """
        SELECT
            schemaname as schema_name,
            viewname as view_name,
            viewowner as owner,
            'view' as type,
            LEFT(definition, 200) as definition_preview
        FROM pg_views
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')

        UNION ALL

        SELECT
            schemaname as schema_name,
            matviewname as view_name,
            matviewowner as owner,
            'materialized view' as type,
            LEFT(definition, 200) as definition_preview
        FROM pg_matviews
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')

        ORDER BY schema_name, view_name
    """

    STORED_PROCEDURES = """
        SELECT
            n.nspname as schema_name,
            p.proname as function_name,
            pg_get_userbyid(p.proowner) as owner,
            l.lanname as language,
            CASE p.prokind
                WHEN 'f' THEN 'function'
                WHEN 'p' THEN 'procedure'
                WHEN 'a' THEN 'aggregate'
                WHEN 'w' THEN 'window'
            END as kind,
            p.provolatile as volatility,
            p.prosecdef as security_definer,
            pg_get_function_arguments(p.oid) as arguments,
            pg_get_function_result(p.oid) as return_type,
            obj_description(p.oid, 'pg_proc') as description
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        JOIN pg_language l ON p.prolang = l.oid
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            AND p.prokind IN ('f', 'p')
        ORDER BY n.nspname, p.proname
    """

    @staticmethod
    def function_source(schema: str, function_name: str) -> str:
        """Get the source code of a function.

        Args:
            schema: Schema name (validated against SQL injection)
            function_name: Function name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(function_name, "function_name")
        return f"""
            SELECT
                n.nspname as schema_name,
                p.proname as function_name,
                pg_get_functiondef(p.oid) as source_code
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = '{schema}'
                AND p.proname = '{function_name}'
        """

    @staticmethod
    def functions_in_schema(schema: str) -> str:
        """List all functions in a schema.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                p.proname as function_name,
                pg_get_userbyid(p.proowner) as owner,
                l.lanname as language,
                CASE p.prokind
                    WHEN 'f' THEN 'function'
                    WHEN 'p' THEN 'procedure'
                    WHEN 'a' THEN 'aggregate'
                    WHEN 'w' THEN 'window'
                END as kind,
                p.provolatile as volatility,
                pg_get_function_arguments(p.oid) as arguments,
                pg_get_function_result(p.oid) as return_type
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            JOIN pg_language l ON p.prolang = l.oid
            WHERE n.nspname = '{schema}'
            ORDER BY p.proname
        """

    TRIGGERS = """
        SELECT
            trigger_schema as schema_name,
            event_object_table as table_name,
            trigger_name,
            event_manipulation as trigger_event,
            action_timing as timing,
            action_orientation as orientation,
            action_statement as action
        FROM information_schema.triggers
        WHERE trigger_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY trigger_schema, event_object_table, trigger_name
    """

    @staticmethod
    def triggers_for_table(schema: str, table: str) -> str:
        """Get all triggers for a specific table.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            SELECT
                t.tgname as trigger_name,
                CASE t.tgtype & 1
                    WHEN 1 THEN 'ROW'
                    ELSE 'STATEMENT'
                END as level,
                CASE
                    WHEN t.tgtype & 2 > 0 THEN 'BEFORE'
                    WHEN t.tgtype & 64 > 0 THEN 'INSTEAD OF'
                    ELSE 'AFTER'
                END as timing,
                ARRAY_TO_STRING(ARRAY[
                    CASE WHEN t.tgtype & 4 > 0 THEN 'INSERT' END,
                    CASE WHEN t.tgtype & 8 > 0 THEN 'DELETE' END,
                    CASE WHEN t.tgtype & 16 > 0 THEN 'UPDATE' END,
                    CASE WHEN t.tgtype & 32 > 0 THEN 'TRUNCATE' END
                ], ' OR ') as events,
                p.proname as function_name,
                t.tgenabled as enabled,
                pg_get_triggerdef(t.oid) as definition
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            JOIN pg_proc p ON t.tgfoid = p.oid
            WHERE n.nspname = '{schema}'
                AND c.relname = '{table}'
                AND NOT t.tgisinternal
            ORDER BY t.tgname
        """

    @staticmethod
    def trigger_functions(schema: str) -> str:
        """Find all trigger functions.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                p.proname as function_name,
                pg_get_userbyid(p.proowner) as owner,
                l.lanname as language,
                obj_description(p.oid, 'pg_proc') as description,
                (
                    SELECT COUNT(*)
                    FROM pg_trigger t
                    WHERE t.tgfoid = p.oid
                ) as trigger_count
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            JOIN pg_language l ON p.prolang = l.oid
            WHERE n.nspname = '{schema}'
                AND pg_get_function_result(p.oid) = 'trigger'
            ORDER BY p.proname
        """

    FOREIGN_DATA_WRAPPERS = """
        SELECT
            fdw.fdwname as wrapper_name,
            pg_get_userbyid(fdw.fdwowner) as owner,
            fdw.fdwhandler::regproc as handler,
            fdw.fdwvalidator::regproc as validator,
            fdw.fdwoptions as options
        FROM pg_foreign_data_wrapper fdw
        ORDER BY fdw.fdwname
    """

    FOREIGN_SERVERS = """
        SELECT
            s.srvname as server_name,
            s.srvowner::regrole as owner,
            f.fdwname as wrapper_name,
            s.srvtype as server_type,
            s.srvversion as server_version,
            s.srvoptions as options
        FROM pg_foreign_server s
        JOIN pg_foreign_data_wrapper f ON s.srvfdw = f.oid
        ORDER BY s.srvname
    """

    USER_MAPPINGS = """
        SELECT
            um.srvname as server_name,
            COALESCE(um.usename, 'PUBLIC') as local_user,
            um.umoptions as options
        FROM pg_user_mappings um
        ORDER BY um.srvname, um.usename
    """

    FOREIGN_TABLES = """
        SELECT
            n.nspname as schema_name,
            c.relname as table_name,
            pg_get_userbyid(c.relowner) as owner,
            s.srvname as server_name,
            ft.ftoptions as options
        FROM pg_foreign_table ft
        JOIN pg_class c ON ft.ftrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_foreign_server s ON ft.ftserver = s.oid
        ORDER BY n.nspname, c.relname
    """

    EXTENSIONS = """
        SELECT
            e.extname as extension_name,
            e.extversion as version,
            n.nspname as schema_name,
            e.extrelocatable as relocatable,
            c.description
        FROM pg_extension e
        JOIN pg_namespace n ON e.extnamespace = n.oid
        LEFT JOIN pg_description c ON c.objoid = e.oid AND c.classoid = 'pg_extension'::regclass
        ORDER BY e.extname
    """

    @staticmethod
    def extension_objects(extension_name: str) -> str:
        """Get objects belonging to an extension.

        Args:
            extension_name: Extension name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(extension_name, "extension_name")
        return f"""
            SELECT
                CASE classid::regclass::text
                    WHEN 'pg_proc' THEN 'function'
                    WHEN 'pg_class' THEN 'relation'
                    WHEN 'pg_type' THEN 'type'
                    WHEN 'pg_cast' THEN 'cast'
                    WHEN 'pg_operator' THEN 'operator'
                    ELSE classid::regclass::text
                END as object_type,
                objid::regclass::text as object_name
            FROM pg_depend d
            JOIN pg_extension e ON d.refobjid = e.oid
            WHERE e.extname = '{extension_name}'
                AND d.deptype = 'e'
            ORDER BY object_type, object_name
            LIMIT 100
        """

    SEQUENCES = """
        SELECT
            schemaname as schema_name,
            sequencename as sequence_name,
            sequenceowner as owner,
            data_type,
            start_value,
            min_value,
            max_value,
            increment_by,
            cycle as is_cyclic,
            cache_size,
            last_value
        FROM pg_sequences
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, sequencename
    """

    @staticmethod
    def sequence_usage(schema: str) -> str:
        """Find which columns use which sequences.

        Args:
            schema: Schema name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                t.relname as table_name,
                a.attname as column_name,
                s.relname as sequence_name,
                pg_get_serial_sequence(n.nspname || '.' || t.relname, a.attname) as serial_sequence
            FROM pg_class t
            JOIN pg_namespace n ON t.relnamespace = n.oid
            JOIN pg_attribute a ON a.attrelid = t.oid
            JOIN pg_depend d ON d.refobjid = t.oid AND d.refobjsubid = a.attnum
            JOIN pg_class s ON d.objid = s.oid AND s.relkind = 'S'
            WHERE n.nspname = '{schema}'
                AND t.relkind = 'r'
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY t.relname, a.attnum
        """

    OBJECT_DEPENDENCIES = """
        SELECT
            dep.classid::regclass as dependent_type,
            dep.objid::regclass as dependent_object,
            dep.refclassid::regclass as referenced_type,
            dep.refobjid::regclass as referenced_object,
            dep.deptype as dependency_type
        FROM pg_depend dep
        WHERE dep.classid::regclass::text NOT LIKE 'pg_%'
            AND dep.deptype IN ('n', 'a')
        LIMIT 100
    """

    @staticmethod
    def table_dependencies(schema: str, table: str) -> str:
        """Find all objects that depend on a specific table.

        Args:
            schema: Schema name (validated against SQL injection)
            table: Table name (validated against SQL injection)
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        SQLSanitizer.validate_identifier(table, "table")
        return f"""
            WITH RECURSIVE deps AS (
                SELECT
                    d.objid,
                    d.refobjid,
                    1 as level,
                    ARRAY[d.refobjid] as path
                FROM pg_depend d
                JOIN pg_class c ON d.refobjid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = '{schema}'
                    AND c.relname = '{table}'
                    AND d.deptype IN ('n', 'a')

                UNION ALL

                SELECT
                    d.objid,
                    d.refobjid,
                    deps.level + 1,
                    deps.path || d.refobjid
                FROM pg_depend d
                JOIN deps ON d.refobjid = deps.objid
                WHERE deps.level < 5
                    AND NOT d.refobjid = ANY(deps.path)
                    AND d.deptype IN ('n', 'a')
            )
            SELECT DISTINCT
                deps.level,
                c.relkind,
                n.nspname as schema_name,
                c.relname as object_name,
                CASE c.relkind
                    WHEN 'r' THEN 'table'
                    WHEN 'v' THEN 'view'
                    WHEN 'm' THEN 'materialized view'
                    WHEN 'i' THEN 'index'
                    WHEN 'S' THEN 'sequence'
                    WHEN 'f' THEN 'foreign table'
                    ELSE c.relkind::text
                END as object_type
            FROM deps
            JOIN pg_class c ON deps.objid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY deps.level, c.relname
        """
