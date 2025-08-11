"""
Background artwork caching service
Handles non-blocking artwork downloads and processing
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from ..models import Album
from ..database import SessionLocal
from .artwork_cache_service import ArtworkCacheService
from .background_tasks import get_background_manager

logger = logging.getLogger(__name__)


class ArtworkCacheBackgroundService:
    """
    Service for handling artwork caching in the background
    """

    def __init__(self):
        """Initialize the background artwork caching service"""
        self.cache_service = ArtworkCacheService()
        self.background_manager = get_background_manager()
        self._cache_status = {}  # Track caching status by album_id

    def trigger_album_cache(
        self,
        album_id: int,
        cover_art_url: Optional[str] = None,
        priority: int = 5
    ) -> str:
        """
        Trigger background caching for an album

        Args:
            album_id: ID of the album to cache artwork for
            cover_art_url: Optional URL to use (will fetch from DB if not provided)
            priority: Task priority (1=highest, 10=lowest)

        Returns:
            Task ID for tracking
        """
        # Check if already caching this album
        if album_id in self._cache_status and self._cache_status[album_id].get('status') == 'processing':
            logger.info(f"Album {album_id} already being cached, skipping duplicate request")
            return self._cache_status[album_id].get('task_id')

        # Mark as processing
        self._cache_status[album_id] = {
            'status': 'processing',
            'started_at': asyncio.get_event_loop().time()
        }

        # Add task to background queue
        task_id = self.background_manager.add_task(
            func=self._cache_album_artwork,
            args=(album_id, cover_art_url),
            name=f"cache_artwork_album_{album_id}",
            priority=priority,
            on_success=lambda result: self._on_cache_success(album_id, result),
            on_error=lambda error: self._on_cache_error(album_id, error)
        )

        self._cache_status[album_id]['task_id'] = task_id

        logger.info(f"Queued artwork caching for album {album_id} (task: {task_id})")
        return task_id

    async def _cache_album_artwork(
        self,
        album_id: int,
        cover_art_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cache artwork for a specific album

        Args:
            album_id: Album ID to cache
            cover_art_url: Optional URL (will fetch from DB if not provided)

        Returns:
            Dict with caching results
        """
        db = SessionLocal()
        try:
            # Get album from database
            album = db.query(Album).filter(Album.id == album_id).first()

            if not album:
                raise ValueError(f"Album {album_id} not found")

            # Use provided URL or get from album
            artwork_url = cover_art_url or album.cover_art_url

            if not artwork_url:
                logger.warning(f"Album {album_id} has no artwork URL")
                return {
                    'album_id': album_id,
                    'success': False,
                    'reason': 'no_artwork_url'
                }

            # Check if already cached
            if album.artwork_cached:
                logger.info(f"Album {album_id} artwork already cached")
                return {
                    'album_id': album_id,
                    'success': True,
                    'already_cached': True
                }

            # Perform caching
            logger.info(f"Starting artwork cache for album {album_id}: {album.name}")
            success = await self.cache_service.cache_artwork(album, artwork_url, db)

            if success:
                logger.info(f"Successfully cached artwork for album {album_id}")
            else:
                logger.warning(f"Failed to cache artwork for album {album_id}")

            return {
                'album_id': album_id,
                'album_name': album.name,
                'success': success,
                'artwork_url': artwork_url
            }

        except Exception as e:
            logger.error(f"Error caching artwork for album {album_id}: {e}")
            raise
        finally:
            db.close()

    def _on_cache_success(self, album_id: int, result: Dict[str, Any]):
        """Handle successful caching"""
        self._cache_status[album_id] = {
            'status': 'completed',
            'success': result.get('success', False),
            'result': result
        }
        logger.info(f"Artwork caching completed for album {album_id}: {result}")

    def _on_cache_error(self, album_id: int, error: Exception):
        """Handle caching error"""
        self._cache_status[album_id] = {
            'status': 'failed',
            'error': str(error)
        }
        logger.error(f"Artwork caching failed for album {album_id}: {error}")

    def get_cache_status(self, album_id: int) -> Optional[Dict[str, Any]]:
        """
        Get caching status for an album

        Args:
            album_id: Album ID to check

        Returns:
            Status dict or None if not found
        """
        return self._cache_status.get(album_id)

    async def cache_multiple_albums(
        self,
        album_ids: list,
        priority: int = 7
    ) -> Dict[str, str]:
        """
        Queue multiple albums for caching

        Args:
            album_ids: List of album IDs to cache
            priority: Task priority for all albums

        Returns:
            Dict mapping album_id to task_id
        """
        task_map = {}

        for album_id in album_ids:
            task_id = self.trigger_album_cache(album_id, priority=priority)
            task_map[album_id] = task_id

        logger.info(f"Queued {len(task_map)} albums for artwork caching")
        return task_map

    async def cache_all_missing_artwork(
        self,
        batch_size: int = 10,
        priority: int = 8
    ) -> Dict[str, Any]:
        """
        Cache artwork for all albums that don't have it cached

        Args:
            batch_size: Number of albums to process at once
            priority: Task priority

        Returns:
            Summary of queued tasks
        """
        db = SessionLocal()
        try:
            # Find albums without cached artwork
            albums_to_cache = db.query(Album).filter(
                Album.artwork_cached == False,
                Album.cover_art_url.isnot(None)
            ).limit(batch_size).all()

            if not albums_to_cache:
                logger.info("No albums need artwork caching")
                return {
                    'queued': 0,
                    'albums': []
                }

            # Queue caching for each album
            album_ids = [album.id for album in albums_to_cache]
            task_map = await self.cache_multiple_albums(album_ids, priority=priority)

            return {
                'queued': len(task_map),
                'albums': album_ids,
                'tasks': task_map
            }

        finally:
            db.close()

    def get_overall_status(self) -> Dict[str, Any]:
        """Get overall status of artwork caching"""
        status_counts = {
            'processing': 0,
            'completed': 0,
            'failed': 0
        }

        for album_status in self._cache_status.values():
            status = album_status.get('status', 'unknown')
            if status in status_counts:
                status_counts[status] += 1

        return {
            'cache_status_counts': status_counts,
            'total_processed': len(self._cache_status),
            'background_tasks': self.background_manager.get_status()
        }


# Global instance
_artwork_cache_background_service = None


def get_artwork_cache_background_service() -> ArtworkCacheBackgroundService:
    """Get the global artwork cache background service instance"""
    global _artwork_cache_background_service
    if _artwork_cache_background_service is None:
        _artwork_cache_background_service = ArtworkCacheBackgroundService()
    return _artwork_cache_background_service
