import pytest
from fastapi import HTTPException

from app.exceptions import (
    TracklistException,
    DatabaseException,
    ValidationException,
    NotFoundError,
    ValidationError,
    ConflictError
)


class TestTracklistException:
    def test_basic_exception(self):
        """Test basic TracklistException"""
        exc = TracklistException("Test error")
        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.details == {}

    def test_exception_with_details(self):
        """Test TracklistException with details"""
        details = {"field": "value", "code": 123}
        exc = TracklistException("Test error", details)
        assert exc.message == "Test error"
        assert exc.details == details


class TestDatabaseException:
    def test_database_exception(self):
        """Test DatabaseException inherits from TracklistException"""
        exc = DatabaseException("Database error")
        assert isinstance(exc, TracklistException)
        assert exc.message == "Database error"


class TestValidationException:
    def test_validation_exception(self):
        """Test ValidationException inherits from TracklistException"""
        exc = ValidationException("Validation error")
        assert isinstance(exc, TracklistException)
        assert exc.message == "Validation error"


class TestNotFoundError:
    def test_not_found_error(self):
        """Test NotFoundError HTTP exception"""
        exc = NotFoundError("Album", "123")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 404
        assert "Album with identifier '123' not found" in exc.detail

    def test_not_found_error_different_resource(self):
        """Test NotFoundError with different resource type"""
        exc = NotFoundError("Artist", "abc-def")
        assert exc.status_code == 404
        assert "Artist with identifier 'abc-def' not found" in exc.detail


class TestValidationError:
    def test_validation_error_basic(self):
        """Test basic ValidationError"""
        exc = ValidationError("Invalid input")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 400
        assert exc.detail["message"] == "Invalid input"
        assert "field" not in exc.detail

    def test_validation_error_with_field(self):
        """Test ValidationError with field specification"""
        exc = ValidationError("Invalid value", field="email")
        assert exc.status_code == 400
        assert exc.detail["message"] == "Invalid value"
        assert exc.detail["field"] == "email"


class TestConflictError:
    def test_conflict_error(self):
        """Test ConflictError HTTP exception"""
        exc = ConflictError("Resource already exists")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 409
        assert exc.detail == "Resource already exists"