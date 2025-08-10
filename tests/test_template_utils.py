"""
Tests for template utility functions
Validates artwork URL resolution and caching
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from app.template_utils import (
    ArtworkURLResolver,
    get_artwork_url,
    get_cache_stats,
    format_file_size,
    format_cache_age
)
from app.models import Album, ArtworkCache


class TestArtworkURLResolver:
    """Test suite for ArtworkURLResolver class"""
    
    @pytest.fixture
    def resolver(self):
        """Create an ArtworkURLResolver instance for testing"""
        return ArtworkURLResolver()
    
    @pytest.fixture
    def mock_album(self):
        """Create a mock Album object"""
        album = Mock(spec=Album)
        album.id = 1
        album.cover_art_url = "https://example.com/album.jpg"
        album.artwork_cached = False
        return album
    
    @pytest.fixture
    def album_dict(self):
        """Create an album dictionary as received by templates"""
        return {
            'id': 1,
            'cover_art_url': 'https://example.com/album.jpg',
            'artwork_cached': False,
            'title': 'Test Album'
        }
    
    def test_resolver_initialization(self, resolver):
        """Test resolver initializes with correct defaults"""
        assert resolver.stats['cache_hits'] == 0
        assert resolver.stats['cache_misses'] == 0
        assert resolver.stats['fallback_used'] == 0
        assert resolver.stats['errors'] == 0
        assert len(resolver._template_cache) == 0
    
    def test_get_artwork_url_with_none_album(self, resolver):
        """Test handling of None album"""
        url = resolver.get_artwork_url(None, 'medium')
        assert url == '/static/img/album-placeholder.svg'
        assert resolver.stats['errors'] == 1
    
    def test_get_artwork_url_with_album_dict(self, resolver, album_dict):
        """Test getting artwork URL with album dictionary"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            # Mock database query returning no cache
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            url = resolver.get_artwork_url(album_dict, 'medium')
            
            assert url == 'https://example.com/album.jpg'
            assert resolver.stats['cache_misses'] == 1
    
    def test_get_artwork_url_with_cached_artwork(self, resolver, album_dict):
        """Test getting cached artwork URL"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            # Mock database query returning cached record
            mock_cache = Mock(spec=ArtworkCache)
            mock_cache.file_path = '/static/artwork_cache/medium/abc123.jpg'
            
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = mock_cache
            
            url = resolver.get_artwork_url(album_dict, 'medium')
            
            assert url == '/static/artwork_cache/medium/abc123.jpg'
            assert resolver.stats['cache_hits'] == 1
    
    def test_get_artwork_url_with_album_object(self, resolver, mock_album):
        """Test getting artwork URL with Album model object"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            url = resolver.get_artwork_url(mock_album, 'large')
            
            assert url == 'https://example.com/album.jpg'
            assert resolver.stats['cache_misses'] == 1
    
    def test_template_cache_hit(self, resolver, album_dict):
        """Test template cache reduces database queries"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # First call - should query database
            url1 = resolver.get_artwork_url(album_dict, 'medium')
            assert mock_session.call_count == 1
            
            # Second call - should use template cache
            url2 = resolver.get_artwork_url(album_dict, 'medium')
            assert mock_session.call_count == 1  # No additional DB call
            
            assert url1 == url2
            assert resolver.stats['cache_hits'] == 1
            assert resolver.stats['cache_misses'] == 1
    
    def test_size_variant_mapping(self, resolver, album_dict):
        """Test size variant name mapping"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # Test various size names
            sizes = ['thumb', 'small', 'medium', 'large', 'original', 'thumbnail']
            
            for size in sizes:
                url = resolver.get_artwork_url(album_dict, size)
                assert url is not None
    
    def test_fallback_handling(self, resolver):
        """Test fallback URL handling"""
        album_dict = {'id': 1}  # No cover_art_url
        
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # Clear stats and cache before test
            resolver.clear_stats()
            resolver.clear_template_cache()
            
            # Without custom fallback
            url = resolver.get_artwork_url(album_dict, 'medium')
            assert url == '/static/img/album-placeholder.svg'
            assert resolver.stats['fallback_used'] == 1
            
            # With custom fallback - use different album ID to avoid cache
            album_dict2 = {'id': 2}  # Different ID
            custom_fallback = '/static/custom-placeholder.png'
            url = resolver.get_artwork_url(album_dict2, 'medium', custom_fallback)
            assert url == custom_fallback
            assert resolver.stats['fallback_used'] == 2
    
    def test_get_stats(self, resolver, album_dict):
        """Test statistics gathering"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # Generate some activity
            resolver.get_artwork_url(album_dict, 'medium')
            resolver.get_artwork_url(album_dict, 'medium')  # Cache hit
            resolver.get_artwork_url(None, 'medium')  # Error
            
            stats = resolver.get_stats()
            
            assert stats['cache_hits'] == 1
            assert stats['cache_misses'] == 1
            assert stats['errors'] == 1
            assert stats['total_requests'] == 2
            assert stats['hit_rate'] == 50.0
            assert stats['template_cache_size'] == 1
    
    def test_clear_template_cache(self, resolver, album_dict):
        """Test clearing template cache"""
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # Add to cache
            resolver.get_artwork_url(album_dict, 'medium')
            assert len(resolver._template_cache) == 1
            
            # Clear cache
            resolver.clear_template_cache()
            assert len(resolver._template_cache) == 0


class TestHelperFunctions:
    """Test suite for helper functions"""
    
    def test_format_file_size(self):
        """Test file size formatting"""
        assert format_file_size(0) == "0 B"
        assert format_file_size(512) == "512 B"
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(5242880) == "5.0 MB"
        assert format_file_size(1073741824) == "1.0 GB"
    
    def test_format_cache_age(self):
        """Test cache age formatting"""
        now = datetime.now(timezone.utc)
        
        # Just now
        assert format_cache_age(now) == "Just now"
        
        # Minutes ago
        from datetime import timedelta
        five_min_ago = now - timedelta(minutes=5)
        assert "5 minute" in format_cache_age(five_min_ago)
        
        # Hours ago
        two_hours_ago = now - timedelta(hours=2)
        assert "2 hour" in format_cache_age(two_hours_ago)
        
        # Days ago
        three_days_ago = now - timedelta(days=3)
        assert "3 day" in format_cache_age(three_days_ago)
        
        # Months ago
        sixty_days_ago = now - timedelta(days=60)
        assert "2 month" in format_cache_age(sixty_days_ago)
        
        # None
        assert format_cache_age(None) == "Never"
    
    def test_global_functions(self):
        """Test global template functions"""
        album_dict = {
            'id': 1,
            'cover_art_url': 'https://example.com/album.jpg'
        }
        
        with patch('app.template_utils.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter_by.return_value.first.return_value = None
            
            # Test get_artwork_url
            url = get_artwork_url(album_dict, 'medium')
            assert url == 'https://example.com/album.jpg'
            
            # Test get_cache_stats
            stats = get_cache_stats()
            assert 'cache_hits' in stats
            assert 'cache_misses' in stats