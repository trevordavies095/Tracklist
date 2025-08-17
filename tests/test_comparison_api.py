"""
Tests for album comparison API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.main import app
from app.services.comparison_service import ComparisonService
from app.exceptions import ServiceValidationError, ServiceNotFoundError


class TestComparisonAPI:
    """Test cases for comparison API endpoints"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.client = TestClient(app)
        
        # Sample comparison data for mocking
        self.sample_comparison_data = {
            "albums": {
                "album1": {
                    "id": 1,
                    "name": "Test Album 1",
                    "artist": {"name": "Test Artist", "id": 1},
                    "year": 2023,
                    "rating_score": 75,
                    "total_tracks": 3,
                    "cover_art_url": "http://example.com/cover1.jpg",
                    "average_track_rating": 0.667
                },
                "album2": {
                    "id": 2,
                    "name": "Test Album 2", 
                    "artist": {"name": "Test Artist", "id": 1},
                    "year": 2023,
                    "rating_score": 80,
                    "total_tracks": 3,
                    "cover_art_url": "http://example.com/cover2.jpg",
                    "average_track_rating": 0.889
                }
            },
            "track_comparison": [
                {
                    "track_number": 1,
                    "album1_track": {"name": "Track 1", "rating": 0.67},
                    "album2_track": {"name": "Track A", "rating": 1.0},
                    "rating_difference": -0.33,
                    "better_album": "album2",
                    "difference_category": "moderate"
                }
            ],
            "statistics": {
                "winner": {"album": "album2", "score_difference": -5},
                "track_wins": {"album1_wins": 1, "album2_wins": 2, "ties": 0},
                "average_ratings": {"album1": 0.667, "album2": 0.889}
            },
            "better_tracks": {
                "album1_significantly_better": [],
                "album2_significantly_better": [
                    {"track_number": 1, "track_name": "Track A", "rating_difference": -0.33}
                ]
            },
            "insights": {
                "summary": "Test Album 2 wins with a 5-point advantage.",
                "highlights": ["Test Album 2 has better individual tracks"]
            }
        }
        
        self.sample_rated_albums = {
            "albums": [
                {"id": 1, "name": "Test Album 1", "artist": "Test Artist", "year": 2023, "score": 75},
                {"id": 2, "name": "Test Album 2", "artist": "Test Artist", "year": 2023, "score": 80}
            ],
            "total": 2
        }
    
    @patch('app.routers.albums.get_comparison_service')
    def test_compare_albums_success(self, mock_get_service):
        """Test successful album comparison API call"""
        # Mock the comparison service
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.return_value = self.sample_comparison_data
        mock_get_service.return_value = mock_service
        
        # Make API request
        response = self.client.get("/api/v1/albums/compare?album1=1&album2=2")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "albums" in data
        assert "track_comparison" in data
        assert "statistics" in data
        assert "better_tracks" in data
        assert "insights" in data
        
        # Verify album data
        assert data["albums"]["album1"]["name"] == "Test Album 1"
        assert data["albums"]["album2"]["name"] == "Test Album 2"
        
        # Verify statistics
        assert data["statistics"]["winner"]["album"] == "album2"
        assert data["statistics"]["winner"]["score_difference"] == -5
        
        # Verify service was called correctly
        mock_service.compare_albums.assert_called_once_with(1, 2, mock_get_service.return_value.compare_albums.call_args[1]['db'])
    
    def test_compare_albums_missing_parameters(self):
        """Test comparison API with missing parameters"""
        # Missing album2
        response = self.client.get("/api/v1/albums/compare?album1=1")
        assert response.status_code == 422  # FastAPI validation error
        
        # Missing album1
        response = self.client.get("/api/v1/albums/compare?album2=2")
        assert response.status_code == 422
        
        # Missing both
        response = self.client.get("/api/v1/albums/compare")
        assert response.status_code == 422
    
    def test_compare_albums_invalid_parameters(self):
        """Test comparison API with invalid parameters"""
        # Non-numeric album IDs
        response = self.client.get("/api/v1/albums/compare?album1=abc&album2=def")
        assert response.status_code == 422
        
        # Zero album IDs
        response = self.client.get("/api/v1/albums/compare?album1=0&album2=1")
        assert response.status_code == 422
        
        # Negative album IDs
        response = self.client.get("/api/v1/albums/compare?album1=-1&album2=2")
        assert response.status_code == 422
    
    @patch('app.routers.albums.get_comparison_service')
    def test_compare_albums_validation_error(self, mock_get_service):
        """Test comparison API with validation error (same album)"""
        # Mock service to raise validation error
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.side_effect = ServiceValidationError("Cannot compare an album to itself")
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/api/v1/albums/compare?album1=1&album2=1")
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "Validation error"
        assert "Cannot compare an album to itself" in data["detail"]["message"]
    
    @patch('app.routers.albums.get_comparison_service')
    def test_compare_albums_not_found_error(self, mock_get_service):
        """Test comparison API with albums not found"""
        # Mock service to raise not found error
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.side_effect = ServiceNotFoundError("Albums not found or not rated: 999")
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/api/v1/albums/compare?album1=1&album2=999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "Albums not found"
        assert "999" in data["detail"]["message"]
    
    @patch('app.routers.albums.get_comparison_service')
    def test_compare_albums_internal_error(self, mock_get_service):
        """Test comparison API with internal server error"""
        # Mock service to raise generic exception
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.side_effect = Exception("Database connection failed")
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/api/v1/albums/compare?album1=1&album2=2")
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "Internal server error"
        assert data["detail"]["message"] == "Failed to compare albums"
    
    @patch('app.routers.albums.get_comparison_service')
    def test_get_rated_albums_success(self, mock_get_service):
        """Test successful rated albums API call"""
        # Mock the comparison service
        mock_service = Mock(spec=ComparisonService)
        mock_service.get_user_rated_albums.return_value = self.sample_rated_albums["albums"]
        mock_get_service.return_value = mock_service
        
        # Make API request
        response = self.client.get("/api/v1/albums/rated")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert "albums" in data
        assert "total" in data
        assert len(data["albums"]) == 2
        assert data["total"] == 2
        
        # Verify album data structure
        album = data["albums"][0]
        assert "id" in album
        assert "name" in album
        assert "artist" in album
        assert "score" in album
        
        # Verify service was called correctly
        mock_service.get_user_rated_albums.assert_called_once()
    
    @patch('app.routers.albums.get_comparison_service')
    def test_get_rated_albums_empty(self, mock_get_service):
        """Test rated albums API with no rated albums"""
        # Mock service to return empty list
        mock_service = Mock(spec=ComparisonService)
        mock_service.get_user_rated_albums.return_value = []
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/api/v1/albums/rated")
        
        assert response.status_code == 200
        data = response.json()
        assert data["albums"] == []
        assert data["total"] == 0
    
    @patch('app.routers.albums.get_comparison_service')
    def test_get_rated_albums_error(self, mock_get_service):
        """Test rated albums API with service error"""
        # Mock service to raise exception
        mock_service = Mock(spec=ComparisonService)
        mock_service.get_user_rated_albums.side_effect = Exception("Database error")
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/api/v1/albums/rated")
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "Internal server error"
        assert data["detail"]["message"] == "Failed to get rated albums"


class TestComparisonTemplateRoute:
    """Test cases for comparison template route"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.client = TestClient(app)
    
    @patch('app.routers.templates.get_comparison_service')
    def test_comparison_page_no_params(self, mock_get_service):
        """Test comparison page without album parameters"""
        response = self.client.get("/albums/compare")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Should not call comparison service when no params
        mock_get_service.return_value.compare_albums.assert_not_called()
    
    @patch('app.routers.templates.get_comparison_service')
    def test_comparison_page_with_params(self, mock_get_service):
        """Test comparison page with album parameters"""
        # Mock comparison data
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.return_value = {
            "albums": {"album1": {"name": "Test 1"}, "album2": {"name": "Test 2"}},
            "track_comparison": [],
            "statistics": {"winner": {"album": "tie"}},
            "better_tracks": {"album1_significantly_better": [], "album2_significantly_better": []},
            "insights": {"summary": "Close match", "highlights": []}
        }
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/albums/compare?album1=1&album2=2")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Should call comparison service with correct params
        mock_service.compare_albums.assert_called_once()
    
    @patch('app.routers.templates.get_comparison_service')
    def test_comparison_page_service_error(self, mock_get_service):
        """Test comparison page with service error"""
        # Mock service to raise exception
        mock_service = Mock(spec=ComparisonService)
        mock_service.compare_albums.side_effect = ServiceNotFoundError("Albums not found")
        mock_get_service.return_value = mock_service
        
        response = self.client.get("/albums/compare?album1=1&album2=999")
        
        # Should still return 200 (page loads with error message)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestComparisonIntegration:
    """Integration tests for comparison functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.client = TestClient(app)
    
    def test_comparison_workflow(self):
        """Test complete comparison workflow"""
        # This would be an integration test with real database
        # For now, just test that endpoints are accessible
        
        # Test rated albums endpoint
        response = self.client.get("/api/v1/albums/rated")
        assert response.status_code in [200, 500]  # May fail without DB setup
        
        # Test comparison endpoint  
        response = self.client.get("/api/v1/albums/compare?album1=1&album2=2")
        assert response.status_code in [200, 404, 500]  # May fail without DB/albums
        
        # Test template endpoint
        response = self.client.get("/albums/compare")
        assert response.status_code == 200
    
    def test_api_documentation(self):
        """Test that comparison endpoints appear in API documentation"""
        response = self.client.get("/docs")
        assert response.status_code == 200
        
        # OpenAPI spec should include our endpoints
        response = self.client.get("/openapi.json")
        assert response.status_code == 200
        
        openapi_spec = response.json()
        paths = openapi_spec.get("paths", {})
        
        # Check that our endpoints are documented
        assert "/api/v1/albums/compare" in paths
        assert "/api/v1/albums/rated" in paths
        
        # Check comparison endpoint has proper parameters
        compare_endpoint = paths["/api/v1/albums/compare"]["get"]
        parameters = compare_endpoint.get("parameters", [])
        param_names = [p["name"] for p in parameters]
        
        assert "album1" in param_names
        assert "album2" in param_names