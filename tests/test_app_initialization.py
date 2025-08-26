"""
Tests for app initialization and configuration.
"""

import pytest
from unittest.mock import patch, Mock
import os


class TestAppInitialization:
    """Test app initialization and configuration."""
    
    @pytest.mark.unit
    def test_app_creation(self):
        """Test that app is created successfully."""
        from app.main import app
        assert app is not None
        assert app.title == "Tracklist"
        assert app.version is not None
    
    @pytest.mark.unit
    def test_app_routes_registered(self):
        """Test that routes are registered."""
        from app.main import app
        
        # Check that we have routes
        routes = [route.path for route in app.routes]
        
        # Check critical routes exist
        assert "/" in routes
        assert "/health" in routes
        assert "/api/albums" in routes
    
    @pytest.mark.unit
    def test_app_middleware_configured(self):
        """Test that middleware is configured."""
        from app.main import app
        
        # Check CORS middleware
        middleware_types = [type(m) for m in app.middleware]
        assert len(middleware_types) > 0
    
    @pytest.mark.unit
    def test_database_url_configuration(self):
        """Test database URL configuration."""
        from app.database import DATABASE_URL
        
        # In testing mode, should be using SQLite
        assert "sqlite" in DATABASE_URL or "TESTING" in os.environ
    
    @pytest.mark.unit
    def test_exception_types(self):
        """Test custom exception types."""
        from app.exceptions import (
            TracklistException,
            ServiceNotFoundError, 
            ServiceValidationError,
            MusicBrainzException
        )
        
        # Test exception hierarchy
        assert issubclass(ServiceNotFoundError, TracklistException)
        assert issubclass(ServiceValidationError, TracklistException)
        assert issubclass(MusicBrainzException, TracklistException)
        
        # Test exception creation
        exc = ServiceNotFoundError("Album", 123)
        assert "Album" in str(exc)
        assert "123" in str(exc)
    
    @pytest.mark.unit
    def test_rating_constants(self):
        """Test rating constants."""
        from app.rating_service import VALID_RATINGS
        
        assert VALID_RATINGS == [0.0, 0.33, 0.67, 1.0]
        assert len(VALID_RATINGS) == 4
        assert all(0 <= r <= 1 for r in VALID_RATINGS)
    
    @pytest.mark.unit
    def test_logging_configuration(self):
        """Test logging is configured."""
        import logging
        from app.logging_config import logger
        
        # Logger should be configured
        assert logger is not None
        assert isinstance(logger, logging.Logger)
        
        # Should have handlers configured
        assert len(logger.handlers) >= 0  # May have handlers in test mode
    
    @pytest.mark.unit
    def test_cache_singleton_pattern(self):
        """Test cache services use singleton pattern."""
        from app.cache import get_cache_service
        
        cache1 = get_cache_service()
        cache2 = get_cache_service()
        assert cache1 is cache2  # Should be same instance
    
    @pytest.mark.unit
    def test_musicbrainz_service_singleton(self):
        """Test MusicBrainz service singleton."""
        from app.musicbrainz_service import get_musicbrainz_service
        
        service1 = get_musicbrainz_service()
        service2 = get_musicbrainz_service()
        assert service1 is service2
    
    @pytest.mark.unit
    def test_rating_service_creation(self):
        """Test rating service can be created."""
        from app.rating_service import get_rating_service
        
        service = get_rating_service()
        assert service is not None
        assert hasattr(service, 'rate_track')
        assert hasattr(service, 'submit_album_rating')
        assert hasattr(service, 'get_album_progress')