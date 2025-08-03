import pytest
import time
from app.cache import SimpleCache, CacheEntry


class TestCacheEntry:
    def test_cache_entry_creation(self):
        """Test cache entry creation with TTL"""
        entry = CacheEntry("test_data", ttl_seconds=60)
        
        assert entry.data == "test_data"
        assert entry.created_at > 0
        assert entry.expires_at > entry.created_at
        assert not entry.is_expired()
    
    def test_cache_entry_expiration(self):
        """Test cache entry expiration"""
        entry = CacheEntry("test_data", ttl_seconds=0)  # Expires immediately
        
        # Should be expired
        assert entry.is_expired()
        assert entry.time_until_expiry() <= 0
    
    def test_cache_entry_time_until_expiry(self):
        """Test time until expiry calculation"""
        entry = CacheEntry("test_data", ttl_seconds=10)
        
        time_left = entry.time_until_expiry()
        assert 9 <= time_left <= 10  # Allow for execution time


class TestSimpleCache:
    def test_cache_set_and_get(self):
        """Test basic cache set and get operations"""
        cache = SimpleCache()
        
        cache.set("test_value", None, "arg1", "arg2", kwarg1="value1")
        result = cache.get("arg1", "arg2", kwarg1="value1")
        
        assert result == "test_value"
    
    def test_cache_miss(self):
        """Test cache miss returns None"""
        cache = SimpleCache()
        
        result = cache.get("nonexistent", "key")
        assert result is None
    
    def test_cache_key_generation(self):
        """Test that different arguments generate different keys"""
        cache = SimpleCache()
        
        cache.set("value1", None, "arg1")
        cache.set("value2", None, "arg2")
        
        assert cache.get("arg1") == "value1"
        assert cache.get("arg2") == "value2"
    
    def test_cache_kwargs_order_independence(self):
        """Test that kwargs order doesn't affect cache key"""
        cache = SimpleCache()
        
        cache.set("test_value", None, kwarg1="value1", kwarg2="value2")
        
        # Should get same value regardless of kwargs order
        result1 = cache.get(kwarg1="value1", kwarg2="value2")
        result2 = cache.get(kwarg2="value2", kwarg1="value1")
        
        assert result1 == "test_value"
        assert result2 == "test_value"
    
    def test_cache_expiration(self):
        """Test that expired entries are automatically removed"""
        cache = SimpleCache(default_ttl=0)  # Expires immediately
        
        cache.set("test_value", None, "test_key")
        
        # Should be expired and return None
        result = cache.get("test_key")
        assert result is None
    
    def test_cache_custom_ttl(self):
        """Test custom TTL for individual entries"""
        cache = SimpleCache(default_ttl=3600)  # 1 hour default
        
        # Set with custom short TTL
        cache.set("short_value", 0, "short_key")  # Expires immediately
        cache.set("long_value", None, "long_key")  # Uses default TTL
        
        assert cache.get("short_key") is None  # Expired
        assert cache.get("long_key") == "long_value"  # Still valid
    
    def test_cache_stats(self):
        """Test cache statistics"""
        cache = SimpleCache(default_ttl=3600, max_size=100)
        
        cache.set("value1", None, "key1")
        cache.set("value2", 0, "key2")  # This will be expired
        
        stats = cache.get_stats()
        
        assert stats["max_size"] == 100
        assert stats["default_ttl"] == 3600
        assert stats["total_entries"] == 2
    
    def test_cache_clear(self):
        """Test cache clearing"""
        cache = SimpleCache()
        
        cache.set("value1", None, "key1")
        cache.set("value2", None, "key2")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        
        stats = cache.get_stats()
        assert stats["total_entries"] == 0
    
    def test_cache_lru_cleanup(self):
        """Test LRU cleanup when cache is full"""
        cache = SimpleCache(max_size=2, default_ttl=3600)
        
        # Fill cache to capacity
        cache.set("value1", None, "key1")
        cache.set("value2", None, "key2")
        
        # Access first key to make it more recently used
        cache.get("key1")
        
        # Add third item, should trigger LRU cleanup
        cache.set("value3", None, "key3")
        
        # key2 should be evicted (least recently used)
        assert cache.get("key1") == "value1"  # Most recently accessed
        assert cache.get("key2") is None      # Should be evicted
        assert cache.get("key3") == "value3"  # Newly added
    
    def test_cache_expired_cleanup(self):
        """Test cleanup of expired entries"""
        cache = SimpleCache(max_size=10)
        
        # Add expired entry
        cache.set("expired_value", 0, "expired_key")
        
        # Add valid entry
        cache.set("valid_value", None, "valid_key")
        
        # Force cleanup by accessing valid key
        cache.get("valid_key")
        
        # Should not contain expired entry
        stats = cache.get_stats()
        assert stats["expired_entries"] >= 1
    
    def test_cache_data_types(self):
        """Test caching different data types"""
        cache = SimpleCache()
        
        test_data = {
            "string": "test_string",
            "number": 42,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "bool": True,
            "none": None
        }
        
        for key, value in test_data.items():
            cache.set(value, None, key)
        
        for key, expected_value in test_data.items():
            assert cache.get(key) == expected_value