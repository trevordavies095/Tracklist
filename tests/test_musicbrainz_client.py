import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
import httpx

from app.musicbrainz_client import (
    MusicBrainzRateLimiter, 
    MusicBrainzClient, 
    MusicBrainzAPIError
)


class TestMusicBrainzRateLimiter:
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiter enforces 1 call per second"""
        limiter = MusicBrainzRateLimiter(calls_per_second=2.0)  # 2 calls per second for faster testing
        
        start_time = time.time()
        
        # First call should be immediate
        await limiter.acquire()
        first_call_time = time.time()
        
        # Second call should be delayed
        await limiter.acquire()
        second_call_time = time.time()
        
        # Should be at least 0.5 seconds between calls (1/2 calls per second)
        time_diff = second_call_time - first_call_time
        assert time_diff >= 0.4  # Allow some tolerance for timing
    
    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting(self):
        """Test rate limiting with concurrent requests"""
        limiter = MusicBrainzRateLimiter(calls_per_second=1.0)
        
        start_time = time.time()
        
        # Make 3 concurrent requests
        await asyncio.gather(
            limiter.acquire(),
            limiter.acquire(),
            limiter.acquire()
        )
        
        end_time = time.time()
        
        # Should take at least 2 seconds for 3 calls at 1 call/second
        assert end_time - start_time >= 2.0


class TestMusicBrainzClient:
    @pytest.mark.asyncio
    async def test_search_releases_success(self):
        """Test successful album search"""
        mock_response = {
            "releases": [
                {
                    "id": "test-release-id",
                    "title": "Test Album",
                    "artist-credit": [{"name": "Test Artist"}],
                    "date": "2023-01-01",
                    "country": "US"
                }
            ],
            "count": 1,
            "offset": 0
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = AsyncMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response_obj
            
            async with MusicBrainzClient() as client:
                result = await client.search_releases("test query")
                
                assert result == mock_response
                mock_client.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_releases_http_error(self):
        """Test album search with HTTP error"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = AsyncMock()
            mock_response_obj.status_code = 404
            mock_response_obj.text = "Not found"
            mock_client.get.return_value = mock_response_obj
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=AsyncMock(), response=mock_response_obj
            )
            
            async with MusicBrainzClient() as client:
                with pytest.raises(MusicBrainzAPIError) as exc_info:
                    await client.search_releases("test query")
                
                assert "HTTP error" in exc_info.value.message
                assert exc_info.value.details["status_code"] == 404
    
    @pytest.mark.asyncio
    async def test_search_releases_request_error(self):
        """Test album search with request error"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_client.get.side_effect = httpx.RequestError("Connection failed")
            
            async with MusicBrainzClient() as client:
                with pytest.raises(MusicBrainzAPIError) as exc_info:
                    await client.search_releases("test query")
                
                assert "request failed" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_get_release_details_success(self):
        """Test successful release details fetch"""
        mock_response = {
            "id": "test-release-id",
            "title": "Test Album",
            "artist-credit": [{"name": "Test Artist"}],
            "media": [
                {
                    "tracks": [
                        {"title": "Track 1", "length": "180000"},
                        {"title": "Track 2", "length": "200000"}
                    ]
                }
            ]
        }
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = AsyncMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response_obj
            
            async with MusicBrainzClient() as client:
                result = await client.get_release_with_tracks("test-release-id")
                
                assert result == mock_response
                mock_client.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_releases_limit_validation(self):
        """Test that search limit is capped at 100"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response_obj = AsyncMock()
            mock_response_obj.json.return_value = {"releases": [], "count": 0}
            mock_response_obj.raise_for_status.return_value = None
            mock_client.get.return_value = mock_response_obj
            
            async with MusicBrainzClient() as client:
                await client.search_releases("test", limit=150)
                
                # Check that limit was capped at 100
                call_args = mock_client.get.call_args
                params = call_args[1]['params']  # kwargs params
                assert params['limit'] == 100
    
    def test_client_without_context_manager(self):
        """Test that client raises error when used without context manager"""
        client = MusicBrainzClient()
        
        with pytest.raises(MusicBrainzAPIError) as exc_info:
            asyncio.run(client._make_request("test", {}))
        
        assert "not initialized" in exc_info.value.message