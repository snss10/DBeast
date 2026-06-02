"""Database schema discovery with TTL-based caching."""

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from models import Column, ForeignKey, Index, Table
from query.templates import SchemaQueries, build_count_query

if TYPE_CHECKING:
    from db.pool import DatabasePool

# Default cache TTL in seconds (1 minute, matches config.py default)
DEFAULT_CACHE_TTL = int(os.getenv("DBEAST_SCHEMA_CACHE_TTL", "60"))

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with timestamp for TTL expiration."""

    value: T
    timestamp: float

    def is_expired(self, ttl: float) -> bool:
        """Check if entry has expired based on TTL."""
        return time.time() - self.timestamp > ttl


class TTLCache(Generic[T]):
    """Simple TTL-based cache for schema metadata."""

    def __init__(self, ttl: float = DEFAULT_CACHE_TTL):
        self._cache: dict[str, CacheEntry[T]] = {}
        self._ttl = ttl

    def get(self, key: str) -> T | None:
        """Get value from cache if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired(self._ttl):
            del self._cache[key]
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        """Store value in cache with current timestamp."""
        self._cache[key] = CacheEntry(value=value, timestamp=time.time())

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def invalidate(self, key: str) -> None:
        """Remove a specific key from cache."""
        self._cache.pop(key, None)

    @property
    def size(self) -> int:
        """Get number of cached entries."""
        return len(self._cache)


class SchemaDiscovery:
    """Discovers and caches database schema information with TTL-based caching.

    Caching helps avoid repeated database calls when multiple tools
    query the same schema information within a short time window.

    Cache TTL can be configured via DBEAST_SCHEMA_CACHE_TTL environment variable.
    """

    def __init__(self, pool: "DatabasePool", cache_ttl: float = DEFAULT_CACHE_TTL):
        """Initialize schema discovery with caching.

        Args:
            pool: Database connection pool
            cache_ttl: Cache time-to-live in seconds (default: 300s / 5 minutes)
        """
        self._pool = pool
        self._table_cache: TTLCache[Table] = TTLCache(ttl=cache_ttl)
        self._schemas_cache: TTLCache[list[dict[str, Any]]] = TTLCache(ttl=cache_ttl)
        self._tables_cache: TTLCache[list[str]] = TTLCache(ttl=cache_ttl)

    def clear_cache(self) -> None:
        """Clear all schema caches."""
        self._table_cache.clear()
        self._schemas_cache.clear()
        self._tables_cache.clear()

    async def get_schemas(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """Get list of all user schemas with table counts and sizes.

        Args:
            use_cache: Whether to use cached results (default: True)

        Returns:
            List of schema dictionaries with name, table_count, and size info
        """
        cache_key = "_schemas_"

        if use_cache:
            cached = self._schemas_cache.get(cache_key)
            if cached is not None:
                return cached

        rows = await self._pool.fetch(SchemaQueries.LIST_SCHEMAS)
        result = [dict(row) for row in rows]

        self._schemas_cache.set(cache_key, result)
        return result

    async def get_tables(self, schema: str = "public", use_cache: bool = True) -> list[str]:
        """Get list of all tables in a schema.

        Args:
            schema: Schema name to list tables from
            use_cache: Whether to use cached results (default: True)

        Returns:
            List of table names in the schema
        """
        cache_key = f"tables:{schema}"

        if use_cache:
            cached = self._tables_cache.get(cache_key)
            if cached is not None:
                return cached

        rows = await self._pool.fetch(SchemaQueries.LIST_TABLES, schema)
        result = [row["table_name"] for row in rows]

        self._tables_cache.set(cache_key, result)
        return result

    async def get_columns(self, table: str, schema: str = "public") -> list[Column]:
        """Get columns for a table."""
        rows = await self._pool.fetch(SchemaQueries.GET_COLUMNS, table, schema)
        return [
            Column(
                name=row["column_name"],
                data_type=row["data_type"],
                is_nullable=row["is_nullable"] == "YES",
                default=row["column_default"],
                is_primary_key=row["is_primary_key"],
            )
            for row in rows
        ]

    async def get_primary_keys(self, table: str, schema: str = "public") -> list[str]:
        """Get primary key columns for a table."""
        rows = await self._pool.fetch(SchemaQueries.GET_PRIMARY_KEYS, table, schema)
        return [row["column_name"] for row in rows]

    async def get_foreign_keys(self, table: str, schema: str = "public") -> list[ForeignKey]:
        """Get foreign key constraints for a table."""
        rows = await self._pool.fetch(SchemaQueries.GET_FOREIGN_KEYS, table, schema)
        return [
            ForeignKey(
                column=row["column_name"],
                references_table=row["references_table"],
                references_column=row["references_column"],
                constraint_name=row["constraint_name"],
            )
            for row in rows
        ]

    async def get_indexes(self, table: str, schema: str = "public") -> list[Index]:
        """Get indexes for a table."""
        rows = await self._pool.fetch(SchemaQueries.GET_INDEXES, table, schema)
        return [
            Index(
                name=row["index_name"],
                columns=row["columns"],
                is_unique=row["is_unique"],
                definition=row["definition"],
            )
            for row in rows
        ]

    async def get_row_count(self, table: str, schema: str = "public") -> int:
        """Get approximate row count for a table."""
        query = build_count_query(table, schema)
        result = await self._pool.fetchval(query)
        return result or 0

    async def get_table(self, table: str, schema: str = "public", use_cache: bool = True) -> Table:
        """Get complete schema information for a table.

        Args:
            table: Table name
            schema: Schema name (default: public)
            use_cache: Whether to use cached results (default: True)

        Returns:
            Table object with columns, keys, indexes, and row count
        """
        cache_key = f"{schema}.{table}"

        if use_cache:
            cached = self._table_cache.get(cache_key)
            if cached is not None:
                return cached

        columns = await self.get_columns(table, schema)
        primary_keys = await self.get_primary_keys(table, schema)
        foreign_keys = await self.get_foreign_keys(table, schema)
        indexes = await self.get_indexes(table, schema)
        row_count = await self.get_row_count(table, schema)

        table_obj = Table(
            schema_name=schema,
            name=table,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
            row_count=row_count,
        )

        self._table_cache.set(cache_key, table_obj)
        return table_obj

    async def get_full_schema(self, schema: str = "public") -> list[Table]:
        """Get complete schema for all tables."""
        tables = await self.get_tables(schema)
        return [await self.get_table(t, schema) for t in tables]

    async def get_relationships(self, schema: str = "public") -> list[dict]:
        """Get all foreign key relationships in the schema."""
        rows = await self._pool.fetch(SchemaQueries.GET_RELATIONSHIPS, schema)
        return [dict(row) for row in rows]

    def format_schema_as_text(self, tables: list[Table]) -> str:
        """Format schema information as human-readable text."""
        lines = []
        for table in tables:
            lines.append(f"## Table: {table.schema_name}.{table.name}")
            lines.append(f"Rows: ~{table.row_count:,}" if table.row_count else "Rows: unknown")
            lines.append("")

            lines.append("### Columns")
            for col in table.columns:
                pk = " [PK]" if col.is_primary_key else ""
                nullable = " NULL" if col.is_nullable else " NOT NULL"
                default = f" DEFAULT {col.default}" if col.default else ""
                lines.append(f"- {col.name}: {col.data_type}{pk}{nullable}{default}")
            lines.append("")

            if table.foreign_keys:
                lines.append("### Foreign Keys")
                for fk in table.foreign_keys:
                    lines.append(f"- {fk.column} -> {fk.references_table}.{fk.references_column}")
                lines.append("")

            if table.indexes:
                lines.append("### Indexes")
                for idx in table.indexes:
                    unique = " (unique)" if idx.is_unique else ""
                    lines.append(f"- {idx.name}: ({', '.join(idx.columns)}){unique}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
