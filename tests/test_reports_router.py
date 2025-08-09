"""
Integration tests for the reports API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.main import app
from app.models import Album, Track, Artist
from app.exceptions import TracklistException


class TestReportsRouter:
    """Test cases for reports API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_reporting_service(self):
        """Create mock reporting service"""
        with patch("app.reporting_service.get_reporting_service") as mock:
            service = MagicMock()
            mock.return_value = service
            yield service
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        with patch("app.database.get_db") as mock:
            db = MagicMock()
            # Make it return the db mock when used as a generator
            mock.return_value = iter([db])
            yield db
    
    def test_get_overview_statistics_success(self, client, mock_reporting_service, mock_db):
        """Test successful retrieval of overview statistics"""
        # Setup mock response
        mock_reporting_service.get_overview_statistics.return_value = {
            "total_albums": 150,
            "fully_rated_count": 87,
            "in_progress_count": 23,
            "average_album_score": 73.5,
            "total_tracks_rated": 1024,
            "rating_distribution": {
                "skip": 120,
                "filler": 340,
                "good": 380,
                "standout": 184
            },
            "unrated_albums_count": 40
        }
        
        # Make request
        response = client.get("/api/v1/reports/overview")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["total_albums"] == 150
        assert data["fully_rated_count"] == 87
        assert data["in_progress_count"] == 23
        assert data["average_album_score"] == 73.5
        assert data["total_tracks_rated"] == 1024
        assert data["rating_distribution"]["skip"] == 120
        assert data["rating_distribution"]["good"] == 380
        assert data["unrated_albums_count"] == 40
    
    def test_get_overview_statistics_empty_collection(self, client, mock_reporting_service, mock_db):
        """Test overview statistics with empty collection"""
        # Setup mock response for empty collection
        mock_reporting_service.get_overview_statistics.return_value = {
            "total_albums": 0,
            "fully_rated_count": 0,
            "in_progress_count": 0,
            "average_album_score": None,
            "total_tracks_rated": 0,
            "rating_distribution": {
                "skip": 0,
                "filler": 0,
                "good": 0,
                "standout": 0
            },
            "unrated_albums_count": 0
        }
        
        # Make request
        response = client.get("/api/v1/reports/overview")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["total_albums"] == 0
        assert data["average_album_score"] is None
        assert data["total_tracks_rated"] == 0
    
    def test_get_overview_statistics_service_error(self, client, mock_reporting_service, mock_db):
        """Test overview statistics with service error"""
        # Setup mock to raise exception
        mock_reporting_service.get_overview_statistics.side_effect = TracklistException("Database connection failed")
        
        # Make request
        response = client.get("/api/v1/reports/overview")
        
        # Verify error response
        assert response.status_code == 500
        data = response.json()
        assert "error" in data["detail"]
        assert "Failed to generate statistics" in data["detail"]["error"]
    
    def test_get_recent_activity_success(self, client, mock_reporting_service, mock_db):
        """Test successful retrieval of recent activity"""
        # Setup mock response
        mock_reporting_service.get_recent_activity.return_value = {
            "recently_rated": [
                {
                    "id": 123,
                    "name": "Abbey Road",
                    "artist": "The Beatles",
                    "year": 1969,
                    "score": 88,
                    "cover_art_url": "https://example.com/cover1.jpg",
                    "rated_at": "2024-01-15T10:30:00"
                },
                {
                    "id": 124,
                    "name": "The Dark Side of the Moon",
                    "artist": "Pink Floyd",
                    "year": 1973,
                    "score": 92,
                    "cover_art_url": "https://example.com/cover2.jpg",
                    "rated_at": "2024-01-14T15:45:00"
                }
            ],
            "in_progress": [
                {
                    "id": 125,
                    "name": "OK Computer",
                    "artist": "Radiohead",
                    "year": 1997,
                    "cover_art_url": "https://example.com/cover3.jpg",
                    "progress": {
                        "rated_tracks": 5,
                        "total_tracks": 12,
                        "percentage": 41.7
                    },
                    "updated_at": "2024-01-16T09:15:00"
                }
            ]
        }
        
        # Make request
        response = client.get("/api/v1/reports/activity")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data["recently_rated"]) == 2
        assert data["recently_rated"][0]["name"] == "Abbey Road"
        assert data["recently_rated"][0]["score"] == 88
        assert len(data["in_progress"]) == 1
        assert data["in_progress"][0]["name"] == "OK Computer"
        assert data["in_progress"][0]["progress"]["percentage"] == 41.7
    
    def test_get_recent_activity_with_limit(self, client, mock_reporting_service, mock_db):
        """Test recent activity with custom limit"""
        mock_reporting_service.get_recent_activity.return_value = {
            "recently_rated": [],
            "in_progress": []
        }
        
        # Make request with limit
        response = client.get("/api/v1/reports/activity?limit=5")
        
        # Verify the service was called with correct limit
        assert response.status_code == 200
        mock_reporting_service.get_recent_activity.assert_called_once()
        call_args = mock_reporting_service.get_recent_activity.call_args
        assert call_args[1]["limit"] == 5
    
    def test_get_recent_activity_invalid_limit(self, client):
        """Test recent activity with invalid limit"""
        # Test limit too high
        response = client.get("/api/v1/reports/activity?limit=100")
        assert response.status_code == 422
        
        # Test limit too low
        response = client.get("/api/v1/reports/activity?limit=0")
        assert response.status_code == 422
    
    def test_get_top_albums_success(self, client, mock_reporting_service, mock_db):
        """Test successful retrieval of top albums"""
        # Setup mock response
        mock_reporting_service.get_top_albums.return_value = [
            {
                "id": 45,
                "name": "OK Computer",
                "artist": "Radiohead",
                "year": 1997,
                "score": 95,
                "cover_art_url": "https://example.com/ok_computer.jpg",
                "rated_at": "2024-01-10T14:22:00"
            },
            {
                "id": 67,
                "name": "In Rainbows",
                "artist": "Radiohead",
                "year": 2007,
                "score": 93,
                "cover_art_url": "https://example.com/in_rainbows.jpg",
                "rated_at": "2024-01-12T16:45:00"
            },
            {
                "id": 89,
                "name": "Revolver",
                "artist": "The Beatles",
                "year": 1966,
                "score": 91,
                "cover_art_url": "https://example.com/revolver.jpg",
                "rated_at": "2024-01-08T11:30:00"
            }
        ]
        
        # Make request
        response = client.get("/api/v1/reports/top-albums")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "OK Computer"
        assert data[0]["score"] == 95
        assert data[1]["name"] == "In Rainbows"
        assert data[1]["score"] == 93
        assert data[2]["name"] == "Revolver"
        assert data[2]["score"] == 91
    
    def test_get_top_albums_with_limit(self, client, mock_reporting_service, mock_db):
        """Test top albums with custom limit"""
        mock_reporting_service.get_top_albums.return_value = []
        
        # Make request with limit
        response = client.get("/api/v1/reports/top-albums?limit=25")
        
        # Verify the service was called with correct limit
        assert response.status_code == 200
        mock_reporting_service.get_top_albums.assert_called_once()
        call_args = mock_reporting_service.get_top_albums.call_args
        assert call_args[1]["limit"] == 25
    
    def test_get_top_albums_empty_collection(self, client, mock_reporting_service, mock_db):
        """Test top albums with no rated albums"""
        # Setup mock response for empty collection
        mock_reporting_service.get_top_albums.return_value = []
        
        # Make request
        response = client.get("/api/v1/reports/top-albums")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
    
    def test_get_top_albums_service_error(self, client, mock_reporting_service, mock_db):
        """Test top albums with service error"""
        # Setup mock to raise exception
        mock_reporting_service.get_top_albums.side_effect = TracklistException("Failed to retrieve albums")
        
        # Make request
        response = client.get("/api/v1/reports/top-albums")
        
        # Verify error response
        assert response.status_code == 500
        data = response.json()
        assert "error" in data["detail"]
        assert "Failed to get top albums" in data["detail"]["error"]
    
    def test_endpoints_are_documented(self, client):
        """Test that endpoints appear in OpenAPI documentation"""
        # Get OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        openapi = response.json()
        paths = openapi["paths"]
        
        # Verify endpoints exist in documentation
        assert "/api/v1/reports/overview" in paths
        assert "/api/v1/reports/activity" in paths
        assert "/api/v1/reports/top-albums" in paths
        
        # Verify tags
        tags = [tag["name"] for tag in openapi["tags"]]
        assert "reports" in tags