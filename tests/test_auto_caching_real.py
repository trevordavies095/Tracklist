#!/usr/bin/env python3
"""
Test automatic artwork caching with real albums
"""

import asyncio
import sys
import time
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.database import SessionLocal
from app.models import Album
from app.services.artwork_cache_background import get_artwork_cache_background_service


async def test_auto_caching_existing():
    """Test automatic artwork caching for existing albums"""
    print("🧪 Testing Automatic Artwork Caching for Existing Albums")
    print("-" * 50)
    
    # Initialize services
    cache_bg_service = get_artwork_cache_background_service()
    
    # Start background tasks
    from app.services.background_tasks import start_background_tasks
    await start_background_tasks()
    print("✅ Background task manager started")
    
    db = SessionLocal()
    
    try:
        # Find albums without cached artwork
        uncached_albums = db.query(Album).filter(
            Album.artwork_cached != True,
            Album.cover_art_url.isnot(None)
        ).limit(2).all()
        
        if not uncached_albums:
            print("❌ No uncached albums found with cover art URLs")
            return False
        
        print(f"\n📊 Found {len(uncached_albums)} uncached albums to test with:")
        
        # Trigger caching for each album
        task_ids = []
        for album in uncached_albums:
            print(f"\n📀 Album: {album.name} (ID: {album.id})")
            print(f"   Cover URL: {album.cover_art_url[:50]}...")
            
            # Trigger background caching
            task_id = cache_bg_service.trigger_album_cache(
                album_id=album.id,
                cover_art_url=album.cover_art_url,
                priority=1  # High priority for testing
            )
            
            task_ids.append((album.id, task_id))
            print(f"   ✅ Caching triggered (Task: {task_id})")
            
            # Check initial status
            cache_status = cache_bg_service.get_cache_status(album.id)
            if cache_status:
                print(f"   📍 Initial status: {cache_status.get('status', 'unknown')}")
        
    finally:
        db.close()
    
    # Wait for processing
    print("\n⏳ Waiting for background caching to complete...")
    await asyncio.sleep(10)  # Give more time for downloading
    
    # Check results
    print("\n📊 Checking Caching Results:")
    print("-" * 30)
    
    db = SessionLocal()
    try:
        for album_id, task_id in task_ids:
            album = db.query(Album).filter(Album.id == album_id).first()
            if album:
                # Refresh from DB to get updated status
                db.refresh(album)
                
                cache_status = cache_bg_service.get_cache_status(album_id)
                print(f"\n📀 {album.name} (ID: {album_id})")
                print(f"   Task ID: {task_id}")
                print(f"   DB Cached Flag: {'✅ Yes' if album.artwork_cached else '❌ No'}")
                
                if cache_status:
                    print(f"   Task Status: {cache_status.get('status', 'unknown')}")
                    if cache_status.get('status') == 'completed':
                        result = cache_status.get('result', {})
                        print(f"   Success: {'✅' if result.get('success') else '❌'}")
                        if not result.get('success'):
                            print(f"   Reason: {result.get('reason', 'unknown')}")
                    elif cache_status.get('status') == 'failed':
                        print(f"   Error: {cache_status.get('error', 'Unknown')}")
                
                # Check if files actually exist
                from app.services.artwork_cache_utils import get_cache_filesystem
                cache_fs = get_cache_filesystem()
                
                if album.cover_art_url:
                    cache_key = cache_fs.generate_cache_key(album.cover_art_url)
                    sizes = ['thumbnail', 'small', 'medium', 'large', 'original']
                    files_found = []
                    
                    for size in sizes:
                        file_path = cache_fs.get_cache_path(cache_key, size, 'jpg')
                        if file_path.exists():
                            files_found.append(size)
                    
                    print(f"   Files Found: {len(files_found)}/{len(sizes)} variants")
                    if files_found:
                        print(f"   Variants: {', '.join(files_found)}")
                
    finally:
        db.close()
    
    # Get overall status
    print("\n📈 Overall Background Task Status:")
    print("-" * 30)
    overall_status = cache_bg_service.get_overall_status()
    
    print(f"Cache Status:")
    for status, count in overall_status['cache_status_counts'].items():
        if count > 0:
            print(f"   {status}: {count}")
    
    bg_status = overall_status['background_tasks']
    print(f"\nBackground Tasks:")
    print(f"   Queued: {bg_status['queued']}")
    print(f"   Running: {bg_status['running']}")
    print(f"   Completed: {bg_status['completed']}")
    print(f"   Failed: {bg_status['failed']}")
    
    if bg_status['running'] > 0:
        print(f"\nRunning Tasks:")
        for task in bg_status['running_tasks']:
            print(f"   - {task['name']} (ID: {task['id']})")
    
    # Stop background tasks
    from app.services.background_tasks import stop_background_tasks
    await stop_background_tasks()
    print("\n✅ Background task manager stopped")
    
    print("\n✅ Test completed!")
    return True


if __name__ == "__main__":
    # Run the async test
    success = asyncio.run(test_auto_caching_existing())
    sys.exit(0 if success else 1)