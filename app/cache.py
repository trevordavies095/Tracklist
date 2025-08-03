"""
Simple in-memory cache for MusicBrainz API responses
Reduces API calls and improves performance
"""

import time
import json
import hashlib
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheEntry:
    """Represents a cached item with expiration"""
    
    def __init__(self, data: Any, ttl_seconds: int = 3600):
        self.data = data
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired"""
        return time.time() > self.expires_at
    
    def time_until_expiry(self) -> float:
        """Get seconds until expiry (negative if expired)"""
        return self.expires_at - time.time()


class SimpleCache:
    """
    Simple in-memory cache with TTL support
    Thread-safe for single-process applications
    """
    
    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        """
        Initialize cache
        
        Args:
            default_ttl: Default time-to-live in seconds (1 hour)
            max_size: Maximum number of entries before cleanup
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._access_times: Dict[str, float] = {}
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments"""
        # Create a deterministic string from args and kwargs
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items() 
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._cache[key]
            self._access_times.pop(key, None)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _cleanup_lru(self):
        """Remove least recently used entries if cache is too large"""
        if len(self._cache) <= self.max_size:
            return
        
        # Sort by access time and remove oldest entries
        sorted_keys = sorted(
            self._access_times.items(), 
            key=lambda x: x[1]
        )
        
        entries_to_remove = len(self._cache) - self.max_size
        for key, _ in sorted_keys[:entries_to_remove]:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)
        
        logger.debug(f"Cleaned up {entries_to_remove} LRU cache entries")
    
    def get(self, *args, **kwargs) -> Optional[Any]:
        """
        Get item from cache
        
        Returns:
            Cached data if found and not expired, None otherwise
        """
        key = self._generate_key(*args, **kwargs)
        
        entry = self._cache.get(key)
        if entry is None:
            logger.debug(f"Cache miss for key: {key[:12]}...")
            return None
        
        if entry.is_expired():
            logger.debug(f"Cache expired for key: {key[:12]}...")
            del self._cache[key]
            self._access_times.pop(key, None)
            return None
        
        # Update access time
        self._access_times[key] = time.time()
        logger.debug(f"Cache hit for key: {key[:12]}... (expires in {entry.time_until_expiry():.0f}s)")
        return entry.data
    
    def set(self, data: Any, ttl: Optional[int] = None, *args, **kwargs):
        """
        Store item in cache
        
        Args:
            data: Data to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        key = self._generate_key(*args, **kwargs)
        ttl = ttl or self.default_ttl
        
        self._cache[key] = CacheEntry(data, ttl)
        self._access_times[key] = time.time()
        
        logger.debug(f"Cached item with key: {key[:12]}... (TTL: {ttl}s)")
        
        # Periodic cleanup
        if len(self._cache) > self.max_size * 1.1:  # 10% buffer
            self._cleanup_expired()
            self._cleanup_lru()
    
    def clear(self):
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        self._access_times.clear()
        logger.info(f"Cleared {count} cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        current_time = time.time()
        expired_count = sum(
            1 for entry in self._cache.values() 
            if entry.is_expired()
        )
        
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "max_size": self.max_size,
            "default_ttl": self.default_ttl
        }


# Global cache instance
_musicbrainz_cache = SimpleCache(
    default_ttl=3600,  # 1 hour TTL for MusicBrainz data
    max_size=500       # Keep up to 500 cached responses
)


def get_cache() -> SimpleCache:
    """Get the global cache instance"""
    return _musicbrainz_cache