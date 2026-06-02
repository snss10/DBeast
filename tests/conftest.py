"""Pytest configuration and fixtures for dbeast tests."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_queries():
    """Sample SQL queries for testing."""
    return {
        "select": "SELECT id, name FROM users WHERE status = 'active'",
        "select_all": "SELECT * FROM users",
        "select_join": "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id",
        "insert": "INSERT INTO users (name, email) VALUES ('Test', 'test@test.com')",
        "update": "UPDATE users SET status = 'inactive' WHERE id = 1",
        "update_no_where": "UPDATE users SET status = 'inactive'",
        "delete": "DELETE FROM users WHERE id = 1",
        "delete_no_where": "DELETE FROM users",
        "drop": "DROP TABLE users",
        "truncate": "TRUNCATE TABLE users",
    }


@pytest.fixture
def dangerous_where_clauses():
    """Dangerous WHERE clauses for SQL injection testing."""
    return [
        "1=1; DROP TABLE users;--",
        "1=1 UNION SELECT * FROM passwords",
        "1=1; DELETE FROM users;",
        "id = 1 /* comment */ OR 1=1",
        "1=1; pg_sleep(10);",
        "1=1 INTO OUTFILE '/etc/passwd'",
    ]


@pytest.fixture
def safe_where_clauses():
    """Safe WHERE clauses for testing."""
    return [
        "id = 1",
        "status = 'active' AND created_at > '2024-01-01'",
        "name LIKE '%test%'",
        "id IN (1, 2, 3)",
        "user_id = 123 AND deleted_at IS NULL",
    ]
