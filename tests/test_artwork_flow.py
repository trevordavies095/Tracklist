#!/usr/bin/env python3
"""
End-to-end test for artwork caching flow
Tests the complete flow from downloading to serving cached images
"""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.database import SessionLocal
from app.models import Album
from app.services.artwork_cache_service import ArtworkCacheService
from app.template_utils import get_artwork_url

async def test_artwork_flow():
    """Test the complete artwork caching flow"""
    print("🧪 Testing Artwork Caching Flow")
    print("-" * 50)
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Get a test album with artwork
        album = db.query(Album).filter(
            Album.cover_art_url.isnot(None)
        ).first()
        
        if not album:
            print("❌ No albums with artwork found in database")
            return False
        
        print(f"✅ Found album: {album.name} (ID: {album.id})")
        print(f"   Cover URL: {album.cover_art_url}")
        
        # Initialize cache service
        cache_service = ArtworkCacheService()
        
        # Test caching
        print("\n📥 Testing artwork caching...")
        success = await cache_service.cache_artwork(album, album.cover_art_url, db)
        
        if success:
            print("✅ Artwork cached successfully")
        else:
            print("❌ Failed to cache artwork")
            return False
        
        # Test template function
        print("\n🔗 Testing template URL resolution...")
        
        # Test different sizes
        sizes = ['thumbnail', 'small', 'medium', 'large', 'original']
        for size in sizes:
            url = get_artwork_url(album, size)
            print(f"   {size}: {url}")
            
            # Check if it's a cached URL (local path)
            if url and not url.startswith('http'):
                print(f"   ✅ Using cached version for {size}")
            else:
                print(f"   ⚠️  Using external URL for {size}")
        
        # Get cache stats
        from app.template_utils import get_cache_stats
        stats = get_cache_stats()
        
        print("\n📊 Cache Statistics:")
        print(f"   Cache hits: {stats['cache_hits']}")
        print(f"   Cache misses: {stats['cache_misses']}")
        print(f"   Hit rate: {stats['hit_rate']:.1%}")
        print(f"   Errors: {stats['errors']}")
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        db.close()

if __name__ == "__main__":
    # Run the async test
    success = asyncio.run(test_artwork_flow())
    sys.exit(0 if success else 1)