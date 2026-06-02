"""Consolidated tests for models and response system."""

import json

from models.responses import (
    ErrorCode,
    ErrorDetail,
    McpResponse,
    Response,
    ResponseMeta,
    connection_error,
    internal_error,
    success,
    success_with_issues,
    timeout_error,
    validation_error,
)


class TestMcpResponse:
    """Tests for McpResponse model."""

    def test_success_response(self):
        """Test success response structure."""
        resp = McpResponse(success=True, data={"key": "value"}, meta=ResponseMeta(connected=True, source="tool"))
        assert resp.success is True
        assert resp.data == {"key": "value"}

    def test_error_response(self):
        """Test error response structure."""
        resp = McpResponse(
            success=False,
            error=ErrorDetail(code="TEST_ERROR", message="Test error"),
            meta=ResponseMeta(connected=False, source="tool"),
        )
        assert resp.error.code == "TEST_ERROR"

    def test_to_json_excludes_none(self):
        """Test JSON excludes None fields."""
        resp = McpResponse(success=True, data={"test": 1})
        data = json.loads(resp.to_json())
        assert "error" not in data


class TestResponseFactory:
    """Tests for Response factory."""

    def test_response_ok(self):
        """Test Response.ok() creates success response."""
        data = json.loads(Response.ok({"test": 1}))
        assert data["success"] is True
        assert data["data"]["test"] == 1

    def test_response_error(self):
        """Test Response.error() creates error response."""
        data = json.loads(Response.error(ErrorCode.NOT_CONNECTED, "Test"))
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_CONNECTED"

    def test_response_not_connected(self):
        """Test Response.not_connected()."""
        data = json.loads(Response.not_connected())
        assert data["error"]["code"] == "NOT_CONNECTED"
        assert data["meta"]["connected"] is False


class TestErrorHelpers:
    """Tests for error helper functions."""

    def test_connection_error(self):
        """Test connection_error()."""
        data = json.loads(connection_error())
        assert data["error"]["code"] == "NOT_CONNECTED"
        assert "hint" in data["error"]

    def test_timeout_error(self):
        """Test timeout_error()."""
        data = json.loads(timeout_error(30000))
        assert data["error"]["code"] == "QUERY_TIMEOUT"
        assert data["error"]["details"]["timeout_ms"] == 30000

    def test_validation_error(self):
        """Test validation_error()."""
        data = json.loads(validation_error("Invalid", field="email", value="bad"))
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["details"]["field"] == "email"

    def test_internal_error(self):
        """Test internal_error()."""
        data = json.loads(internal_error(ValueError("Error"), context="test"))
        assert data["error"]["code"] == "INTERNAL_ERROR"


class TestSuccessHelpers:
    """Tests for success helper functions."""

    def test_success(self):
        """Test success()."""
        data = json.loads(success({"rows": [1, 2]}))
        assert data["success"] is True
        assert data["data"]["rows"] == [1, 2]

    def test_success_with_issues(self):
        """Test success_with_issues()."""
        data = json.loads(success_with_issues({"health": "ok"}, issues=["Issue 1"], severity="warning"))
        assert data["success"] is True
        assert data["data"]["issue_count"] == 1
        assert data["data"]["healthy"] is False
