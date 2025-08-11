"""
Cache cleanup service for managing disk space
Automatically removes old unused cache entries based on configurable retention policies
"""

import os
import logging
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..models import ArtworkCache, Album
from ..database import SessionLocal
from .artwork_cache_utils import get_cache_filesystem

logger = logging.getLogger(__name__)


@dataclass
class CleanupConfig:
    """Configuration for cache cleanup"""
    # Retention periods in days
    default_retention_days: int = 365  # 1 year default
    minimum_retention_days: int = 30   # Never delete items newer than this
    recently_added_grace_days: int = 7  # Grace period for newly cached items

    # Size limits
    max_cache_size_mb: Optional[int] = None  # Optional size limit
    target_size_mb: Optional[int] = None     # Target size after cleanup

    # Behavior
    dry_run: bool = False                    # If True, only simulate
    delete_orphaned_files: bool = True       # Delete files without DB records
    delete_invalid_records: bool = True      # Delete DB records without files

    # Performance
    batch_size: int = 100                    # Process in batches
    max_deletions_per_run: int = 1000        # Safety limit


class CacheCleanupService:
    """
    Service for cleaning up old cache entries
    """

    def __init__(self, config: Optional[CleanupConfig] = None):
        """
        Initialize the cleanup service

        Args:
            config: Cleanup configuration (uses defaults if None)
        """
        self.config = config or CleanupConfig()
        self.cache_fs = get_cache_filesystem()
        self.stats = self._reset_stats()

    def _reset_stats(self) -> Dict[str, Any]:
        """Reset statistics tracking"""
        return {
            'started_at': None,
            'completed_at': None,
            'duration_seconds': 0,
            'files_scanned': 0,
            'files_deleted': 0,
            'bytes_freed': 0,
            'records_scanned': 0,
            'records_deleted': 0,
            'orphaned_files': 0,
            'invalid_records': 0,
            'errors': [],
            'dry_run': self.config.dry_run
        }

    def cleanup(self, custom_retention_days: Optional[int] = None) -> Dict[str, Any]:
        """
        Run the cleanup process

        Args:
            custom_retention_days: Override default retention period

        Returns:
            Cleanup statistics and report
        """
        self.stats = self._reset_stats()
        self.stats['started_at'] = datetime.now(timezone.utc)

        retention_days = custom_retention_days or self.config.default_retention_days

        logger.info(f"Starting cache cleanup (retention: {retention_days} days, dry_run: {self.config.dry_run})")

        try:
            # Step 1: Clean up old cache entries
            self._cleanup_old_entries(retention_days)

            # Step 2: Clean up orphaned files
            if self.config.delete_orphaned_files:
                self._cleanup_orphaned_files()

            # Step 3: Clean up invalid database records
            if self.config.delete_invalid_records:
                self._cleanup_invalid_records()

            # Step 4: Enforce size limits if configured
            if self.config.max_cache_size_mb:
                self._enforce_size_limits()

            # Calculate summary
            self.stats['completed_at'] = datetime.now(timezone.utc)
            self.stats['duration_seconds'] = (
                self.stats['completed_at'] - self.stats['started_at']
            ).total_seconds()

            # Log summary
            self._log_summary()

            # Save report
            self._save_report()

            return self.stats

        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            self.stats['errors'].append(str(e))
            raise

    def _cleanup_old_entries(self, retention_days: int) -> None:
        """
        Remove cache entries older than retention period

        Args:
            retention_days: Number of days to retain
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        grace_date = datetime.now(timezone.utc) - timedelta(days=self.config.recently_added_grace_days)
        min_date = datetime.now(timezone.utc) - timedelta(days=self.config.minimum_retention_days)

        db = SessionLocal()
        try:
            # Find old entries that haven't been accessed recently
            old_entries = db.query(ArtworkCache).filter(
                and_(
                    ArtworkCache.last_accessed_at < cutoff_date,
                    ArtworkCache.last_fetched_at < grace_date,  # Not recently added
                    ArtworkCache.last_accessed_at < min_date     # Respect minimum retention
                )
            ).limit(self.config.max_deletions_per_run).all()

            logger.info(f"Found {len(old_entries)} cache entries to clean up")

            deletions = 0
            bytes_freed = 0

            for entry in old_entries:
                self.stats['records_scanned'] += 1

                # Delete file if it exists
                if entry.file_path:
                    file_path = Path(entry.file_path)
                    if file_path.exists():
                        file_size = file_path.stat().st_size

                        if not self.config.dry_run:
                            try:
                                file_path.unlink()
                                self.stats['files_deleted'] += 1
                                bytes_freed += file_size
                                logger.debug(f"Deleted file: {file_path} ({file_size} bytes)")
                            except Exception as e:
                                logger.error(f"Failed to delete file {file_path}: {e}")
                                self.stats['errors'].append(f"File deletion error: {e}")
                        else:
                            # Dry run - just count
                            self.stats['files_deleted'] += 1
                            bytes_freed += file_size

                # Delete database record
                if not self.config.dry_run:
                    db.delete(entry)
                    deletions += 1
                else:
                    deletions += 1

                self.stats['records_deleted'] += 1

                # Batch commit
                if deletions % self.config.batch_size == 0:
                    if not self.config.dry_run:
                        db.commit()
                    logger.debug(f"Processed {deletions} deletions")

            # Final commit
            if not self.config.dry_run:
                db.commit()

            self.stats['bytes_freed'] += bytes_freed

            logger.info(f"Cleaned up {deletions} old cache entries, freed {bytes_freed / (1024*1024):.2f} MB")

        except Exception as e:
            db.rollback()
            logger.error(f"Error cleaning old entries: {e}")
            self.stats['errors'].append(f"Old entries cleanup error: {e}")
            raise
        finally:
            db.close()

    def _cleanup_orphaned_files(self) -> None:
        """
        Remove files that don't have corresponding database records
        """
        logger.info("Scanning for orphaned files...")

        db = SessionLocal()
        try:
            # Get all file paths from database
            db_files = set()
            for record in db.query(ArtworkCache.file_path).filter(
                ArtworkCache.file_path.isnot(None)
            ).all():
                if record.file_path:
                    db_files.add(Path(record.file_path).name)

            # Scan cache directories
            cache_dir = Path(self.cache_fs.base_path)
            orphaned_bytes = 0

            for size_dir in cache_dir.iterdir():
                if not size_dir.is_dir():
                    continue

                for file_path in size_dir.iterdir():
                    if not file_path.is_file():
                        continue

                    self.stats['files_scanned'] += 1

                    # Check if file is in database
                    if file_path.name not in db_files:
                        file_size = file_path.stat().st_size
                        file_age = datetime.now(timezone.utc) - datetime.fromtimestamp(
                            file_path.stat().st_mtime,
                            tz=timezone.utc
                        )

                        # Only delete if older than grace period
                        if file_age.days > self.config.recently_added_grace_days:
                            if not self.config.dry_run:
                                try:
                                    file_path.unlink()
                                    logger.debug(f"Deleted orphaned file: {file_path}")
                                except Exception as e:
                                    logger.error(f"Failed to delete orphaned file {file_path}: {e}")
                                    self.stats['errors'].append(f"Orphaned file deletion error: {e}")
                                    continue

                            self.stats['orphaned_files'] += 1
                            self.stats['files_deleted'] += 1
                            orphaned_bytes += file_size

            self.stats['bytes_freed'] += orphaned_bytes

            logger.info(f"Cleaned up {self.stats['orphaned_files']} orphaned files, freed {orphaned_bytes / (1024*1024):.2f} MB")

        finally:
            db.close()

    def _cleanup_invalid_records(self) -> None:
        """
        Remove database records that point to non-existent files
        """
        logger.info("Scanning for invalid database records...")

        db = SessionLocal()
        try:
            invalid_records = []

            # Check all records with file paths
            records = db.query(ArtworkCache).filter(
                ArtworkCache.file_path.isnot(None)
            ).all()

            for record in records:
                self.stats['records_scanned'] += 1

                if record.file_path:
                    file_path = Path(record.file_path)
                    if not file_path.exists():
                        invalid_records.append(record)
                        self.stats['invalid_records'] += 1

            # Delete invalid records
            if invalid_records:
                logger.info(f"Found {len(invalid_records)} invalid database records")

                for record in invalid_records:
                    if not self.config.dry_run:
                        db.delete(record)
                    self.stats['records_deleted'] += 1

                if not self.config.dry_run:
                    db.commit()

                logger.info(f"Cleaned up {len(invalid_records)} invalid records")

        except Exception as e:
            db.rollback()
            logger.error(f"Error cleaning invalid records: {e}")
            self.stats['errors'].append(f"Invalid records cleanup error: {e}")
        finally:
            db.close()

    def _enforce_size_limits(self) -> None:
        """
        Enforce maximum cache size by removing least recently used items
        """
        if not self.config.max_cache_size_mb:
            return

        current_size_mb = self._get_cache_size_mb()

        if current_size_mb <= self.config.max_cache_size_mb:
            logger.info(f"Cache size ({current_size_mb:.2f} MB) is within limit ({self.config.max_cache_size_mb} MB)")
            return

        target_size_mb = self.config.target_size_mb or (self.config.max_cache_size_mb * 0.8)
        bytes_to_free = int((current_size_mb - target_size_mb) * 1024 * 1024)

        logger.info(f"Cache size ({current_size_mb:.2f} MB) exceeds limit, need to free {bytes_to_free / (1024*1024):.2f} MB")

        db = SessionLocal()
        try:
            # Get LRU entries
            lru_entries = db.query(ArtworkCache).filter(
                ArtworkCache.file_path.isnot(None)
            ).order_by(
                ArtworkCache.last_accessed_at.asc()
            ).limit(self.config.max_deletions_per_run).all()

            bytes_freed = 0

            for entry in lru_entries:
                if bytes_freed >= bytes_to_free:
                    break

                # Skip recently added items
                if entry.last_fetched_at:
                    age = datetime.now(timezone.utc) - entry.last_fetched_at
                    if age.days < self.config.recently_added_grace_days:
                        continue

                # Delete file
                if entry.file_path:
                    file_path = Path(entry.file_path)
                    if file_path.exists():
                        file_size = file_path.stat().st_size

                        if not self.config.dry_run:
                            try:
                                file_path.unlink()
                                db.delete(entry)
                            except Exception as e:
                                logger.error(f"Failed to delete {file_path}: {e}")
                                continue

                        bytes_freed += file_size
                        self.stats['files_deleted'] += 1
                        self.stats['records_deleted'] += 1

            if not self.config.dry_run:
                db.commit()

            self.stats['bytes_freed'] += bytes_freed

            logger.info(f"Freed {bytes_freed / (1024*1024):.2f} MB to enforce size limits")

        except Exception as e:
            db.rollback()
            logger.error(f"Error enforcing size limits: {e}")
            self.stats['errors'].append(f"Size limit enforcement error: {e}")
        finally:
            db.close()

    def _get_cache_size_mb(self) -> float:
        """Get total cache size in MB"""
        cache_dir = Path(self.cache_fs.base_path)
        total_size = 0

        for size_dir in cache_dir.iterdir():
            if size_dir.is_dir():
                for file_path in size_dir.iterdir():
                    if file_path.is_file():
                        total_size += file_path.stat().st_size

        return total_size / (1024 * 1024)

    def _log_summary(self) -> None:
        """Log cleanup summary"""
        duration = self.stats['duration_seconds']
        mb_freed = self.stats['bytes_freed'] / (1024 * 1024)

        summary = f"""
Cache Cleanup Summary:
  Duration: {duration:.2f} seconds
  Files scanned: {self.stats['files_scanned']}
  Files deleted: {self.stats['files_deleted']}
  Records deleted: {self.stats['records_deleted']}
  Orphaned files: {self.stats['orphaned_files']}
  Invalid records: {self.stats['invalid_records']}
  Space freed: {mb_freed:.2f} MB
  Errors: {len(self.stats['errors'])}
  Dry run: {self.stats['dry_run']}
        """

        logger.info(summary)

    def _save_report(self) -> None:
        """Save cleanup report to file"""
        reports_dir = Path("logs/cleanup_reports")
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"cleanup_{timestamp}.json"

        with open(report_file, 'w') as f:
            json.dump(self.stats, f, indent=2, default=str)

        logger.info(f"Cleanup report saved to {report_file}")

    def get_cleanup_status(self) -> Dict[str, Any]:
        """
        Get current cache status and cleanup recommendations

        Returns:
            Status information and recommendations
        """
        db = SessionLocal()
        try:
            # Get cache statistics
            total_entries = db.query(ArtworkCache).count()

            # Get old entries count
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.default_retention_days)
            old_entries = db.query(ArtworkCache).filter(
                ArtworkCache.last_accessed_at < cutoff_date
            ).count()

            # Get cache size
            cache_size_mb = self._get_cache_size_mb()

            # Get recently accessed count (last 30 days)
            recent_date = datetime.now(timezone.utc) - timedelta(days=30)
            recent_entries = db.query(ArtworkCache).filter(
                ArtworkCache.last_accessed_at >= recent_date
            ).count()

            return {
                'total_entries': total_entries,
                'old_entries': old_entries,
                'recent_entries': recent_entries,
                'cache_size_mb': cache_size_mb,
                'retention_days': self.config.default_retention_days,
                'recommended_cleanup': old_entries > 0 or (
                    self.config.max_cache_size_mb and
                    cache_size_mb > self.config.max_cache_size_mb
                ),
                'estimated_space_to_free_mb': self._estimate_space_to_free(db, cutoff_date)
            }

        finally:
            db.close()

    def _estimate_space_to_free(self, db: Session, cutoff_date: datetime) -> float:
        """Estimate space that would be freed by cleanup"""
        old_entries = db.query(ArtworkCache).filter(
            ArtworkCache.last_accessed_at < cutoff_date
        ).all()

        total_bytes = 0
        for entry in old_entries:
            if entry.file_path:
                file_path = Path(entry.file_path)
                if file_path.exists():
                    total_bytes += file_path.stat().st_size

        return total_bytes / (1024 * 1024)


# Global instance
_cleanup_service = None


def get_cleanup_service(config: Optional[CleanupConfig] = None) -> CacheCleanupService:
    """Get the global cleanup service instance"""
    global _cleanup_service
    if _cleanup_service is None or config:
        _cleanup_service = CacheCleanupService(config)
    return _cleanup_service
