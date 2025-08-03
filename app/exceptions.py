from fastapi import HTTPException
from typing import Any, Dict, Optional


class TracklistException(Exception):
    """Base exception for Tracklist application"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class DatabaseException(TracklistException):
    """Database related exceptions"""
    pass


class ValidationException(TracklistException):
    """Validation related exceptions"""
    pass


class NotFoundError(HTTPException):
    """Resource not found exception"""
    def __init__(self, resource: str, identifier: Any):
        detail = f"{resource} with identifier '{identifier}' not found"
        super().__init__(status_code=404, detail=detail)


class ValidationError(HTTPException):
    """Validation error exception"""
    def __init__(self, message: str, field: Optional[str] = None):
        detail = {"message": message}
        if field:
            detail["field"] = field
        super().__init__(status_code=400, detail=detail)


class ConflictError(HTTPException):
    """Resource conflict exception"""
    def __init__(self, message: str):
        super().__init__(status_code=409, detail=message)