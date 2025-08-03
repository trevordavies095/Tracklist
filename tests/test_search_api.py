import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.exceptions import TracklistException


class TestSearchAPI:
    def test_search_albums_success(self, client):
        """Test successful albums search"""
        mock_result = {
            "releases": [
                {
                    "musicbrainz_id": "test-id",
                    "title": "Test Album",
                    "artist": "Test Artist",
                    "year": 2023,
                    "country": "US",
                    "track_count": 10
                }
            ],
            "count": 1,
            "offset": 0
        }
        
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.search_albums.return_value = mock_result
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/search/albums?q=test+album")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check response structure
            assert "releases" in data
            assert "pagination" in data
            assert len(data["releases"]) == 1
            
            # Check pagination metadata
            pagination = data["pagination"]
            assert pagination["limit"] == 25
            assert pagination["offset"] == 0
            assert pagination["total"] == 1
            assert pagination["has_more"] is False
            
            # Check release data
            release = data["releases"][0]
            assert release["musicbrainz_id"] == "test-id"
            assert release["title"] == "Test Album"
            assert release["artist"] == "Test Artist"
    
    def test_search_albums_with_pagination(self, client):
        """Test albums search with pagination parameters"""
        mock_result = {
            "releases": [],
            "count": 100,
            "offset": 25
        }
        
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.search_albums.return_value = mock_result
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/search/albums?q=test&limit=10&offset=25")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check service was called with correct parameters
            mock_service.search_albums.assert_called_once_with("test", 10, 25)
            
            # Check pagination
            pagination = data["pagination"]
            assert pagination["limit"] == 10
            assert pagination["offset"] == 25
            assert pagination["total"] == 100
            assert pagination["has_more"] is True  # 25 + 10 < 100
    
    def test_search_albums_empty_query(self, client):
        """Test albums search with empty query"""
        response = client.get("/api/v1/search/albums?q=")
        
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "error" in data
    
    def test_search_albums_invalid_limit(self, client):
        """Test albums search with invalid limit"""
        # Test limit too high
        response = client.get("/api/v1/search/albums?q=test&limit=200")
        
        assert response.status_code == 422  # Validation error
        
        # Test negative limit
        response = client.get("/api/v1/search/albums?q=test&limit=-1")
        
        assert response.status_code == 422  # Validation error
    
    def test_search_albums_service_error(self, client):
        """Test albums search with service error"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.search_albums.side_effect = TracklistException(
                "MusicBrainz API error", {"status_code": 500}
            )
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/search/albums?q=test")
            
            assert response.status_code == 502
            data = response.json()
            assert data["detail"]["error"] == "Search service unavailable"
    
    def test_search_albums_unexpected_error(self, client):
        """Test albums search with unexpected error"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.search_albums.side_effect = Exception("Unexpected error")
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/search/albums?q=test")
            
            assert response.status_code == 500
            data = response.json()
            assert data["detail"]["error"] == "Internal server error"
    
    def test_get_album_details_success(self, client):
        """Test successful album details fetch"""
        mock_result = {
            "musicbrainz_id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Test Album",
            "artist": {
                "name": "Test Artist",
                "musicbrainz_id": "artist-id"
            },
            "year": 2023,
            "tracks": [
                {
                    "track_number": 1,
                    "title": "Track 1",
                    "duration_ms": 180000
                }
            ],
            "total_tracks": 1,
            "total_duration_ms": 180000
        }
        
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_album_details.return_value = mock_result
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/albums/550e8400-e29b-41d4-a716-446655440000/details")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["musicbrainz_id"] == "550e8400-e29b-41d4-a716-446655440000"
            assert data["title"] == "Test Album"
            assert data["artist"]["name"] == "Test Artist"
            assert len(data["tracks"]) == 1
            assert data["tracks"][0]["title"] == "Track 1"
    
    def test_get_album_details_invalid_id(self, client):
        """Test album details with invalid MusicBrainz ID"""
        response = client.get("/api/v1/albums/invalid-id/details")
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "Invalid MusicBrainz ID"
    
    def test_get_album_details_not_found(self, client):
        """Test album details with not found error"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_album_details.side_effect = TracklistException(
                "Album not found", {"status_code": 404}
            )
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/albums/550e8400-e29b-41d4-a716-446655440000/details")
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"]["error"] == "Album not found"
    
    def test_get_album_details_service_error(self, client):
        """Test album details with service error"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_album_details.side_effect = TracklistException(
                "API error", {"status_code": 500}
            )
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/albums/550e8400-e29b-41d4-a716-446655440000/details")
            
            assert response.status_code == 502
            data = response.json()
            assert data["detail"]["error"] == "Music service unavailable"
    
    def test_get_cache_stats(self, client):
        """Test cache statistics endpoint"""
        mock_stats = {
            "total_entries": 10,
            "expired_entries": 2,
            "active_entries": 8,
            "max_size": 500,
            "default_ttl": 3600
        }
        
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_cache_stats.return_value = mock_stats
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/cache/stats")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert data["cache_stats"] == mock_stats
    
    def test_clear_cache(self, client):
        """Test cache clearing endpoint"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.clear_cache.return_value = None
            mock_get_service.return_value = mock_service
            
            response = client.delete("/api/v1/cache")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "success"
            assert data["message"] == "Cache cleared successfully"
            mock_service.clear_cache.assert_called_once()
    
    def test_cache_endpoints_error_handling(self, client):
        """Test error handling in cache endpoints"""
        with patch('app.routers.search.get_musicbrainz_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_cache_stats.side_effect = Exception("Cache error")
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/v1/cache/stats")
            
            assert response.status_code == 500
            data = response.json()
            assert data["detail"]["error"] == "Unable to get cache statistics"