"""
Tests for authentication system.
Ensures passwords are never exposed and auth works correctly.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json

from app.main import app
from app.database import SessionLocal
from app.models import UserSettings
from app.services.auth_service import get_auth_service


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Create database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def reset_auth(db):
    """Reset authentication to disabled state."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    if settings:
        settings.auth_enabled = False
        settings.password_hash = None
        settings.session_token = None
        settings.is_setup_complete = False
        db.commit()
    yield
    # Clean up after test
    if settings:
        settings.auth_enabled = False
        settings.password_hash = None
        settings.session_token = None
        settings.is_setup_complete = False
        db.commit()


class TestAuthSecurity:
    """Test that passwords are never exposed."""
    
    def test_auth_status_no_passwords(self, client):
        """Auth status endpoint should never return password data."""
        response = client.get("/api/v1/auth/status")
        assert response.status_code == 200
        data = response.json()
        
        # Check that no password fields are present
        assert "password_hash" not in data
        assert "password" not in data
        assert "session_token" not in data
        assert "session_expiry" not in data
        
        # Only safe fields should be present
        assert "auth_enabled" in data
        assert "has_password" in data  # Boolean only
    
    def test_settings_endpoint_no_passwords(self, client):
        """Settings endpoint should never return password data."""
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        
        # Check that no password fields are present
        assert "password_hash" not in data
        assert "password" not in data
        assert "session_token" not in data
        
    def test_export_no_passwords(self, client):
        """Export endpoint should never include passwords."""
        response = client.get("/api/v1/settings/export")
        assert response.status_code == 200
        
        # Parse the JSON export
        export_data = response.json()
        
        # Check settings section
        if "settings" in export_data:
            settings = export_data["settings"]
            assert "password_hash" not in settings
            assert "password" not in settings
            assert "session_token" not in settings
            assert "session_expiry" not in settings
            
            # Only auth status flags should be present
            assert "auth_enabled" in settings or "auth_was_enabled" in settings


class TestAuthDisabled:
    """Test behavior when authentication is disabled."""
    
    def test_access_without_auth(self, client, reset_auth):
        """All endpoints should be accessible when auth is disabled."""
        # Test various endpoints
        endpoints = [
            "/",
            "/search",
            "/albums",
            "/stats",
            "/settings",
            "/api/v1/settings"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not redirect to login
            assert response.status_code != 303
            assert "/login" not in str(response.url)
    
    def test_login_redirects_when_disabled(self, client, reset_auth):
        """Login page should redirect to home when auth is disabled."""
        response = client.get("/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"


class TestAuthEnable:
    """Test enabling authentication."""
    
    def test_enable_auth_with_password(self, client, db, reset_auth):
        """Test enabling authentication with initial password."""
        # Enable auth
        response = client.post("/api/v1/auth/enable", json={
            "new_password": "TestPassword123!",
            "confirm_password": "TestPassword123!"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # Verify password is NOT in response
        assert "password" not in data
        assert "password_hash" not in data
        
        # Check auth is enabled
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        assert settings.auth_enabled == True
        assert settings.password_hash is not None
        assert settings.is_setup_complete == True
        
        # Verify password hash is actually a hash
        assert not settings.password_hash.startswith("TestPassword")
        assert "$" in settings.password_hash  # bcrypt format
    
    def test_enable_auth_password_mismatch(self, client, reset_auth):
        """Test that mismatched passwords are rejected."""
        response = client.post("/api/v1/auth/enable", json={
            "new_password": "TestPassword123!",
            "confirm_password": "DifferentPassword!"
        })
        assert response.status_code == 422  # Validation error


class TestAuthLogin:
    """Test login functionality."""
    
    def test_login_with_valid_password(self, client, db):
        """Test login with correct password."""
        # First enable auth
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        # Try to login via API
        response = client.post("/api/v1/auth/login-api", json={
            "password": "TestPassword123!",
            "remember_me": False
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # Check that NO token is in response body
        assert "token" not in data
        assert "session_token" not in data
        
        # Check cookie was set
        assert "tracklist_session" in response.cookies
    
    def test_login_with_invalid_password(self, client, db):
        """Test login with wrong password."""
        # First enable auth
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        # Try to login with wrong password
        response = client.post("/api/v1/auth/login-api", json={
            "password": "WrongPassword!",
            "remember_me": False
        })
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]


class TestPasswordChange:
    """Test password change functionality."""
    
    def test_change_password(self, client, db):
        """Test changing password."""
        # Enable auth with initial password
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "OldPassword123!")
        
        # Login first
        login_response = client.post("/api/v1/auth/login-api", json={
            "password": "OldPassword123!",
            "remember_me": False
        })
        assert login_response.status_code == 200
        
        # Change password
        response = client.post("/api/v1/auth/change-password", 
            json={
                "old_password": "OldPassword123!",
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!"
            },
            cookies=login_response.cookies
        )
        assert response.status_code == 200
        
        # Verify no password data in response
        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data
        
        # Try to login with new password
        new_login = client.post("/api/v1/auth/login-api", json={
            "password": "NewPassword456!",
            "remember_me": False
        })
        assert new_login.status_code == 200
        
        # Old password should fail
        old_login = client.post("/api/v1/auth/login-api", json={
            "password": "OldPassword123!",
            "remember_me": False
        })
        assert old_login.status_code == 401


class TestAuthMiddleware:
    """Test authentication middleware."""
    
    def test_protected_routes_redirect(self, client, db):
        """Test that protected routes redirect to login when auth is enabled."""
        # Enable auth
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        # Try to access protected route
        response = client.get("/albums", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]
    
    def test_api_routes_return_401(self, client, db):
        """Test that API routes return 401 when auth is enabled."""
        # Enable auth
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        # Try to access API route
        response = client.get("/api/v1/albums/rated")
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]
    
    def test_exempt_paths(self, client, db):
        """Test that exempt paths are accessible without auth."""
        # Enable auth
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        # These should be accessible
        exempt_paths = [
            "/login",
            "/api/v1/auth/status",
            "/health",
            "/static/css/variables.css"
        ]
        
        for path in exempt_paths:
            response = client.get(path, follow_redirects=False)
            # Should not redirect to login
            assert response.status_code != 303 or "/login" not in response.headers.get("location", "")


class TestSessionManagement:
    """Test session token management."""
    
    def test_logout_invalidates_session(self, client, db):
        """Test that logout properly invalidates the session."""
        # Enable auth and login
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        login_response = client.post("/api/v1/auth/login-api", json={
            "password": "TestPassword123!",
            "remember_me": False
        })
        assert login_response.status_code == 200
        
        # Access protected route with session
        albums_response = client.get("/api/v1/albums/rated", 
                                     cookies=login_response.cookies)
        assert albums_response.status_code == 200
        
        # Logout
        logout_response = client.post("/api/v1/auth/logout",
                                      cookies=login_response.cookies)
        assert logout_response.status_code == 303
        
        # Try to access protected route with old session
        invalid_response = client.get("/api/v1/albums/rated",
                                      cookies=login_response.cookies)
        assert invalid_response.status_code == 401
    
    def test_password_change_invalidates_sessions(self, client, db):
        """Test that changing password invalidates all sessions."""
        # Enable auth and login
        auth_service = get_auth_service()
        auth_service.enable_auth(db, "TestPassword123!")
        
        login_response = client.post("/api/v1/auth/login-api", json={
            "password": "TestPassword123!",
            "remember_me": False
        })
        assert login_response.status_code == 200
        
        # Change password
        change_response = client.post("/api/v1/auth/change-password",
            json={
                "old_password": "TestPassword123!",
                "new_password": "NewPassword456!",
                "confirm_password": "NewPassword456!"
            },
            cookies=login_response.cookies
        )
        assert change_response.status_code == 200
        
        # Old session should be invalid
        invalid_response = client.get("/api/v1/albums/rated",
                                      cookies=login_response.cookies)
        assert invalid_response.status_code == 401