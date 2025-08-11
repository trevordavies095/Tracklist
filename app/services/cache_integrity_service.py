"""
Cache Integrity Verification Service
Verifies and repairs artwork cache integrity
"""

import os
import hashlib
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..models import Album, ArtworkCache
from ..database import SessionLocal
from .artwork_cache_utils import ArtworkCacheFileSystem, get_cache_filesystem
from .image_processor import ImageProcessor, get_image_processor
from .artwork_cache_service import ArtworkCacheService

logger = logging.getLogger(__name__)


class CacheIntegrityError(Exception):
    """Exception for cache integrity issues"""
    pass


class CacheIntegrityService:
    """
    Service for verifying and repairing artwork cache integrity

    Performs:
    - Database-filesystem consistency checks
    - File validation (size, format, corruption)
    - Orphaned file detection
    - Missing variant rebuilding
    - Integrity reporting
    """

    # Valid image extensions
    VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

    # Size variants that should exist
    EXPECTED_VARIANTS = ['thumbnail', 'small', 'medium', 'large', 'original']

    def __init__(self, cache_fs: Optional[ArtworkCacheFileSystem] = None):
        """
        Initialize the integrity service

        Args:
            cache_fs: Optional filesystem manager
        """
        self.cache_fs = cache_fs or get_cache_filesystem()
        self.image_processor = get_image_processor()
        self.cache_service = ArtworkCacheService(self.cache_fs)

        # Track verification results
        self.results = {
            'start_time': None,
            'end_time': None,
            'total_records': 0,
            'valid_files': 0,
            'missing_files': [],
            'corrupted_files': [],
            'orphaned_files': [],
            'size_mismatches': [],
            'missing_variants': [],
            'repaired_files': [],
            'failed_repairs': [],
            'errors': []
        }

    def verify_integrity(
        self,
        repair: bool = False,
        albums_limit: Optional[int] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Verify cache integrity and optionally repair issues

        Args:
            repair: Whether to attempt repairs
            albums_limit: Limit number of albums to check
            verbose: Include detailed information

        Returns:
            Integrity report dictionary
        """
        logger.info(f"Starting cache integrity verification (repair={repair})")
        self.results['start_time'] = datetime.now(timezone.utc)

        try:
            with SessionLocal() as db:
                # 1. Check database records against filesystem
                self._verify_database_files(db, albums_limit)

                # 2. Check filesystem for orphaned files
                self._check_orphaned_files(db)

                # 3. Verify file integrity (size, format)
                self._verify_file_integrity(db)

                # 4. Check for missing variants
                self._check_missing_variants(db, albums_limit)

                # 5. Attempt repairs if requested
                if repair:
                    self._repair_issues(db)
                    db.commit()

                # 6. Generate report
                self.results['end_time'] = datetime.now(timezone.utc)
                return self._generate_report(verbose)

        except Exception as e:
            logger.error(f"Integrity verification failed: {e}")
            self.results['errors'].append(str(e))
            self.results['end_time'] = datetime.now(timezone.utc)
            return self._generate_report(verbose)

    def _verify_database_files(self, db: Session, albums_limit: Optional[int] = None) -> None:
        """
        Verify that files referenced in database actually exist

        Args:
            db: Database session
            albums_limit: Limit number of albums to check
        """
        logger.debug("Verifying database files...")

        # Get all cache records
        query = db.query(ArtworkCache).filter(
            ArtworkCache.file_path.isnot(None)
        )

        if albums_limit:
            album_ids = db.query(Album.id).limit(albums_limit).subquery()
            query = query.filter(ArtworkCache.album_id.in_(album_ids))

        cache_records = query.all()
        self.results['total_records'] = len(cache_records)

        for record in cache_records:
            file_path = Path(record.file_path)

            if not file_path.exists():
                self.results['missing_files'].append({
                    'record_id': record.id,
                    'album_id': record.album_id,
                    'size_variant': record.size_variant,
                    'file_path': str(file_path)
                })
                logger.warning(f"Missing file: {file_path}")
            else:
                # Check file size matches
                actual_size = file_path.stat().st_size
                if record.file_size_bytes and actual_size != record.file_size_bytes:
                    self.results['size_mismatches'].append({
                        'record_id': record.id,
                        'album_id': record.album_id,
                        'expected_size': record.file_size_bytes,
                        'actual_size': actual_size,
                        'file_path': str(file_path)
                    })
                else:
                    self.results['valid_files'] += 1

    def _check_orphaned_files(self, db: Session) -> None:
        """
        Find files in cache directory not referenced in database

        Args:
            db: Database session
        """
        logger.debug("Checking for orphaned files...")

        # Get all file paths from database
        db_files = set()
        cache_records = db.query(ArtworkCache.file_path).filter(
            ArtworkCache.file_path.isnot(None)
        ).all()

        for record in cache_records:
            db_files.add(Path(record.file_path).resolve())

        # Walk through cache directory
        cache_dir = Path(self.cache_fs.base_path)

        for size_variant in self.EXPECTED_VARIANTS:
            variant_dir = cache_dir / size_variant
            if not variant_dir.exists():
                continue

            for file_path in variant_dir.glob("*"):
                if file_path.is_file() and file_path.suffix.lower() in self.VALID_EXTENSIONS:
                    resolved_path = file_path.resolve()

                    if resolved_path not in db_files:
                        self.results['orphaned_files'].append({
                            'file_path': str(file_path),
                            'size': file_path.stat().st_size,
                            'modified': datetime.fromtimestamp(
                                file_path.stat().st_mtime,
                                timezone.utc
                            ).isoformat()
                        })
                        logger.warning(f"Orphaned file: {file_path}")

    def _verify_file_integrity(self, db: Session) -> None:
        """
        Verify file integrity (check if images are valid)

        Args:
            db: Database session
        """
        logger.debug("Verifying file integrity...")

        # Sample files to check (don't check all for performance)
        sample_size = min(100, self.results['total_records']) if self.results['total_records'] > 0 else 0

        cache_records = db.query(ArtworkCache).filter(
            ArtworkCache.file_path.isnot(None)
        ).limit(sample_size).all()

        for record in cache_records:
            file_path = Path(record.file_path)

            if file_path.exists():
                try:
                    # Try to open and verify image
                    with Image.open(file_path) as img:
                        img.verify()

                        # Check if format matches extension
                        expected_format = 'JPEG' if file_path.suffix.lower() in ['.jpg', '.jpeg'] else file_path.suffix[1:].upper()
                        if img.format and img.format != expected_format:
                            logger.warning(f"Format mismatch: {file_path} (expected {expected_format}, got {img.format})")

                except Exception as e:
                    self.results['corrupted_files'].append({
                        'record_id': record.id,
                        'album_id': record.album_id,
                        'file_path': str(file_path),
                        'error': str(e)
                    })
                    logger.error(f"Corrupted file: {file_path} - {e}")

    def _check_missing_variants(self, db: Session, albums_limit: Optional[int] = None) -> None:
        """
        Check for albums missing expected size variants

        Args:
            db: Database session
            albums_limit: Limit number of albums to check
        """
        logger.debug("Checking for missing variants...")

        # Get albums with cached artwork
        query = db.query(Album).filter(
            Album.artwork_cached == True
        )

        if albums_limit:
            query = query.limit(albums_limit)

        albums = query.all()

        for album in albums:
            # Get existing variants for this album
            existing_variants = db.query(ArtworkCache.size_variant).filter(
                ArtworkCache.album_id == album.id,
                ArtworkCache.file_path.isnot(None)
            ).all()

            existing_set = {v[0] for v in existing_variants}
            missing = set(self.EXPECTED_VARIANTS) - existing_set

            if missing:
                # Check if we have original to rebuild from
                has_original = 'original' in existing_set

                self.results['missing_variants'].append({
                    'album_id': album.id,
                    'album_name': album.name,
                    'missing': list(missing),
                    'has_original': has_original,
                    'can_rebuild': has_original and 'original' not in missing
                })

    def _repair_issues(self, db: Session) -> None:
        """
        Attempt to repair detected issues

        Args:
            db: Database session
        """
        logger.info("Attempting to repair issues...")

        # 1. Remove database records for missing files
        for missing in self.results['missing_files']:
            try:
                record = db.query(ArtworkCache).filter(
                    ArtworkCache.id == missing['record_id']
                ).first()

                if record:
                    db.delete(record)
                    self.results['repaired_files'].append({
                        'type': 'removed_missing_record',
                        'record_id': missing['record_id']
                    })
                    logger.info(f"Removed record for missing file: {missing['file_path']}")

            except Exception as e:
                self.results['failed_repairs'].append({
                    'type': 'remove_record',
                    'record_id': missing['record_id'],
                    'error': str(e)
                })

        # 2. Remove orphaned files
        for orphaned in self.results['orphaned_files']:
            try:
                file_path = Path(orphaned['file_path'])
                if file_path.exists():
                    file_path.unlink()
                    self.results['repaired_files'].append({
                        'type': 'removed_orphaned_file',
                        'file_path': str(file_path)
                    })
                    logger.info(f"Removed orphaned file: {file_path}")

            except Exception as e:
                self.results['failed_repairs'].append({
                    'type': 'remove_file',
                    'file_path': orphaned['file_path'],
                    'error': str(e)
                })

        # 3. Rebuild missing variants
        for missing_variant in self.results['missing_variants']:
            if missing_variant['can_rebuild']:
                try:
                    album = db.query(Album).filter(
                        Album.id == missing_variant['album_id']
                    ).first()

                    if album:
                        # Get original image
                        original = db.query(ArtworkCache).filter(
                            ArtworkCache.album_id == album.id,
                            ArtworkCache.size_variant == 'original',
                            ArtworkCache.file_path.isnot(None)
                        ).first()

                        if original and Path(original.file_path).exists():
                            # Rebuild missing variants
                            for variant in missing_variant['missing']:
                                if variant != 'original':
                                    self._rebuild_variant(album, original, variant, db)

                except Exception as e:
                    self.results['failed_repairs'].append({
                        'type': 'rebuild_variant',
                        'album_id': missing_variant['album_id'],
                        'error': str(e)
                    })

        # 4. Update albums with no cached artwork flag
        for missing in self.results['missing_files']:
            album = db.query(Album).filter(
                Album.id == missing['album_id']
            ).first()

            if album:
                # Check if album has any valid cached files
                valid_count = db.query(ArtworkCache).filter(
                    ArtworkCache.album_id == album.id,
                    ArtworkCache.file_path.isnot(None)
                ).count()

                if valid_count == 0:
                    album.artwork_cached = False
                    logger.info(f"Marked album {album.id} as not cached")

    def _rebuild_variant(
        self,
        album: Album,
        original: ArtworkCache,
        variant: str,
        db: Session
    ) -> None:
        """
        Rebuild a missing size variant from original

        Args:
            album: Album model
            original: Original artwork cache record
            variant: Size variant to rebuild
            db: Database session
        """
        try:
            # Load original image
            with Image.open(original.file_path) as img:
                # Get target dimensions
                dimensions = self.image_processor.SIZE_VARIANTS.get(variant)
                if not dimensions:
                    logger.warning(f"Unknown variant: {variant}")
                    return

                # Process image
                processed = self.image_processor.process_image(
                    img,
                    variant,
                    smart_crop=True
                )

                # Save to cache
                cache_key = self.cache_service.generate_cache_key(album)
                file_path = self.cache_fs.get_cache_path(cache_key, variant)

                # Save processed image
                processed.save(file_path, quality=85, optimize=True)

                # Create database record
                cache_record = ArtworkCache(
                    album_id=album.id,
                    original_url=album.cover_art_url,
                    size_variant=variant,
                    file_path=str(file_path),
                    file_size_bytes=file_path.stat().st_size,
                    width=processed.width,
                    height=processed.height,
                    format='JPEG',
                    cached_at=datetime.now(timezone.utc)
                )

                db.add(cache_record)

                self.results['repaired_files'].append({
                    'type': 'rebuilt_variant',
                    'album_id': album.id,
                    'variant': variant,
                    'file_path': str(file_path)
                })

                logger.info(f"Rebuilt {variant} variant for album {album.id}")

        except Exception as e:
            logger.error(f"Failed to rebuild {variant} for album {album.id}: {e}")
            raise

    def _generate_report(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Generate integrity verification report

        Args:
            verbose: Include detailed information

        Returns:
            Report dictionary
        """
        duration = None
        if self.results['start_time'] and self.results['end_time']:
            duration = (self.results['end_time'] - self.results['start_time']).total_seconds()

        # Calculate integrity score
        total_issues = (
            len(self.results['missing_files']) +
            len(self.results['corrupted_files']) +
            len(self.results['orphaned_files']) +
            len(self.results['size_mismatches']) +
            len(self.results['missing_variants'])
        )

        integrity_score = 100
        if self.results['total_records'] > 0:
            issue_rate = total_issues / self.results['total_records']
            integrity_score = max(0, 100 - (issue_rate * 100))

        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': duration,
            'integrity_score': round(integrity_score, 2),
            'summary': {
                'total_records': self.results['total_records'],
                'valid_files': self.results['valid_files'],
                'issues_found': total_issues,
                'repairs_completed': len(self.results['repaired_files']),
                'repairs_failed': len(self.results['failed_repairs'])
            },
            'issues': {
                'missing_files': len(self.results['missing_files']),
                'corrupted_files': len(self.results['corrupted_files']),
                'orphaned_files': len(self.results['orphaned_files']),
                'size_mismatches': len(self.results['size_mismatches']),
                'missing_variants': len(self.results['missing_variants'])
            }
        }

        if verbose:
            report['details'] = {
                'missing_files': self.results['missing_files'][:10],  # Limit to 10
                'corrupted_files': self.results['corrupted_files'][:10],
                'orphaned_files': self.results['orphaned_files'][:10],
                'missing_variants': self.results['missing_variants'][:10],
                'repaired_files': self.results['repaired_files'][:10],
                'failed_repairs': self.results['failed_repairs']
            }

        if self.results['errors']:
            report['errors'] = self.results['errors']

        # Save report to file
        report_path = Path('logs') / f"integrity_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(exist_ok=True)

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Integrity report saved to {report_path}")

        return report

    def quick_check(self) -> Dict[str, Any]:
        """
        Perform a quick integrity check (sample-based)

        Returns:
            Quick check results
        """
        logger.info("Performing quick integrity check...")

        with SessionLocal() as db:
            # Check a sample of records
            total_records = db.query(ArtworkCache).count()
            sample_size = min(50, total_records)

            sample_records = db.query(ArtworkCache).filter(
                ArtworkCache.file_path.isnot(None)
            ).order_by(db.func.random()).limit(sample_size).all()

            missing = 0
            valid = 0

            for record in sample_records:
                if Path(record.file_path).exists():
                    valid += 1
                else:
                    missing += 1

            # Extrapolate to full dataset
            if sample_size > 0:
                estimated_missing = int((missing / sample_size) * total_records)
                estimated_integrity = ((valid / sample_size) * 100)
            else:
                estimated_missing = 0
                estimated_integrity = 100

            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'quick_check',
                'sample_size': sample_size,
                'total_records': total_records,
                'sample_valid': valid,
                'sample_missing': missing,
                'estimated_missing': estimated_missing,
                'estimated_integrity_score': round(estimated_integrity, 2)
            }


# Global instance
_integrity_service = None


def get_integrity_service() -> CacheIntegrityService:
    """Get or create global integrity service instance"""
    global _integrity_service
    if _integrity_service is None:
        _integrity_service = CacheIntegrityService()
    return _integrity_service
