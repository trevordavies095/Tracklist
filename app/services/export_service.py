"""
Export service for exporting complete database to JSON format for backup/restore
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from ..models import Album, Artist, Track, UserSettings

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting complete database to JSON format"""
    
    def __init__(self):
        """Initialize the export service"""
        pass
    
    def export_database(self, db: Session) -> Dict[str, Any]:
        """
        Export complete database to JSON format
        
        This creates a comprehensive backup that can be used to restore
        the entire database state including all albums, artists, tracks,
        ratings, and settings.
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with complete database export
        """
        try:
            logger.info("Starting complete database export")
            
            # Build the export structure
            export_data = {
                "export_metadata": {
                    "version": "2.0",
                    "export_date": datetime.now(timezone.utc).isoformat(),
                    "application": "Tracklist",
                    "description": "Complete database backup for import/restore"
                },
                "statistics": {},
                "settings": {},
                "artists": [],
                "albums": [],
                "tracks": []
            }
            
            # Export User Settings
            logger.info("Exporting user settings...")
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if settings:
                export_data["settings"] = {
                    "album_bonus": settings.album_bonus,
                    "theme": settings.theme,
                    "date_format": settings.date_format,
                    "default_sort_order": settings.default_sort_order,
                    "auto_cache_artwork": settings.auto_cache_artwork,
                    "auto_migrate_artwork": settings.auto_migrate_artwork,
                    "migration_batch_size": settings.migration_batch_size,
                    "cache_retention_days": settings.cache_retention_days,
                    "cache_max_size_mb": settings.cache_max_size_mb,
                    "cache_cleanup_enabled": settings.cache_cleanup_enabled,
                    "cache_cleanup_schedule": settings.cache_cleanup_schedule,
                    "cache_cleanup_time": settings.cache_cleanup_time
                }
            
            # Export Artists
            logger.info("Exporting artists...")
            artists = db.query(Artist).order_by(Artist.id).all()
            artist_map = {}  # Map old IDs to export index for reference
            
            for idx, artist in enumerate(artists):
                artist_map[artist.id] = idx
                export_data["artists"].append({
                    "id": artist.id,  # Keep original ID for reference
                    "name": artist.name,
                    "musicbrainz_id": artist.musicbrainz_id,
                    "created_at": artist.created_at.isoformat() if artist.created_at else None
                })
            
            # Export Albums
            logger.info("Exporting albums...")
            albums = db.query(Album).order_by(Album.id).all()
            album_map = {}  # Map old IDs to export index
            
            for idx, album in enumerate(albums):
                album_map[album.id] = idx
                export_data["albums"].append({
                    "id": album.id,  # Keep original ID for reference
                    "artist_id": album.artist_id,
                    "name": album.name,
                    "release_year": album.release_year,
                    "musicbrainz_id": album.musicbrainz_id,
                    "cover_art_url": album.cover_art_url,
                    "genre": album.genre,
                    "total_tracks": album.total_tracks,
                    "total_duration_ms": album.total_duration_ms,
                    "rating_score": album.rating_score,
                    "album_bonus": album.album_bonus,
                    "is_rated": album.is_rated,
                    "notes": album.notes,
                    "created_at": album.created_at.isoformat() if album.created_at else None,
                    "updated_at": album.updated_at.isoformat() if album.updated_at else None,
                    "rated_at": album.rated_at.isoformat() if album.rated_at else None,
                    "artwork_cached": album.artwork_cached,
                    "artwork_cache_date": album.artwork_cache_date.isoformat() if album.artwork_cache_date else None
                })
            
            # Export Tracks
            logger.info("Exporting tracks...")
            tracks = db.query(Track).order_by(Track.album_id, Track.track_number).all()
            
            for track in tracks:
                export_data["tracks"].append({
                    "id": track.id,  # Keep original ID for reference
                    "album_id": track.album_id,
                    "track_number": track.track_number,
                    "name": track.name,
                    "duration_ms": track.duration_ms,
                    "musicbrainz_id": track.musicbrainz_id,
                    "track_rating": track.track_rating,
                    "created_at": track.created_at.isoformat() if track.created_at else None,
                    "updated_at": track.updated_at.isoformat() if track.updated_at else None
                })
            
            
            # Calculate statistics
            rated_albums = [a for a in export_data["albums"] if a["is_rated"]]
            rated_tracks = [t for t in export_data["tracks"] if t["track_rating"] is not None]
            
            export_data["statistics"] = {
                "total_artists": len(export_data["artists"]),
                "total_albums": len(export_data["albums"]),
                "rated_albums": len(rated_albums),
                "unrated_albums": len(export_data["albums"]) - len(rated_albums),
                "total_tracks": len(export_data["tracks"]),
                "rated_tracks": len(rated_tracks),
                "unrated_tracks": len(export_data["tracks"]) - len(rated_tracks),
                "average_album_score": (
                    sum(a["rating_score"] for a in rated_albums) / len(rated_albums) 
                    if rated_albums else 0
                ),
                "highest_rated_album": (
                    max(rated_albums, key=lambda a: a["rating_score"])["name"] 
                    if rated_albums else None
                ),
                "lowest_rated_album": (
                    min(rated_albums, key=lambda a: a["rating_score"])["name"] 
                    if rated_albums else None
                )
            }
            
            logger.info(f"Export complete: {export_data['statistics']['total_albums']} albums, "
                       f"{export_data['statistics']['total_tracks']} tracks")
            
            return {
                "success": True,
                "data": export_data,
                "filename": f"tracklist_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            }
            
        except Exception as e:
            logger.error(f"Database export failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    def export_to_json_string(self, db: Session) -> tuple[str, str]:
        """
        Export database and return as JSON string
        
        Args:
            db: Database session
            
        Returns:
            Tuple of (json_content, filename)
        """
        result = self.export_database(db)
        
        if not result["success"]:
            raise Exception(f"Export failed: {result.get('error', 'Unknown error')}")
        
        # Convert to formatted JSON string
        json_content = json.dumps(result["data"], indent=2, ensure_ascii=False)
        
        return json_content, result["filename"]
    
    def get_export_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Get statistics about what would be exported
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with export statistics
        """
        try:
            stats = {
                "total_artists": db.query(Artist).count(),
                "total_albums": db.query(Album).count(),
                "rated_albums": db.query(Album).filter(Album.is_rated == True).count(),
                "total_tracks": db.query(Track).count(),
                "rated_tracks": db.query(Track).filter(Track.track_rating.isnot(None)).count(),
                "settings_configured": db.query(UserSettings).filter(UserSettings.user_id == 1).count() > 0
            }
            
            stats["unrated_albums"] = stats["total_albums"] - stats["rated_albums"]
            stats["unrated_tracks"] = stats["total_tracks"] - stats["rated_tracks"]
            
            # Calculate database size estimate (rough estimate in KB)
            stats["estimated_export_size_kb"] = (
                (stats["total_albums"] * 2) +  # ~2KB per album
                (stats["total_tracks"] * 0.5) +  # ~0.5KB per track
                (stats["total_artists"] * 0.3) +  # ~0.3KB per artist
                10  # Base overhead
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get export statistics: {e}")
            raise


# Global instance
_export_service = None


def get_export_service() -> ExportService:
    """Get or create the global export service instance"""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service