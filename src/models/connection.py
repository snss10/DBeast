"""Connection-related models."""

from pydantic import BaseModel


class ConnectionConfig(BaseModel):
    """Database connection configuration."""

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    database: str = "postgres"


class ConnectionResult(BaseModel):
    """Result of a connection attempt."""

    status: str
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    version: str | None = None
    error: str | None = None
