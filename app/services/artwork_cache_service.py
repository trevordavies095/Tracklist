"""
Artwork Cache Service
Centralized service for managing album artwork caching operations
"""

import logging
import hashlib
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..models import Album, ArtworkCache
from ..exceptions import TracklistException
from .artwork_cache_utils import ArtworkCacheFileSystem, get_cache_filesystem
from .cover_art_service import get_cover_art_service
from .artwork_downloader import ArtworkDownloader, ArtworkDownloadError
from .image_processor import ImageProcessor, get_image_processor, ImageProcessingError

logger = logging.getLogger(__name__)

# Try to import httpx, fallback to requests if needed
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available - artwork caching will be limited")


class ArtworkCacheError(TracklistException):
    """Exception raised for artwork cache operations"""
    pass


class ArtworkCacheService:
    """
    Service for managing artwork caching operations
    Handles downloading, resizing, storing, and retrieving cached artwork
    """
    
    # Image format settings
    DEFAULT_FORMAT = "JPEG"
    DEFAULT_QUALITY = 85
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max
    
    # Cache settings
    CACHE_TIMEOUT = 30  # seconds for download timeout
    
    def __init__(self, cache_fs: Optional[ArtworkCacheFileSystem] = None):
        """
        Initialize the artwork cache service
        
        Args:
            cache_fs: Optional filesystem manager, uses default if not provided
        """
        self.cache_fs = cache_fs or get_cache_filesystem()
        self.cover_art_service = get_cover_art_service()
        self.image_processor = get_image_processor()
        
        # Use the enhanced downloader with retry and rate limiting
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(
                timeout=self.CACHE_TIMEOUT,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5)
            )
            self.downloader = ArtworkDownloader(self.client)
        else:
            self.client = None
            self.downloader = None
        
        logger.info("ArtworkCacheService initialized")
    
    def generate_cache_key(self, album: Album) -> str:
        """
        Generate a unique cache key for an album
        
        Args:
            album: Album model instance
            
        Returns:
            16-character cache key based on MusicBrainz ID
        """
        # Use MusicBrainz ID as the primary key source
        key_source = f"{album.musicbrainz_id}_{album.id}"
        cache_key = hashlib.md5(key_source.encode()).hexdigest()[:16]
        
        logger.debug(f"Generated cache key {cache_key} for album {album.id}")
        return cache_key
    
    async def get_or_cache_artwork(
        self, 
        album: Album, 
        size_variant: str,
        db: Session
    ) -> Optional[str]:
        """
        Get cached artwork URL or download and cache if needed
        
        Args:
            album: Album model instance
            size_variant: Size variant to retrieve
            db: Database session
            
        Returns:
            Web-accessible URL for the cached artwork, or None if not available
        """
        try:
            # Generate cache key
            cache_key = self.generate_cache_key(album)
            
            # Check if already cached in filesystem
            if self.cache_fs.exists(cache_key, size_variant):
                logger.debug(f"Cache hit for {cache_key}/{size_variant}")
                
                # Update access tracking
                await self._update_access_tracking(album.id, size_variant, db)
                
                return self.cache_fs.get_web_path(cache_key, size_variant)
            
            # Check if we have the original cached
            if size_variant != "original" and self.cache_fs.exists(cache_key, "original"):
                logger.debug(f"Generating {size_variant} from cached original")
                
                # Generate variant from original
                success = await self._generate_variant_from_original(cache_key, size_variant)
                if success:
                    await self._update_access_tracking(album.id, size_variant, db)
                    return self.cache_fs.get_web_path(cache_key, size_variant)
            
            # Need to download and cache
            logger.info(f"Cache miss for {cache_key}/{size_variant}, downloading...")
            
            # Get artwork URL
            artwork_url = album.cover_art_url
            if not artwork_url:
                # Try to fetch from Cover Art Archive
                artwork_url = await self.cover_art_service.get_cover_art_url(album.musicbrainz_id)
                
                if artwork_url:
                    # Update album with the URL
                    album.cover_art_url = artwork_url
                    db.commit()
            
            if not artwork_url:
                logger.warning(f"No artwork URL available for album {album.id}")
                return None
            
            # Download and cache the artwork
            success = await self.cache_artwork(album, artwork_url, db)
            
            if success:
                # Return the cached URL
                return self.cache_fs.get_web_path(cache_key, size_variant)
            
            # Fallback to external URL
            return artwork_url
            
        except Exception as e:
            logger.error(f"Error getting artwork for album {album.id}: {e}")
            return album.cover_art_url  # Fallback to external URL
    
    async def cache_artwork(
        self, 
        album: Album,
        artwork_url: str,
        db: Session
    ) -> bool:
        """
        Download and cache artwork in all size variants
        
        Args:
            album: Album model instance
            artwork_url: URL to download artwork from
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("HTTP client not available for downloading artwork")
            return False
        
        try:
            cache_key = self.generate_cache_key(album)
            logger.info(f"Downloading artwork for album {album.id} from {artwork_url}")
            
            # Download the image with metadata
            download_result = await self._download_image(artwork_url)
            if not download_result:
                return False
            
            image_data, metadata = download_result
            
            # Generate all size variants (including original)
            variants_metadata = await self._generate_all_variants_with_metadata(cache_key, image_data)
            
            if not variants_metadata:
                logger.error(f"No variants could be created for album {album.id}")
                return False
            
            # Update database records with metadata
            await self._update_cache_records_with_metadata(
                album, cache_key, artwork_url, variants_metadata, db, metadata
            )
            
            # Update album cache status
            album.artwork_cached = True
            album.artwork_cache_date = datetime.now(timezone.utc)
            db.commit()
            
            logger.info(f"Successfully cached artwork for album {album.id} with {len(variants_metadata)} variants")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache artwork for album {album.id}: {e}")
            db.rollback()
            return False
    
    async def _download_image(self, url: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """
        Download image from URL with enhanced validation and retry logic
        
        Args:
            url: URL to download from
            
        Returns:
            Tuple of (image_data, metadata) or None if failed
        """
        if not self.downloader:
            # Fallback to simple download without retry
            try:
                response = await self.client.get(url)
                
                if response.status_code != 200:
                    logger.warning(f"Failed to download image: HTTP {response.status_code}")
                    return None
                
                image_data = response.content
                metadata = {
                    'url': str(response.url),
                    'content_length': len(image_data),
                    'content_type': response.headers.get('content-type', '')
                }
                return image_data, metadata
                
            except Exception as e:
                logger.error(f"Error downloading image: {e}")
                return None
        
        # Use enhanced downloader with retry and validation
        try:
            image_data, metadata = await self.downloader.download_with_retry(url)
            logger.info(f"Successfully downloaded artwork from {url} ({metadata.get('content_length', 0)} bytes)")
            return image_data, metadata
            
        except ArtworkDownloadError as e:
            logger.warning(f"Failed to download artwork: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading artwork: {e}")
            return None
    
    async def _save_original(self, cache_key: str, image_data: bytes) -> Optional[Path]:
        """
        Save original image to cache
        
        Args:
            cache_key: Cache key for the image
            image_data: Original image data
            
        Returns:
            Path to saved file, or None if failed
        """
        try:
            # Determine format from image data
            img = Image.open(BytesIO(image_data))
            format_ext = img.format.lower() if img.format else "jpg"
            
            # Get path for original
            file_path = self.cache_fs.get_cache_path(cache_key, "original", format_ext)
            
            # Save asynchronously
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_data)
            
            logger.debug(f"Saved original to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save original image: {e}")
            return None
    
    async def _generate_all_variants_with_metadata(
        self,
        cache_key: str,
        image_data: bytes
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate all size variants and return with metadata
        
        Args:
            cache_key: Cache key for the image
            image_data: Original image data
            
        Returns:
            Dictionary mapping variant names to their metadata
        """
        variants_metadata = {}
        
        try:
            # Process all variants using the image processor
            processed_variants = self.image_processor.process_all_variants(
                image_data,
                optimize=True
            )
            
            # Save each processed variant and collect metadata
            for variant_name, (variant_data, metadata) in processed_variants.items():
                try:
                    # Determine file extension based on format
                    ext = metadata.get('format', 'JPEG').lower()
                    if ext == 'jpeg':
                        ext = 'jpg'
                    
                    # Get path for variant
                    file_path = self.cache_fs.get_cache_path(cache_key, variant_name, ext)
                    
                    # Save asynchronously
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(variant_data)
                    
                    # Store metadata with file path
                    metadata['file_path'] = str(file_path)
                    variants_metadata[variant_name] = metadata
                    
                    logger.debug(
                        f"Created {variant_name} variant: "
                        f"{metadata['width']}x{metadata['height']}, "
                        f"{metadata['file_size_bytes']} bytes, "
                        f"compression: {metadata.get('compression_ratio', 'N/A')}"
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to save {variant_name} variant: {e}")
            
            # Log processing statistics
            if variants_metadata:
                stats = self.image_processor.get_processing_stats()
                logger.info(
                    f"Image processing complete: {len(variants_metadata)} variants, "
                    f"{stats['mb_saved']}MB saved"
                )
            
        except Exception as e:
            logger.error(f"Failed to generate variants: {e}")
            # Try to at least save the original
            try:
                file_path = self.cache_fs.get_cache_path(cache_key, 'original', 'jpg')
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(image_data)
                variants_metadata['original'] = {
                    'file_path': str(file_path),
                    'file_size_bytes': len(image_data)
                }
            except Exception as save_error:
                logger.error(f"Failed to save original: {save_error}")
        
        return variants_metadata
    
    async def _generate_all_variants(
        self, 
        cache_key: str, 
        image_data: bytes
    ) -> List[str]:
        """
        Generate all size variants from original image using enhanced image processor
        
        Args:
            cache_key: Cache key for the image
            image_data: Original image data
            
        Returns:
            List of successfully created variant names
        """
        variants_created = []
        processing_errors = []
        
        try:
            # Process all variants using the image processor
            processed_variants = self.image_processor.process_all_variants(
                image_data,
                optimize=True
            )
            
            # Save each processed variant
            for variant_name, (variant_data, metadata) in processed_variants.items():
                try:
                    # Determine file extension based on format
                    ext = metadata.get('format', 'JPEG').lower()
                    if ext == 'jpeg':
                        ext = 'jpg'
                    
                    # Get path for variant
                    file_path = self.cache_fs.get_cache_path(cache_key, variant_name, ext)
                    
                    # Save asynchronously
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(variant_data)
                    
                    variants_created.append(variant_name)
                    logger.debug(
                        f"Created {variant_name} variant at {file_path} "
                        f"({metadata['width']}x{metadata['height']}, "
                        f"{metadata['file_size_bytes']} bytes, "
                        f"compression ratio: {metadata.get('compression_ratio', 'N/A')})"
                    )
                    
                except Exception as e:
                    processing_errors.append((variant_name, str(e)))
                    logger.warning(f"Failed to save {variant_name} variant: {e}")
            
            # Log processing statistics
            stats = self.image_processor.get_processing_stats()
            logger.info(
                f"Image processing complete: {len(variants_created)} variants created, "
                f"{stats['mb_saved']}MB saved through optimization"
            )
            
        except ImageProcessingError as e:
            logger.error(f"Image processing failed: {e}")
            # If we have at least the original, continue
            if 'original' not in variants_created:
                # Try to at least save the original
                try:
                    file_path = self.cache_fs.get_cache_path(cache_key, 'original', 'jpg')
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(image_data)
                    variants_created.append('original')
                except Exception as save_error:
                    logger.error(f"Failed to save even original: {save_error}")
        except Exception as e:
            logger.error(f"Unexpected error generating variants: {e}")
        
        if processing_errors:
            logger.warning(f"Some variants failed to process: {processing_errors}")
        
        return variants_created
    
    async def _generate_variant_from_original(
        self, 
        cache_key: str, 
        size_variant: str
    ) -> bool:
        """
        Generate a specific size variant from cached original using enhanced processor
        
        Args:
            cache_key: Cache key for the image
            size_variant: Size variant to generate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find original file
            original_path = None
            for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                path = self.cache_fs.get_cache_path(cache_key, "original", ext)
                if path.exists():
                    original_path = path
                    break
            
            if not original_path:
                logger.warning(f"Original not found for {cache_key}")
                return False
            
            # Load original data
            async with aiofiles.open(original_path, 'rb') as f:
                original_data = await f.read()
            
            # Process using image processor
            try:
                processed_data, metadata = self.image_processor.process_image(
                    original_data,
                    size_variant,
                    optimize=True,
                    maintain_aspect=True,
                    smart_crop=True
                )
                
                # Save processed variant
                ext = metadata.get('format', 'JPEG').lower()
                if ext == 'jpeg':
                    ext = 'jpg'
                    
                file_path = self.cache_fs.get_cache_path(cache_key, size_variant, ext)
                
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(processed_data)
                
                logger.debug(
                    f"Generated {size_variant} variant from original: "
                    f"{metadata['width']}x{metadata['height']}, "
                    f"{metadata['file_size_bytes']} bytes"
                )
                return True
                
            except ImageProcessingError as e:
                logger.error(f"Failed to process variant {size_variant}: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to generate variant from original: {e}")
            return False
    
    async def _update_cache_records_with_metadata(
        self,
        album: Album,
        cache_key: str,
        original_url: str,
        variants_metadata: Dict[str, Dict[str, Any]],
        db: Session,
        download_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update database cache records with detailed variant metadata
        
        Args:
            album: Album model instance
            cache_key: Cache key used
            original_url: Original artwork URL
            variants_metadata: Dictionary of variant metadata
            db: Database session
            download_metadata: Optional download metadata (etag, etc.)
        """
        try:
            now = datetime.now(timezone.utc)
            
            for variant_name, variant_meta in variants_metadata.items():
                # Check if record exists
                cache_record = db.query(ArtworkCache).filter_by(
                    album_id=album.id,
                    size_variant=variant_name
                ).first()
                
                if not cache_record:
                    # Create new record
                    cache_record = ArtworkCache(
                        album_id=album.id,
                        original_url=original_url,
                        cache_key=f"{cache_key}_{variant_name}",
                        size_variant=variant_name,
                        last_fetched_at=now,
                        last_accessed_at=now,
                        access_count=1
                    )
                    db.add(cache_record)
                else:
                    # Update existing record
                    cache_record.last_fetched_at = now
                    cache_record.last_accessed_at = now
                    cache_record.access_count += 1
                
                # Update with variant metadata
                cache_record.file_path = variant_meta.get('file_path')
                cache_record.file_size_bytes = variant_meta.get('file_size_bytes')
                cache_record.width = variant_meta.get('width')
                cache_record.height = variant_meta.get('height')
                cache_record.content_type = f"image/{variant_meta.get('format', 'jpeg').lower()}"
                
                # Add download metadata if available
                if download_metadata:
                    cache_record.etag = download_metadata.get('etag')
                
                # Store checksum if available
                if 'checksum' in variant_meta:
                    # Store in etag field if not already used
                    if not cache_record.etag:
                        cache_record.etag = variant_meta['checksum']
                
                logger.debug(
                    f"Updated cache record for {variant_name}: "
                    f"{cache_record.width}x{cache_record.height}, "
                    f"{cache_record.file_size_bytes} bytes"
                )
            
            db.commit()
            logger.info(f"Updated {len(variants_metadata)} cache records for album {album.id}")
            
        except SQLAlchemyError as e:
            logger.error(f"Database error updating cache records: {e}")
            db.rollback()
            raise
    
    async def _update_cache_records(
        self,
        album: Album,
        cache_key: str,
        original_url: str,
        variants_created: List[str],
        db: Session,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update database cache records for an album with metadata
        
        Args:
            album: Album model instance
            cache_key: Cache key used
            original_url: Original artwork URL
            variants_created: List of variant names created
            db: Database session
            metadata: Optional download metadata (etag, checksum, etc.)
        """
        try:
            now = datetime.now(timezone.utc)
            
            for variant in variants_created:
                # Check if record exists
                cache_record = db.query(ArtworkCache).filter_by(
                    album_id=album.id,
                    size_variant=variant
                ).first()
                
                if not cache_record:
                    # Create new record
                    cache_record = ArtworkCache(
                        album_id=album.id,
                        original_url=original_url,
                        cache_key=f"{cache_key}_{variant}",  # Unique key per variant
                        size_variant=variant,
                        last_fetched_at=now,
                        last_accessed_at=now,
                        access_count=1
                    )
                    db.add(cache_record)
                else:
                    # Update existing record
                    cache_record.last_fetched_at = now
                    cache_record.last_accessed_at = now
                    cache_record.access_count += 1
                
                # Update file info
                file_info = self.cache_fs.get_file_info(cache_key, variant)
                if file_info:
                    cache_record.file_path = file_info["path"]
                    cache_record.file_size_bytes = file_info["size_bytes"]
                
                # Set dimensions
                if variant in self.cache_fs.SIZE_SPECS and self.cache_fs.SIZE_SPECS[variant]:
                    cache_record.width = self.cache_fs.SIZE_SPECS[variant][0]
                    cache_record.height = self.cache_fs.SIZE_SPECS[variant][1]
                
                # Add metadata if available
                if metadata:
                    cache_record.etag = metadata.get('etag')
                    cache_record.content_type = metadata.get('content_type', 'image/jpeg')
                    
                    # Store original image dimensions for the original variant
                    if variant == 'original' and 'width' in metadata:
                        cache_record.width = metadata.get('width')
                        cache_record.height = metadata.get('height')
                else:
                    cache_record.content_type = "image/jpeg"
            
            db.commit()
            logger.debug(f"Updated cache records for album {album.id}")
            
        except SQLAlchemyError as e:
            logger.error(f"Database error updating cache records: {e}")
            db.rollback()
            raise
    
    async def _update_access_tracking(
        self,
        album_id: int,
        size_variant: str,
        db: Session
    ) -> None:
        """
        Update access tracking for cached artwork
        
        Args:
            album_id: Album ID
            size_variant: Size variant accessed
            db: Database session
        """
        try:
            cache_record = db.query(ArtworkCache).filter_by(
                album_id=album_id,
                size_variant=size_variant
            ).first()
            
            if cache_record:
                cache_record.last_accessed_at = datetime.now(timezone.utc)
                cache_record.access_count += 1
                db.commit()
                
        except Exception as e:
            logger.debug(f"Failed to update access tracking: {e}")
            # Don't fail the request for tracking issues
            pass
    
    async def cleanup_stale_cache(self, days_old: int = 30, db: Session = None) -> int:
        """
        Remove cached images not accessed in specified days
        
        Args:
            days_old: Remove images not accessed in this many days
            db: Database session
            
        Returns:
            Number of files removed
        """
        try:
            from datetime import timedelta
            
            threshold = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            # Find stale cache records
            stale_records = db.query(ArtworkCache).filter(
                ArtworkCache.last_accessed_at < threshold
            ).all()
            
            deleted_count = 0
            
            for record in stale_records:
                # Extract cache key (remove variant suffix)
                cache_key = record.cache_key.rsplit('_', 1)[0]
                
                # Delete file
                if self.cache_fs.delete_cache(cache_key, record.size_variant) > 0:
                    deleted_count += 1
                
                # Delete database record
                db.delete(record)
            
            db.commit()
            
            logger.info(f"Cleaned up {deleted_count} stale cache files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup stale cache: {e}")
            if db:
                db.rollback()
            return 0
    
    async def clear_album_cache(self, album: Album, db: Session) -> bool:
        """
        Clear all cached artwork for a specific album
        
        Args:
            album: Album model instance
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self.generate_cache_key(album)
            
            # Delete files
            deleted = self.cache_fs.delete_cache(cache_key)
            
            # Delete database records
            db.query(ArtworkCache).filter_by(album_id=album.id).delete()
            
            # Update album status
            album.artwork_cached = False
            album.artwork_cache_date = None
            
            db.commit()
            
            logger.info(f"Cleared cache for album {album.id}, deleted {deleted} files")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear album cache: {e}")
            db.rollback()
            return False
    
    async def get_cache_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics
        
        Args:
            db: Database session
            
        Returns:
            Dictionary with cache statistics
        """
        try:
            # Filesystem statistics
            fs_stats = self.cache_fs.get_cache_statistics()
            
            # Database statistics
            total_cached = db.query(ArtworkCache).count()
            albums_cached = db.query(Album).filter(Album.artwork_cached == True).count()
            total_albums = db.query(Album).count()
            
            # Access statistics
            most_accessed = db.query(ArtworkCache).order_by(
                ArtworkCache.access_count.desc()
            ).limit(5).all()
            
            return {
                "filesystem": fs_stats,
                "database": {
                    "total_cache_records": total_cached,
                    "albums_cached": albums_cached,
                    "total_albums": total_albums,
                    "cache_coverage": round((albums_cached / total_albums * 100) if total_albums > 0 else 0, 2)
                },
                "most_accessed": [
                    {
                        "album_id": record.album_id,
                        "size_variant": record.size_variant,
                        "access_count": record.access_count
                    }
                    for record in most_accessed
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {}
    
    async def close(self):
        """Close HTTP client and cleanup resources"""
        if self.client:
            await self.client.aclose()
        logger.info("ArtworkCacheService closed")


# Global instance
_artwork_cache_service = None


def get_artwork_cache_service() -> ArtworkCacheService:
    """Get or create the global artwork cache service instance"""
    global _artwork_cache_service
    if _artwork_cache_service is None:
        _artwork_cache_service = ArtworkCacheService()
    return _artwork_cache_service