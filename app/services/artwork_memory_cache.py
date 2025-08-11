"""
High-performance memory cache for artwork URLs
Provides ultra-fast access to frequently used artwork URLs
"""

import time
import threading
import sys
from typing import Dict, Any, Optional, Tuple
from collections import OrderedDict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class ArtworkMemoryCache:
    """
    Thread-safe in-memory cache optimized for artwork URLs
    Uses LRU eviction and provides detailed monitoring
    """

    def __init__(
        self,
        max_entries: int = 200,
        ttl_seconds: int = 3600,
        enable_stats: bool = True
    ):
        """
        Initialize the artwork memory cache

        Args:
            max_entries: Maximum number of URLs to cache (default 200)
            ttl_seconds: Time-to-live for entries in seconds (default 1 hour)
            enable_stats: Whether to track detailed statistics
        """
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.enable_stats = enable_stats

        # Thread-safe cache storage using OrderedDict for LRU
        self._cache: OrderedDict[str, Tuple[str, float, Dict[str, Any]]] = OrderedDict()
        self._lock = threading.RLock()  # Reentrant lock for thread safety

        # Statistics tracking
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0,
            'total_requests': 0,
            'bytes_cached': 0,
            'startup_time': time.time()
        }

        # Access pattern tracking
        self._access_counts: Dict[str, int] = {}
        self._last_cleanup = time.time()

        logger.info(f"Artwork memory cache initialized (max_entries={max_entries}, ttl={ttl_seconds}s)")

    def _generate_cache_key(self, album_id: int, size: str) -> str:
        """Generate a cache key for album artwork"""
        return f"album_{album_id}_{size}"

    def get(self, album_id: int, size: str) -> Optional[str]:
        """
        Get cached artwork URL

        Args:
            album_id: Album ID
            size: Size variant (thumbnail, small, medium, large, original)

        Returns:
            Cached URL if found and valid, None otherwise
        """
        key = self._generate_cache_key(album_id, size)

        with self._lock:
            self._stats['total_requests'] += 1

            # Check if key exists
            if key not in self._cache:
                self._stats['misses'] += 1
                logger.debug(f"Cache miss: {key}")
                return None

            # Get entry and check expiration
            url, timestamp, metadata = self._cache[key]

            if time.time() - timestamp > self.ttl_seconds:
                # Entry expired
                del self._cache[key]
                self._access_counts.pop(key, None)
                self._stats['expirations'] += 1
                self._stats['misses'] += 1
                logger.debug(f"Cache expired: {key}")
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            # Update statistics
            self._stats['hits'] += 1
            self._access_counts[key] = self._access_counts.get(key, 0) + 1

            logger.debug(f"Cache hit: {key} -> {url[:50]}...")
            return url

    def set(
        self,
        album_id: int,
        size: str,
        url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store artwork URL in cache

        Args:
            album_id: Album ID
            size: Size variant
            url: URL to cache
            metadata: Optional metadata (file size, dimensions, etc.)
        """
        key = self._generate_cache_key(album_id, size)

        with self._lock:
            # Check if we need to evict
            if len(self._cache) >= self.max_entries:
                # Remove least recently used (first item)
                evicted_key = next(iter(self._cache))
                evicted_url, _, _ = self._cache[evicted_key]
                del self._cache[evicted_key]
                self._access_counts.pop(evicted_key, None)
                self._stats['evictions'] += 1
                self._stats['bytes_cached'] -= sys.getsizeof(evicted_url)
                logger.debug(f"Evicted LRU entry: {evicted_key}")

            # Add new entry
            timestamp = time.time()
            self._cache[key] = (url, timestamp, metadata or {})
            self._stats['bytes_cached'] += sys.getsizeof(url)

            logger.debug(f"Cached: {key} -> {url[:50]}...")

            # Periodic cleanup
            if time.time() - self._last_cleanup > 300:  # Every 5 minutes
                self._cleanup_expired()

    def _cleanup_expired(self) -> int:
        """Remove expired entries from cache"""
        with self._lock:
            current_time = time.time()
            expired_keys = []

            for key, (url, timestamp, _) in self._cache.items():
                if current_time - timestamp > self.ttl_seconds:
                    expired_keys.append(key)

            for key in expired_keys:
                url, _, _ = self._cache[key]
                del self._cache[key]
                self._access_counts.pop(key, None)
                self._stats['bytes_cached'] -= sys.getsizeof(url)
                self._stats['expirations'] += 1

            self._last_cleanup = current_time

            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)

    def invalidate(self, album_id: int, size: Optional[str] = None) -> int:
        """
        Invalidate cache entries for an album

        Args:
            album_id: Album ID
            size: Optional specific size to invalidate (None = all sizes)

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            if size:
                # Invalidate specific size
                key = self._generate_cache_key(album_id, size)
                if key in self._cache:
                    url, _, _ = self._cache[key]
                    del self._cache[key]
                    self._access_counts.pop(key, None)
                    self._stats['bytes_cached'] -= sys.getsizeof(url)
                    logger.debug(f"Invalidated: {key}")
                    return 1
                return 0
            else:
                # Invalidate all sizes for album
                sizes = ['thumbnail', 'small', 'medium', 'large', 'original']
                invalidated = 0

                for s in sizes:
                    key = self._generate_cache_key(album_id, s)
                    if key in self._cache:
                        url, _, _ = self._cache[key]
                        del self._cache[key]
                        self._access_counts.pop(key, None)
                        self._stats['bytes_cached'] -= sys.getsizeof(url)
                        invalidated += 1

                if invalidated:
                    logger.debug(f"Invalidated {invalidated} entries for album {album_id}")

                return invalidated

    def clear_album(self, album_id: int) -> int:
        """
        Clear all cache entries for a specific album (alias for invalidate)

        Args:
            album_id: Album ID to clear from cache

        Returns:
            Number of entries removed
        """
        return self.invalidate(album_id)

    def warm_cache(self, entries: list[Tuple[int, str, str]]) -> int:
        """
        Pre-populate cache with frequently accessed URLs

        Args:
            entries: List of (album_id, size, url) tuples

        Returns:
            Number of entries added
        """
        added = 0

        for album_id, size, url in entries:
            if not self.get(album_id, size):  # Only add if not already cached
                self.set(album_id, size, url)
                added += 1

        logger.info(f"Warmed cache with {added} entries")
        return added

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        with self._lock:
            uptime = time.time() - self._stats['startup_time']
            hit_rate = (
                self._stats['hits'] / self._stats['total_requests'] * 100
                if self._stats['total_requests'] > 0
                else 0
            )

            # Get top accessed entries
            top_accessed = sorted(
                self._access_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]

            # Calculate memory usage
            memory_usage = {
                'entries': len(self._cache),
                'bytes_urls': self._stats['bytes_cached'],
                'bytes_overhead': sys.getsizeof(self._cache) + sys.getsizeof(self._access_counts),
                'bytes_total': self._stats['bytes_cached'] + sys.getsizeof(self._cache) + sys.getsizeof(self._access_counts)
            }

            return {
                'performance': {
                    'hits': self._stats['hits'],
                    'misses': self._stats['misses'],
                    'hit_rate': f"{hit_rate:.1f}%",
                    'total_requests': self._stats['total_requests'],
                    'avg_requests_per_minute': self._stats['total_requests'] / (uptime / 60) if uptime > 0 else 0
                },
                'capacity': {
                    'current_entries': len(self._cache),
                    'max_entries': self.max_entries,
                    'utilization': f"{(len(self._cache) / self.max_entries * 100):.1f}%",
                    'evictions': self._stats['evictions'],
                    'expirations': self._stats['expirations']
                },
                'memory': {
                    'bytes_urls': memory_usage['bytes_urls'],
                    'bytes_overhead': memory_usage['bytes_overhead'],
                    'bytes_total': memory_usage['bytes_total'],
                    'mb_total': memory_usage['bytes_total'] / (1024 * 1024)
                },
                'top_accessed': [
                    {'key': key, 'count': count}
                    for key, count in top_accessed
                ],
                'config': {
                    'max_entries': self.max_entries,
                    'ttl_seconds': self.ttl_seconds,
                    'uptime_seconds': uptime
                }
            }

    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_counts.clear()
            self._stats['bytes_cached'] = 0
            logger.info(f"Cleared {count} cache entries")

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get detailed memory usage information"""
        with self._lock:
            return {
                'entries': len(self._cache),
                'bytes': {
                    'urls': self._stats['bytes_cached'],
                    'cache_dict': sys.getsizeof(self._cache),
                    'access_counts': sys.getsizeof(self._access_counts),
                    'total': (
                        self._stats['bytes_cached'] +
                        sys.getsizeof(self._cache) +
                        sys.getsizeof(self._access_counts)
                    )
                },
                'mb': {
                    'urls': self._stats['bytes_cached'] / (1024 * 1024),
                    'total': (
                        self._stats['bytes_cached'] +
                        sys.getsizeof(self._cache) +
                        sys.getsizeof(self._access_counts)
                    ) / (1024 * 1024)
                }
            }


# Global instance
_artwork_memory_cache = None


def get_artwork_memory_cache() -> ArtworkMemoryCache:
    """Get the global artwork memory cache instance"""
    global _artwork_memory_cache
    if _artwork_memory_cache is None:
        _artwork_memory_cache = ArtworkMemoryCache()
    return _artwork_memory_cache
