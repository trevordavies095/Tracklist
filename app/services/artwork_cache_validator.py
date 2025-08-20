"""
Artwork Cache Validator Service
Validates and corrects artwork_cached flags on startup
"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models import Album, ArtworkCache
from ..database import SessionLocal

logger = logging.getLogger(__name__)


class ArtworkCacheValidator:
    """
    Service to validate and fix artwork_cached flags
    Ensures artwork_cached is only True when local files actually exist
    """
    
    def __init__(self):
        """Initialize the artwork cache validator"""
        self.stats = {
            'total_albums': 0,
            'correctly_marked': 0,
            'fixed': 0,
            'errors': 0
        }
    
    def validate_and_fix_cache_flags(self, db: Session = None) -> Dict[str, Any]:
        """
        Validate and fix all artwork_cached flags in the database
        
        Args:
            db: Optional database session (will create one if not provided)
            
        Returns:
            Dictionary with validation statistics
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
            
        try:
            logger.info("Starting artwork cache validation...")
            
            # Reset stats
            self.stats = {
                'total_albums': 0,
                'correctly_marked': 0,
                'incorrectly_cached': 0,
                'incorrectly_uncached': 0,
                'fixed': 0,
                'errors': 0
            }
            
            # Get all albums
            albums = db.query(Album).all()
            self.stats['total_albums'] = len(albums)
            
            if self.stats['total_albums'] == 0:
                logger.info("No albums found to validate")
                return self.stats
            
            # Lists to track issues
            to_mark_uncached = []  # Albums marked cached but no files
            to_mark_cached = []     # Albums marked uncached but have files
            
            for album in albums:
                try:
                    # Check if album has actual cache files
                    has_cache_files = self._check_cache_files_exist(album.id, db)
                    
                    if album.artwork_cached and has_cache_files:
                        # Correctly marked as cached
                        self.stats['correctly_marked'] += 1
                    elif not album.artwork_cached and not has_cache_files:
                        # Correctly marked as uncached
                        self.stats['correctly_marked'] += 1
                    elif album.artwork_cached and not has_cache_files:
                        # Incorrectly marked as cached - needs to be uncached
                        self.stats['incorrectly_cached'] += 1
                        to_mark_uncached.append(album)
                        logger.debug(f"Album {album.id} '{album.name}' incorrectly marked as cached")
                    elif not album.artwork_cached and has_cache_files:
                        # Incorrectly marked as uncached - needs to be cached
                        self.stats['incorrectly_uncached'] += 1
                        to_mark_cached.append(album)
                        logger.debug(f"Album {album.id} '{album.name}' incorrectly marked as uncached")
                        
                except Exception as e:
                    logger.error(f"Error checking album {album.id}: {e}")
                    self.stats['errors'] += 1
            
            # Fix discrepancies
            if to_mark_uncached or to_mark_cached:
                logger.info(f"Found {len(to_mark_uncached)} albums to mark as uncached, "
                           f"{len(to_mark_cached)} to mark as cached")
                
                # Fix albums that should be marked as uncached
                for album in to_mark_uncached:
                    album.artwork_cached = False
                    album.artwork_cache_date = None
                    self.stats['fixed'] += 1
                    logger.debug(f"Fixed: Set artwork_cached=False for album {album.id}")
                
                # Fix albums that should be marked as cached
                for album in to_mark_cached:
                    album.artwork_cached = True
                    # Get cache date from ArtworkCache record if available
                    cache_record = db.query(ArtworkCache).filter(
                        ArtworkCache.album_id == album.id
                    ).first()
                    if cache_record and cache_record.last_fetched_at:
                        album.artwork_cache_date = cache_record.last_fetched_at
                    self.stats['fixed'] += 1
                    logger.debug(f"Fixed: Set artwork_cached=True for album {album.id}")
                
                # Commit all fixes
                db.commit()
                logger.info(f"Fixed {self.stats['fixed']} artwork_cached flags")
            else:
                logger.info("All artwork_cached flags are correct")
            
            # Log summary
            logger.info(f"Artwork cache validation complete: "
                       f"{self.stats['total_albums']} albums checked, "
                       f"{self.stats['correctly_marked']} correct, "
                       f"{self.stats['fixed']} fixed, "
                       f"{self.stats['errors']} errors")
            
            return self.stats
            
        except Exception as e:
            logger.error(f"Failed to validate artwork cache flags: {e}")
            self.stats['errors'] += 1
            return self.stats
            
        finally:
            if close_db:
                db.close()
    
    def _check_cache_files_exist(self, album_id: int, db: Session) -> bool:
        """
        Check if actual cache files exist for an album
        
        Args:
            album_id: Album ID to check
            db: Database session
            
        Returns:
            True if at least one cache file exists, False otherwise
        """
        # Get cache records for this album
        cache_records = db.query(ArtworkCache).filter(
            ArtworkCache.album_id == album_id
        ).all()
        
        # Check if any referenced files actually exist
        for record in cache_records:
            if record.file_path:
                file_path = Path(record.file_path)
                if file_path.exists():
                    return True
        
        # Also check for orphaned files (files without DB records)
        # This handles edge cases where DB records are missing but files exist
        from .artwork_cache_utils import get_cache_filesystem
        cache_fs = get_cache_filesystem()
        
        # Generate the cache key for this album
        from .artwork_cache_service import get_artwork_cache_service
        from ..models import Album
        
        album = db.query(Album).filter(Album.id == album_id).first()
        if album:
            cache_service = get_artwork_cache_service()
            cache_key = cache_service.generate_cache_key(album)
            
            # Check if any variant exists
            for variant in ['original', 'large', 'medium', 'small', 'thumbnail']:
                if cache_fs.exists(cache_key, variant):
                    return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get the latest validation statistics"""
        return self.stats.copy()


# Global instance
_validator = None


def get_artwork_cache_validator() -> ArtworkCacheValidator:
    """Get or create the global artwork cache validator instance"""
    global _validator
    if _validator is None:
        _validator = ArtworkCacheValidator()
    return _validator


def validate_artwork_cache_on_startup(db: Session = None) -> Dict[str, Any]:
    """
    Convenience function to validate artwork cache on application startup
    
    Args:
        db: Optional database session
        
    Returns:
        Dictionary with validation statistics
    """
    validator = get_artwork_cache_validator()
    return validator.validate_and_fix_cache_flags(db)