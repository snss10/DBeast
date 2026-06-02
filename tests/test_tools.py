"""Consolidated tests for MCP tools (health, data quality, query, security, connection)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models import QueryInput

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.is_connected = True
    return pool


@pytest.fixture
def mock_schema_discovery():
    """Create a mock schema discovery."""
    discovery = MagicMock()
    discovery.get_schemas = AsyncMock(return_value=[{"schema_name": "public", "table_count": 5}])
    discovery.get_tables = AsyncMock(return_value=[])
    discovery.get_columns = AsyncMock(return_value=[])
    return discovery


@pytest.fixture
def mock_ctx(mock_db_pool, mock_schema_discovery):
    """Create a mock tool context."""
    ctx = MagicMock()
    ctx.db_pool = mock_db_pool
    ctx.schema_discovery = mock_schema_discovery
    ctx.ensure_connected = AsyncMock(return_value=None)
    ctx.formatter = MagicMock()
    return ctx


@pytest.fixture
def mock_mcp():
    """Create a mock FastMCP server."""
    mcp = MagicMock()
    registered_tools = []

    def tool_decorator():
        def decorator(func):
            registered_tools.append(func)
            return func

        return decorator

    mcp.tool = tool_decorator
    mcp._registered_tools = registered_tools
    return mcp


# =============================================================================
# Query Template Tests
# =============================================================================


class TestQueryTemplates:
    """Tests for SQL query templates."""

    def test_health_queries(self):
        """Test health query templates."""
        from query.templates.health import HealthQueries

        assert "SELECT" in HealthQueries.DATABASE_STATS.upper()
        assert "pg_stat_database" in HealthQueries.DATABASE_STATS

    def test_data_quality_queries(self):
        """Test data quality query templates."""
        from query.templates.data_quality import DataQualityQueries

        query = DataQualityQueries.null_analysis("public", "users")
        assert "SELECT" in query.upper()

    def test_security_queries(self):
        """Test security query templates."""
        from query.templates.security import SecurityQueries

        assert "SELECT" in SecurityQueries.SUPERUSERS.upper()


# =============================================================================
# Security Service Tests
# =============================================================================


class TestSecurityAuditService:
    """Tests for SecurityAuditService."""

    @pytest.fixture
    def service(self, mock_db_pool, mock_schema_discovery):
        """Create a SecurityAuditService instance."""
        from services import SecurityAuditService

        return SecurityAuditService(mock_db_pool, mock_schema_discovery)

    @pytest.mark.asyncio
    async def test_audit_schema_security(self, service, mock_db_pool):
        """Test basic schema security audit."""
        result = await service.audit_schema_security("public", "all")
        assert result["schema"] == "public"
        assert "issues" in result

    @pytest.mark.asyncio
    async def test_full_audit_all_schemas(self, service, mock_db_pool):
        """Test full audit for all schemas."""
        result = await service.full_audit("all", "all")
        assert "schemas_analyzed" in result

    def test_format_audit_markdown(self, service):
        """Test markdown formatting."""
        result = {"superusers": [{"rolname": "postgres"}], "ssl_config": [{"name": "ssl", "setting": "on"}]}
        markdown = service.format_audit_markdown(result, "public")
        assert "Security Audit Report" in markdown


# =============================================================================
# Query Analyzer Tests
# =============================================================================


class TestBatchQueryAnalyzer:
    """Tests for BatchQueryAnalyzer."""

    @pytest.fixture
    def analyzer(self, mock_db_pool, mock_schema_discovery):
        """Create a BatchQueryAnalyzer instance."""
        from query import BatchQueryAnalyzer

        return BatchQueryAnalyzer(pool=mock_db_pool, schema_discovery=mock_schema_discovery)

    @pytest.mark.asyncio
    async def test_analyze_batch_single_query(self, analyzer):
        """Test analyzing a single query in a batch."""
        queries = [QueryInput(id="q1", sql="SELECT id FROM users", name="get_users")]
        result = await analyzer.analyze_batch(queries, include_explain=False)
        assert len(result.queries) == 1
        assert result.queries[0].query_type == "SELECT"

    @pytest.mark.asyncio
    async def test_analyze_batch_multiple(self, analyzer):
        """Test analyzing multiple queries."""
        queries = [
            QueryInput(id="q1", sql="SELECT * FROM users", name="q1"),
            QueryInput(id="q2", sql="SELECT * FROM orders", name="q2"),
        ]
        result = await analyzer.analyze_batch(queries, include_explain=False)
        assert len(result.queries) == 2


class TestImpactAnalyzer:
    """Tests for ImpactAnalyzer."""

    @pytest.fixture
    def analyzer(self, mock_db_pool, mock_schema_discovery):
        """Create an ImpactAnalyzer instance."""
        from query import ImpactAnalyzer

        return ImpactAnalyzer(pool=mock_db_pool, schema=mock_schema_discovery)

    def test_parse_query_type(self, analyzer):
        """Test query type detection."""
        assert analyzer.parse_query_type("DELETE FROM users") == "DELETE"
        assert analyzer.parse_query_type("UPDATE users SET x=1") == "UPDATE"
        assert analyzer.parse_query_type("SELECT * FROM users") == "SELECT"

    def test_extract_table_name(self, analyzer):
        """Test table name extraction."""
        assert analyzer.extract_table_name("DELETE FROM users WHERE id=1") == "users"
        assert analyzer.extract_table_name("UPDATE orders SET status='done'") == "orders"

    @pytest.mark.asyncio
    async def test_analyze_delete(self, analyzer, mock_db_pool):
        """Test analyzing DELETE statement."""
        mock_db_pool.fetchrow = AsyncMock(return_value={"count": 42})
        mock_db_pool.fetch = AsyncMock(return_value=[])
        result = await analyzer.analyze_delete("DELETE FROM users WHERE active=false", schema="public")
        assert result.query_type == "DELETE"


# =============================================================================
# SQL Sanitizer Tests
# =============================================================================


class TestSQLSanitizer:
    """Tests for SQL injection prevention."""

    def test_validate_identifier_valid(self):
        """Test valid identifiers pass."""
        from query.templates.schema import SQLSanitizer

        SQLSanitizer.validate_identifier("users", "table")
        SQLSanitizer.validate_identifier("user_id", "column")

    def test_validate_identifier_invalid(self):
        """Test invalid identifiers rejected."""
        from query.templates.schema import SQLSanitizer

        with pytest.raises((ValueError, Exception)):
            SQLSanitizer.validate_identifier("users; DROP TABLE--", "table")

    def test_validate_where_clause(self):
        """Test WHERE clause validation."""
        from query.templates.schema import SQLSanitizer

        # Safe clause should pass
        result = SQLSanitizer.validate_where_clause("id = 1")
        assert result == "id = 1"
        # Dangerous clause should fail
        with pytest.raises(ValueError, match="dangerous SQL pattern"):
            SQLSanitizer.validate_where_clause("1=1; DROP TABLE users;--")
