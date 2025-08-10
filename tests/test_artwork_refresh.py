"""
Tests for artwork refresh functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_rate_limiter import UserRateLimiter, ArtworkRefreshLimiter


class TestUserRateLimiter:
    """Test user rate limiter functionality"""
    
    def test_rate_limiter_allows_requests_within_limit(self):
        """Test that rate limiter allows requests within the limit"""
        limiter = UserRateLimiter(max_requests=3, window_seconds=60)
        
        # First 3 requests should be allowed
        for i in range(3):
            allowed, info = limiter.check_rate_limit("user1")
            assert allowed is True
            assert info["requests_remaining"] == 3 - i
            limiter.record_request("user1")
    
    def test_rate_limiter_blocks_excess_requests(self):
        """Test that rate limiter blocks requests over the limit"""
        limiter = UserRateLimiter(max_requests=2, window_seconds=60)
        
        # Record 2 requests
        limiter.record_request("user1")
        limiter.record_request("user1")
        
        # Third request should be blocked
        allowed, info = limiter.check_rate_limit("user1")
        assert allowed is False
        assert info["requests_made"] == 2
        assert "reset_in_seconds" in info
    
    def test_rate_limiter_tracks_users_separately(self):
        """Test that rate limiter tracks different users separately"""
        limiter = UserRateLimiter(max_requests=1, window_seconds=60)
        
        # User 1 makes a request
        limiter.record_request("user1")
        
        # User 1 should be blocked
        allowed1, _ = limiter.check_rate_limit("user1")
        assert allowed1 is False
        
        # User 2 should still be allowed
        allowed2, _ = limiter.check_rate_limit("user2")
        assert allowed2 is True
    
    def test_rate_limiter_reset_user(self):
        """Test resetting rate limit for a user"""
        limiter = UserRateLimiter(max_requests=1, window_seconds=60)
        
        # User makes a request
        limiter.record_request("user1")
        
        # Should be blocked
        allowed, _ = limiter.check_rate_limit("user1")
        assert allowed is False
        
        # Reset the user
        limiter.reset_user("user1")
        
        # Should be allowed again
        allowed, _ = limiter.check_rate_limit("user1")
        assert allowed is True


class TestArtworkRefreshLimiter:
    """Test artwork refresh rate limiter"""
    
    def test_artwork_refresh_limiter_hourly_limit(self):
        """Test artwork refresh hourly limit"""
        limiter = ArtworkRefreshLimiter()
        
        # Should allow up to 5 refreshes per hour
        for i in range(5):
            allowed, info = limiter.check_limit("session1")
            assert allowed is True
            limiter.record_refresh("session1")
        
        # 6th request should be blocked
        allowed, info = limiter.check_limit("session1")
        assert allowed is False
        assert info["limit_type"] == "hourly"
        assert "Hourly refresh limit exceeded" in info["message"]
    
    def test_artwork_refresh_limiter_daily_limit(self):
        """Test artwork refresh daily limit"""
        limiter = ArtworkRefreshLimiter()
        
        # Simulate reaching daily limit (20 refreshes)
        for i in range(20):
            allowed, info = limiter.check_limit("session2")
            if allowed:
                limiter.record_refresh("session2")
        
        # Next request should be blocked by daily limit
        allowed, info = limiter.check_limit("session2")
        assert allowed is False
    
    def test_artwork_refresh_limiter_stats(self):
        """Test getting rate limiter statistics"""
        limiter = ArtworkRefreshLimiter()
        
        # Record some refreshes
        limiter.record_refresh("session1")
        limiter.record_refresh("session2")
        
        stats = limiter.get_stats()
        
        assert "hourly" in stats
        assert "daily" in stats
        assert stats["hourly"]["active_users"] == 2
        assert stats["daily"]["active_users"] == 2


class TestArtworkRefreshEndpoint:
    """Test the artwork refresh API endpoint"""
    
    @pytest.mark.asyncio
    async def test_refresh_artwork_success(self):
        """Test successful artwork refresh"""
        from app.routers.albums import refresh_album_artwork
        
        # Mock dependencies
        mock_request = Mock()
        mock_request.headers = {"X-Session-Id": "test-session"}
        mock_request.client.host = "127.0.0.1"
        
        mock_db = Mock(spec=Session)
        mock_album = Mock()
        mock_album.id = 1
        mock_album.name = "Test Album"
        mock_album.cover_art_url = "http://example.com/artwork.jpg"
        mock_album.artwork_cached = True
        
        mock_db.query().filter().first.return_value = mock_album
        
        with patch('app.services.user_rate_limiter.get_artwork_refresh_limiter') as mock_get_limiter, \
             patch('app.services.artwork_cache_service.ArtworkCacheService') as mock_cache_service, \
             patch('app.services.artwork_memory_cache.get_artwork_memory_cache') as mock_memory_cache, \
             patch('app.services.artwork_cache_background.get_artwork_cache_background_service') as mock_bg_service:
            
            # Setup mocks
            mock_limiter = Mock()
            mock_limiter.check_limit.return_value = (True, {"allowed": True})
            mock_get_limiter.return_value = mock_limiter
            
            mock_cache = Mock()
            mock_cache.clear_album_cache_sync.return_value = {"files_deleted": 3}
            mock_cache_service.return_value = mock_cache
            
            mock_mem = Mock()
            mock_memory_cache.return_value = mock_mem
            
            mock_bg = Mock()
            mock_bg.trigger_album_cache.return_value = "task-123"
            mock_bg_service.return_value = mock_bg
            
            # Call the endpoint
            result = await refresh_album_artwork(
                request=mock_request,
                album_id=1,
                db=mock_db
            )
            
            # Verify result
            assert result["success"] is True
            assert result["album_id"] == 1
            assert result["task_id"] == "task-123"
            assert "Artwork refresh initiated" in result["message"]
            
            # Verify calls
            mock_limiter.check_limit.assert_called_once_with("test-session")
            mock_limiter.record_refresh.assert_called_once_with("test-session")
            mock_cache.clear_album_cache_sync.assert_called_once_with(1, mock_db)
            mock_mem.clear_album.assert_called_once_with(1)
            mock_bg.trigger_album_cache.assert_called_once_with(
                album_id=1,
                cover_art_url="http://example.com/artwork.jpg",
                priority=2
            )
    
    @pytest.mark.asyncio
    async def test_refresh_artwork_rate_limited(self):
        """Test artwork refresh when rate limited"""
        from app.routers.albums import refresh_album_artwork
        
        # Mock dependencies
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        mock_db = Mock(spec=Session)
        
        with patch('app.services.user_rate_limiter.get_artwork_refresh_limiter') as mock_get_limiter:
            # Setup rate limiter to deny request
            mock_limiter = Mock()
            mock_limiter.check_limit.return_value = (False, {
                "message": "Hourly refresh limit exceeded",
                "reset_in_seconds": 1800
            })
            mock_get_limiter.return_value = mock_limiter
            
            # Call should raise HTTPException with 429 status
            with pytest.raises(HTTPException) as exc_info:
                await refresh_album_artwork(
                    request=mock_request,
                    album_id=1,
                    db=mock_db
                )
            
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in exc_info.value.detail["error"]
    
    @pytest.mark.asyncio
    async def test_refresh_artwork_album_not_found(self):
        """Test artwork refresh when album doesn't exist"""
        from app.routers.albums import refresh_album_artwork
        
        # Mock dependencies
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        mock_db = Mock(spec=Session)
        mock_db.query().filter().first.return_value = None
        
        with patch('app.services.user_rate_limiter.get_artwork_refresh_limiter') as mock_get_limiter:
            # Setup rate limiter to allow request
            mock_limiter = Mock()
            mock_limiter.check_limit.return_value = (True, {"allowed": True})
            mock_get_limiter.return_value = mock_limiter
            
            # Call should raise HTTPException with 404 status
            with pytest.raises(HTTPException) as exc_info:
                await refresh_album_artwork(
                    request=mock_request,
                    album_id=999,
                    db=mock_db
                )
            
            assert exc_info.value.status_code == 404
            assert "Album not found" in exc_info.value.detail["error"]
    
    @pytest.mark.asyncio
    async def test_refresh_artwork_no_cover_url(self):
        """Test artwork refresh when album has no cover art URL"""
        from app.routers.albums import refresh_album_artwork
        
        # Mock dependencies
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"
        
        mock_db = Mock(spec=Session)
        mock_album = Mock()
        mock_album.id = 1
        mock_album.name = "Test Album"
        mock_album.cover_art_url = None  # No cover URL
        
        mock_db.query().filter().first.return_value = mock_album
        
        with patch('app.services.user_rate_limiter.get_artwork_refresh_limiter') as mock_get_limiter:
            # Setup rate limiter to allow request
            mock_limiter = Mock()
            mock_limiter.check_limit.return_value = (True, {"allowed": True})
            mock_get_limiter.return_value = mock_limiter
            
            # Call should raise HTTPException with 400 status
            with pytest.raises(HTTPException) as exc_info:
                await refresh_album_artwork(
                    request=mock_request,
                    album_id=1,
                    db=mock_db
                )
            
            assert exc_info.value.status_code == 400
            assert "No artwork available" in exc_info.value.detail["error"]