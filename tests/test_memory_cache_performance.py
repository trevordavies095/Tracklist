#!/usr/bin/env python3
"""
Performance benchmark for artwork memory cache
Tests cache speed and memory efficiency
"""

import time
import sys
import statistics
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add app to path
sys.path.append(str(Path(__file__).parent))

from app.services.artwork_memory_cache import ArtworkMemoryCache
from app.template_utils import get_artwork_url
from app.database import SessionLocal
from app.models import Album


def benchmark_memory_cache():
    """Run comprehensive performance benchmarks"""
    print("🧪 Artwork Memory Cache Performance Benchmark")
    print("=" * 60)
    
    # Initialize cache
    cache = ArtworkMemoryCache(max_entries=200, ttl_seconds=3600)
    
    # Test data
    test_albums = list(range(1, 201))  # 200 test album IDs
    sizes = ['thumbnail', 'small', 'medium', 'large', 'original']
    
    print("\n📊 Test 1: Sequential Write Performance")
    print("-" * 40)
    
    # Benchmark writes
    write_times = []
    for album_id in test_albums:
        for size in sizes:
            url = f"https://example.com/album/{album_id}/{size}.jpg"
            start = time.perf_counter()
            cache.set(album_id, size, url)
            elapsed = time.perf_counter() - start
            write_times.append(elapsed * 1000)  # Convert to ms
    
    print(f"Total writes: {len(write_times)}")
    print(f"Avg write time: {statistics.mean(write_times):.3f} ms")
    print(f"Min write time: {min(write_times):.3f} ms")
    print(f"Max write time: {max(write_times):.3f} ms")
    print(f"Median write time: {statistics.median(write_times):.3f} ms")
    
    # Check memory usage after writes
    memory_stats = cache.get_memory_usage()
    print(f"\nMemory after writes:")
    print(f"  Entries: {memory_stats['entries']}")
    print(f"  Total MB: {memory_stats['mb']['total']:.2f}")
    
    print("\n📊 Test 2: Sequential Read Performance")
    print("-" * 40)
    
    # Benchmark reads - first pass (all hits)
    read_times = []
    hits = 0
    
    for _ in range(3):  # Multiple passes
        for album_id in test_albums[:40]:  # Test subset
            for size in sizes:
                start = time.perf_counter()
                result = cache.get(album_id, size)
                elapsed = time.perf_counter() - start
                read_times.append(elapsed * 1000)  # Convert to ms
                if result:
                    hits += 1
    
    print(f"Total reads: {len(read_times)}")
    print(f"Cache hits: {hits}/{len(read_times)}")
    print(f"Avg read time: {statistics.mean(read_times):.3f} ms")
    print(f"Min read time: {min(read_times):.3f} ms")
    print(f"Max read time: {max(read_times):.3f} ms")
    print(f"Median read time: {statistics.median(read_times):.3f} ms")
    
    print("\n📊 Test 3: Concurrent Access Performance")
    print("-" * 40)
    
    # Reset cache for concurrent test
    cache.clear()
    
    # Pre-populate with some data
    for album_id in range(1, 51):
        for size in sizes:
            cache.set(album_id, size, f"https://example.com/{album_id}/{size}.jpg")
    
    def concurrent_access(thread_id):
        """Simulate concurrent cache access"""
        times = []
        for i in range(100):
            album_id = (thread_id * 10 + i) % 50 + 1
            size = sizes[i % len(sizes)]
            
            start = time.perf_counter()
            # Mix reads and writes
            if i % 3 == 0:
                cache.set(album_id, size, f"https://example.com/new/{album_id}/{size}.jpg")
            else:
                cache.get(album_id, size)
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)
        
        return times
    
    # Run concurrent test
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(concurrent_access, i) for i in range(10)]
        
        all_times = []
        for future in as_completed(futures):
            all_times.extend(future.result())
    
    print(f"Total operations: {len(all_times)}")
    print(f"Avg operation time: {statistics.mean(all_times):.3f} ms")
    print(f"Min operation time: {min(all_times):.3f} ms")
    print(f"Max operation time: {max(all_times):.3f} ms")
    print(f"95th percentile: {statistics.quantiles(all_times, n=20)[18]:.3f} ms")
    
    print("\n📊 Test 4: Cache Eviction Performance")
    print("-" * 40)
    
    # Test LRU eviction
    cache.clear()
    eviction_times = []
    
    # Fill cache beyond capacity
    for album_id in range(1, 301):  # 300 albums (exceeds 200 limit)
        for size in ['thumbnail', 'medium']:  # Just 2 sizes
            start = time.perf_counter()
            cache.set(album_id, size, f"https://example.com/{album_id}/{size}.jpg")
            elapsed = time.perf_counter() - start
            eviction_times.append(elapsed * 1000)
    
    print(f"Operations with eviction: {len(eviction_times)}")
    print(f"Avg time with eviction: {statistics.mean(eviction_times):.3f} ms")
    print(f"Max time (worst eviction): {max(eviction_times):.3f} ms")
    
    # Check final state
    final_stats = cache.get_stats()
    print(f"\nFinal cache state:")
    print(f"  Entries: {final_stats['capacity']['current_entries']}")
    print(f"  Evictions: {final_stats['capacity']['evictions']}")
    print(f"  Memory MB: {final_stats['memory']['mb_total']:.2f}")
    
    print("\n📊 Test 5: Real-World Simulation")
    print("-" * 40)
    
    # Simulate realistic access patterns
    cache.clear()
    db = SessionLocal()
    
    try:
        # Get real albums
        real_albums = db.query(Album).limit(20).all()
        
        if real_albums:
            # Simulate template function calls
            template_times = []
            
            for _ in range(5):  # Multiple page loads
                for album in real_albums:
                    for size in ['thumbnail', 'medium']:
                        start = time.perf_counter()
                        url = get_artwork_url(album, size)
                        elapsed = time.perf_counter() - start
                        template_times.append(elapsed * 1000)
            
            print(f"Template function calls: {len(template_times)}")
            print(f"Avg template call time: {statistics.mean(template_times):.3f} ms")
            print(f"Min template call time: {min(template_times):.3f} ms")
            print(f"Max template call time: {max(template_times):.3f} ms")
            
            # Get memory cache stats
            from app.services.artwork_memory_cache import get_artwork_memory_cache
            memory_cache = get_artwork_memory_cache()
            cache_stats = memory_cache.get_stats()
            
            print(f"\nMemory cache performance:")
            print(f"  Hit rate: {cache_stats['performance']['hit_rate']}")
            print(f"  Total requests: {cache_stats['performance']['total_requests']}")
            print(f"  Memory usage: {cache_stats['memory']['mb_total']:.2f} MB")
            
    finally:
        db.close()
    
    print("\n✅ Benchmark Complete!")
    print("=" * 60)
    
    # Summary
    print("\n📈 Performance Summary:")
    print(f"  • Write performance: {statistics.mean(write_times):.3f} ms avg")
    print(f"  • Read performance: {statistics.mean(read_times):.3f} ms avg")
    print(f"  • Concurrent ops: {statistics.mean(all_times):.3f} ms avg")
    print(f"  • Memory efficiency: {memory_stats['mb']['total']:.2f} MB for {memory_stats['entries']} entries")
    print(f"  • Cache capacity: {final_stats['capacity']['utilization']}")
    
    return True


if __name__ == "__main__":
    success = benchmark_memory_cache()
    sys.exit(0 if success else 1)