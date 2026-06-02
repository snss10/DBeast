"""Security audit query templates.

All methods that accept schema/table parameters validate them using SQLSanitizer
to prevent SQL injection attacks.
"""

from query.templates.schema import SQLSanitizer


class SecurityQueries:
    """Queries for security auditing.

    All static methods that build dynamic SQL validate their inputs
    using SQLSanitizer.validate_identifier() before string interpolation.
    """

    ROLE_OVERVIEW = """
        SELECT
            r.rolname as role_name,
            r.rolsuper as is_superuser,
            r.rolinherit as can_inherit,
            r.rolcreaterole as can_create_role,
            r.rolcreatedb as can_create_db,
            r.rolcanlogin as can_login,
            r.rolreplication as is_replication_role,
            r.rolbypassrls as bypass_rls,
            r.rolconnlimit as connection_limit,
            r.rolvaliduntil as password_expiry,
            ARRAY(
                SELECT b.rolname
                FROM pg_auth_members m
                JOIN pg_roles b ON m.roleid = b.oid
                WHERE m.member = r.oid
            ) as member_of
        FROM pg_roles r
        WHERE r.rolname NOT LIKE 'pg_%'
        ORDER BY r.rolsuper DESC, r.rolcanlogin DESC, r.rolname
    """

    SUPERUSERS = """
        SELECT
            rolname as username,
            rolvaliduntil as password_expiry,
            rolconnlimit as connection_limit
        FROM pg_roles
        WHERE rolsuper = true
        ORDER BY rolname
    """

    LOGIN_ROLES = """
        SELECT
            r.rolname as username,
            r.rolsuper as is_superuser,
            r.rolcreatedb as can_create_db,
            r.rolcreaterole as can_create_role,
            r.rolreplication as is_replication,
            r.rolbypassrls as bypass_rls,
            r.rolvaliduntil as password_expiry,
            r.rolconnlimit as connection_limit,
            COALESCE(
                (SELECT COUNT(*) FROM pg_stat_activity WHERE usename = r.rolname),
                0
            ) as active_connections
        FROM pg_roles r
        WHERE r.rolcanlogin = true
            AND r.rolname NOT LIKE 'pg_%'
        ORDER BY r.rolsuper DESC, r.rolname
    """

    ROLE_MEMBERSHIPS = """
        SELECT
            r.rolname as role_name,
            m.rolname as member_name,
            g.rolname as granted_by,
            am.admin_option
        FROM pg_auth_members am
        JOIN pg_roles r ON am.roleid = r.oid
        JOIN pg_roles m ON am.member = m.oid
        LEFT JOIN pg_roles g ON am.grantor = g.oid
        WHERE r.rolname NOT LIKE 'pg_%'
            AND m.rolname NOT LIKE 'pg_%'
        ORDER BY r.rolname, m.rolname
    """

    TABLE_PRIVILEGES = """
        SELECT
            grantee,
            table_schema,
            table_name,
            privilege_type,
            is_grantable
        FROM information_schema.role_table_grants
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            AND grantee NOT LIKE 'pg_%'
        ORDER BY table_schema, table_name, grantee, privilege_type
    """

    @staticmethod
    def table_privileges_summary(schema: str) -> str:
        """Get privilege summary per table.

        Args:
            schema: Schema name (validated against SQL injection)

        Returns:
            SQL query string

        Raises:
            ValueError: If schema name is invalid
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                table_name,
                grantee,
                array_agg(DISTINCT privilege_type ORDER BY privilege_type) as privileges,
                bool_or(is_grantable = 'YES') as has_grant_option
            FROM information_schema.role_table_grants
            WHERE table_schema = '{schema}'
                AND grantee NOT LIKE 'pg_%'
            GROUP BY table_name, grantee
            ORDER BY table_name, grantee
        """

    SCHEMA_PRIVILEGES = """
        SELECT
            nspname as schema_name,
            pg_get_userbyid(nspowner) as owner,
            nspacl::text as acl
        FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%'
            AND nspname != 'information_schema'
        ORDER BY nspname
    """

    RLS_POLICIES = """
        SELECT
            schemaname as schema_name,
            tablename as table_name,
            policyname as policy_name,
            permissive,
            roles::text as applies_to,
            cmd as command,
            qual::text as using_expression,
            with_check::text as with_check_expression
        FROM pg_policies
        ORDER BY schemaname, tablename, policyname
    """

    @staticmethod
    def rls_coverage(schema: str) -> str:
        """Check RLS coverage for tables.

        Args:
            schema: Schema name (validated against SQL injection)

        Returns:
            SQL query string

        Raises:
            ValueError: If schema name is invalid
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                c.relname as table_name,
                c.relrowsecurity as rls_enabled,
                c.relforcerowsecurity as rls_forced,
                COALESCE(
                    (SELECT COUNT(*) FROM pg_policies p WHERE p.tablename = c.relname AND p.schemaname = '{schema}'),
                    0
                ) as policy_count
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = '{schema}'
                AND c.relkind = 'r'
            ORDER BY c.relrowsecurity DESC, c.relname
        """

    SENSITIVE_COLUMNS = """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type,
            CASE
                WHEN column_name ~* 'password|passwd|pwd|secret' THEN 'password/secret'
                WHEN column_name ~* 'ssn|social_security' THEN 'SSN'
                WHEN column_name ~* 'credit.?card|card.?number|ccn' THEN 'credit card'
                WHEN column_name ~* 'api.?key|apikey|access.?key' THEN 'API key'
                WHEN column_name ~* 'token|auth.?token|bearer' THEN 'auth token'
                WHEN column_name ~* 'private.?key|priv.?key' THEN 'private key'
                WHEN column_name ~* 'dob|birth.?date|date.?of.?birth' THEN 'date of birth (PII)'
                WHEN column_name ~* 'address|street|city|zip|postal' THEN 'address (PII)'
                WHEN column_name ~* 'phone|mobile|tel' THEN 'phone (PII)'
                WHEN column_name ~* 'email' THEN 'email (PII)'
                WHEN column_name ~* 'salary|wage|income|compensation' THEN 'financial (sensitive)'
                WHEN column_name ~* 'bank|account.?num|routing' THEN 'banking (sensitive)'
                WHEN column_name ~* 'medical|diagnosis|health' THEN 'health (PHI)'
                ELSE 'other sensitive'
            END as sensitivity_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            AND column_name ~* 'password|passwd|pwd|secret|ssn|social_security|credit.?card|card.?number|ccn|api.?key|apikey|access.?key|token|auth.?token|bearer|private.?key|priv.?key|dob|birth.?date|date.?of.?birth|salary|wage|income|compensation|bank|account.?num|routing|medical|diagnosis|health'
        ORDER BY
            CASE
                WHEN column_name ~* 'password|secret|key|token' THEN 1
                WHEN column_name ~* 'ssn|credit|bank' THEN 2
                ELSE 3
            END,
            table_schema, table_name, column_name
    """

    @staticmethod
    def sensitive_columns_in_schema(schema: str) -> str:
        """Find sensitive columns in a specific schema.

        Args:
            schema: Schema name (validated against SQL injection)

        Returns:
            SQL query string

        Raises:
            ValueError: If schema name is invalid
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                table_name,
                column_name,
                data_type,
                CASE
                    WHEN column_name ~* 'password|passwd|pwd|secret' THEN 'credential'
                    WHEN column_name ~* 'ssn|social_security' THEN 'government_id'
                    WHEN column_name ~* 'credit.?card|card.?number|ccn' THEN 'payment'
                    WHEN column_name ~* 'api.?key|apikey|access.?key|token' THEN 'auth_token'
                    WHEN column_name ~* 'email|phone|address|dob|birth' THEN 'pii'
                    WHEN column_name ~* 'salary|income|bank|account' THEN 'financial'
                    WHEN column_name ~* 'medical|health|diagnosis' THEN 'phi'
                    ELSE 'other'
                END as category
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
                AND column_name ~* 'password|passwd|pwd|secret|ssn|social|credit|card|api.?key|token|email|phone|address|dob|birth|salary|income|bank|account|medical|health'
            ORDER BY table_name, column_name
        """

    SSL_CONFIG = """
        SELECT
            name,
            setting,
            short_desc
        FROM pg_settings
        WHERE name IN (
            'ssl', 'ssl_ca_file', 'ssl_cert_file', 'ssl_key_file',
            'ssl_ciphers', 'ssl_prefer_server_ciphers', 'ssl_min_protocol_version',
            'ssl_max_protocol_version', 'ssl_dh_params_file', 'ssl_passphrase_command'
        )
        ORDER BY name
    """

    CONNECTION_SECURITY = """
        SELECT
            name,
            setting,
            short_desc
        FROM pg_settings
        WHERE name IN (
            'password_encryption', 'krb_server_keyfile', 'krb_caseins_users',
            'db_user_namespace', 'row_security'
        )
        ORDER BY name
    """

    AUDIT_SETTINGS = """
        SELECT
            name,
            setting,
            short_desc
        FROM pg_settings
        WHERE name IN (
            'log_connections', 'log_disconnections', 'log_statement',
            'log_min_duration_statement', 'log_checkpoints', 'log_lock_waits',
            'log_temp_files', 'log_autovacuum_min_duration', 'log_error_verbosity',
            'log_hostname', 'log_line_prefix', 'log_duration'
        )
        ORDER BY name
    """

    PGAUDIT_SETTINGS = """
        SELECT
            name,
            setting,
            short_desc
        FROM pg_settings
        WHERE name LIKE 'pgaudit.%'
        ORDER BY name
    """

    DEFAULT_PRIVILEGES = """
        SELECT
            pg_get_userbyid(d.defaclrole) as role,
            CASE d.defaclobjtype
                WHEN 'r' THEN 'table'
                WHEN 'S' THEN 'sequence'
                WHEN 'f' THEN 'function'
                WHEN 'T' THEN 'type'
                WHEN 'n' THEN 'schema'
            END as object_type,
            n.nspname as schema,
            d.defaclacl::text as default_acl
        FROM pg_default_acl d
        LEFT JOIN pg_namespace n ON d.defaclnamespace = n.oid
        ORDER BY role, object_type, schema
    """

    UNUSED_ROLES = """
        SELECT
            r.rolname as role_name,
            r.rolcanlogin as can_login,
            r.rolconnlimit as connection_limit,
            r.rolvaliduntil as password_expiry,
            CASE
                WHEN r.rolvaliduntil < NOW() THEN 'expired'
                WHEN NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity WHERE usename = r.rolname
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.role_table_grants WHERE grantee = r.rolname
                ) THEN 'potentially unused'
                ELSE 'active'
            END as status
        FROM pg_roles r
        WHERE r.rolname NOT LIKE 'pg_%'
            AND r.rolname NOT IN ('postgres')
        ORDER BY r.rolcanlogin DESC, r.rolname
    """

    FUNCTIONS_WITH_SECURITY_DEFINER = """
        SELECT
            n.nspname as schema_name,
            p.proname as function_name,
            pg_get_userbyid(p.proowner) as owner,
            p.prosecdef as security_definer,
            pg_get_function_arguments(p.oid) as arguments
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.prosecdef = true
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, p.proname
    """

    @staticmethod
    def public_schema_objects(schema: str = "public") -> str:
        """Check for objects in a schema (security consideration).

        Args:
            schema: Schema name (validated against SQL injection)

        Returns:
            SQL query string

        Raises:
            ValueError: If schema name is invalid
        """
        SQLSanitizer.validate_identifier(schema, "schema")
        return f"""
            SELECT
                c.relname as object_name,
                CASE c.relkind
                    WHEN 'r' THEN 'table'
                    WHEN 'v' THEN 'view'
                    WHEN 'm' THEN 'materialized view'
                    WHEN 'i' THEN 'index'
                    WHEN 'S' THEN 'sequence'
                    WHEN 'f' THEN 'foreign table'
                    WHEN 'p' THEN 'partitioned table'
                END as object_type,
                pg_get_userbyid(c.relowner) as owner,
                pg_size_pretty(pg_total_relation_size(c.oid)) as size
            FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = '{schema}'
                AND c.relkind IN ('r', 'v', 'm', 'S', 'f', 'p')
            ORDER BY c.relkind, c.relname
        """
