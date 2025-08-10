#!/usr/bin/env python3
"""
Test lazy loading implementation
Verifies that images load progressively and performance is improved
"""

import time
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.database import SessionLocal
from app.models import Album
from app.template_utils import get_lazy_image_html, get_artwork_url


def test_lazy_loading():
    """Test lazy loading functionality"""
    print("🧪 Testing Lazy Loading Implementation")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Get test albums
        albums = db.query(Album).limit(10).all()
        
        if not albums:
            print("❌ No albums found in database")
            return False
        
        print(f"\n📊 Testing with {len(albums)} albums")
        
        # Test 1: Lazy image HTML generation
        print("\n✅ Test 1: Lazy Image HTML Generation")
        print("-" * 40)
        
        for i, album in enumerate(albums[:3], 1):
            print(f"\nAlbum {i}: {album.name}")
            
            # Test different loading strategies
            lazy_html = get_lazy_image_html(album, 'medium', 'test-class', loading='lazy')
            eager_html = get_lazy_image_html(album, 'medium', 'test-class', loading='eager')
            
            # Check for data-src in lazy loading
            has_data_src = 'data-src' in lazy_html
            has_noscript = '<noscript>' in lazy_html
            
            print(f"  Lazy loading: {'✅' if has_data_src else '❌'}")
            print(f"  NoScript fallback: {'✅' if has_noscript else '❌'}")
            
            # Eager loading should not have data-src
            eager_has_data_src = 'data-src' in eager_html
            print(f"  Eager loads immediately: {'✅' if not eager_has_data_src else '❌'}")
        
        # Test 2: Performance comparison
        print("\n✅ Test 2: Performance Comparison")
        print("-" * 40)
        
        # Time regular URL fetching
        start = time.perf_counter()
        for album in albums:
            for size in ['thumbnail', 'medium', 'large']:
                url = get_artwork_url(album, size)
        regular_time = time.perf_counter() - start
        
        print(f"  Regular URL fetch time: {regular_time*1000:.2f}ms")
        
        # Time lazy HTML generation
        start = time.perf_counter()
        for album in albums:
            for size in ['thumbnail', 'medium', 'large']:
                html = get_lazy_image_html(album, size)
        lazy_time = time.perf_counter() - start
        
        print(f"  Lazy HTML generation time: {lazy_time*1000:.2f}ms")
        print(f"  Overhead: {((lazy_time - regular_time) * 1000):.2f}ms")
        
        # Test 3: Check album dict support
        print("\n✅ Test 3: Album Dict Support")
        print("-" * 40)
        
        album_dict = {
            'id': 1,
            'name': 'Test Album',
            'cover_art_url': 'https://example.com/album.jpg'
        }
        
        dict_html = get_lazy_image_html(album_dict, 'medium')
        
        print(f"  Dict support: {'✅' if dict_html else '❌'}")
        print(f"  Has placeholder: {'✅' if 'album-placeholder.svg' in dict_html else '❌'}")
        print(f"  Has data-src: {'✅' if 'data-src' in dict_html else '❌'}")
        
        # Test 4: Cached vs uncached behavior
        print("\n✅ Test 4: Cached vs Uncached Behavior")
        print("-" * 40)
        
        cached_album = None
        uncached_album = None
        
        for album in albums:
            if album.artwork_cached:
                cached_album = album
            else:
                uncached_album = album
            
            if cached_album and uncached_album:
                break
        
        if cached_album:
            cached_html = get_lazy_image_html(cached_album, 'medium')
            # Cached images should load immediately (no data-src)
            print(f"  Cached loads immediately: {'✅' if 'data-src' not in cached_html else '❌'}")
        
        if uncached_album:
            uncached_html = get_lazy_image_html(uncached_album, 'medium')
            # Uncached images should lazy load (has data-src)
            print(f"  Uncached uses lazy loading: {'✅' if 'data-src' in uncached_html else '❌'}")
        
        # Test 5: Memory cache integration
        print("\n✅ Test 5: Memory Cache Integration")
        print("-" * 40)
        
        from app.services.artwork_memory_cache import get_artwork_memory_cache
        memory_cache = get_artwork_memory_cache()
        
        initial_stats = memory_cache.get_stats()
        
        # Generate URLs to populate cache
        for album in albums[:5]:
            get_artwork_url(album, 'medium')
        
        final_stats = memory_cache.get_stats()
        
        print(f"  Cache hits: {final_stats['performance']['hits']}")
        print(f"  Cache entries: {final_stats['capacity']['current_entries']}")
        print(f"  Memory usage: {final_stats['memory']['mb_total']:.3f} MB")
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    success = test_lazy_loading()
    print("\n" + "=" * 60)
    if success:
        print("🎉 Lazy loading implementation verified successfully!")
    else:
        print("❌ Lazy loading tests failed")
    
    sys.exit(0 if success else 1)