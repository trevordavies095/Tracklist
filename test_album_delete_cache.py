#!/usr/bin/env python3
"""
Test that cache is properly cleaned up when an album is deleted
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, create_tables, init_db
from app.models import Album, Artist, ArtworkCache
from app.rating_service import RatingService
from app.services.artwork_cache_service import ArtworkCacheService
from app.services.artwork_memory_cache import get_artwork_memory_cache

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_album_delete_cache_cleanup():
    """Test that deleting an album cleans up its cache"""
    logger.info("Testing album delete cache cleanup...")
    
    # Initialize database
    create_tables()
    init_db()
    
    db = SessionLocal()
    rating_service = RatingService()
    cache_service = ArtworkCacheService()
    memory_cache = get_artwork_memory_cache()
    
    try:
        # Create test artist
        artist = Artist(
            name="Test Cache Delete Artist",
            musicbrainz_id=f"test-artist-{datetime.now().timestamp()}"
        )
        db.add(artist)
        db.commit()
        
        # Create test album
        album = Album(
            name="Test Album for Cache Deletion",
            artist_id=artist.id,
            musicbrainz_id=f"test-album-{datetime.now().timestamp()}",
            release_year=2024,
            cover_art_url="https://example.com/test.jpg"
        )
        db.add(album)
        db.commit()
        album_id = album.id
        
        logger.info(f"Created test album with ID {album_id}")
        
        # Create cache files
        cache_dir = Path("static/artwork_cache/medium")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        test_file_1 = cache_dir / f"test_{album_id}_medium.jpg"
        test_file_2 = cache_dir / f"test_{album_id}_thumbnail.jpg"
        
        test_file_1.write_bytes(b"Test image data 1")
        test_file_2.write_bytes(b"Test image data 2")
        
        logger.info(f"Created test cache files: {test_file_1}, {test_file_2}")
        
        # Create cache database records
        cache_record_1 = ArtworkCache(
            album_id=album_id,
            original_url="https://example.com/test.jpg",
            cache_key=f"test-key-{album_id}-medium",
            size_variant="medium",
            file_path=str(test_file_1),
            file_size_bytes=test_file_1.stat().st_size,
            content_type="image/jpeg",
            last_fetched_at=datetime.now(timezone.utc),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=1
        )
        
        cache_record_2 = ArtworkCache(
            album_id=album_id,
            original_url="https://example.com/test.jpg",
            cache_key=f"test-key-{album_id}-thumbnail",
            size_variant="thumbnail",
            file_path=str(test_file_2),
            file_size_bytes=test_file_2.stat().st_size,
            content_type="image/jpeg",
            last_fetched_at=datetime.now(timezone.utc),
            last_accessed_at=datetime.now(timezone.utc),
            access_count=1
        )
        
        db.add(cache_record_1)
        db.add(cache_record_2)
        db.commit()
        
        # Add to memory cache
        memory_cache.set(album_id, "medium", "/static/artwork_cache/medium/test.jpg")
        memory_cache.set(album_id, "thumbnail", "/static/artwork_cache/thumbnail/test.jpg")
        
        # Verify files and records exist
        assert test_file_1.exists(), "Cache file 1 should exist"
        assert test_file_2.exists(), "Cache file 2 should exist"
        
        cache_count = db.query(ArtworkCache).filter_by(album_id=album_id).count()
        assert cache_count == 2, f"Should have 2 cache records, got {cache_count}"
        
        memory_entry = memory_cache.get(album_id, "medium")
        assert memory_entry is not None, "Memory cache should have entry"
        
        logger.info("✓ Setup complete: files, database records, and memory cache entries created")
        
        # Delete the album
        logger.info(f"Deleting album {album_id}...")
        result = rating_service.delete_album(album_id, db)
        
        logger.info(f"Delete result: {result}")
        
        # Close and create new session to ensure we see the changes
        db.close()
        db = SessionLocal()
        
        # Verify album is deleted
        deleted_album = db.query(Album).filter_by(id=album_id).first()
        assert deleted_album is None, "Album should be deleted"
        
        # Verify cache files are deleted
        assert not test_file_1.exists(), "Cache file 1 should be deleted"
        assert not test_file_2.exists(), "Cache file 2 should be deleted"
        
        # Verify cache records are deleted (cascade)
        remaining_cache = db.query(ArtworkCache).filter_by(album_id=album_id).count()
        logger.info(f"Remaining cache records after deletion: {remaining_cache}")
        assert remaining_cache == 0, f"Should have 0 cache records, got {remaining_cache}"
        
        # Verify memory cache is cleared
        memory_entry = memory_cache.get(album_id, "medium")
        assert memory_entry is None, "Memory cache should be cleared"
        
        memory_entry = memory_cache.get(album_id, "thumbnail")
        assert memory_entry is None, "Memory cache thumbnail should be cleared"
        
        # Check the stats returned
        assert result['success'] == True, "Delete should be successful"
        assert result['cache_files_deleted'] >= 2, f"Should delete at least 2 cache files, got {result.get('cache_files_deleted', 0)}"
        
        logger.info("✅ SUCCESS: Album deletion properly cleaned up all cache!")
        logger.info(f"  - Album deleted: ✓")
        logger.info(f"  - Cache files deleted: ✓ ({result.get('cache_files_deleted', 0)} files)")
        logger.info(f"  - Database records cascade deleted: ✓")
        logger.info(f"  - Memory cache cleared: ✓")
        logger.info(f"  - Bytes freed: {result.get('cache_bytes_freed', 0)} bytes")
        
        return True
        
    except AssertionError as e:
        logger.error(f"❌ Test failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return False
    finally:
        # Cleanup any remaining test data
        try:
            # Clean up test files if they still exist
            for file in [test_file_1, test_file_2]:
                if file.exists():
                    file.unlink()
        except:
            pass
        
        db.close()


def main():
    """Main entry point"""
    success = test_album_delete_cache_cleanup()
    
    if success:
        logger.info("\n✅ Album delete cache cleanup is working correctly!")
        sys.exit(0)
    else:
        logger.error("\n❌ Album delete cache cleanup test failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()