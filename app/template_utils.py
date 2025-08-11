"""
Template utility functions for Jinja2
Provides helper functions for templates including artwork URL resolution
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from .models import Album, ArtworkCache
from .services.artwork_cache_service import get_artwork_cache_service
from .database import SessionLocal

logger = logging.getLogger(__name__)


class ArtworkURLResolver:
    """
    Resolver for artwork URLs with cache tracking
    Provides template functions for getting cached or external artwork URLs
    """

    def __init__(self):
        """Initialize the artwork URL resolver"""
        self.cache_service = get_artwork_cache_service()

        # Cache hit/miss tracking
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'fallback_used': 0,
            'errors': 0,
            'start_time': datetime.now(timezone.utc)
        }

        # In-memory cache for template calls (short-lived)
        self._template_cache = {}
        self._cache_ttl = 300  # 5 minutes

    def get_artwork_url(
        self,
        album,
        size: str = 'medium',
        fallback: Optional[str] = None
    ) -> str:
        """
        Get artwork URL for an album, preferring cached version

        Args:
            album: Album model instance or dict with album data
            size: Size variant (thumbnail, small, medium, large, original)
            fallback: Optional fallback URL or path

        Returns:
            URL string for the artwork
        """
        try:
            # Quick validation
            if not album:
                self.stats['errors'] += 1
                return fallback or '/static/img/album-placeholder.svg'

            # Handle both Album objects and dicts
            if isinstance(album, dict):
                album_id = album.get('id')
                cover_art_url = album.get('cover_art_url')
                artwork_cached = album.get('artwork_cached', False)
            else:
                # Assume it's an Album model instance
                album_id = album.id
                cover_art_url = album.cover_art_url
                artwork_cached = getattr(album, 'artwork_cached', False)

            if not album_id:
                self.stats['errors'] += 1
                return fallback or '/static/img/album-placeholder.svg'

            # Check memory cache first (fastest)
            from .services.artwork_memory_cache import get_artwork_memory_cache
            memory_cache = get_artwork_memory_cache()
            cached_url = memory_cache.get(album_id, size)
            if cached_url:
                self.stats['cache_hits'] += 1
                return cached_url

            # Check template cache second (in-memory but with more overhead)
            cache_key = f"{album_id}_{size}"
            if cache_key in self._template_cache:
                cached_entry = self._template_cache[cache_key]
                if (datetime.now(timezone.utc) - cached_entry['time']).seconds < self._cache_ttl:
                    self.stats['cache_hits'] += 1
                    # Also store in memory cache for next time
                    memory_cache.set(album_id, size, cached_entry['url'])
                    return cached_entry['url']

            # Map size names to standard variants
            size_map = {
                'thumb': 'thumbnail',
                'small': 'small',
                'medium': 'medium',
                'large': 'large',
                'original': 'original',
                'thumbnail': 'thumbnail'
            }

            normalized_size = size_map.get(size.lower(), 'medium')

            # Try to get from database cache
            with SessionLocal() as db:
                cache_record = db.query(ArtworkCache).filter_by(
                    album_id=album_id,
                    size_variant=normalized_size
                ).first()

                if cache_record and cache_record.file_path:
                    # Build web path
                    web_path = self._build_web_path(cache_record.file_path)

                    # Update stats
                    self.stats['cache_hits'] += 1

                    # Store in both caches
                    self._template_cache[cache_key] = {
                        'url': web_path,
                        'time': datetime.now(timezone.utc)
                    }
                    memory_cache.set(album_id, normalized_size, web_path)

                    return web_path

            # Cache miss - use external URL if available
            self.stats['cache_misses'] += 1

            if cover_art_url:
                # Store external URL in both caches
                self._template_cache[cache_key] = {
                    'url': cover_art_url,
                    'time': datetime.now(timezone.utc)
                }
                memory_cache.set(album_id, normalized_size, cover_art_url)
                # Optionally trigger async caching in background
                self._trigger_background_cache_for_dict(album_id, cover_art_url, artwork_cached)
                return cover_art_url

            # Use fallback
            self.stats['fallback_used'] += 1
            fallback_url = fallback or '/static/img/album-placeholder.svg'

            # Store fallback in template cache
            self._template_cache[cache_key] = {
                'url': fallback_url,
                'time': datetime.now(timezone.utc)
            }

            return fallback_url

        except Exception as e:
            logger.error(f"Error resolving artwork URL for album {album.id if album else 'None'}: {e}")
            self.stats['errors'] += 1
            return fallback or '/static/img/album-placeholder.svg'

    def get_artwork_url_async(
        self,
        album: Album,
        size: str = 'medium',
        db: Session = None
    ) -> str:
        """
        Async version for use in async contexts

        Args:
            album: Album model instance
            size: Size variant
            db: Database session

        Returns:
            URL string for the artwork
        """
        # For now, just wrap the sync version
        # Could be enhanced to use async cache service methods
        return self.get_artwork_url(album, size)

    def _build_web_path(self, file_path: str) -> str:
        """
        Convert file system path to web-accessible path

        Args:
            file_path: File system path

        Returns:
            Web-accessible URL path
        """
        # Extract relative path from static directory
        if 'static/' in file_path:
            relative_path = file_path.split('static/')[-1]
            return f"/static/{relative_path}"

        # Fallback to direct path
        return f"/{file_path}"

    def _trigger_background_cache_for_dict(self, album_id: int, cover_art_url: str, artwork_cached: bool) -> None:
        """
        Trigger background caching of album artwork for dict data

        Args:
            album_id: Album ID
            cover_art_url: Album artwork URL
            artwork_cached: Whether artwork is already cached
        """
        try:
            # Only trigger if album has artwork URL and isn't already cached
            if cover_art_url and not artwork_cached:
                # This would ideally use a task queue
                # For now, just log the intention
                logger.debug(f"Would trigger background cache for album {album_id}")
        except Exception as e:
            logger.debug(f"Could not trigger background cache: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        total_requests = (
            self.stats['cache_hits'] +
            self.stats['cache_misses']
        )

        hit_rate = 0
        if total_requests > 0:
            hit_rate = (self.stats['cache_hits'] / total_requests) * 100

        uptime = datetime.now(timezone.utc) - self.stats['start_time']

        return {
            'cache_hits': self.stats['cache_hits'],
            'cache_misses': self.stats['cache_misses'],
            'fallback_used': self.stats['fallback_used'],
            'errors': self.stats['errors'],
            'total_requests': total_requests,
            'hit_rate': round(hit_rate, 2),
            'uptime_seconds': uptime.total_seconds(),
            'template_cache_size': len(self._template_cache)
        }

    def clear_template_cache(self) -> None:
        """Clear the in-memory template cache"""
        self._template_cache.clear()
        logger.info("Template cache cleared")

    def clear_stats(self) -> None:
        """Reset all statistics"""
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'fallback_used': 0,
            'errors': 0,
            'total_requests': 0
        }
        logger.debug("Statistics cleared")


# Global instance
_artwork_resolver = None


def get_artwork_resolver() -> ArtworkURLResolver:
    """Get or create the global artwork resolver instance"""
    global _artwork_resolver
    if _artwork_resolver is None:
        _artwork_resolver = ArtworkURLResolver()
    return _artwork_resolver


# Template function wrappers
def get_lazy_image_html(
    album,
    size: str = 'medium',
    css_class: str = '',
    alt_text: Optional[str] = None,
    loading: str = 'lazy'
) -> str:
    """
    Generate HTML for a lazy-loaded image with fallback

    Args:
        album: Album object or dict
        size: Image size variant
        css_class: Additional CSS classes
        alt_text: Alt text for the image
        loading: Loading strategy ('lazy', 'eager', 'auto')

    Returns:
        HTML string for the image element
    """
    from markupsafe import Markup

    # Get the artwork URL
    url = get_artwork_url(album, size)

    # Determine album name for alt text
    if isinstance(album, dict):
        album_name = album.get('name', 'Album')
    else:
        album_name = getattr(album, 'name', 'Album')

    alt = alt_text or f"{album_name} cover"

    # Check if URL is cached (local) or external
    is_cached = url and not url.startswith('http')

    if is_cached or loading == 'eager':
        # Load immediately for cached images or eager loading
        html = f'''
            <img src="{url}"
                 alt="{alt}"
                 class="{css_class}"
                 loading="{loading}">
        '''
    else:
        # Use lazy loading for external images
        placeholder = '/static/img/album-placeholder.svg'
        html = f'''
            <img src="{placeholder}"
                 data-src="{url}"
                 alt="{alt}"
                 class="{css_class}"
                 loading="{loading}">
            <noscript>
                <img src="{url}"
                     alt="{alt}"
                     class="{css_class} noscript-img">
            </noscript>
        '''

    return Markup(html.strip())


def get_artwork_url(album, size: str = 'medium', fallback: Optional[str] = None) -> str:
    """
    Template function to get artwork URL

    Args:
        album: Album model instance
        size: Size variant (thumbnail, small, medium, large, original)
        fallback: Optional fallback URL

    Returns:
        URL string for the artwork
    """
    resolver = get_artwork_resolver()
    return resolver.get_artwork_url(album, size, fallback)


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for monitoring

    Returns:
        Dictionary with cache statistics
    """
    resolver = get_artwork_resolver()
    return resolver.get_stats()


# Additional template utilities
def format_file_size(bytes_size: int) -> str:
    """
    Format file size in human-readable format

    Args:
        bytes_size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    if not bytes_size:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB']
    unit_index = 0
    size = float(bytes_size)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def format_cache_age(cache_date: datetime) -> str:
    """
    Format cache age in human-readable format

    Args:
        cache_date: Cache datetime

    Returns:
        Formatted string (e.g., "2 hours ago")
    """
    if not cache_date:
        return "Never"

    # Ensure timezone awareness
    if cache_date.tzinfo is None:
        cache_date = cache_date.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - cache_date

    if delta.days > 30:
        return f"{delta.days // 30} month{'s' if delta.days > 60 else ''} ago"
    elif delta.days > 0:
        return f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif delta.seconds > 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"
