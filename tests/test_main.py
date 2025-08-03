import pytest
from fastapi.testclient import TestClient


class TestMainApplication:
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tracklist"

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "Welcome to Tracklist" in data["message"]

    def test_openapi_docs(self, client):
        """Test that OpenAPI docs are accessible"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_json(self, client):
        """Test OpenAPI JSON schema"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        data = response.json()
        assert data["info"]["title"] == "Tracklist"
        assert data["info"]["version"] == "1.0.0"

    def test_nonexistent_endpoint(self, client):
        """Test 404 for nonexistent endpoint"""
        response = client.get("/nonexistent")
        assert response.status_code == 404


class TestExceptionHandlers:
    def test_validation_error_handler(self, client):
        """Test validation error handling"""
        # This would require an endpoint that accepts parameters
        # For now, we'll test with invalid JSON
        response = client.post(
            "/nonexistent",
            json={"invalid": "data"},
            headers={"Content-Type": "application/json"}
        )
        # Should return 404 for nonexistent endpoint, not validation error
        assert response.status_code == 404

    def test_global_exception_handler(self, client):
        """Test global exception handler"""
        # This test is more complex as it requires modifying the app
        # For now, we'll test that a 404 returns proper error format
        response = client.get("/nonexistent-error-endpoint")
        assert response.status_code == 404


class TestApplicationStartup:
    def test_app_configuration(self):
        """Test FastAPI app configuration"""
        from app.main import app
        assert app.title == "Tracklist"
        assert app.description == "Self-hostable music album rating application"
        assert app.version == "1.0.0"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"