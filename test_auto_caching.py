#!/usr/bin/env python3
"""
Test automatic artwork caching on album creation
"""

import asyncio
import sys
import time
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.database import SessionLocal
from app.models import Album
from app.rating_service import RatingService
from app.services.artwork_cache_background import get_artwork_cache_background_service


async def test_auto_caching():
    """Test automatic artwork caching when creating albums"""
    print("🧪 Testing Automatic Artwork Caching")
    print("-" * 50)
    
    # Initialize services
    rating_service = RatingService()
    cache_bg_service = get_artwork_cache_background_service()
    
    # Start background tasks
    from app.services.background_tasks import start_background_tasks
    await start_background_tasks()
    print("✅ Background task manager started")
    
    # Test albums with different sources
    test_albums = [
        {
            "mbid": "1dc4c347-a1db-32aa-b14f-bc9cc507b843",  # Radiohead - The Bends
            "name": "The Bends"
        },
        {
            "mbid": "b1392450-e666-3926-a536-22c65f834433",  # Nirvana - Nevermind
            "name": "Nevermind"
        }
    ]
    
    created_albums = []
    
    for test_album in test_albums:
        print(f"\n📀 Creating album: {test_album['name']}")
        db = SessionLocal()
        
        try:
            # Check if album already exists
            existing = db.query(Album).filter(
                Album.musicbrainz_id == test_album['mbid']
            ).first()
            
            if existing:
                print(f"   ⚠️ Album already exists (ID: {existing.id})")
                created_albums.append(existing.id)
            else:
                # Create album through rating service
                result = await rating_service.create_album_for_rating(
                    test_album['mbid'], 
                    db
                )
                
                album_id = result['id']
                created_albums.append(album_id)
                print(f"   ✅ Album created (ID: {album_id})")
                print(f"   📷 Cover art: {result.get('cover_art_url', 'None')}")
                
                # Check if caching was triggered
                cache_status = cache_bg_service.get_cache_status(album_id)
                if cache_status:
                    print(f"   🔄 Caching status: {cache_status.get('status', 'unknown')}")
                else:
                    print(f"   ❌ No caching task found")
            
        except Exception as e:
            print(f"   ❌ Error creating album: {e}")
        finally:
            db.close()
    
    # Wait for background tasks to process
    print("\n⏳ Waiting for background caching to complete...")
    await asyncio.sleep(5)
    
    # Check caching results
    print("\n📊 Checking Caching Results:")
    print("-" * 30)
    
    db = SessionLocal()
    try:
        for album_id in created_albums:
            album = db.query(Album).filter(Album.id == album_id).first()
            if album:
                cache_status = cache_bg_service.get_cache_status(album_id)
                print(f"\n📀 {album.name} (ID: {album_id})")
                print(f"   Cached: {'✅ Yes' if album.artwork_cached else '❌ No'}")
                
                if cache_status:
                    print(f"   Task Status: {cache_status.get('status', 'unknown')}")
                    if cache_status.get('status') == 'completed':
                        result = cache_status.get('result', {})
                        print(f"   Success: {'✅' if result.get('success') else '❌'}")
                    elif cache_status.get('status') == 'failed':
                        print(f"   Error: {cache_status.get('error', 'Unknown')}")
                
                # Check if files exist
                from app.services.artwork_cache_utils import get_cache_filesystem
                cache_fs = get_cache_filesystem()
                
                sizes = ['thumbnail', 'small', 'medium', 'large', 'original']
                files_found = 0
                for size in sizes:
                    cache_key = cache_fs.generate_cache_key(album.cover_art_url) if album.cover_art_url else None
                    if cache_key:
                        file_path = cache_fs.get_cache_path(cache_key, size, 'jpg')
                        if file_path.exists():
                            files_found += 1
                
                print(f"   Files: {files_found}/{len(sizes)} variants found")
                
    finally:
        db.close()
    
    # Get overall status
    print("\n📈 Overall Background Task Status:")
    print("-" * 30)
    overall_status = cache_bg_service.get_overall_status()
    
    print(f"Cache Status:")
    for status, count in overall_status['cache_status_counts'].items():
        print(f"   {status}: {count}")
    
    bg_status = overall_status['background_tasks']
    print(f"\nBackground Tasks:")
    print(f"   Queued: {bg_status['queued']}")
    print(f"   Running: {bg_status['running']}")
    print(f"   Completed: {bg_status['completed']}")
    print(f"   Failed: {bg_status['failed']}")
    
    # Stop background tasks
    from app.services.background_tasks import stop_background_tasks
    await stop_background_tasks()
    print("\n✅ Background task manager stopped")
    
    print("\n✅ Test completed!")
    return True


if __name__ == "__main__":
    # Run the async test
    success = asyncio.run(test_auto_caching())
    sys.exit(0 if success else 1)