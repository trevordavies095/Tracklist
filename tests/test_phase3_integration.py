"""
Integration tests for Phase 3: Core Rating System
Tests the complete workflow from album creation to rating submission
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db, create_tables
from app.models import Album, Artist, Track, UserSettings
from app.rating_service import RatingService, get_rating_service


class TestPhase3Integration:
    """Integration tests for Phase 3 rating system"""
    
    @pytest.fixture
    def client(self):
        """Test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_musicbrainz_service(self):
        """Mock MusicBrainz service with realistic data"""
        service = AsyncMock()
        
        # Mock album data
        service.get_album_details.return_value = {
            "title": "OK Computer",
            "artist": {
                "name": "Radiohead",
                "musicbrainz_id": "a74b1b7f-71a5-4011-9441-d0b5e4122711"
            },
            "year": 1997,
            "country": "GB",
            "total_tracks": 12,
            "total_duration_ms": 3186000,  # ~53 minutes
            "tracks": [
                {"track_number": 1, "title": "Airbag", "duration_ms": 284000},
                {"track_number": 2, "title": "Paranoid Android", "duration_ms": 383000},
                {"track_number": 3, "title": "Subterranean Homesick Alien", "duration_ms": 267000},
                {"track_number": 4, "title": "Exit Music (For a Film)", "duration_ms": 264000},
                {"track_number": 5, "title": "Let Down", "duration_ms": 299000},
                {"track_number": 6, "title": "Karma Police", "duration_ms": 261000},
                {"track_number": 7, "title": "Fitter Happier", "duration_ms": 117000},
                {"track_number": 8, "title": "Electioneering", "duration_ms": 230000},
                {"track_number": 9, "title": "Climbing Up the Walls", "duration_ms": 287000},
                {"track_number": 10, "title": "No Surprises", "duration_ms": 229000},
                {"track_number": 11, "title": "Lucky", "duration_ms": 259000},
                {"track_number": 12, "title": "The Tourist", "duration_ms": 324000}
            ]
        }
        
        return service
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session for integration tests"""
        from unittest.mock import MagicMock
        
        # Mock session
        session = MagicMock(spec=Session)
        
        # Mock query results
        session.query.return_value = session
        session.filter.return_value = session
        session.order_by.return_value = session
        session.join.return_value = session
        session.offset.return_value = session
        session.limit.return_value = session
        session.all.return_value = []
        session.first.return_value = None
        session.count.return_value = 0
        
        return session
    
    def test_complete_rating_workflow(self, client, mock_musicbrainz_service, mock_db_session):
        """Test complete workflow: create album -> rate tracks -> submit"""
        
        # Step 1: Create album for rating
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                # Setup mock service
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Mock album creation response
                mock_service.create_album_for_rating.return_value = {
                    "id": 1,
                    "musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef",
                    "title": "OK Computer",
                    "artist": {
                        "name": "Radiohead",
                        "musicbrainz_id": "a74b1b7f-71a5-4011-9441-d0b5e4122711"
                    },
                    "year": 1997,
                    "total_tracks": 12,
                    "is_rated": False
                }
                
                # Create album
                response = client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
                
                assert response.status_code == 200
                album_data = response.json()
                assert album_data["title"] == "OK Computer"
                assert album_data["total_tracks"] == 12
                
                album_id = album_data["id"]
        
        # Step 2: Rate individual tracks
        track_ratings = [
            (1, 1.0),    # Airbag - Standout
            (2, 1.0),    # Paranoid Android - Standout  
            (3, 0.67),   # Subterranean Homesick Alien - Good
            (4, 1.0),    # Exit Music - Standout
            (5, 1.0),    # Let Down - Standout
            (6, 1.0),    # Karma Police - Standout
            (7, 0.33),   # Fitter Happier - Filler
            (8, 0.67),   # Electioneering - Good
            (9, 0.67),   # Climbing Up the Walls - Good
            (10, 1.0),   # No Surprises - Standout
            (11, 0.67),  # Lucky - Good
            (12, 0.67)   # The Tourist - Good
        ]
        
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                for track_id, rating in track_ratings:
                    # Mock progress response after each rating
                    rated_so_far = track_id
                    completion_pct = (rated_so_far / 12) * 100
                    
                    mock_service.rate_track.return_value = {
                        "album_id": album_id,
                        "album_title": "OK Computer",
                        "completion_percentage": completion_pct,
                        "projected_score": 85,  # Projected based on current ratings
                        "is_complete": completion_pct == 100.0
                    }
                    
                    # Rate the track
                    response = client.put(
                        f"/api/v1/tracks/{track_id}/rating",
                        json={"rating": rating}
                    )
                    
                    assert response.status_code == 200
                    progress_data = response.json()
                    assert progress_data["completion_percentage"] == completion_pct
                    assert progress_data["album_id"] == album_id
        
        # Step 3: Check album progress when complete
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                mock_service.get_album_progress.return_value = {
                    "album_id": album_id,
                    "album_title": "OK Computer",
                    "artist_name": "Radiohead",
                    "total_tracks": 12,
                    "rated_tracks": 12,
                    "completion_percentage": 100.0,
                    "is_complete": True,
                    "projected_score": 85,
                    "is_submitted": False,
                    "final_score": None,
                    "album_bonus": 0.25
                }
                
                response = client.get(f"/api/v1/albums/{album_id}/progress")
                
                assert response.status_code == 200
                progress_data = response.json()
                assert progress_data["completion_percentage"] == 100.0
                assert progress_data["is_complete"] is True
                assert progress_data["is_submitted"] is False
        
        # Step 4: Submit final album rating
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Calculate expected final score
                # Average of ratings: (6*1.0 + 5*0.67 + 1*0.33) / 12 = (6 + 3.35 + 0.33) / 12 = 0.806
                # (0.806 * 10) + 0.25 = 8.31, floor = 8, * 10 = 80
                expected_score = 80
                
                mock_service.submit_album_rating.return_value = {
                    "id": album_id,
                    "title": "OK Computer",
                    "artist": {"name": "Radiohead"},
                    "rating_score": expected_score,
                    "is_rated": True,
                    "rated_at": "2023-12-01T12:00:00+00:00",
                    "tracks": [
                        {"id": i+1, "title": f"Track {i+1}", "rating": track_ratings[i][1]}
                        for i in range(12)
                    ]
                }
                
                response = client.post(f"/api/v1/albums/{album_id}/submit")
                
                assert response.status_code == 200
                final_data = response.json()
                assert final_data["rating_score"] == expected_score
                assert final_data["is_rated"] is True
                assert "tracks" in final_data
                assert len(final_data["tracks"]) == 12
        
        # Step 5: Verify final album data
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                mock_service.get_album_rating.return_value = {
                    "id": album_id,
                    "title": "OK Computer",
                    "artist": {"name": "Radiohead", "musicbrainz_id": "a74b1b7f-71a5-4011-9441-d0b5e4122711"},
                    "year": 1997,
                    "rating_score": expected_score,
                    "is_rated": True,
                    "rated_at": "2023-12-01T12:00:00+00:00",
                    "tracks": [
                        {"id": i+1, "title": f"Track {i+1}", "rating": track_ratings[i][1]}
                        for i in range(12)
                    ]
                }
                
                response = client.get(f"/api/v1/albums/{album_id}")
                
                assert response.status_code == 200
                album_data = response.json()
                assert album_data["rating_score"] == expected_score
                assert album_data["is_rated"] is True
                assert len(album_data["tracks"]) == 12
    
    def test_rating_validation_workflow(self, client, mock_db_session):
        """Test rating validation throughout the workflow"""
        
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Test invalid rating values
                from app.exceptions import ServiceValidationError
                mock_service.rate_track.side_effect = ServiceValidationError("Invalid rating: 0.5. Must be one of [0.0, 0.33, 0.67, 1.0]")
                
                response = client.put(
                    "/api/v1/tracks/1/rating",
                    json={"rating": 0.5}  # Invalid rating
                )
                
                assert response.status_code == 400
                error_data = response.json()
                assert error_data["error"] == "Invalid rating"
                assert error_data["valid_ratings"] == [0.0, 0.33, 0.67, 1.0]
    
    def test_incomplete_submission_workflow(self, client, mock_db_session):
        """Test trying to submit incomplete album rating"""
        
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Mock incomplete album submission
                from app.exceptions import ServiceValidationError
                mock_service.submit_album_rating.side_effect = ServiceValidationError(
                    "Cannot submit incomplete rating. Unrated tracks: 3, 7, 11"
                )
                
                response = client.post("/api/v1/albums/1/submit")
                
                assert response.status_code == 400
                error_data = response.json()
                assert error_data["error"] == "Cannot submit album"
                assert "Unrated tracks: 3, 7, 11" in error_data["message"]
    
    def test_album_listing_workflow(self, client, mock_db_session):
        """Test album listing with different filters"""
        
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Mock user albums response
                mock_service.get_user_albums.return_value = {
                    "albums": [
                        {
                            "id": 1,
                            "title": "OK Computer",
                            "artist": "Radiohead",
                            "year": 1997,
                            "is_rated": True,
                            "rating_score": 85,
                            "rated_at": "2023-12-01T12:00:00+00:00"
                        },
                        {
                            "id": 2,
                            "title": "In Rainbows",
                            "artist": "Radiohead",
                            "year": 2007,
                            "is_rated": False,
                            "rating_score": None,
                            "rated_at": None
                        }
                    ],
                    "total": 2,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False
                }
                
                # Test getting all albums
                response = client.get("/api/v1/albums")
                assert response.status_code == 200
                data = response.json()
                assert len(data["albums"]) == 2
                assert data["total"] == 2
                
                # Test filtering for rated albums only
                mock_service.get_user_albums.return_value = {
                    "albums": [
                        {
                            "id": 1,
                            "title": "OK Computer",
                            "artist": "Radiohead",
                            "is_rated": True,
                            "rating_score": 85
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False
                }
                
                response = client.get("/api/v1/albums?rated=true")
                assert response.status_code == 200
                data = response.json()
                assert len(data["albums"]) == 1
                assert data["albums"][0]["is_rated"] is True
    
    def test_score_calculation_accuracy(self):
        """Test the accuracy of score calculation algorithm"""
        from app.rating_service import RatingCalculator
        
        # Test case 1: Perfect album
        perfect_ratings = [1.0] * 10
        score = RatingCalculator.calculate_album_score(perfect_ratings, 0.25)
        # (1.0 * 10) + 0.25 = 10.25, floor = 10, * 10 = 100
        assert score == 100
        
        # Test case 2: Mixed ratings (realistic)
        mixed_ratings = [1.0, 1.0, 0.67, 0.67, 0.67, 0.33, 1.0, 0.67, 0.33, 1.0]
        score = RatingCalculator.calculate_album_score(mixed_ratings, 0.25)
        # Average = (4*1.0 + 4*0.67 + 2*0.33) / 10 = (4 + 2.68 + 0.66) / 10 = 0.734
        # (0.734 * 10) + 0.25 = 7.59, floor = 7, * 10 = 70
        assert score == 70
        
        # Test case 3: Poor album
        poor_ratings = [0.33, 0.0, 0.33, 0.0, 0.67, 0.0, 0.33, 0.0, 0.33, 0.67]
        score = RatingCalculator.calculate_album_score(poor_ratings, 0.25)
        # Average = (4*0.33 + 4*0.0 + 2*0.67) / 10 = (1.32 + 0 + 1.34) / 10 = 0.266
        # (0.266 * 10) + 0.25 = 2.91, floor = 2, * 10 = 20
        assert score == 20
        
        # Test case 4: Different album bonus values
        ratings = [0.67] * 5
        
        # Low bonus
        score_low = RatingCalculator.calculate_album_score(ratings, 0.1)
        # (0.67 * 10) + 0.1 = 6.8, floor = 6, * 10 = 60
        assert score_low == 60
        
        # High bonus  
        score_high = RatingCalculator.calculate_album_score(ratings, 0.4)
        # (0.67 * 10) + 0.4 = 7.1, floor = 7, * 10 = 70
        assert score_high == 70
    
    def test_error_handling_edge_cases(self, client, mock_db_session):
        """Test error handling for edge cases"""
        
        with patch('app.routers.albums.get_rating_service') as mock_get_service:
            with patch('app.routers.albums.get_db', return_value=mock_db_session):
                mock_service = MagicMock(spec=RatingService)
                mock_get_service.return_value = mock_service
                
                # Test internal server error
                mock_service.create_album_for_rating.side_effect = Exception("Database connection failed")
                
                response = client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
                
                assert response.status_code == 500
                error_data = response.json()
                assert error_data["error"] == "Internal server error"
                
                # Test service unavailable (MusicBrainz down)
                from app.exceptions import TracklistException
                mock_service.create_album_for_rating.side_effect = TracklistException("Service timeout")
                
                response = client.post(
                    "/api/v1/albums",
                    params={"musicbrainz_id": "01234567-89ab-cdef-0123-456789abcdef"}
                )
                
                assert response.status_code == 502
                error_data = response.json()
                assert error_data["error"] == "Music service unavailable"