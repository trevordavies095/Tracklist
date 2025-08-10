#!/usr/bin/env python3
"""
Test script for cache cleanup functionality
Tests retention enforcement, orphaned file cleanup, and reporting
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import shutil

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, create_tables, init_db
from app.models import Album, Artist, ArtworkCache
from app.services.cache_cleanup_service import CacheCleanupService, CleanupConfig
from app.services.artwork_cache_utils import get_cache_filesystem
from app.services.scheduled_tasks import get_scheduled_task_manager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CacheCleanupTester:
    """Test harness for cache cleanup functionality"""
    
    def __init__(self):
        self.db = SessionLocal()
        self.cache_fs = get_cache_filesystem()
        self.test_files = []
        self.test_records = []
        
    def setup(self):
        """Setup test environment"""
        logger.info("Setting up test environment...")
        
        # Ensure database is initialized
        create_tables()
        init_db()
        
        # Create test artist if not exists
        artist = self.db.query(Artist).filter(Artist.name == "Test Artist").first()
        if not artist:
            artist = Artist(
                name="Test Artist",
                musicbrainz_id="test-artist-cleanup-" + str(datetime.now().timestamp())
            )
            self.db.add(artist)
            self.db.commit()
        
        self.test_artist = artist
        logger.info(f"Test artist ready: {artist.name}")
        
    def teardown(self):
        """Clean up test data"""
        logger.info("Cleaning up test data...")
        
        # Delete test files
        for file_path in self.test_files:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Deleted test file: {file_path}")
        
        # Delete test records
        for record_id in self.test_records:
            record = self.db.query(ArtworkCache).filter(ArtworkCache.id == record_id).first()
            if record:
                self.db.delete(record)
        self.db.commit()
        
        self.db.close()
        logger.info("Cleanup complete")
    
    def create_test_cache_entry(self, age_days: int, accessed_days_ago: int = None) -> ArtworkCache:
        """Create a test cache entry with specified age"""
        
        # Create test album
        album = Album(
            name=f"Test Album {datetime.now().timestamp()}",
            artist_id=self.test_artist.id,
            musicbrainz_id=f"test-album-{datetime.now().timestamp()}",
            release_year=2024
        )
        self.db.add(album)
        self.db.commit()
        
        # Create cache file
        cache_dir = Path(self.cache_fs.base_path) / "medium"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = f"test_{album.id}_{datetime.now().timestamp()}.jpg"
        file_path = cache_dir / file_name
        
        # Write dummy content
        file_path.write_bytes(b"Test image data" * 100)  # ~1.4KB file
        self.test_files.append(file_path)
        
        # Create cache record
        now = datetime.now(timezone.utc)
        fetch_date = now - timedelta(days=age_days)
        access_date = now - timedelta(days=accessed_days_ago if accessed_days_ago is not None else age_days)
        
        cache_entry = ArtworkCache(
            album_id=album.id,
            original_url="https://example.com/test.jpg",
            cache_key=f"test-cache-key-{album.id}-medium",
            size_variant="medium",
            file_path=str(file_path),
            file_size_bytes=file_path.stat().st_size,
            content_type="image/jpeg",
            etag=f"test-etag-{album.id}",
            last_fetched_at=fetch_date,
            last_accessed_at=access_date,
            access_count=1,
            is_placeholder=False
        )
        
        self.db.add(cache_entry)
        self.db.commit()
        self.test_records.append(cache_entry.id)
        
        logger.info(f"Created test cache entry: age={age_days} days, last_accessed={accessed_days_ago or age_days} days ago")
        return cache_entry
    
    def create_orphaned_file(self, age_days: int) -> Path:
        """Create an orphaned file without database record"""
        cache_dir = Path(self.cache_fs.base_path) / "small"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = f"orphaned_{datetime.now().timestamp()}.jpg"
        file_path = cache_dir / file_name
        
        # Write dummy content
        file_path.write_bytes(b"Orphaned file data" * 50)
        
        # Set modification time to simulate age
        age_timestamp = (datetime.now() - timedelta(days=age_days)).timestamp()
        os.utime(file_path, (age_timestamp, age_timestamp))
        
        self.test_files.append(file_path)
        logger.info(f"Created orphaned file: {file_path} (age={age_days} days)")
        return file_path
    
    def create_invalid_record(self) -> ArtworkCache:
        """Create a database record pointing to non-existent file"""
        
        # Create test album
        album = Album(
            name=f"Invalid Record Album {datetime.now().timestamp()}",
            artist_id=self.test_artist.id,
            musicbrainz_id=f"invalid-album-{datetime.now().timestamp()}",
            release_year=2024
        )
        self.db.add(album)
        self.db.commit()
        
        # Create cache record with non-existent file
        cache_entry = ArtworkCache(
            album_id=album.id,
            original_url="https://example.com/invalid.jpg",
            cache_key=f"test-cache-key-{album.id}-large",
            size_variant="large",
            file_path=f"/nonexistent/path/file_{datetime.now().timestamp()}.jpg",
            file_size_bytes=1024,
            content_type="image/jpeg",
            last_fetched_at=datetime.now(timezone.utc),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=1,
            is_placeholder=False
        )
        
        self.db.add(cache_entry)
        self.db.commit()
        self.test_records.append(cache_entry.id)
        
        logger.info(f"Created invalid record pointing to: {cache_entry.file_path}")
        return cache_entry
    
    def test_retention_cleanup(self):
        """Test that old entries are cleaned up correctly"""
        logger.info("\n=== Testing Retention-Based Cleanup ===")
        
        # Create entries with different ages
        old_entry = self.create_test_cache_entry(age_days=400, accessed_days_ago=400)  # Should be deleted
        old_entry_id = old_entry.id
        recent_entry = self.create_test_cache_entry(age_days=10, accessed_days_ago=5)   # Should be kept
        recent_entry_id = recent_entry.id
        old_but_accessed = self.create_test_cache_entry(age_days=400, accessed_days_ago=20)  # Should be kept (min retention)
        old_but_accessed_id = old_but_accessed.id
        
        # Run cleanup with 365 day retention
        config = CleanupConfig(
            default_retention_days=365,
            minimum_retention_days=30,
            dry_run=False
        )
        
        service = CacheCleanupService(config)
        result = service.cleanup()
        
        # Verify results
        assert result['records_deleted'] >= 1, f"Expected at least 1 record deleted, got {result['records_deleted']}"
        assert result['files_deleted'] >= 1, f"Expected at least 1 file deleted, got {result['files_deleted']}"
        
        # Check that old entry was deleted
        old_record = self.db.query(ArtworkCache).filter(ArtworkCache.id == old_entry_id).first()
        assert old_record is None, "Old entry should have been deleted"
        
        # Check that recent entry still exists
        recent_record = self.db.query(ArtworkCache).filter(ArtworkCache.id == recent_entry_id).first()
        assert recent_record is not None, "Recent entry should still exist"
        
        # Check that old but recently accessed entry still exists
        accessed_record = self.db.query(ArtworkCache).filter(ArtworkCache.id == old_but_accessed_id).first()
        assert accessed_record is not None, "Old but recently accessed entry should still exist (minimum retention)"
        
        logger.info(f"✓ Retention cleanup test passed: {result['records_deleted']} records deleted")
        return True
    
    def test_orphaned_files_cleanup(self):
        """Test that orphaned files are cleaned up"""
        logger.info("\n=== Testing Orphaned Files Cleanup ===")
        
        # Create orphaned files
        old_orphan = self.create_orphaned_file(age_days=30)
        new_orphan = self.create_orphaned_file(age_days=3)  # Should be kept (grace period)
        
        # Run cleanup
        config = CleanupConfig(
            default_retention_days=365,
            recently_added_grace_days=7,
            delete_orphaned_files=True,
            dry_run=False
        )
        
        service = CacheCleanupService(config)
        result = service.cleanup()
        
        # Verify results
        assert result['orphaned_files'] >= 1, f"Expected at least 1 orphaned file cleaned, got {result['orphaned_files']}"
        
        # Check that old orphan was deleted
        assert not old_orphan.exists(), "Old orphaned file should have been deleted"
        
        # Check that new orphan still exists
        assert new_orphan.exists(), "New orphaned file should still exist (grace period)"
        
        logger.info(f"✓ Orphaned files cleanup test passed: {result['orphaned_files']} files cleaned")
        return True
    
    def test_invalid_records_cleanup(self):
        """Test that invalid database records are cleaned up"""
        logger.info("\n=== Testing Invalid Records Cleanup ===")
        
        # Create invalid record
        invalid_record = self.create_invalid_record()
        invalid_record_id = invalid_record.id
        
        # Run cleanup
        config = CleanupConfig(
            default_retention_days=365,
            delete_invalid_records=True,
            dry_run=False
        )
        
        service = CacheCleanupService(config)
        result = service.cleanup()
        
        # Verify results
        assert result['invalid_records'] >= 1, f"Expected at least 1 invalid record cleaned, got {result['invalid_records']}"
        
        # Check that invalid record was deleted
        record = self.db.query(ArtworkCache).filter(ArtworkCache.id == invalid_record_id).first()
        assert record is None, "Invalid record should have been deleted"
        
        logger.info(f"✓ Invalid records cleanup test passed: {result['invalid_records']} records cleaned")
        return True
    
    def test_dry_run(self):
        """Test that dry run doesn't actually delete anything"""
        logger.info("\n=== Testing Dry Run Mode ===")
        
        # Create test data
        old_entry = self.create_test_cache_entry(age_days=400, accessed_days_ago=400)
        old_entry_id = old_entry.id
        orphan = self.create_orphaned_file(age_days=30)
        
        # Get initial counts
        initial_records = self.db.query(ArtworkCache).count()
        
        # Run cleanup in dry run mode
        config = CleanupConfig(
            default_retention_days=365,
            minimum_retention_days=30,
            delete_orphaned_files=True,
            dry_run=True  # DRY RUN MODE
        )
        
        service = CacheCleanupService(config)
        result = service.cleanup()
        
        # Verify that counts are reported but nothing was actually deleted
        assert result['dry_run'] == True, "Should be in dry run mode"
        assert result['records_deleted'] >= 1, f"Should report records to delete: {result['records_deleted']}"
        assert result['files_deleted'] >= 1, f"Should report files to delete: {result['files_deleted']}"
        
        # Check that nothing was actually deleted
        final_records = self.db.query(ArtworkCache).count()
        assert final_records == initial_records, "No records should be deleted in dry run"
        
        assert orphan.exists(), "Orphaned file should still exist in dry run"
        
        record = self.db.query(ArtworkCache).filter(ArtworkCache.id == old_entry_id).first()
        assert record is not None, "Old record should still exist in dry run"
        
        logger.info(f"✓ Dry run test passed: {result['records_deleted']} records would be deleted (but weren't)")
        return True
    
    def test_cleanup_status(self):
        """Test cleanup status reporting"""
        logger.info("\n=== Testing Cleanup Status ===")
        
        # Create some test data
        self.create_test_cache_entry(age_days=400, accessed_days_ago=400)
        self.create_test_cache_entry(age_days=10, accessed_days_ago=5)
        
        # Get cleanup status
        service = CacheCleanupService()
        status = service.get_cleanup_status()
        
        # Verify status structure
        assert 'total_entries' in status, "Status should include total_entries"
        assert 'old_entries' in status, "Status should include old_entries"
        assert 'recent_entries' in status, "Status should include recent_entries"
        assert 'cache_size_mb' in status, "Status should include cache_size_mb"
        assert 'recommended_cleanup' in status, "Status should include recommended_cleanup"
        
        logger.info(f"✓ Cleanup status test passed:")
        logger.info(f"  Total entries: {status['total_entries']}")
        logger.info(f"  Old entries: {status['old_entries']}")
        logger.info(f"  Recent entries: {status['recent_entries']}")
        logger.info(f"  Cache size: {status['cache_size_mb']:.2f} MB")
        logger.info(f"  Cleanup recommended: {status['recommended_cleanup']}")
        
        return True
    
    async def test_scheduled_cleanup(self):
        """Test scheduled cleanup trigger"""
        logger.info("\n=== Testing Scheduled Cleanup Trigger ===")
        
        # Create old entry that should be cleaned
        self.create_test_cache_entry(age_days=400, accessed_days_ago=400)
        
        # Get scheduled task manager
        manager = get_scheduled_task_manager()
        
        # Trigger cleanup manually
        result = await manager.trigger_cleanup_now(dry_run=False)
        
        # Verify result
        assert result['records_deleted'] >= 1, f"Expected cleanup to delete records: {result['records_deleted']}"
        
        logger.info(f"✓ Scheduled cleanup test passed: {result['records_deleted']} records cleaned")
        return True
    
    def run_all_tests(self):
        """Run all tests"""
        logger.info("Starting Cache Cleanup Tests")
        logger.info("=" * 50)
        
        try:
            self.setup()
            
            # Run tests
            results = []
            
            results.append(("Retention Cleanup", self.test_retention_cleanup()))
            results.append(("Orphaned Files", self.test_orphaned_files_cleanup()))
            results.append(("Invalid Records", self.test_invalid_records_cleanup()))
            results.append(("Dry Run Mode", self.test_dry_run()))
            results.append(("Status Reporting", self.test_cleanup_status()))
            
            # Run async test
            loop = asyncio.get_event_loop()
            results.append(("Scheduled Cleanup", loop.run_until_complete(self.test_scheduled_cleanup())))
            
            # Print summary
            logger.info("\n" + "=" * 50)
            logger.info("TEST SUMMARY")
            logger.info("=" * 50)
            
            all_passed = True
            for test_name, passed in results:
                status = "✓ PASSED" if passed else "✗ FAILED"
                logger.info(f"{test_name:.<30} {status}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                logger.info("\n🎉 All tests passed!")
            else:
                logger.error("\n❌ Some tests failed!")
            
            return all_passed
            
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            return False
        finally:
            self.teardown()


def main():
    """Main entry point"""
    tester = CacheCleanupTester()
    success = tester.run_all_tests()
    
    if success:
        logger.info("\n✅ Cache cleanup functionality is working correctly!")
        sys.exit(0)
    else:
        logger.error("\n❌ Cache cleanup tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()