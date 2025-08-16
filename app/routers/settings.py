"""
User Settings API routes
Handles user preferences including theme settings
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import logging

from ..database import get_db
from ..models import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class UserSettingsResponse(BaseModel):
    """Response model for user settings"""
    user_id: int
    album_bonus: float
    theme: str
    
    class Config:
        from_attributes = True


class UpdateThemeRequest(BaseModel):
    """Request model for theme updates"""
    theme: str = Field(..., description="Theme preference ('light' or 'dark')")
    
    class Config:
        schema_extra = {
            "example": {
                "theme": "dark"
            }
        }


class UpdateAlbumBonusRequest(BaseModel):
    """Request model for album bonus updates"""
    album_bonus: float = Field(..., ge=0.1, le=0.4, description="Album bonus factor (0.1 to 0.4)")
    
    class Config:
        schema_extra = {
            "example": {
                "album_bonus": 0.33
            }
        }


@router.get("/", response_model=UserSettingsResponse)
async def get_user_settings(db: Session = Depends(get_db)):
    """
    Get current user settings
    
    Returns user preferences including theme and album bonus settings.
    """
    logger.info("Fetching user settings")
    
    # Get user settings (user_id=1 for single-user mode)
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if not settings:
        # Create default settings if they don't exist
        settings = UserSettings(
            user_id=1,
            album_bonus=0.33,
            theme='light'
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        logger.info("Created default user settings")
    
    return settings


@router.patch("/theme", response_model=UserSettingsResponse)
async def update_theme(
    request: UpdateThemeRequest,
    db: Session = Depends(get_db)
):
    """
    Update user theme preference
    
    Updates the user's theme preference between 'light' and 'dark' modes.
    """
    logger.info(f"Updating theme to: {request.theme}")
    
    # Validate theme value
    if request.theme not in ['light', 'dark']:
        raise HTTPException(
            status_code=400,
            detail="Theme must be either 'light' or 'dark'"
        )
    
    # Get or create user settings
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if not settings:
        settings = UserSettings(
            user_id=1,
            album_bonus=0.33,
            theme=request.theme
        )
        db.add(settings)
    else:
        settings.theme = request.theme
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Theme updated successfully to: {request.theme}")
    
    return settings


@router.patch("/album-bonus", response_model=UserSettingsResponse)
async def update_album_bonus(
    request: UpdateAlbumBonusRequest,
    db: Session = Depends(get_db)
):
    """
    Update user album bonus preference
    
    Updates the album bonus factor used in score calculations.
    """
    logger.info(f"Updating album bonus to: {request.album_bonus}")
    
    # Get or create user settings
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if not settings:
        settings = UserSettings(
            user_id=1,
            album_bonus=request.album_bonus,
            theme='light'
        )
        db.add(settings)
    else:
        settings.album_bonus = request.album_bonus
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Album bonus updated successfully to: {request.album_bonus}")
    
    return settings


@router.patch("/", response_model=UserSettingsResponse)
async def update_user_settings(
    theme: Optional[str] = None,
    album_bonus: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Update multiple user settings at once
    
    Updates user preferences. Only provided fields will be updated.
    """
    logger.info(f"Updating user settings - theme: {theme}, album_bonus: {album_bonus}")
    
    # Validate inputs
    if theme is not None and theme not in ['light', 'dark']:
        raise HTTPException(
            status_code=400,
            detail="Theme must be either 'light' or 'dark'"
        )
    
    if album_bonus is not None and (album_bonus < 0.1 or album_bonus > 0.4):
        raise HTTPException(
            status_code=400,
            detail="Album bonus must be between 0.1 and 0.4"
        )
    
    # Get or create user settings
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if not settings:
        settings = UserSettings(
            user_id=1,
            album_bonus=album_bonus or 0.33,
            theme=theme or 'light'
        )
        db.add(settings)
    else:
        if theme is not None:
            settings.theme = theme
        if album_bonus is not None:
            settings.album_bonus = album_bonus
    
    db.commit()
    db.refresh(settings)
    
    logger.info("User settings updated successfully")
    
    return settings