"""
Batch artwork processor for efficiently processing multiple albums
Includes retry logic, error handling, and progress tracking
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models import Album, ArtworkCache
from .artwork_cache_service import ArtworkCacheService, get_artwork_cache_service
from .image_processor import ImageProcessingError

logger = logging.getLogger(__name__)


class BatchProcessingError(Exception):
    """Exception raised during batch processing operations"""
    pass


class BatchArtworkProcessor:
    """
    Batch processor for artwork caching with concurrent processing,
    error recovery, and progress tracking
    """
    
    # Processing settings
    DEFAULT_BATCH_SIZE = 10
    DEFAULT_CONCURRENCY = 3
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __init__(
        self,
        cache_service: Optional[ArtworkCacheService] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY
    ):
        """
        Initialize the batch processor
        
        Args:
            cache_service: Artwork cache service instance
            batch_size: Number of albums to process in each batch
            concurrency: Number of concurrent processing tasks
        """
        self.cache_service = cache_service or get_artwork_cache_service()
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        
        # Processing statistics
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'retried': 0,
            'start_time': None,
            'end_time': None
        }
        
        # Error tracking
        self.processing_errors = []
        
        # Progress callback
        self.progress_callback = None
    
    async def process_albums(
        self,
        albums: List[Album],
        db: Session,
        force_reprocess: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Process multiple albums for artwork caching
        
        Args:
            albums: List of Album models to process
            db: Database session
            force_reprocess: Whether to reprocess already cached albums
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with processing results and statistics
        """
        self.progress_callback = progress_callback
        self.stats['start_time'] = datetime.now(timezone.utc)
        self.stats['total_processed'] = len(albums)
        
        logger.info(f"Starting batch processing of {len(albums)} albums")
        
        try:
            # Filter albums based on force_reprocess flag
            albums_to_process = self._filter_albums(albums, db, force_reprocess)
            
            if not albums_to_process:
                logger.info("No albums need processing")
                self.stats['skipped'] = len(albums)
                return self._generate_report()
            
            # Process in batches
            for i in range(0, len(albums_to_process), self.batch_size):
                batch = albums_to_process[i:i + self.batch_size]
                await self._process_batch(batch, db)
                
                # Report progress
                if self.progress_callback:
                    progress = (i + len(batch)) / len(albums_to_process) * 100
                    self.progress_callback(progress, self.stats)
            
            self.stats['end_time'] = datetime.now(timezone.utc)
            
            # Final report
            report = self._generate_report()
            logger.info(f"Batch processing complete: {report['summary']}")
            
            return report
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            self.stats['end_time'] = datetime.now(timezone.utc)
            raise BatchProcessingError(f"Batch processing failed: {str(e)}")
    
    async def _process_batch(
        self,
        batch: List[Album],
        db: Session
    ) -> None:
        """
        Process a batch of albums concurrently
        
        Args:
            batch: List of albums in this batch
            db: Database session
        """
        logger.info(f"Processing batch of {len(batch)} albums")
        
        tasks = []
        for album in batch:
            task = self._process_album_with_retry(album, db)
            tasks.append(task)
        
        # Process concurrently with semaphore control
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        for album, result in zip(batch, results):
            if isinstance(result, Exception):
                self.stats['failed'] += 1
                self.processing_errors.append({
                    'album_id': album.id,
                    'album_name': album.name,
                    'error': str(result)
                })
                logger.error(f"Failed to process album {album.id}: {result}")
            else:
                if result:
                    self.stats['successful'] += 1
                else:
                    self.stats['skipped'] += 1
    
    async def _process_album_with_retry(
        self,
        album: Album,
        db: Session
    ) -> bool:
        """
        Process a single album with retry logic
        
        Args:
            album: Album to process
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        async with self.semaphore:
            for attempt in range(self.MAX_RETRIES):
                try:
                    # Check if album has artwork URL
                    if not album.cover_art_url:
                        logger.debug(f"Album {album.id} has no artwork URL, skipping")
                        return False
                    
                    # Process the album
                    success = await self.cache_service.cache_artwork(
                        album,
                        album.cover_art_url,
                        db
                    )
                    
                    if success:
                        logger.info(f"Successfully processed album {album.id}: {album.name}")
                        return True
                    else:
                        if attempt < self.MAX_RETRIES - 1:
                            self.stats['retried'] += 1
                            await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                        else:
                            raise Exception("Failed after all retries")
                    
                except ImageProcessingError as e:
                    # Image processing errors are not retryable
                    logger.error(f"Image processing error for album {album.id}: {e}")
                    raise
                    
                except Exception as e:
                    if attempt < self.MAX_RETRIES - 1:
                        self.stats['retried'] += 1
                        logger.warning(
                            f"Attempt {attempt + 1} failed for album {album.id}: {e}, retrying..."
                        )
                        await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    else:
                        logger.error(f"All attempts failed for album {album.id}: {e}")
                        raise
            
            return False
    
    def _filter_albums(
        self,
        albums: List[Album],
        db: Session,
        force_reprocess: bool
    ) -> List[Album]:
        """
        Filter albums based on processing requirements
        
        Args:
            albums: List of all albums
            db: Database session
            force_reprocess: Whether to include already cached albums
            
        Returns:
            Filtered list of albums to process
        """
        if force_reprocess:
            return albums
        
        # Get albums that are not cached
        albums_to_process = []
        
        for album in albums:
            # Check if album has all required variants cached
            required_variants = ['original', 'large', 'medium', 'small', 'thumbnail']
            
            cached_variants = db.query(ArtworkCache.size_variant).filter(
                ArtworkCache.album_id == album.id
            ).all()
            
            cached_variant_names = {v[0] for v in cached_variants}
            
            if not all(v in cached_variant_names for v in required_variants):
                albums_to_process.append(album)
            else:
                logger.debug(f"Album {album.id} already fully cached, skipping")
        
        logger.info(
            f"Filtered {len(albums)} albums to {len(albums_to_process)} for processing"
        )
        
        return albums_to_process
    
    async def process_missing_variants(
        self,
        db: Session,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process albums that are missing some size variants
        
        Args:
            db: Database session
            limit: Optional limit on number of albums to process
            
        Returns:
            Processing report
        """
        logger.info("Searching for albums with missing variants...")
        
        # Find albums with incomplete variants
        required_variants = ['original', 'large', 'medium', 'small', 'thumbnail']
        
        # Get all albums with their cached variants
        albums = db.query(Album).filter(
            Album.cover_art_url.isnot(None)
        ).all()
        
        albums_missing_variants = []
        
        for album in albums:
            cached_variants = db.query(ArtworkCache.size_variant).filter(
                ArtworkCache.album_id == album.id
            ).all()
            
            cached_variant_names = {v[0] for v in cached_variants}
            missing = set(required_variants) - cached_variant_names
            
            if missing:
                albums_missing_variants.append((album, missing))
                if limit and len(albums_missing_variants) >= limit:
                    break
        
        if not albums_missing_variants:
            logger.info("No albums with missing variants found")
            return {'status': 'complete', 'processed': 0}
        
        logger.info(
            f"Found {len(albums_missing_variants)} albums with missing variants"
        )
        
        # Process these albums
        albums_to_process = [album for album, _ in albums_missing_variants]
        return await self.process_albums(albums_to_process, db, force_reprocess=True)
    
    async def validate_cached_artwork(
        self,
        db: Session
    ) -> Dict[str, Any]:
        """
        Validate all cached artwork files exist and are valid
        
        Args:
            db: Database session
            
        Returns:
            Validation report
        """
        logger.info("Starting cached artwork validation...")
        
        validation_results = {
            'total_checked': 0,
            'valid': 0,
            'missing_files': [],
            'corrupted_files': [],
            'database_inconsistencies': []
        }
        
        # Get all cache records
        cache_records = db.query(ArtworkCache).all()
        validation_results['total_checked'] = len(cache_records)
        
        for record in cache_records:
            try:
                # Check if file exists
                if record.file_path:
                    from pathlib import Path
                    file_path = Path(record.file_path)
                    
                    if not file_path.exists():
                        validation_results['missing_files'].append({
                            'album_id': record.album_id,
                            'variant': record.size_variant,
                            'path': record.file_path
                        })
                        continue
                    
                    # Validate file can be opened
                    try:
                        with open(file_path, 'rb') as f:
                            data = f.read(100)  # Read first 100 bytes
                            if not data:
                                raise ValueError("Empty file")
                        
                        validation_results['valid'] += 1
                        
                    except Exception as e:
                        validation_results['corrupted_files'].append({
                            'album_id': record.album_id,
                            'variant': record.size_variant,
                            'path': record.file_path,
                            'error': str(e)
                        })
                else:
                    validation_results['database_inconsistencies'].append({
                        'album_id': record.album_id,
                        'variant': record.size_variant,
                        'issue': 'No file path recorded'
                    })
                    
            except Exception as e:
                logger.error(f"Validation error for record {record.id}: {e}")
        
        # Generate summary
        validation_results['summary'] = {
            'total': validation_results['total_checked'],
            'valid': validation_results['valid'],
            'missing': len(validation_results['missing_files']),
            'corrupted': len(validation_results['corrupted_files']),
            'inconsistent': len(validation_results['database_inconsistencies']),
            'health_percentage': round(
                validation_results['valid'] / validation_results['total_checked'] * 100, 2
            ) if validation_results['total_checked'] > 0 else 0
        }
        
        logger.info(f"Validation complete: {validation_results['summary']}")
        
        return validation_results
    
    def _generate_report(self) -> Dict[str, Any]:
        """
        Generate a processing report
        
        Returns:
            Dictionary with processing statistics and results
        """
        duration = None
        if self.stats['start_time'] and self.stats['end_time']:
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        return {
            'summary': {
                'total': self.stats['total_processed'],
                'successful': self.stats['successful'],
                'failed': self.stats['failed'],
                'skipped': self.stats['skipped'],
                'retried': self.stats['retried'],
                'success_rate': round(
                    self.stats['successful'] / self.stats['total_processed'] * 100, 2
                ) if self.stats['total_processed'] > 0 else 0,
                'duration_seconds': duration,
                'avg_time_per_album': round(
                    duration / self.stats['total_processed'], 2
                ) if duration and self.stats['total_processed'] > 0 else 0
            },
            'errors': self.processing_errors[:10],  # First 10 errors
            'error_count': len(self.processing_errors),
            'statistics': self.stats
        }
    
    async def cleanup_orphaned_files(
        self,
        db: Session
    ) -> int:
        """
        Clean up orphaned cache files not in database
        
        Args:
            db: Database session
            
        Returns:
            Number of files cleaned up
        """
        logger.info("Starting orphaned file cleanup...")
        
        # Get all valid cache keys from database
        cache_records = db.query(ArtworkCache.cache_key).distinct().all()
        valid_keys = {record[0].rsplit('_', 1)[0] for record in cache_records}
        
        # Use filesystem utility to clean up
        deleted = self.cache_service.cache_fs.cleanup_orphaned_files(valid_keys)
        
        logger.info(f"Cleaned up {deleted} orphaned files")
        return deleted


# Global instance
_batch_processor = None


def get_batch_processor(
    batch_size: int = BatchArtworkProcessor.DEFAULT_BATCH_SIZE,
    concurrency: int = BatchArtworkProcessor.DEFAULT_CONCURRENCY
) -> BatchArtworkProcessor:
    """Get or create the global batch processor instance"""
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = BatchArtworkProcessor(
            batch_size=batch_size,
            concurrency=concurrency
        )
    return _batch_processor