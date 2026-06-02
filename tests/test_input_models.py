"""Tests for input validation models.

Validates that Pydantic models correctly enforce constraints
on tool input parameters.
"""

import pytest
from pydantic import ValidationError

from models.inputs import (
    AnalyzeImpactInput,
    AnalyzeQueryInput,
    ConfigurationReviewInput,
    ConnectInput,
    DatabaseHealthInput,
    DataQualityInput,
    DependencyAnalysisInput,
    DuplicateDetectionInput,
    ExecuteQueryInput,
    MaintenanceAnalysisInput,
    PartitionAnalysisInput,
    QueryPerformanceInput,
    ReplicationStatusInput,
    SchemaInput,
    SecurityAuditInput,
)


class TestExecuteQueryInput:
    """Tests for ExecuteQueryInput model."""

    def test_valid_query(self):
        """Test valid query input."""
        input_data = ExecuteQueryInput(query="SELECT * FROM users")
        assert input_data.query == "SELECT * FROM users"
        assert input_data.limit == 100  # default
        assert input_data.timeout_ms == 300000  # default (5 min)

    def test_custom_limit(self):
        """Test custom limit."""
        input_data = ExecuteQueryInput(query="SELECT * FROM users", limit=500)
        assert input_data.limit == 500

    def test_empty_query_rejected(self):
        """Test that empty query is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteQueryInput(query="")
        assert "min_length" in str(exc_info.value).lower() or "at least" in str(exc_info.value).lower()

    def test_whitespace_only_query_rejected(self):
        """Test that whitespace-only query is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="   ")

    def test_limit_too_low(self):
        """Test that limit below minimum is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="SELECT 1", limit=0)

    def test_limit_too_high(self):
        """Test that limit above maximum is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="SELECT 1", limit=100000)

    def test_timeout_too_low(self):
        """Test that timeout below minimum is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="SELECT 1", timeout_ms=50)

    def test_timeout_too_high(self):
        """Test that timeout above maximum is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="SELECT 1", timeout_ms=1000000)

    def test_invalid_format(self):
        """Test that invalid format is rejected."""
        with pytest.raises(ValidationError):
            ExecuteQueryInput(query="SELECT 1", format="xml")


class TestAnalyzeQueryInput:
    """Tests for AnalyzeQueryInput model."""

    def test_valid_input(self):
        """Test valid analyze query input."""
        input_data = AnalyzeQueryInput(query="SELECT * FROM users")
        assert input_data.query == "SELECT * FROM users"
        assert input_data.detect_duplicates is True
        assert input_data.include_explain is False

    def test_schema_pattern_valid(self):
        """Test valid schema names."""
        input_data = AnalyzeQueryInput(query="SELECT 1", schema="my_schema")
        assert input_data.schema == "my_schema"

    def test_schema_none_allowed(self):
        """Test schema can be None (prompts user to specify)."""
        input_data = AnalyzeQueryInput(query="SELECT 1", schema=None)
        assert input_data.schema is None

    def test_schema_max_length(self):
        """Test schema max length constraint."""
        with pytest.raises(ValidationError):
            AnalyzeQueryInput(query="SELECT 1", schema="a" * 129)  # exceeds 128 char limit


class TestAnalyzeImpactInput:
    """Tests for AnalyzeImpactInput model."""

    def test_valid_delete(self):
        """Test valid DELETE query."""
        input_data = AnalyzeImpactInput(query="DELETE FROM users WHERE id = 1")
        assert "DELETE" in input_data.query

    def test_sample_limit_range(self):
        """Test sample_limit constraints."""
        # Valid
        input_data = AnalyzeImpactInput(query="DELETE FROM x", sample_limit=50)
        assert input_data.sample_limit == 50

        # Too low
        with pytest.raises(ValidationError):
            AnalyzeImpactInput(query="DELETE FROM x", sample_limit=0)

        # Too high
        with pytest.raises(ValidationError):
            AnalyzeImpactInput(query="DELETE FROM x", sample_limit=2000)


class TestSchemaInput:
    """Tests for SchemaInput model."""

    def test_default_schema_none(self):
        """Test default schema is None (list all)."""
        input_data = SchemaInput()
        assert input_data.schema is None

    def test_schema_all(self):
        """Test 'all' schema value."""
        input_data = SchemaInput(schema="all")
        assert input_data.schema == "all"

    def test_specific_schema(self):
        """Test specific schema name."""
        input_data = SchemaInput(schema="public")
        assert input_data.schema == "public"

    def test_mermaid_format(self):
        """Test mermaid format option."""
        input_data = SchemaInput(format="mermaid")
        assert input_data.format == "mermaid"

    def test_invalid_format(self):
        """Test invalid format rejected."""
        with pytest.raises(ValidationError):
            SchemaInput(format="csv")


class TestDuplicateDetectionInput:
    """Tests for DuplicateDetectionInput model."""

    def test_valid_input(self):
        """Test valid duplicate detection input."""
        input_data = DuplicateDetectionInput(table="users", columns="email,name")
        assert input_data.table == "users"
        assert input_data.columns == "email,name"

    def test_empty_table_rejected(self):
        """Test empty table name rejected."""
        with pytest.raises(ValidationError):
            DuplicateDetectionInput(table="", columns="id")

    def test_invalid_table_name(self):
        """Test invalid table name rejected."""
        with pytest.raises(ValidationError):
            DuplicateDetectionInput(table="users; DROP--", columns="id")

    def test_empty_columns_rejected(self):
        """Test empty columns rejected."""
        with pytest.raises(ValidationError):
            DuplicateDetectionInput(table="users", columns="")

    def test_invalid_column_names(self):
        """Test invalid column names in list rejected."""
        with pytest.raises(ValidationError):
            DuplicateDetectionInput(table="users", columns="id, name; DROP")

    def test_columns_with_spaces(self):
        """Test columns with spaces around commas."""
        input_data = DuplicateDetectionInput(table="users", columns="email, name, id")
        assert input_data.columns == "email, name, id"


class TestQueryPerformanceInput:
    """Tests for QueryPerformanceInput model."""

    def test_defaults(self):
        """Test default values."""
        input_data = QueryPerformanceInput()
        assert input_data.limit == 20
        assert input_data.order_by == "total_time"
        assert input_data.min_calls == 1

    def test_valid_order_by(self):
        """Test valid order_by options."""
        for order in ["total_time", "calls", "mean_time", "rows", "shared_blks_hit", "shared_blks_read"]:
            input_data = QueryPerformanceInput(order_by=order)
            assert input_data.order_by == order

    def test_invalid_order_by(self):
        """Test invalid order_by rejected."""
        with pytest.raises(ValidationError):
            QueryPerformanceInput(order_by="invalid_field")

    def test_limit_constraints(self):
        """Test limit constraints."""
        # Valid
        input_data = QueryPerformanceInput(limit=100)
        assert input_data.limit == 100

        # Too high
        with pytest.raises(ValidationError):
            QueryPerformanceInput(limit=1000)


class TestConnectInput:
    """Tests for ConnectInput model."""

    def test_minimal_input(self):
        """Test minimal connect input."""
        input_data = ConnectInput()
        assert input_data.url is None
        assert input_data.host is None

    def test_url_input(self):
        """Test URL-based connection."""
        input_data = ConnectInput(url="postgresql://user:pass@localhost:5432/db")
        assert "postgresql" in input_data.url

    def test_host_port_input(self):
        """Test host/port connection."""
        input_data = ConnectInput(host="localhost", port=5432, user="postgres", database="mydb")
        assert input_data.host == "localhost"
        assert input_data.port == 5432

    def test_port_constraints(self):
        """Test port number constraints."""
        # Valid
        input_data = ConnectInput(port=5432)
        assert input_data.port == 5432

        # Too low
        with pytest.raises(ValidationError):
            ConnectInput(port=0)

        # Too high
        with pytest.raises(ValidationError):
            ConnectInput(port=70000)

    def test_discover_flag(self):
        """Test discover flag."""
        input_data = ConnectInput(discover=True)
        assert input_data.discover is True


class TestLiteralTypeValidation:
    """Tests for Literal type validation across models."""

    def test_database_health_include(self):
        """Test DatabaseHealthInput include options."""
        for include in ["all", "summary", "sessions", "locks", "transactions", "queries", "bloat"]:
            input_data = DatabaseHealthInput(include=include)
            assert input_data.include == include

        with pytest.raises(ValidationError):
            DatabaseHealthInput(include="invalid")

    def test_security_audit_include(self):
        """Test SecurityAuditInput include options."""
        for include in ["all", "roles", "privileges", "rls", "ssl", "sensitive", "functions"]:
            input_data = SecurityAuditInput(include=include)
            assert input_data.include == include

    def test_maintenance_include(self):
        """Test MaintenanceAnalysisInput include options."""
        for include in ["all", "indexes", "tables", "vacuum", "fk_indexes", "toast"]:
            input_data = MaintenanceAnalysisInput(include=include)
            assert input_data.include == include

    def test_replication_include(self):
        """Test ReplicationStatusInput include options."""
        for include in ["all", "physical", "logical", "slots", "wal", "archiving"]:
            input_data = ReplicationStatusInput(include=include)
            assert input_data.include == include

    def test_config_review_include(self):
        """Test ConfigurationReviewInput include options."""
        for include in ["all", "memory", "connections", "logging", "autovacuum", "extensions"]:
            input_data = ConfigurationReviewInput(include=include)
            assert input_data.include == include

    def test_partition_include(self):
        """Test PartitionAnalysisInput include options."""
        for include in ["all", "details", "size", "activity", "indexes", "maintenance"]:
            input_data = PartitionAnalysisInput(include=include)
            assert input_data.include == include

    def test_dependency_include(self):
        """Test DependencyAnalysisInput include options."""
        for include in ["all", "views", "functions", "triggers", "sequences", "extensions", "fdw"]:
            input_data = DependencyAnalysisInput(include=include)
            assert input_data.include == include

    def test_data_quality_include(self):
        """Test DataQualityInput include options."""
        for include in ["all", "nulls", "cardinality", "empty", "outliers", "soft_delete", "types"]:
            input_data = DataQualityInput(include=include)
            assert input_data.include == include
