"""Tests for QueryExecutor write detection and safety checks."""

from unittest.mock import MagicMock

import pytest

from query.executor import QueryExecutor


class TestWriteDetection:
    """Tests for write query detection."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor with a mock pool."""
        mock_pool = MagicMock()
        return QueryExecutor(mock_pool)

    def test_detect_insert(self, executor):
        """INSERT queries should be detected as write."""
        assert executor.is_write_query("INSERT INTO users VALUES (1)")
        assert executor.is_write_query("  INSERT INTO users VALUES (1)")
        assert executor.is_write_query("insert into users values (1)")

    def test_detect_update(self, executor):
        """UPDATE queries should be detected as write."""
        assert executor.is_write_query("UPDATE users SET name = 'test'")
        assert executor.is_write_query("  update users set name = 'test'")

    def test_detect_delete(self, executor):
        """DELETE queries should be detected as write."""
        assert executor.is_write_query("DELETE FROM users WHERE id = 1")
        assert executor.is_write_query("delete from users")

    def test_detect_drop(self, executor):
        """DROP queries should be detected as write."""
        assert executor.is_write_query("DROP TABLE users")
        assert executor.is_write_query("DROP INDEX idx_users")

    def test_detect_create(self, executor):
        """CREATE queries should be detected as write."""
        assert executor.is_write_query("CREATE TABLE users (id INT)")
        assert executor.is_write_query("CREATE INDEX idx ON users(id)")

    def test_detect_alter(self, executor):
        """ALTER queries should be detected as write."""
        assert executor.is_write_query("ALTER TABLE users ADD COLUMN name TEXT")

    def test_detect_truncate(self, executor):
        """TRUNCATE queries should be detected as write."""
        assert executor.is_write_query("TRUNCATE TABLE users")

    def test_detect_grant(self, executor):
        """GRANT queries should be detected as write."""
        assert executor.is_write_query("GRANT SELECT ON users TO reader")

    def test_detect_revoke(self, executor):
        """REVOKE queries should be detected as write."""
        assert executor.is_write_query("REVOKE SELECT ON users FROM reader")

    def test_select_not_write(self, executor):
        """SELECT queries should not be detected as write."""
        assert not executor.is_write_query("SELECT * FROM users")
        assert not executor.is_write_query("SELECT id, name FROM users WHERE id = 1")

    def test_explain_not_write(self, executor):
        """EXPLAIN queries should not be detected as write."""
        assert not executor.is_write_query("EXPLAIN SELECT * FROM users")
        assert not executor.is_write_query("EXPLAIN ANALYZE SELECT * FROM users")

    def test_cte_select_not_write(self, executor):
        """CTE SELECT queries should not be detected as write."""
        query = "WITH active AS (SELECT * FROM users WHERE active) SELECT * FROM active"
        assert not executor.is_write_query(query)

    def test_is_safe_read_inverse(self, executor):
        """is_safe_read_query should be inverse of is_write_query."""
        select_query = "SELECT * FROM users"
        insert_query = "INSERT INTO users VALUES (1)"

        assert executor.is_safe_read_query(select_query)
        assert not executor.is_safe_read_query(insert_query)


class TestLimitInjection:
    """Tests for automatic LIMIT injection."""

    @pytest.fixture
    def executor(self):
        """Create a QueryExecutor with a mock pool."""
        mock_pool = MagicMock()
        return QueryExecutor(mock_pool)

    def test_add_limit_to_select(self, executor):
        """LIMIT should be added to queries without it."""
        query = "SELECT * FROM users"
        result = executor._add_limit_if_needed(query, 100)
        assert result == "SELECT * FROM users LIMIT 100"

    def test_preserve_existing_limit(self, executor):
        """Existing LIMIT should be preserved."""
        query = "SELECT * FROM users LIMIT 50"
        result = executor._add_limit_if_needed(query, 100)
        assert result == query

    def test_strip_trailing_semicolon(self, executor):
        """Trailing semicolon should be removed before adding LIMIT."""
        query = "SELECT * FROM users;"
        result = executor._add_limit_if_needed(query, 100)
        assert result == "SELECT * FROM users LIMIT 100"

    def test_handle_whitespace(self, executor):
        """Whitespace should be handled correctly."""
        query = "SELECT * FROM users  ;  "
        result = executor._add_limit_if_needed(query, 100)
        assert result.endswith("LIMIT 100")
