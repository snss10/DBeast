"""PostgreSQL connection pool with retry logic and health monitoring."""

import asyncio
import logging
import ssl
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import asyncpg

from core.exceptions import DbConnectionError
from models import ConnectionConfig
from utils import AWSDefaults, get_db_credentials_from_secret

if TYPE_CHECKING:
    from core.config import Settings

# Lazy imports to avoid circular dependencies
_logger: logging.Logger | None = None
_settings: "Settings | None" = None


def _get_logger():
    """Get logger lazily to avoid import issues."""
    global _logger
    if _logger is None:
        try:
            from core.logging import get_logger

            _logger = get_logger("db.pool")
        except ImportError:
            import logging

            _logger = logging.getLogger("dbeast.db.pool")
    return _logger


def _get_settings() -> "Settings":
    """Get settings lazily to avoid circular imports."""
    global _settings
    if _settings is None:
        from core.config import get_settings

        _settings = get_settings()
    return _settings


class DatabasePool:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._config: ConnectionConfig | None = None
        self._extensions: dict[str, bool] = {}
        self._pg_version: int | None = None
        self._ssl_verified: bool = False

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    @property
    def config(self) -> ConnectionConfig | None:
        return self._config

    @property
    def extensions(self) -> dict[str, bool]:
        return self._extensions

    @property
    def pg_version(self) -> int | None:
        return self._pg_version

    def has_extension(self, name: str) -> bool:
        return self._extensions.get(name, False)

    @staticmethod
    def _config_from_url(url: str) -> tuple[ConnectionConfig, bool]:
        parsed = urlparse(url)
        ssl_mode = parse_qs(parsed.query).get("sslmode", ["prefer"])[0]
        return ConnectionConfig(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "postgres",
            password=parsed.password or "",
            database=parsed.path.lstrip("/") or "postgres",
        ), ssl_mode in ("require", "verify-ca", "verify-full")

    @staticmethod
    def _config_from_env() -> tuple[ConnectionConfig, bool]:
        """Build connection config from settings/environment."""
        settings = _get_settings()
        if settings.database_url:
            return DatabasePool._config_from_url(settings.database_url)
        ssl_mode = settings.db_sslmode
        return ConnectionConfig(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password.get_secret_value(),
            database=settings.db_name,
        ), ssl_mode in ("require", "verify-ca", "verify-full")

    @staticmethod
    def _config_from_aws_secret(
        secret_name: str,
        region: str = AWSDefaults.DEFAULT_REGION,
        host_override: str | None = None,
        port_override: int | None = None,
    ) -> ConnectionConfig:
        """Build connection config from AWS Secrets Manager.

        When using SSH tunnels, pass host_override='localhost' and port_override
        to connect through the tunnel while using credentials from the secret.
        """
        creds = get_db_credentials_from_secret(secret_name, region)
        return ConnectionConfig(
            host=host_override or creds.host,
            port=port_override or creds.port,
            user=creds.username,
            password=creds.password,
            database=creds.dbname,
        )

    @staticmethod
    def _create_ssl_context(verify: bool = True) -> ssl.SSLContext:
        """Create SSL context for database connections.

        Args:
            verify: If True (default), verify server certificate.
                   If False, disable verification (INSECURE - for dev/testing only).

        Returns:
            Configured SSL context
        """
        ctx = ssl.create_default_context()
        if not verify:
            # WARNING: Disabling verification is insecure and should only be used
            # for development/testing with self-signed certificates
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def connect(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        url: str | None = None,
        use_ssl: bool | None = None,
        ssl_verify: bool | None = None,
        aws_secret_name: str | None = None,
        aws_region: str = AWSDefaults.DEFAULT_REGION,
    ) -> dict:
        """Connect to PostgreSQL database.

        Args:
            host: Database host
            port: Database port
            user: Database user
            password: Database password
            database: Database name
            url: Full connection URL (alternative to individual params)
            use_ssl: Whether to use SSL (default based on sslmode)
            ssl_verify: Whether to verify SSL certificates (default from DBEAST_SSL_VERIFY env or True)
            aws_secret_name: AWS Secrets Manager secret name
            aws_region: AWS region for secrets

        Returns:
            Connection status dictionary
        """
        if self._pool:
            await self.disconnect()

        settings = _get_settings()
        ssl_required = False
        # Use provided ssl_verify, or fall back to settings default
        verify_ssl = ssl_verify if ssl_verify is not None else settings.ssl_verify

        if aws_secret_name:
            self._config = self._config_from_aws_secret(
                aws_secret_name, aws_region, host_override=host, port_override=port
            )
            ssl_required = use_ssl if use_ssl is not None else (host is None)  # SSL off for localhost tunnels
        elif url:
            self._config, ssl_required = self._config_from_url(url)
        elif any([host, port, user, password, database]):
            env_config, env_ssl = self._config_from_env()
            self._config = ConnectionConfig(
                host=host or env_config.host,
                port=port or env_config.port,
                user=user or env_config.user,
                password=password or env_config.password,
                database=database or env_config.database,
            )
            ssl_required = env_ssl
        else:
            self._config, ssl_required = self._config_from_env()

        if use_ssl is not None:
            ssl_required = use_ssl

        # Store SSL verification status
        self._ssl_verified = verify_ssl if ssl_required else False

        logger = _get_logger()
        logger.info(
            "Connecting to database",
            extra={
                "host": self._config.host,
                "port": self._config.port,
                "database": self._config.database,
                "user": self._config.user,
                "ssl": ssl_required,
            },
        )

        try:
            self._pool = await asyncpg.create_pool(
                host=self._config.host,
                port=self._config.port,
                user=self._config.user,
                password=self._config.password,
                database=self._config.database,
                ssl=self._create_ssl_context(verify=verify_ssl) if ssl_required else None,
                min_size=settings.pool_min_size,
                max_size=settings.pool_max_size,
                command_timeout=settings.command_timeout,
                timeout=settings.pool_connection_timeout,
            )
            async with self._pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                # Detect PostgreSQL major version
                version_num = await conn.fetchval("SHOW server_version_num")
                self._pg_version = int(version_num) // 10000 if version_num else None
                # Detect available extensions
                ext_rows = await conn.fetch("""
                    SELECT extname FROM pg_extension
                    WHERE extname IN ('pg_stat_statements', 'pgstattuple', 'pg_buffercache', 'pg_prewarm')
                """)
                self._extensions = {row["extname"]: True for row in ext_rows}

            logger.info(
                "Connected to database",
                extra={
                    "host": self._config.host,
                    "database": self._config.database,
                    "pg_version": self._pg_version,
                    "extensions": list(self._extensions.keys()),
                },
            )

            return {
                "status": "connected",
                "host": self._config.host,
                "port": self._config.port,
                "database": self._config.database,
                "user": self._config.user,
                "ssl": ssl_required,
                "ssl_verified": self._ssl_verified,
                "aws_secret": aws_secret_name,
                "version": version,
                "pg_version": self._pg_version,
                "extensions": list(self._extensions.keys()),
            }
        except Exception as e:
            # Capture host before clearing config
            failed_host = self._config.host if self._config else None
            logger.error(
                "Failed to connect to database",
                extra={"error": str(e), "host": failed_host},
            )
            self._pool = None
            self._config = None
            self._extensions = {}
            self._pg_version = None
            self._ssl_verified = False
            raise DbConnectionError(
                f"Failed to connect: {str(e)}",
                host=failed_host,
                original_error=e,
            ) from e

    async def connect_with_retry(self, **kwargs) -> dict:
        """Connect with exponential backoff retry logic.

        Attempts to connect up to max_retries times with exponential backoff
        between attempts. Useful for production environments where transient
        failures may occur.

        Args:
            **kwargs: Arguments to pass to connect()

        Returns:
            Connection status dictionary

        Raises:
            DbConnectionError: If all retry attempts fail
        """
        settings = _get_settings()
        logger = _get_logger()
        last_error: Exception | None = None
        max_retries = settings.connection_max_retries
        retry_delay_base = settings.connection_retry_delay

        for attempt in range(max_retries):
            try:
                return await self.connect(**kwargs)
            except DbConnectionError as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = retry_delay_base * (2**attempt)
                    logger.warning(
                        f"Connection attempt {attempt + 1}/{max_retries} failed, retrying in {delay}s",
                        extra={"attempt": attempt + 1, "delay": delay, "error": str(e)},
                    )
                    await asyncio.sleep(delay)

        logger.error(f"All {max_retries} connection attempts failed", extra={"last_error": str(last_error)})
        raise last_error  # type: ignore

    async def disconnect(self) -> dict:
        """Disconnect from the database and cleanup resources."""
        logger = _get_logger()
        if self._pool:
            logger.info("Disconnecting from database")
            await self._pool.close()
            self._pool = None
            self._config = None
            self._extensions = {}
            self._pg_version = None
            self._ssl_verified = False
            return {"status": "disconnected"}
        return {"status": "not_connected"}

    async def health_check(self) -> dict:
        """Check database connection health.

        Returns:
            Health status dictionary with connection info
        """
        if not self._pool:
            return {
                "healthy": False,
                "status": "not_connected",
                "message": "No database connection",
            }

        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")  # Validate connection works
                pool_size = self._pool.get_size()
                pool_free = self._pool.get_idle_size()

                return {
                    "healthy": True,
                    "status": "connected",
                    "host": self._config.host if self._config else None,
                    "database": self._config.database if self._config else None,
                    "pg_version": self._pg_version,
                    "pool_size": pool_size,
                    "pool_free": pool_free,
                    "pool_used": pool_size - pool_free,
                    "extensions": list(self._extensions.keys()),
                }
        except Exception as e:
            return {
                "healthy": False,
                "status": "error",
                "message": str(e),
            }

    def get_pool(self) -> asyncpg.Pool | None:
        """Get the underlying connection pool (for advanced use cases)."""
        return self._pool

    async def execute(self, query: str, *args, timeout: float | None = None) -> str:
        if not self._pool:
            raise DbConnectionError("Not connected to database")
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def fetch(self, query: str, *args, timeout: float | None = None) -> list[dict]:
        """Execute query and return all rows. timeout is in seconds."""
        if not self._pool:
            raise DbConnectionError("Not connected to database")
        async with self._pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch(query, *args, timeout=timeout)]

    async def fetchrow(self, query: str, *args, timeout: float | None = None) -> dict | None:
        """Execute query and return first row. timeout is in seconds."""
        if not self._pool:
            raise DbConnectionError("Not connected to database")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args, timeout=timeout)
            return dict(row) if row else None

    async def fetchval(self, query: str, *args, timeout: float | None = None) -> Any:
        """Execute query and return first column of first row. timeout is in seconds."""
        if not self._pool:
            raise DbConnectionError("Not connected to database")
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)
