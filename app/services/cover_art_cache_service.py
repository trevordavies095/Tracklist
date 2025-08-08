"""
Local Cover Art Cache Service
Handles downloading, caching, and serving album artwork locally
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from PIL import Image
from io import BytesIO
import mimetypes

logger = logging.getLogger(__name__)

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available - cover art caching will be disabled")


class CoverArtCacheService:
    """Service for caching album cover art locally"""
    
    # Image size configurations
    SIZES = {
        'thumbnail': (150, 150),
        'medium': (300, 300),
        'large': (600, 600)
    }
    
    # Cache configuration
    CACHE_DIR = Path("static/covers")
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}
    WEBP_QUALITY = 85
    JPEG_QUALITY = 90
    
    def __init__(self):
        """Initialize the cover art cache service"""
        self.ensure_cache_directories()
        self._client = None
    
    def ensure_cache_directories(self):
        """Create cache directories if they don't exist"""
        for size in self.SIZES:
            size_dir = self.CACHE_DIR / size
            size_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_client(self) -> Optional[httpx.AsyncClient]:
        """Get or create the HTTP client"""
        if not HTTPX_AVAILABLE:
            return None
        
        # Check if client exists and is not closed
        if self._client and not self._client.is_closed:
            return self._client
        
        # Create a new client if needed
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Tracklist/1.0 Cover Art Cache"
            }
        )
        return self._client
    
    def get_cache_filename(self, album_id: int, size: str = 'medium') -> str:
        """
        Generate consistent cache filename for an album
        
        Args:
            album_id: Album database ID
            size: Image size (thumbnail, medium, large)
            
        Returns:
            Filename for the cached image
        """
        return f"album_{album_id}_{size}.webp"
    
    def get_cache_path(self, album_id: int, size: str = 'medium') -> Path:
        """
        Get full path for cached image
        
        Args:
            album_id: Album database ID
            size: Image size
            
        Returns:
            Path object for the cached file
        """
        filename = self.get_cache_filename(album_id, size)
        return self.CACHE_DIR / size / filename
    
    def get_relative_path(self, album_id: int, size: str = 'medium') -> str:
        """
        Get relative path for serving via web
        
        Args:
            album_id: Album database ID
            size: Image size
            
        Returns:
            Relative path string for web serving
        """
        filename = self.get_cache_filename(album_id, size)
        return f"/static/covers/{size}/{filename}"
    
    async def download_and_cache(
        self, 
        album_id: int, 
        cover_art_url: str,
        force: bool = False
    ) -> Optional[Dict[str, str]]:
        """
        Download cover art from URL and create cached versions
        
        Args:
            album_id: Album database ID
            cover_art_url: External URL to download from
            force: Force re-download even if cache exists
            
        Returns:
            Dictionary of size -> local path mappings, or None if failed
        """
        client = await self.get_client()
        if not client:
            logger.warning("httpx not available, skipping cover art cache")
            return None
        
        # Check if already cached (unless force refresh)
        if not force:
            existing_paths = self.get_cached_paths(album_id)
            if existing_paths:
                logger.debug(f"Using existing cache for album {album_id}")
                return existing_paths
        
        try:
            logger.info(f"Downloading cover art for album {album_id} from {cover_art_url}")
            
            # Download the image
            response = await client.get(cover_art_url)
            if response.status_code != 200:
                logger.error(f"Failed to download cover art: HTTP {response.status_code}")
                return None
            
            # Open image with PIL
            image = Image.open(BytesIO(response.content))
            
            # Convert RGBA to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Create different sized versions
            paths = {}
            for size_name, dimensions in self.SIZES.items():
                sized_path = self.get_cache_path(album_id, size_name)
                
                # Create resized version
                resized = image.copy()
                resized.thumbnail(dimensions, Image.Resampling.LANCZOS)
                
                # Save as WebP for better compression
                resized.save(
                    sized_path, 
                    'WEBP', 
                    quality=self.WEBP_QUALITY,
                    optimize=True
                )
                
                paths[size_name] = self.get_relative_path(album_id, size_name)
                logger.debug(f"Saved {size_name} version to {sized_path}")
            
            # Also save original size (but optimized)
            original_path = self.CACHE_DIR / 'original' / f"album_{album_id}_original.webp"
            original_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(
                original_path,
                'WEBP',
                quality=self.WEBP_QUALITY,
                optimize=True
            )
            paths['original'] = f"/static/covers/original/album_{album_id}_original.webp"
            
            logger.info(f"Successfully cached cover art for album {album_id}")
            return paths
            
        except Exception as e:
            logger.error(f"Error caching cover art for album {album_id}: {e}")
            return None
    
    def get_cached_paths(self, album_id: int) -> Optional[Dict[str, str]]:
        """
        Check if cover art is cached and return paths
        
        Args:
            album_id: Album database ID
            
        Returns:
            Dictionary of size -> path mappings if cached, None otherwise
        """
        paths = {}
        
        for size_name in self.SIZES:
            cache_path = self.get_cache_path(album_id, size_name)
            if cache_path.exists():
                paths[size_name] = self.get_relative_path(album_id, size_name)
        
        return paths if paths else None
    
    def has_cached_cover(self, album_id: int, size: str = 'medium') -> bool:
        """
        Check if a specific size is cached
        
        Args:
            album_id: Album database ID
            size: Image size to check
            
        Returns:
            True if cached, False otherwise
        """
        return self.get_cache_path(album_id, size).exists()
    
    def delete_cached_covers(self, album_id: int) -> bool:
        """
        Delete all cached versions of an album's cover art
        
        Args:
            album_id: Album database ID
            
        Returns:
            True if any files were deleted
        """
        deleted = False
        
        # Delete all sizes
        for size_name in self.SIZES:
            cache_path = self.get_cache_path(album_id, size_name)
            if cache_path.exists():
                cache_path.unlink()
                deleted = True
                logger.debug(f"Deleted cached {size_name} for album {album_id}")
        
        # Delete original
        original_path = self.CACHE_DIR / 'original' / f"album_{album_id}_original.webp"
        if original_path.exists():
            original_path.unlink()
            deleted = True
        
        return deleted
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'by_size': {}
        }
        
        for size_name in list(self.SIZES.keys()) + ['original']:
            size_dir = self.CACHE_DIR / size_name
            if size_dir.exists():
                files = list(size_dir.glob('*.webp'))
                total_size = sum(f.stat().st_size for f in files)
                
                stats['by_size'][size_name] = {
                    'count': len(files),
                    'size_mb': round(total_size / (1024 * 1024), 2)
                }
                stats['total_files'] += len(files)
                stats['total_size_mb'] += stats['by_size'][size_name]['size_mb']
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        return stats
    
    async def cleanup_orphaned_files(self, valid_album_ids: list[int]) -> int:
        """
        Remove cached files for albums that no longer exist
        
        Args:
            valid_album_ids: List of album IDs that should have cache
            
        Returns:
            Number of files cleaned up
        """
        cleaned = 0
        valid_ids_set = set(valid_album_ids)
        
        for size_name in list(self.SIZES.keys()) + ['original']:
            size_dir = self.CACHE_DIR / size_name
            if not size_dir.exists():
                continue
            
            for file_path in size_dir.glob('album_*.webp'):
                # Extract album ID from filename
                try:
                    # Format: album_{id}_{size}.webp
                    parts = file_path.stem.split('_')
                    if len(parts) >= 2:
                        album_id = int(parts[1])
                        if album_id not in valid_ids_set:
                            file_path.unlink()
                            cleaned += 1
                            logger.debug(f"Cleaned up orphaned file: {file_path}")
                except (ValueError, IndexError):
                    # Invalid filename format, skip
                    continue
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} orphaned cover art files")
        
        return cleaned
    
    async def close(self):
        """Close the HTTP client if it exists"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Global instance
_cover_art_cache_service = None


def get_cover_art_cache_service() -> CoverArtCacheService:
    """Get or create the global cover art cache service instance"""
    global _cover_art_cache_service
    if _cover_art_cache_service is None:
        _cover_art_cache_service = CoverArtCacheService()
    return _cover_art_cache_service