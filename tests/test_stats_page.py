"""
Tests for the statistics page
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


class TestStatsPage:
    """Test cases for the statistics page"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    def test_stats_page_loads(self, client):
        """Test that the stats page loads successfully"""
        response = client.get("/stats")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Your Statistics" in response.text
        assert "Total Albums" in response.text
        assert "Rating Distribution" in response.text
    
    def test_stats_page_has_navigation(self, client):
        """Test that stats page has proper navigation"""
        response = client.get("/stats")
        
        # Check for navigation links
        assert 'href="/"' in response.text
        assert 'href="/search"' in response.text
        assert 'href="/albums"' in response.text
        assert 'href="/stats"' in response.text
        
        # Check that Statistics nav item is active
        assert 'nav_stats' in response.text
    
    def test_stats_page_javascript_endpoints(self, client):
        """Test that the stats page includes correct API endpoint calls"""
        response = client.get("/stats")
        
        # Check for API endpoint references in JavaScript
        assert "/api/v1/reports/overview" in response.text
        assert "/api/v1/reports/activity" in response.text
        assert "/api/v1/reports/top-albums" in response.text
    
    def test_stats_page_loading_states(self, client):
        """Test that the stats page has loading state elements"""
        response = client.get("/stats")
        
        # Check for loading skeleton elements
        assert "stats-loading" in response.text
        assert "loading-skeleton" in response.text
        
        # Check for content containers
        assert "stats-content" in response.text
        assert "overview-cards" in response.text
        assert "rating-distribution" in response.text
    
    def test_stats_page_empty_state(self, client):
        """Test that the stats page has empty state handling"""
        response = client.get("/stats")
        
        # Check for empty state element
        assert "empty-state" in response.text
        assert "No Statistics Yet" in response.text
        assert "Start rating albums" in response.text
    
    def test_stats_page_responsive_design(self, client):
        """Test that the stats page uses responsive design classes"""
        response = client.get("/stats")
        
        # Check for responsive grid classes
        assert "grid-cols-1" in response.text
        assert "md:grid-cols-2" in response.text
        assert "lg:grid-cols-4" in response.text
        
        # Check for responsive text sizes
        assert "text-sm" in response.text
        assert "text-lg" in response.text
        assert "text-2xl" in response.text
    
    def test_homepage_stats_link(self, client):
        """Test that the homepage has a working link to stats"""
        response = client.get("/")
        
        # Check for stats card/link on homepage
        assert 'href="/stats"' in response.text
        assert "Your Stats" in response.text
        assert "View detailed statistics" in response.text
    
    @patch("app.reporting_service.ReportingService.get_overview_statistics")
    def test_api_integration_with_empty_data(self, mock_overview, client):
        """Test API integration with empty data scenario"""
        # Mock empty statistics
        mock_overview.return_value = {
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
        
        # Test that the API endpoint works with empty data
        response = client.get("/api/v1/reports/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["total_albums"] == 0
        assert data["average_album_score"] is None
    
    def test_stats_page_score_color_functions(self, client):
        """Test that JavaScript score color functions are included"""
        response = client.get("/stats")
        
        # Check for score color utility function
        assert "getScoreColor" in response.text
        assert "text-green-800" in response.text  # Perfect score color
        assert "text-green-600" in response.text  # Good score color
        assert "text-amber-600" in response.text  # Medium score color
        assert "text-red-600" in response.text    # Low score color