"""
Settings Service - Central access point for application settings
Checks database first, falls back to environment variables
"""

import os
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from ..models import UserSettings
from ..database import get_db

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for accessing application settings with database and env fallback"""

    _instance = None
    _settings_cache = None
    _cache_timestamp = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_setting(
        self, key: str, default: Any = None, db: Optional[Session] = None
    ) -> Any:
        """
        Get a setting value, checking database first then environment variables

        Args:
            key: Setting key name
            default: Default value if not found
            db: Database session (optional)

        Returns:
            Setting value from database, environment, or default
        """
        # Try to get from database first
        if db:
            try:
                settings = (
                    db.query(UserSettings).filter(UserSettings.user_id == 1).first()
                )
                if settings and hasattr(settings, key):
                    value = getattr(settings, key)
                    if value is not None:
                        return value
            except Exception as e:
                logger.warning(f"Error getting setting {key} from database: {e}")

        # Fall back to environment variable
        env_key = key.upper()
        env_value = os.getenv(env_key)
        if env_value is not None:
            # Convert boolean strings
            if env_value.lower() in ("true", "false"):
                return env_value.lower() == "true"
            # Try to convert to int if possible
            try:
                return int(env_value)
            except ValueError:
                pass
            # Try to convert to float if possible
            try:
                return float(env_value)
            except ValueError:
                pass
            return env_value

        # Return default
        return default

    def get_cache_config(self, db: Optional[Session] = None) -> dict:
        """Get cache-related configuration settings"""
        return {
            "retention_days": self.get_setting("cache_retention_days", 365, db),
            "max_size_mb": self.get_setting("cache_max_size_mb", 5000, db),
            "cleanup_enabled": self.get_setting("cache_cleanup_enabled", True, db),
            "cleanup_schedule": self.get_setting("cache_cleanup_schedule", "daily", db),
            "cleanup_time": self.get_setting("cache_cleanup_time", "03:00", db),
            "auto_cache": self.get_setting("auto_cache_artwork", True, db),
        }

    def get_automation_config(self, db: Optional[Session] = None) -> dict:
        """Get automation-related configuration settings"""
        return {
            "auto_migrate_artwork": self.get_setting("auto_migrate_artwork", True, db),
            "auto_cache_artwork": self.get_setting("auto_cache_artwork", True, db),
            "migration_batch_size": self.get_setting("migration_batch_size", 10, db),
        }

    def get_display_config(self, db: Optional[Session] = None) -> dict:
        """Get display-related configuration settings"""
        return {
            "theme": self.get_setting("theme", "light", db),
            "default_sort_order": self.get_setting(
                "default_sort_order", "created_desc", db
            ),
            "date_format": self.get_setting("date_format", "YYYY-MM-DD", db),
        }

    def get_general_config(self, db: Optional[Session] = None) -> dict:
        """Get general configuration settings"""
        return {
            "album_bonus": self.get_setting("album_bonus", 0.33, db),
        }

    def refresh_cache(self):
        """Clear the settings cache to force reload from database"""
        self._settings_cache = None
        self._cache_timestamp = None


# Singleton instance
_settings_service = None


def get_settings_service() -> SettingsService:
    """Get the singleton SettingsService instance"""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service
