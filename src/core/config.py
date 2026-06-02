"""Configuration management for dbeast using pydantic-settings.

Provides validated, type-safe configuration loaded from environment variables
and .env files. All settings have sensible defaults for production deployment.

Usage:
    from core.config import get_settings

    settings = get_settings()
    print(settings.db_host)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation loaded from environment variables.

    Settings are loaded from:
    1. Environment variables (highest priority)
    2. .env file (if present)
    3. Default values (lowest priority)

    All settings have sensible defaults for production use.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # =========================================================================
    # Database Connection
    # =========================================================================
    database_url: str | None = Field(
        default=None,
        description="Full PostgreSQL connection URL. If set, individual DB_* vars are ignored.",
        json_schema_extra={"env": "DATABASE_URL"},
    )
    db_host: str = Field(
        default="localhost",
        description="Database host address",
        json_schema_extra={"env": "DB_HOST"},
    )
    db_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="Database port (1-65535)",
        json_schema_extra={"env": "DB_PORT"},
    )
    db_user: str = Field(
        default="postgres",
        min_length=1,
        description="Database username",
        json_schema_extra={"env": "DB_USER"},
    )
    db_password: SecretStr = Field(
        default=SecretStr(""),
        description="Database password (stored securely)",
        json_schema_extra={"env": "DB_PASSWORD"},
    )
    db_name: str = Field(
        default="postgres",
        min_length=1,
        description="Database name",
        json_schema_extra={"env": "DB_NAME"},
    )
    db_sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = Field(
        default="prefer",
        description="PostgreSQL SSL mode",
        json_schema_extra={"env": "DB_SSLMODE"},
    )

    # =========================================================================
    # AWS Integration
    # =========================================================================
    aws_secret_name: str | None = Field(
        default=None,
        description="AWS Secrets Manager secret name for DB credentials",
        json_schema_extra={"env": "AWS_SECRET_NAME"},
    )
    aws_region: str = Field(
        default="us-west-1",
        description="AWS region for Secrets Manager",
        json_schema_extra={"env": "AWS_REGION"},
    )

    # =========================================================================
    # Connection Pool (DBEAST_ prefix)
    # =========================================================================
    dbeast_pool_min_size: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Minimum pool connections",
        alias="DBEAST_POOL_MIN_SIZE",
    )
    dbeast_pool_max_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum pool connections",
        alias="DBEAST_POOL_MAX_SIZE",
    )
    dbeast_command_timeout: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="SQL command timeout in seconds (5 min default for DB-wide analysis)",
        alias="DBEAST_COMMAND_TIMEOUT",
    )
    dbeast_pool_connection_timeout: float = Field(
        default=300.0,
        ge=1.0,
        le=600.0,
        description="Timeout for acquiring connection from pool in seconds (5 min default)",
        alias="DBEAST_POOL_CONNECTION_TIMEOUT",
    )

    # =========================================================================
    # Query Settings (DBEAST_ prefix)
    # =========================================================================
    dbeast_query_timeout: float = Field(
        default=300.0,
        ge=1.0,
        le=3600.0,
        description="Query timeout in seconds (5 min default for complex DB analysis)",
        alias="DBEAST_QUERY_TIMEOUT",
    )
    dbeast_default_row_limit: int = Field(
        default=100,
        ge=1,
        le=100000,
        description="Default maximum rows returned",
        alias="DBEAST_DEFAULT_ROW_LIMIT",
    )

    # =========================================================================
    # SSL/TLS Settings
    # =========================================================================
    dbeast_ssl_verify: bool = Field(
        default=True,
        description="Verify SSL certificates (disable only for development)",
        alias="DBEAST_SSL_VERIFY",
    )

    # =========================================================================
    # Logging
    # =========================================================================
    dbeast_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
        alias="DBEAST_LOG_LEVEL",
    )
    dbeast_log_json: bool = Field(
        default=False,
        description="Use JSON format for logs (recommended for production)",
        alias="DBEAST_LOG_JSON",
    )

    # =========================================================================
    # Connection Retry
    # =========================================================================
    dbeast_connection_max_retries: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Maximum connection retry attempts",
        alias="DBEAST_CONNECTION_MAX_RETRIES",
    )
    dbeast_connection_retry_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Delay between connection retries in seconds",
        alias="DBEAST_CONNECTION_RETRY_DELAY",
    )

    # =========================================================================
    # Feature Flags
    # =========================================================================
    dbeast_enable_docker_discovery: bool = Field(
        default=True,
        description="Enable Docker PostgreSQL container discovery (disable in production)",
        alias="DBEAST_ENABLE_DOCKER_DISCOVERY",
    )

    # =========================================================================
    # Risk Thresholds for Impact Analysis
    # =========================================================================
    dbeast_mass_update_rows: int = Field(
        default=1000,
        ge=1,
        description="Row count threshold for mass UPDATE warning",
        alias="DBEAST_MASS_UPDATE_ROWS",
    )
    dbeast_mass_delete_rows: int = Field(
        default=100,
        ge=1,
        description="Row count threshold for mass DELETE warning",
        alias="DBEAST_MASS_DELETE_ROWS",
    )
    dbeast_dangerous_percent: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Percentage of table affected to trigger dangerous warning",
        alias="DBEAST_DANGEROUS_PERCENT",
    )
    dbeast_critical_percent: int = Field(
        default=90,
        ge=1,
        le=100,
        description="Percentage of table affected to trigger critical warning",
        alias="DBEAST_CRITICAL_PERCENT",
    )

    # =========================================================================
    # Schema Cache
    # =========================================================================
    dbeast_schema_cache_ttl: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="Schema cache TTL in seconds (0 to disable)",
        alias="DBEAST_SCHEMA_CACHE_TTL",
    )

    # =========================================================================
    # Audit Logging
    # =========================================================================
    dbeast_audit_enabled: bool = Field(
        default=True,
        description="Enable MCP request/response audit logging",
        alias="DBEAST_AUDIT_ENABLED",
    )
    dbeast_audit_dir: str = Field(
        default="logs/mcp_audit",
        description="Directory for audit log files",
        alias="DBEAST_AUDIT_DIR",
    )
    dbeast_audit_max_response_size: int = Field(
        default=10000,
        ge=1000,
        le=100000,
        description="Max response size in audit logs (truncates if larger)",
        alias="DBEAST_AUDIT_MAX_RESPONSE_SIZE",
    )

    @field_validator("dbeast_log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        return v.upper() if isinstance(v, str) else v

    @field_validator("dbeast_pool_max_size")
    @classmethod
    def validate_pool_sizes(cls, v: int, info) -> int:
        """Ensure max_size >= min_size."""
        min_size = info.data.get("dbeast_pool_min_size", 1)
        if v < min_size:
            raise ValueError(f"pool_max_size ({v}) must be >= pool_min_size ({min_size})")
        return v

    def has_database_credentials(self) -> bool:
        """Check if any database credentials are configured."""
        return bool(self.database_url or (self.db_host and self.db_user) or self.aws_secret_name)

    def get_connection_string(self, mask_password: bool = False) -> str | None:
        """Build connection string from settings.

        Args:
            mask_password: If True, replace password with '***' (for logging)

        Returns:
            PostgreSQL connection string or None if insufficient credentials
        """
        if self.database_url:
            if mask_password:
                # Mask password in URL for safe logging
                import re

                return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", self.database_url)
            return self.database_url

        if not self.db_host or not self.db_user:
            return None

        password = "***" if mask_password else self.db_password.get_secret_value()
        password_part = f":{password}" if password else ""
        return f"postgresql://{self.db_user}{password_part}@{self.db_host}:{self.db_port}/{self.db_name}"

    # =========================================================================
    # Property aliases for backward compatibility
    # =========================================================================
    @property
    def pool_min_size(self) -> int:
        return self.dbeast_pool_min_size

    @property
    def pool_max_size(self) -> int:
        return self.dbeast_pool_max_size

    @property
    def command_timeout(self) -> int:
        return self.dbeast_command_timeout

    @property
    def pool_connection_timeout(self) -> float:
        return self.dbeast_pool_connection_timeout

    @property
    def query_timeout(self) -> float:
        return self.dbeast_query_timeout

    @property
    def default_row_limit(self) -> int:
        return self.dbeast_default_row_limit

    @property
    def ssl_verify(self) -> bool:
        return self.dbeast_ssl_verify

    @property
    def log_level(self) -> str:
        return self.dbeast_log_level

    @property
    def log_json(self) -> bool:
        return self.dbeast_log_json

    @property
    def connection_max_retries(self) -> int:
        return self.dbeast_connection_max_retries

    @property
    def connection_retry_delay(self) -> float:
        return self.dbeast_connection_retry_delay

    @property
    def schema_cache_ttl(self) -> int:
        return self.dbeast_schema_cache_ttl

    @property
    def enable_docker_discovery(self) -> bool:
        return self.dbeast_enable_docker_discovery


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are validated on first access. Invalid configuration
    will raise a ValidationError with details about what's wrong.

    Returns:
        Settings instance (cached after first call)
    """
    return Settings()


def reload_settings() -> Settings:
    """Reload settings from environment (clears cache).

    Use this after modifying environment variables at runtime.

    Returns:
        Fresh Settings instance
    """
    get_settings.cache_clear()
    return get_settings()
