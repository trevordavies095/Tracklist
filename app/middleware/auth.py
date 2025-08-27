"""
Authentication middleware for protecting routes.
Only active when authentication is enabled.
"""

import logging
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services.auth_service import get_auth_service

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce authentication on protected routes.
    
    Features:
    - Only active when auth is enabled
    - Exempts public paths (login, static, health, etc.)
    - Redirects unauthenticated users to login
    - Validates session tokens from HttpOnly cookies
    """
    
    # Paths that don't require authentication
    EXEMPT_PATHS = [
        "/login",
        "/setup",
        "/api/v1/auth/",
        "/static/",
        "/health",
        "/favicon.ico",
        "/api/v1/docs",
        "/docs",
        "/redoc",
        "/openapi.json"
    ]
    
    async def dispatch(self, request: Request, call_next):
        """Process each request through auth checks."""
        
        # Get database session
        db = SessionLocal()
        try:
            auth_service = get_auth_service()
            
            # Check if authentication is enabled
            if not auth_service.is_auth_enabled(db):
                # Auth disabled, allow all requests
                return await call_next(request)
            
            # Check if path is exempt
            path = request.url.path
            if self._is_exempt_path(path):
                return await call_next(request)
            
            # Special case: if auth is enabled but not set up, redirect to setup
            if auth_service.needs_setup(db):
                if path != "/setup" and not path.startswith("/api/v1/auth/"):
                    logger.debug("Auth enabled but not set up, redirecting to setup")
                    return RedirectResponse(url="/setup", status_code=303)
                return await call_next(request)
            
            # Check for session cookie
            session_token = request.cookies.get("tracklist_session")
            
            # Validate session
            if not session_token or not auth_service.validate_session(db, session_token):
                # Handle API vs HTML requests differently
                if path.startswith("/api/"):
                    # API request - return 401
                    return Response(
                        content='{"detail": "Authentication required"}',
                        status_code=401,
                        media_type="application/json"
                    )
                else:
                    # HTML request - redirect to login
                    logger.debug(f"No valid session for {path}, redirecting to login")
                    # Store the original URL to redirect back after login
                    redirect_url = f"/login?next={request.url.path}"
                    return RedirectResponse(url=redirect_url, status_code=303)
            
            # Valid session, proceed with request
            # Add auth status to request state for use in endpoints
            request.state.auth_validated = True
            
        finally:
            db.close()
        
        # Continue to the actual endpoint
        response = await call_next(request)
        return response
    
    def _is_exempt_path(self, path: str) -> bool:
        """Check if the path is exempt from authentication."""
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return True
        return False


async def auth_middleware(request: Request, call_next):
    """
    Function-based middleware for authentication.
    Alternative to class-based middleware if needed.
    """
    middleware = AuthMiddleware(None)
    return await middleware.dispatch(request, call_next)