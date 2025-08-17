"""
User Settings API routes
Handles user preferences including theme settings
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
import logging
import os

from ..database import get_db
from ..models import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class UserSettingsResponse(BaseModel):
    """Response model for user settings"""
    user_id: int
    album_bonus: float
    theme: str
    auto_migrate_artwork: bool
    cache_retention_days: int
    cache_max_size_mb: int
    cache_cleanup_enabled: bool
    cache_cleanup_schedule: str
    cache_cleanup_time: str
    default_sort_order: str
    date_format: str
    auto_cache_artwork: bool
    migration_batch_size: int
    
    class Config:
        from_attributes = True


class UpdateThemeRequest(BaseModel):
    """Request model for theme updates"""
    theme: str = Field(..., description="Theme preference ('light' or 'dark')")
    
    class Config:
        json_schema_extra = {
            "example": {
                "theme": "dark"
            }
        }


class UpdateAlbumBonusRequest(BaseModel):
    """Request model for album bonus updates"""
    album_bonus: float = Field(..., ge=0.1, le=0.4, description="Album bonus factor (0.1 to 0.4)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "album_bonus": 0.33
            }
        }


class UpdateAllSettingsRequest(BaseModel):
    """Request model for updating all settings"""
    # General Settings
    album_bonus: Optional[float] = Field(None, ge=0.1, le=0.4, description="Album bonus factor")
    default_sort_order: Optional[Literal[
        'created_desc', 'created_asc', 
        'rated_desc', 'rated_asc',
        'name_asc', 'name_desc',
        'year_desc', 'year_asc',
        'score_desc', 'score_asc'
    ]] = None
    
    # Display Settings
    theme: Optional[Literal['light', 'dark']] = None
    date_format: Optional[Literal['YYYY-MM-DD', 'MM/DD/YYYY', 'DD/MM/YYYY']] = None
    
    # Automation Settings
    auto_migrate_artwork: Optional[bool] = None
    auto_cache_artwork: Optional[bool] = None
    migration_batch_size: Optional[int] = Field(None, ge=1, le=50)
    
    # Storage & Cleanup Settings
    cache_retention_days: Optional[int] = Field(None, ge=7, le=3650)
    cache_max_size_mb: Optional[int] = Field(None, ge=100, le=100000)
    cache_cleanup_enabled: Optional[bool] = None
    cache_cleanup_schedule: Optional[Literal['daily', 'weekly', 'monthly']] = None
    cache_cleanup_time: Optional[str] = Field(None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    
    @validator('cache_cleanup_time')
    def validate_time_format(cls, v):
        if v is not None:
            try:
                hour, minute = map(int, v.split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except:
                raise ValueError("Time must be in HH:MM format (24-hour)")
        return v


def get_settings_with_defaults(db: Session) -> UserSettings:
    """Get or create user settings with environment variable defaults"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if not settings:
        # Create with defaults from environment or hardcoded
        settings = UserSettings(
            user_id=1,
            album_bonus=float(os.getenv("DEFAULT_ALBUM_BONUS", "0.33")),
            theme='light',
            auto_migrate_artwork=os.getenv("AUTO_MIGRATE_ARTWORK", "true").lower() == "true",
            cache_retention_days=int(os.getenv("CACHE_RETENTION_DAYS", "365")),
            cache_max_size_mb=int(os.getenv("CACHE_MAX_SIZE_MB", "5000")),
            cache_cleanup_enabled=os.getenv("CACHE_CLEANUP_ENABLED", "true").lower() == "true",
            cache_cleanup_schedule=os.getenv("CACHE_CLEANUP_SCHEDULE", "daily"),
            cache_cleanup_time=os.getenv("CACHE_CLEANUP_TIME", "03:00"),
            default_sort_order=os.getenv("DEFAULT_SORT_ORDER", "created_desc"),
            date_format=os.getenv("DATE_FORMAT", "YYYY-MM-DD"),
            auto_cache_artwork=os.getenv("AUTO_CACHE_ARTWORK", "true").lower() == "true",
            migration_batch_size=int(os.getenv("MIGRATION_BATCH_SIZE", "10"))
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        logger.info("Created default user settings from environment variables")
    
    return settings


@router.get("/", response_model=UserSettingsResponse)
async def get_user_settings(db: Session = Depends(get_db)):
    """
    Get current user settings
    
    Returns user preferences including theme and album bonus settings.
    """
    logger.info("Fetching user settings")
    settings = get_settings_with_defaults(db)
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
    
    settings = get_settings_with_defaults(db)
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
    
    settings = get_settings_with_defaults(db)
    settings.album_bonus = request.album_bonus
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Album bonus updated successfully to: {request.album_bonus}")
    
    return settings


@router.put("/", response_model=UserSettingsResponse)
async def update_all_settings(
    request: UpdateAllSettingsRequest,
    db: Session = Depends(get_db)
):
    """
    Update all user settings
    
    Updates multiple user preferences at once. Only provided fields will be updated.
    """
    logger.info("Updating user settings")
    
    settings = get_settings_with_defaults(db)
    
    # Update only provided fields
    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(settings, field):
            setattr(settings, field, value)
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"User settings updated: {list(update_data.keys())}")
    
    return settings


@router.patch("/", response_model=UserSettingsResponse)
async def update_user_settings(
    theme: Optional[str] = None,
    album_bonus: Optional[float] = None,
    auto_migrate_artwork: Optional[bool] = None,
    cache_retention_days: Optional[int] = None,
    cache_max_size_mb: Optional[int] = None,
    cache_cleanup_enabled: Optional[bool] = None,
    cache_cleanup_schedule: Optional[str] = None,
    cache_cleanup_time: Optional[str] = None,
    default_sort_order: Optional[str] = None,
    date_format: Optional[str] = None,
    auto_cache_artwork: Optional[bool] = None,
    migration_batch_size: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Update specific user settings
    
    Updates user preferences. Only provided fields will be updated.
    """
    logger.info(f"Updating specific user settings")
    
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
    
    if cache_cleanup_schedule is not None and cache_cleanup_schedule not in ['daily', 'weekly', 'monthly']:
        raise HTTPException(
            status_code=400,
            detail="Cleanup schedule must be 'daily', 'weekly', or 'monthly'"
        )
    
    if cache_cleanup_time is not None:
        try:
            hour, minute = map(int, cache_cleanup_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except:
            raise HTTPException(
                status_code=400,
                detail="Cleanup time must be in HH:MM format (24-hour)"
            )
    
    settings = get_settings_with_defaults(db)
    
    # Update provided fields
    if theme is not None:
        settings.theme = theme
    if album_bonus is not None:
        settings.album_bonus = album_bonus
    if auto_migrate_artwork is not None:
        settings.auto_migrate_artwork = auto_migrate_artwork
    if cache_retention_days is not None:
        settings.cache_retention_days = cache_retention_days
    if cache_max_size_mb is not None:
        settings.cache_max_size_mb = cache_max_size_mb
    if cache_cleanup_enabled is not None:
        settings.cache_cleanup_enabled = cache_cleanup_enabled
    if cache_cleanup_schedule is not None:
        settings.cache_cleanup_schedule = cache_cleanup_schedule
    if cache_cleanup_time is not None:
        settings.cache_cleanup_time = cache_cleanup_time
    if default_sort_order is not None:
        settings.default_sort_order = default_sort_order
    if date_format is not None:
        settings.date_format = date_format
    if auto_cache_artwork is not None:
        settings.auto_cache_artwork = auto_cache_artwork
    if migration_batch_size is not None:
        settings.migration_batch_size = migration_batch_size
    
    db.commit()
    db.refresh(settings)
    
    logger.info("User settings updated successfully")
    
    return settings


@router.post("/reset-defaults", response_model=UserSettingsResponse)
async def reset_to_defaults(db: Session = Depends(get_db)):
    """
    Reset all settings to default values
    
    Resets all user settings to their default values from environment variables or hardcoded defaults.
    """
    logger.info("Resetting user settings to defaults")
    
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    
    if settings:
        # Update existing settings to defaults
        settings.album_bonus = float(os.getenv("DEFAULT_ALBUM_BONUS", "0.33"))
        settings.theme = 'light'
        settings.auto_migrate_artwork = os.getenv("AUTO_MIGRATE_ARTWORK", "true").lower() == "true"
        settings.cache_retention_days = int(os.getenv("CACHE_RETENTION_DAYS", "365"))
        settings.cache_max_size_mb = int(os.getenv("CACHE_MAX_SIZE_MB", "5000"))
        settings.cache_cleanup_enabled = os.getenv("CACHE_CLEANUP_ENABLED", "true").lower() == "true"
        settings.cache_cleanup_schedule = os.getenv("CACHE_CLEANUP_SCHEDULE", "daily")
        settings.cache_cleanup_time = os.getenv("CACHE_CLEANUP_TIME", "03:00")
        settings.default_sort_order = os.getenv("DEFAULT_SORT_ORDER", "created_desc")
        settings.date_format = os.getenv("DATE_FORMAT", "YYYY-MM-DD")
        settings.auto_cache_artwork = os.getenv("AUTO_CACHE_ARTWORK", "true").lower() == "true"
        settings.migration_batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "10"))
    else:
        # Create new settings with defaults
        settings = get_settings_with_defaults(db)
    
    db.commit()
    db.refresh(settings)
    
    logger.info("User settings reset to defaults")
    
    return settings