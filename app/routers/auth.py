"""
Authentication routes for login, setup, and password management.
All password operations are server-side only - passwords are NEVER sent to clients.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from ..database import get_db
from ..services.auth_service import get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="templates")


# Request models - passwords come in but NEVER go out
class LoginRequest(BaseModel):
    """Login request with password only (single-user system)."""
    password: str = Field(..., min_length=1)
    remember_me: bool = Field(default=False)


class AuthEnableRequest(BaseModel):
    """Enable authentication with initial password."""
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class AuthDisableRequest(BaseModel):
    """Disable authentication (requires current password)."""
    current_password: str = Field(..., min_length=1)


class PasswordChangeRequest(BaseModel):
    """Change password request."""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


# Page routes
@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Login page.
    Only shown when authentication is enabled.
    """
    auth_service = get_auth_service()
    
    # If auth is disabled, redirect to home
    if not auth_service.is_auth_enabled(db):
        return RedirectResponse(url="/", status_code=303)
    
    # If auth needs setup, redirect to setup
    if auth_service.needs_setup(db):
        return RedirectResponse(url="/setup", status_code=303)
    
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "next_url": next or "/",
            "error": None
        }
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    First-time setup page.
    Shown when auth is enabled but no password is set.
    """
    auth_service = get_auth_service()
    
    # If auth is disabled, redirect to home
    if not auth_service.is_auth_enabled(db):
        return RedirectResponse(url="/", status_code=303)
    
    # If setup is complete, redirect to login
    if not auth_service.needs_setup(db):
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(
        "auth/setup.html",
        {
            "request": request,
            "error": None
        }
    )


# API routes
@router.get("/api/v1/auth/status")
async def get_auth_status(db: Session = Depends(get_db)):
    """
    Get authentication status.
    Returns ONLY safe information - NO PASSWORD DATA.
    """
    auth_service = get_auth_service()
    return auth_service.get_auth_status(db)


@router.post("/api/v1/auth/enable")
async def enable_auth(
    request: AuthEnableRequest,
    db: Session = Depends(get_db)
):
    """
    Enable authentication and set initial password.
    Password is hashed server-side and NEVER returned.
    """
    auth_service = get_auth_service()
    
    # Check if already enabled
    if auth_service.is_auth_enabled(db):
        raise HTTPException(400, "Authentication is already enabled")
    
    # Enable auth and set password
    if not auth_service.enable_auth(db, request.new_password):
        raise HTTPException(500, "Failed to enable authentication")
    
    return {
        "status": "success",
        "message": "Authentication enabled successfully",
        # NO password data returned
    }


@router.post("/api/v1/auth/disable")
async def disable_auth(
    request: AuthDisableRequest,
    db: Session = Depends(get_db)
):
    """
    Disable authentication.
    Requires current password for security.
    """
    auth_service = get_auth_service()
    
    # Check if auth is enabled
    if not auth_service.is_auth_enabled(db):
        raise HTTPException(400, "Authentication is not enabled")
    
    # Disable auth (verifies password internally)
    if not auth_service.disable_auth(db, request.current_password):
        raise HTTPException(401, "Invalid password")
    
    return {
        "status": "success",
        "message": "Authentication disabled successfully"
    }


@router.post("/api/v1/auth/setup")
async def complete_setup(
    password: str = Form(...),
    confirm_password: str = Form(...),
    response: Response = None,
    db: Session = Depends(get_db)
):
    """
    Complete initial setup by setting password.
    Used when auth is enabled but no password exists.
    """
    auth_service = get_auth_service()
    
    # Verify setup is needed
    if not auth_service.needs_setup(db):
        raise HTTPException(400, "Setup is not required")
    
    # Validate passwords match
    if password != confirm_password:
        raise HTTPException(400, "Passwords do not match")
    
    # Validate password length
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    
    # Set password
    if not auth_service.set_password(db, password):
        raise HTTPException(500, "Failed to set password")
    
    # Create session
    token = auth_service.create_session(db, remember_me=False)
    if not token:
        raise HTTPException(500, "Failed to create session")
    
    # Set cookie and redirect
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="tracklist_session",
        value=token,
        httponly=True,  # Not accessible via JavaScript
        secure=request.url.scheme == "https",  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=30 * 24 * 60 * 60  # 30 days
    )
    
    return response


@router.post("/api/v1/auth/login")
async def login(
    request: Request,
    response: Response,
    password: str = Form(...),
    remember_me: bool = Form(default=False),
    next_url: str = Form(default="/"),
    db: Session = Depends(get_db)
):
    """
    Login endpoint.
    Password verified server-side, session token set as HttpOnly cookie.
    """
    auth_service = get_auth_service()
    
    # Check if auth is enabled
    if not auth_service.is_auth_enabled(db):
        raise HTTPException(400, "Authentication is not enabled")
    
    # Verify password (server-side only)
    if not auth_service.verify_password(db, password):
        # Generic error to prevent user enumeration
        logger.warning("Failed login attempt")
        # Return to login page with error
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "next_url": next_url,
                "error": "Invalid password"
            },
            status_code=401
        )
    
    # Create session
    token = auth_service.create_session(db, remember_me=remember_me)
    if not token:
        raise HTTPException(500, "Failed to create session")
    
    # Set HttpOnly cookie and redirect
    response = RedirectResponse(url=next_url, status_code=303)
    
    # Determine cookie expiry
    max_age = 90 * 24 * 60 * 60 if remember_me else 30 * 24 * 60 * 60
    
    response.set_cookie(
        key="tracklist_session",
        value=token,
        httponly=True,  # Critical: Not accessible via JavaScript
        secure=request.url.scheme == "https",  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=max_age
    )
    
    logger.info("User logged in successfully")
    return response


@router.post("/api/v1/auth/logout")
async def logout(
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Logout endpoint.
    Invalidates session and clears cookie.
    """
    auth_service = get_auth_service()
    
    # Invalidate session in database
    auth_service.invalidate_session(db)
    
    # Clear cookie and redirect
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="tracklist_session")
    
    logger.info("User logged out successfully")
    return response


@router.post("/api/v1/auth/change-password")
async def change_password(
    request: PasswordChangeRequest,
    db: Session = Depends(get_db)
):
    """
    Change password endpoint.
    Old password verified, new password set server-side only.
    All existing sessions are invalidated.
    """
    auth_service = get_auth_service()
    
    # Verify old password
    if not auth_service.verify_password(db, request.old_password):
        raise HTTPException(401, "Current password is incorrect")
    
    # Set new password (invalidates sessions)
    if not auth_service.set_password(db, request.new_password):
        raise HTTPException(500, "Failed to change password")
    
    return {
        "status": "success",
        "message": "Password changed successfully. Please log in again.",
        # NO password data returned
    }


@router.post("/api/v1/auth/login-api")
async def login_api(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    API login endpoint for JSON requests.
    Returns success status without any password data.
    """
    auth_service = get_auth_service()
    
    # Check if auth is enabled
    if not auth_service.is_auth_enabled(db):
        raise HTTPException(400, "Authentication is not enabled")
    
    # Verify password
    if not auth_service.verify_password(db, request.password):
        # Generic error
        raise HTTPException(401, "Invalid credentials")
    
    # Create session
    token = auth_service.create_session(db, remember_me=request.remember_me)
    if not token:
        raise HTTPException(500, "Failed to create session")
    
    # Set HttpOnly cookie
    max_age = 90 * 24 * 60 * 60 if request.remember_me else 30 * 24 * 60 * 60
    
    response.set_cookie(
        key="tracklist_session",
        value=token,
        httponly=True,
        secure=False,  # Will be True in production with HTTPS
        samesite="strict",
        max_age=max_age
    )
    
    return {
        "status": "success",
        "message": "Logged in successfully"
        # NO token in response body - only in HttpOnly cookie
    }