import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.rating_service import RatingService
from app.exceptions import ServiceNotFoundError, ServiceValidationError, TracklistException


class TestAlbumsRouter:
    """Test the albums API endpoints"""
    
    def setup_method(self):
        """Setup for each test"""
        self.client = TestClient(app)
    
    @pytest.fixture
    def mock_rating_service(self):
        """Mock rating service"""
        service = MagicMock(spec=RatingService)
        return service
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()
    
    def test_create_album_for_rating_success(self, mock_rating_service, mock_db):
        """Test successful album creation"""
        mock_response = {
            "id": 1,
            "musicbrainz_id": "test-mb-id",
            "title": "Test Album",
            "artist": {"name": "Test Artist", "musicbrainz_id": "artist-mb-id"},
            "year": 2023,
            "total_tracks": 10,
            "is_rated": False
        }
        mock_rating_service.create_album_for_rating.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Test Album"
        assert data["artist"]["name"] == "Test Artist"
        assert data["is_rated"] is False
    
    def test_create_album_for_rating_invalid_mbid_length(self):
        """Test album creation with invalid MusicBrainz ID length"""
        response = self.client.post(
            "/api/v1/albums",
            params={"musicbrainz_id": "short-id"}
        )
        
        assert response.status_code == 422  # Validation error
        assert "validation error" in response.json()["detail"][0]["msg"].lower()
    
    def test_create_album_for_rating_validation_error(self, mock_rating_service, mock_db):
        """Test album creation with validation error"""
        mock_rating_service.create_album_for_rating.side_effect = ServiceValidationError("Invalid MusicBrainz ID")
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Validation error"
        assert "Invalid MusicBrainz ID" in data["message"]
    
    def test_create_album_for_rating_not_found(self, mock_rating_service, mock_db):
        """Test album creation with not found error"""
        mock_rating_service.create_album_for_rating.side_effect = TracklistException("Album not found in MusicBrainz")
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Album not found"
    
    def test_create_album_for_rating_service_error(self, mock_rating_service, mock_db):
        """Test album creation with service error"""
        mock_rating_service.create_album_for_rating.side_effect = TracklistException("Service unavailable")
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
        
        assert response.status_code == 502
        data = response.json()
        assert data["error"] == "Music service unavailable"
    
    def test_update_track_rating_success(self, mock_rating_service, mock_db):
        """Test successful track rating update"""
        mock_response = {
            "album_id": 1,
            "album_title": "Test Album",
            "completion_percentage": 25.0,
            "projected_score": 80,
            "is_complete": False
        }
        mock_rating_service.rate_track.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.put(
                    "/api/v1/tracks/1/rating",
                    json={"rating": 0.67}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["album_id"] == 1
        assert data["completion_percentage"] == 25.0
        assert data["projected_score"] == 80
        
        mock_rating_service.rate_track.assert_called_once_with(1, 0.67, mock_db)
    
    def test_update_track_rating_invalid_track_id(self):
        """Test track rating update with invalid track ID"""
        response = self.client.put(
            "/api/v1/tracks/0/rating",  # Invalid ID (must be > 0)
            json={"rating": 1.0}
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_update_track_rating_track_not_found(self, mock_rating_service, mock_db):
        """Test track rating update with non-existent track"""
        mock_rating_service.rate_track.side_effect = ServiceNotFoundError("Track", 999)
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.put(
                    "/api/v1/tracks/999/rating",
                    json={"rating": 1.0}
                )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Track not found"
        assert "999" in data["message"]
    
    def test_update_track_rating_invalid_rating(self, mock_rating_service, mock_db):
        """Test track rating update with invalid rating value"""
        mock_rating_service.rate_track.side_effect = ServiceValidationError("Invalid rating: 0.5. Must be one of [0.0, 0.33, 0.67, 1.0]")
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.put(
                    "/api/v1/tracks/1/rating",
                    json={"rating": 0.5}
                )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Invalid rating"
        assert "valid_ratings" in data
        assert data["valid_ratings"] == [0.0, 0.33, 0.67, 1.0]
    
    def test_get_album_progress_success(self, mock_rating_service, mock_db):
        """Test successful album progress retrieval"""
        mock_response = {
            "album_id": 1,
            "album_title": "Test Album",
            "artist_name": "Test Artist",
            "total_tracks": 10,
            "rated_tracks": 7,
            "completion_percentage": 70.0,
            "is_complete": False,
            "projected_score": 85,
            "is_submitted": False,
            "final_score": None,
            "album_bonus": 0.25
        }
        mock_rating_service.get_album_progress.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get("/api/v1/albums/1/progress")
        
        assert response.status_code == 200
        data = response.json()
        assert data["album_id"] == 1
        assert data["completion_percentage"] == 70.0
        assert data["projected_score"] == 85
        assert data["is_complete"] is False
        
        mock_rating_service.get_album_progress.assert_called_once_with(1, mock_db)
    
    def test_get_album_progress_not_found(self, mock_rating_service, mock_db):
        """Test album progress retrieval for non-existent album"""
        mock_rating_service.get_album_progress.side_effect = ServiceNotFoundError("Album", 999)
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get("/api/v1/albums/999/progress")
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Album not found"
        assert "999" in data["message"]
    
    def test_submit_album_rating_success(self, mock_rating_service, mock_db):
        """Test successful album rating submission"""
        mock_response = {
            "id": 1,
            "title": "Test Album",
            "artist": {"name": "Test Artist"},
            "rating_score": 85,
            "is_rated": True,
            "rated_at": "2023-12-01T12:00:00Z",
            "tracks": [
                {"id": 1, "title": "Track 1", "rating": 1.0},
                {"id": 2, "title": "Track 2", "rating": 0.67}
            ]
        }
        mock_rating_service.submit_album_rating.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post("/api/v1/albums/1/submit")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["rating_score"] == 85
        assert data["is_rated"] is True
        assert "tracks" in data
        
        mock_rating_service.submit_album_rating.assert_called_once_with(1, mock_db)
    
    def test_submit_album_rating_incomplete(self, mock_rating_service, mock_db):
        """Test album submission with incomplete ratings"""
        mock_rating_service.submit_album_rating.side_effect = ServiceValidationError("Cannot submit incomplete rating. Unrated tracks: 3, 7")
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post("/api/v1/albums/1/submit")
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Cannot submit album"
        assert "Unrated tracks" in data["message"]
    
    def test_submit_album_rating_not_found(self, mock_rating_service, mock_db):
        """Test album submission for non-existent album"""
        mock_rating_service.submit_album_rating.side_effect = ServiceNotFoundError("Album", 999)
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.post("/api/v1/albums/999/submit")
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Album not found"
    
    def test_get_album_rating_success(self, mock_rating_service, mock_db):
        """Test successful album rating retrieval"""
        mock_response = {
            "id": 1,
            "title": "Test Album",
            "artist": {"name": "Test Artist", "musicbrainz_id": "artist-mb-id"},
            "year": 2023,
            "rating_score": 85,
            "is_rated": True,
            "tracks": [
                {"id": 1, "title": "Track 1", "rating": 1.0},
                {"id": 2, "title": "Track 2", "rating": 0.67}
            ]
        }
        mock_rating_service.get_album_rating.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get("/api/v1/albums/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Test Album"
        assert data["rating_score"] == 85
        assert len(data["tracks"]) == 2
        
        mock_rating_service.get_album_rating.assert_called_once_with(1, mock_db)
    
    def test_get_album_rating_not_found(self, mock_rating_service, mock_db):
        """Test album rating retrieval for non-existent album"""
        mock_rating_service.get_album_rating.side_effect = ServiceNotFoundError("Album", 999)
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get("/api/v1/albums/999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Album not found"
    
    def test_get_user_albums_success(self, mock_rating_service, mock_db):
        """Test successful user albums retrieval"""
        mock_response = {
            "albums": [
                {"id": 1, "title": "Album 1", "artist": "Artist 1", "is_rated": True, "rating_score": 85},
                {"id": 2, "title": "Album 2", "artist": "Artist 2", "is_rated": False, "rating_score": None}
            ],
            "total": 15,
            "limit": 50,
            "offset": 0,
            "has_more": False
        }
        mock_rating_service.get_user_albums.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get("/api/v1/albums")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 15
        assert len(data["albums"]) == 2
        assert data["has_more"] is False
        
        mock_rating_service.get_user_albums.assert_called_once_with(mock_db, 50, 0, None)
    
    def test_get_user_albums_with_filters(self, mock_rating_service, mock_db):
        """Test user albums retrieval with filters"""
        mock_response = {
            "albums": [
                {"id": 1, "title": "Rated Album", "artist": "Artist 1", "is_rated": True, "rating_score": 85}
            ],
            "total": 5,
            "limit": 10,
            "offset": 0,
            "has_more": False
        }
        mock_rating_service.get_user_albums.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                response = self.client.get(
                    "/api/v1/albums",
                    params={"limit": 10, "offset": 0, "rated": "true"}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["albums"]) == 1
        assert data["albums"][0]["is_rated"] is True
        
        mock_rating_service.get_user_albums.assert_called_once_with(mock_db, 10, 0, True)
    
    def test_get_user_albums_pagination_limits(self):
        """Test user albums pagination limits"""
        # Test limit too high
        response = self.client.get("/api/v1/albums", params={"limit": 200})
        assert response.status_code == 422  # Validation error
        
        # Test limit too low
        response = self.client.get("/api/v1/albums", params={"limit": 0})
        assert response.status_code == 422  # Validation error
        
        # Test negative offset
        response = self.client.get("/api/v1/albums", params={"offset": -1})
        assert response.status_code == 422  # Validation error
    
    def test_get_user_albums_rated_filter_values(self, mock_rating_service, mock_db):
        """Test different values for rated filter"""
        mock_response = {"albums": [], "total": 0, "limit": 50, "offset": 0, "has_more": False}
        mock_rating_service.get_user_albums.return_value = mock_response
        
        with patch('app.routers.albums.get_rating_service', return_value=mock_rating_service):
            with patch('app.routers.albums.get_db', return_value=mock_db):
                # Test rated=true
                response = self.client.get("/api/v1/albums", params={"rated": "true"})
                assert response.status_code == 200
                mock_rating_service.get_user_albums.assert_called_with(mock_db, 50, 0, True)
                
                # Test rated=false
                response = self.client.get("/api/v1/albums", params={"rated": "false"})
                assert response.status_code == 200
                mock_rating_service.get_user_albums.assert_called_with(mock_db, 50, 0, False)
                
                # Test no rated filter (null/none)
                response = self.client.get("/api/v1/albums")
                assert response.status_code == 200
                mock_rating_service.get_user_albums.assert_called_with(mock_db, 50, 0, None)