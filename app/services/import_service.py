"""
Import service for restoring database from JSON backup
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..models import Album, Artist, Track, UserSettings
from ..database import engine

logger = logging.getLogger(__name__)


class ImportService:
    """Service for importing database from JSON backup"""

    REQUIRED_KEYS = ["export_metadata", "settings", "artists", "albums", "tracks"]
    SUPPORTED_VERSIONS = ["1.0", "2.0"]

    def __init__(self):
        """Initialize the import service"""
        pass

    def validate_backup(self, backup_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate the backup JSON structure and content

        Args:
            backup_data: Parsed JSON backup data

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check for required top-level keys
            for key in self.REQUIRED_KEYS:
                if key not in backup_data:
                    return False, f"Missing required key: {key}"

            # Check metadata
            metadata = backup_data.get("export_metadata", {})
            if "version" not in metadata:
                return False, "Missing version in export metadata"

            if metadata["version"] not in self.SUPPORTED_VERSIONS:
                return False, f"Unsupported backup version: {metadata['version']}"

            # Validate settings structure
            settings = backup_data.get("settings")
            if not isinstance(settings, dict):
                return False, "Invalid settings structure"

            # Validate artists array
            artists = backup_data.get("artists")
            if not isinstance(artists, list):
                return False, "Invalid artists structure - expected array"

            # Validate albums array
            albums = backup_data.get("albums")
            if not isinstance(albums, list):
                return False, "Invalid albums structure - expected array"

            # Validate tracks array
            tracks = backup_data.get("tracks")
            if not isinstance(tracks, list):
                return False, "Invalid tracks structure - expected array"

            # Basic validation of data integrity
            if albums:
                album = albums[0]
                required_album_fields = ["id", "name", "artist_id"]
                for field in required_album_fields:
                    if field not in album:
                        return False, f"Album missing required field: {field}"

            if tracks:
                track = tracks[0]
                required_track_fields = ["id", "name", "album_id", "track_number"]
                for field in required_track_fields:
                    if field not in track:
                        return False, f"Track missing required field: {field}"

            logger.info(
                f"Backup validation successful - Version: {metadata['version']}"
            )
            return True, ""

        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False, f"Validation error: {str(e)}"

    def import_database(
        self, db: Session, backup_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Import complete database from JSON backup

        This will DELETE all existing data and replace it with the backup.
        Uses transactions to ensure all-or-nothing import.

        Args:
            db: Database session
            backup_data: Validated backup data

        Returns:
            Tuple of (success, message)
        """
        try:
            logger.info("Starting database import")

            # Start transaction
            db.begin()

            try:
                # Clear existing data in correct order (respecting foreign keys)
                logger.info("Clearing existing database")
                db.query(Track).delete()
                db.query(Album).delete()
                db.query(Artist).delete()
                db.query(UserSettings).delete()
                db.flush()

                # Import settings
                logger.info("Importing settings")
                settings_data = backup_data["settings"]
                settings = UserSettings(
                    user_id=1,  # Always use user_id=1 for now
                    album_bonus=settings_data.get("album_bonus", 0.2),
                    theme=settings_data.get("theme", "light"),
                    date_format=settings_data.get("date_format", "MM/DD/YYYY"),
                    default_sort_order=settings_data.get(
                        "default_sort_order", "created_desc"
                    ),
                    auto_cache_artwork=settings_data.get("auto_cache_artwork", True),
                    auto_migrate_artwork=settings_data.get(
                        "auto_migrate_artwork", False
                    ),
                    migration_batch_size=settings_data.get("migration_batch_size", 10),
                    cache_retention_days=settings_data.get("cache_retention_days", 365),
                    cache_max_size_mb=settings_data.get("cache_max_size_mb", 5000),
                    cache_cleanup_enabled=settings_data.get(
                        "cache_cleanup_enabled", True
                    ),
                    cache_cleanup_time=settings_data.get("cache_cleanup_time", "03:00"),
                )
                db.add(settings)
                db.flush()

                # Import artists
                logger.info(f"Importing {len(backup_data['artists'])} artists")
                artist_map = {}  # Map old IDs to new IDs
                for artist_data in backup_data["artists"]:
                    artist = Artist(
                        name=artist_data["name"],
                        musicbrainz_id=artist_data.get("musicbrainz_id"),
                    )
                    db.add(artist)
                    db.flush()
                    artist_map[artist_data["id"]] = artist.id

                # Import albums
                logger.info(f"Importing {len(backup_data['albums'])} albums")
                album_map = {}  # Map old IDs to new IDs
                for album_data in backup_data["albums"]:
                    # Convert datetime strings to datetime objects
                    created_at = None
                    if album_data.get("created_at"):
                        created_at = datetime.fromisoformat(
                            album_data["created_at"].replace("Z", "+00:00")
                        )

                    completed_at = None
                    if album_data.get("completed_at"):
                        completed_at = datetime.fromisoformat(
                            album_data["completed_at"].replace("Z", "+00:00")
                        )

                    album = Album(
                        name=album_data["name"],
                        artist_id=artist_map.get(album_data["artist_id"]),
                        release_year=album_data.get("release_year"),
                        musicbrainz_id=album_data.get("musicbrainz_id"),
                        cover_art_url=album_data.get("cover_art_url"),
                        genre=album_data.get("genre"),
                        total_tracks=album_data.get("total_tracks"),
                        total_duration_ms=album_data.get("total_duration_ms"),
                        rating_score=album_data.get("rating_score"),
                        album_bonus=album_data.get("album_bonus", 0.33),
                        is_rated=album_data.get("is_rated", False),
                        notes=album_data.get("notes"),
                        created_at=created_at,
                        rated_at=completed_at,  # Using completed_at as rated_at
                        artwork_cached=album_data.get("artwork_cached", False),
                        artwork_cache_date=(
                            datetime.fromisoformat(
                                album_data["artwork_cache_date"].replace("Z", "+00:00")
                            )
                            if album_data.get("artwork_cache_date")
                            else None
                        ),
                    )
                    db.add(album)
                    db.flush()
                    album_map[album_data["id"]] = album.id

                # Import tracks
                logger.info(f"Importing {len(backup_data['tracks'])} tracks")
                for track_data in backup_data["tracks"]:
                    track = Track(
                        name=track_data["name"],
                        album_id=album_map.get(track_data["album_id"]),
                        track_number=track_data["track_number"],
                        duration_ms=track_data.get("duration_ms"),
                        track_rating=track_data.get("track_rating"),
                        musicbrainz_id=track_data.get("musicbrainz_id"),
                    )
                    db.add(track)

                # Commit transaction
                db.commit()

                # Reset sequences for SQLite
                if "sqlite" in str(engine.url):
                    logger.info("Resetting SQLite sequences")
                    try:
                        # Check if sqlite_sequence table exists
                        result = db.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
                            )
                        )
                        if result.fetchone():
                            db.execute(text("DELETE FROM sqlite_sequence"))
                            db.execute(
                                text(
                                    f"INSERT INTO sqlite_sequence (name, seq) VALUES ('artists', {len(backup_data['artists'])})"
                                )
                            )
                            db.execute(
                                text(
                                    f"INSERT INTO sqlite_sequence (name, seq) VALUES ('albums', {len(backup_data['albums'])})"
                                )
                            )
                            db.execute(
                                text(
                                    f"INSERT INTO sqlite_sequence (name, seq) VALUES ('tracks', {len(backup_data['tracks'])})"
                                )
                            )
                            db.commit()
                    except Exception as e:
                        logger.warning(f"Could not reset SQLite sequences: {e}")

                message = f"Successfully imported {len(backup_data['artists'])} artists, {len(backup_data['albums'])} albums, and {len(backup_data['tracks'])} tracks"
                logger.info(message)
                return True, message

            except Exception as e:
                # Rollback on any error
                db.rollback()
                logger.error(f"Import failed, rolling back: {str(e)}")
                return False, f"Import failed: {str(e)}"

        except Exception as e:
            logger.error(f"Import error: {str(e)}")
            return False, f"Import error: {str(e)}"
