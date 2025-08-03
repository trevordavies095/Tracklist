import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.musicbrainz_service import MusicBrainzService
from app.exceptions import TracklistException


class TestMusicBrainzService:
    def setup_method(self):
        """Set up test fixtures"""
        self.service = MusicBrainzService()
        
        # Mock cache to avoid interference between tests
        self.mock_cache = MagicMock()
        self.service.cache = self.mock_cache
    
    @pytest.mark.asyncio
    async def test_search_albums_cache_hit(self):
        """Test album search with cache hit"""
        cached_result = {
            "releases": [{"title": "Cached Album", "artist": "Cached Artist"}],
            "count": 1,
            "offset": 0
        }
        
        self.mock_cache.get.return_value = cached_result
        
        result = await self.service.search_albums("test query")
        
        assert result == cached_result
        self.mock_cache.get.assert_called_once()
        self.mock_cache.set.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_search_albums_cache_miss(self):
        """Test album search with cache miss"""
        self.mock_cache.get.return_value = None
        
        mock_raw_data = {
            "releases": [
                {
                    "id": "test-id",
                    "title": "Test Album",
                    "artist-credit": [{"name": "Test Artist"}],
                    "date": "2023-01-01",
                    "country": "US",
                    "track-count": 10
                }
            ],
            "count": 1,
            "offset": 0
        }
        
        with patch('app.musicbrainz_service.MusicBrainzClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.search_releases.return_value = mock_raw_data
            
            result = await self.service.search_albums("test query")
            
            # Should call API and cache result
            mock_client.search_releases.assert_called_once_with("test query", 25, 0)
            self.mock_cache.set.assert_called_once()
            
            # Check result formatting
            assert len(result["releases"]) == 1
            release = result["releases"][0]
            assert release["musicbrainz_id"] == "test-id"
            assert release["title"] == "Test Album"
            assert release["artist"] == "Test Artist"
            assert release["year"] == 2023
    
    @pytest.mark.asyncio
    async def test_search_albums_api_error(self):
        """Test album search with API error"""
        self.mock_cache.get.return_value = None
        
        with patch('app.musicbrainz_service.MusicBrainzClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            from app.musicbrainz_client import MusicBrainzAPIError
            mock_client.search_releases.side_effect = MusicBrainzAPIError(
                "API Error", {"status_code": 500}
            )
            
            with pytest.raises(TracklistException) as exc_info:
                await self.service.search_albums("test query")
            
            assert "Album search failed" in exc_info.value.message
            assert "API Error" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_get_album_details_cache_hit(self):
        """Test album details with cache hit"""
        cached_result = {
            "musicbrainz_id": "test-id",
            "title": "Cached Album",
            "artist": {"name": "Cached Artist"},
            "tracks": []
        }
        
        self.mock_cache.get.return_value = cached_result
        
        result = await self.service.get_album_details("test-id")
        
        assert result == cached_result
        self.mock_cache.get.assert_called_once()
        self.mock_cache.set.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_album_details_cache_miss(self):
        """Test album details with cache miss"""
        self.mock_cache.get.return_value = None
        
        mock_raw_data = {
            "id": "test-id",
            "title": "Test Album",
            "artist-credit": [
                {
                    "name": "Test Artist",
                    "artist": {"id": "artist-id"}
                }
            ],
            "date": "2023-01-01",
            "country": "US",
            "media": [
                {
                    "tracks": [
                        {
                            "title": "Track 1",
                            "length": "180000",
                            "recording": {"id": "recording-1"}
                        },
                        {
                            "title": "Track 2",
                            "length": "200000",
                            "recording": {"id": "recording-2"}
                        }
                    ]
                }
            ]
        }
        
        with patch('app.musicbrainz_service.MusicBrainzClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get_release_with_tracks.return_value = mock_raw_data
            
            result = await self.service.get_album_details("test-id")
            
            # Should call API and cache result
            mock_client.get_release_with_tracks.assert_called_once_with("test-id")
            self.mock_cache.set.assert_called_once()
            
            # Check result formatting
            assert result["musicbrainz_id"] == "test-id"
            assert result["title"] == "Test Album"
            assert result["artist"]["name"] == "Test Artist"
            assert result["artist"]["musicbrainz_id"] == "artist-id"
            assert result["year"] == 2023
            assert result["total_tracks"] == 2
            assert result["total_duration_ms"] == 380000
            
            # Check tracks
            assert len(result["tracks"]) == 2
            assert result["tracks"][0]["title"] == "Track 1"
            assert result["tracks"][0]["duration_ms"] == 180000
            assert result["tracks"][0]["track_number"] == 1
            assert result["tracks"][1]["title"] == "Track 2"
            assert result["tracks"][1]["duration_ms"] == 200000
            assert result["tracks"][1]["track_number"] == 2
    
    @pytest.mark.asyncio
    async def test_get_album_details_api_error(self):
        """Test album details with API error"""
        self.mock_cache.get.return_value = None
        
        with patch('app.musicbrainz_service.MusicBrainzClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            from app.musicbrainz_client import MusicBrainzAPIError
            mock_client.get_release_with_tracks.side_effect = MusicBrainzAPIError(
                "Not Found", {"status_code": 404}
            )
            
            with pytest.raises(TracklistException) as exc_info:
                await self.service.get_album_details("test-id")
            
            assert "Album details fetch failed" in exc_info.value.message
            assert "Not Found" in exc_info.value.message
    
    def test_format_search_results_minimal_data(self):
        """Test search result formatting with minimal data"""
        raw_data = {
            "releases": [
                {
                    "id": "test-id",
                    "title": "Test Album"
                    # Missing artist-credit, date, etc.
                }
            ],
            "count": 1,
            "offset": 0
        }
        
        result = self.service._format_search_results(raw_data)
        
        assert len(result["releases"]) == 1
        release = result["releases"][0]
        assert release["musicbrainz_id"] == "test-id"
        assert release["title"] == "Test Album"
        assert release["artist"] == "Unknown Artist"
        assert release["year"] is None
    
    def test_format_album_details_minimal_data(self):
        """Test album details formatting with minimal data"""
        raw_data = {
            "id": "test-id",
            "title": "Test Album",
            "media": []  # No tracks
        }
        
        result = self.service._format_album_details(raw_data)
        
        assert result["musicbrainz_id"] == "test-id"
        assert result["title"] == "Test Album"
        assert result["artist"]["name"] == "Unknown Artist"
        assert result["artist"]["musicbrainz_id"] is None
        assert result["total_tracks"] == 0
        assert result["total_duration_ms"] == 0
        assert len(result["tracks"]) == 0
    
    def test_format_album_details_invalid_durations(self):
        """Test album details formatting with invalid track durations"""
        raw_data = {
            "id": "test-id",
            "title": "Test Album",
            "media": [
                {
                    "tracks": [
                        {"title": "Track 1", "length": "invalid"},
                        {"title": "Track 2", "length": None},
                        {"title": "Track 3"}  # No length field
                    ]
                }
            ]
        }
        
        result = self.service._format_album_details(raw_data)
        
        assert result["total_tracks"] == 3
        assert result["total_duration_ms"] is None  # No valid durations
        
        for track in result["tracks"]:
            assert track["duration_ms"] is None
    
    def test_cache_stats(self):
        """Test cache statistics retrieval"""
        mock_stats = {
            "total_entries": 10,
            "expired_entries": 2,
            "active_entries": 8
        }
        
        self.mock_cache.get_stats.return_value = mock_stats
        
        result = self.service.get_cache_stats()
        
        assert result == mock_stats
        self.mock_cache.get_stats.assert_called_once()
    
    def test_clear_cache(self):
        """Test cache clearing"""
        self.service.clear_cache()
        
        self.mock_cache.clear.assert_called_once()