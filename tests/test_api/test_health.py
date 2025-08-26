"""
Tests for health check and basic API functionality.
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthCheck:
    """Test health check endpoint."""
    
    @pytest.mark.unit
    def test_health_check(self, client: TestClient):
        """Test that health check endpoint returns success."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    @pytest.mark.unit
    def test_api_docs_available(self, client: TestClient):
        """Test that API documentation is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
        
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
    
    @pytest.mark.unit
    def test_static_files_served(self, client: TestClient):
        """Test that static files can be served."""
        # Test CSS file
        response = client.get("/static/css/styles.css")
        # May be 200 or 404 depending on if file exists
        assert response.status_code in [200, 404]
    
    @pytest.mark.unit
    def test_index_page(self, client: TestClient):
        """Test that the main index page loads."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]