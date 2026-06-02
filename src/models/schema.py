"""Database schema models."""

from pydantic import BaseModel


class Column(BaseModel):
    """Database column definition."""

    name: str
    data_type: str
    is_nullable: bool
    default: str | None = None
    is_primary_key: bool = False


class ForeignKey(BaseModel):
    """Foreign key constraint."""

    column: str
    references_table: str
    references_column: str
    constraint_name: str


class Index(BaseModel):
    """Database index definition."""

    name: str
    columns: list[str]
    is_unique: bool
    definition: str


class Table(BaseModel):
    """Complete table schema information."""

    schema_name: str
    name: str
    columns: list[Column]
    primary_keys: list[str]
    foreign_keys: list[ForeignKey]
    indexes: list[Index]
    row_count: int | None = None
