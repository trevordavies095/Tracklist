"""
Tests to ensure export version is properly maintained when schema changes.
This helps catch when developers forget to bump the export version.
"""

import pytest
from sqlalchemy import inspect
from app.models import UserSettings, Album, Track, Artist
from app.services.export_service import ExportService
from app.services.import_service import ImportService


class TestExportVersioning:
    """Test export version management."""
    
    def test_current_version_is_documented(self):
        """Ensure current version matches what's documented."""
        export_service = ExportService()
        import_service = ImportService()
        
        # This will need to be updated when version changes
        EXPECTED_CURRENT_VERSION = "2.1"
        
        # Create a dummy export to check version
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            export_data = export_service.export_database(db)
            actual_version = export_data["export_metadata"]["version"]
            
            assert actual_version == EXPECTED_CURRENT_VERSION, (
                f"Export version mismatch! Expected {EXPECTED_CURRENT_VERSION}, got {actual_version}. "
                "Did you forget to update the test after bumping version?"
            )
            
            assert actual_version in import_service.SUPPORTED_VERSIONS, (
                f"Export version {actual_version} not in supported versions!"
            )
        finally:
            db.close()
    
    def test_auth_fields_present_in_export(self):
        """Ensure auth fields are included in export (added in v2.1)."""
        from app.database import SessionLocal
        
        export_service = ExportService()
        db = SessionLocal()
        try:
            # Create settings if they don't exist
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                settings = UserSettings(user_id=1)
                db.add(settings)
                db.commit()
            
            # Export and check for auth fields
            export_data = export_service.export_database(db)
            settings_export = export_data.get("settings", {})
            
            # These fields should be present in v2.1+
            assert "auth_enabled" in settings_export, "auth_enabled field missing from export!"
            assert "auth_was_enabled" in settings_export, "auth_was_enabled field missing from export!"
            
            # These fields should NEVER be present
            assert "password_hash" not in settings_export, "password_hash should NEVER be exported!"
            assert "session_token" not in settings_export, "session_token should NEVER be exported!"
            assert "session_expiry" not in settings_export, "session_expiry should NEVER be exported!"
            
        finally:
            db.close()
    
    def test_model_fields_match_export(self):
        """
        Check if model fields match what's being exported.
        This test helps identify when new fields are added but not exported.
        """
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            # Get all columns from UserSettings model
            inspector = inspect(db.bind)
            settings_columns = {col['name'] for col in inspector.get_columns('user_settings')}
            
            # Fields that should NEVER be exported
            NEVER_EXPORT = {
                'password_hash', 'session_token', 'session_expiry',
                'id', 'user_id', 'created_at', 'updated_at',  # System fields
                'is_setup_complete'  # Internal state
            }
            
            # Fields that MUST be exported
            MUST_EXPORT = {
                'album_bonus', 'theme', 'date_format', 'default_sort_order',
                'auto_cache_artwork', 'auto_migrate_artwork', 'migration_batch_size',
                'cache_retention_days', 'cache_max_size_mb', 'cache_cleanup_enabled',
                'cache_cleanup_schedule', 'cache_cleanup_time',
                'auth_enabled'  # Added in v2.1
            }
            
            # Check if there are any new fields not accounted for
            all_known_fields = NEVER_EXPORT | MUST_EXPORT
            new_fields = settings_columns - all_known_fields
            
            if new_fields:
                pytest.fail(
                    f"New database fields detected that aren't in export logic: {new_fields}\n"
                    "Did you add new columns without updating the export/import services?\n"
                    "Remember to:\n"
                    "1. Update export_service.py\n"
                    "2. Update import_service.py\n" 
                    "3. BUMP THE EXPORT VERSION\n"
                    "4. Update docs/EXPORT_VERSIONING.md"
                )
            
        finally:
            db.close()
    
    def test_backward_compatibility(self):
        """Test that all supported versions can be imported."""
        import_service = ImportService()
        
        for version in import_service.SUPPORTED_VERSIONS:
            # Create minimal valid export for each version
            test_export = {
                "export_metadata": {
                    "version": version,
                    "export_date": "2024-01-01T00:00:00Z",
                    "application": "Tracklist"
                },
                "settings": {},
                "artists": [],
                "albums": [],
                "tracks": []
            }
            
            is_valid, error_msg = import_service.validate_backup(test_export)
            assert is_valid, f"Version {version} failed validation: {error_msg}"