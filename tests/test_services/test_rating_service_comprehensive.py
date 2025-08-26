"""
Comprehensive tests for the rating service to achieve 80% coverage.
Tests all major functionality including album creation, rating, edge cases, and error handling.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import os

from app.rating_service import RatingService, RatingCalculator, VALID_RATINGS
from app.models import Album, Track, Artist, UserSettings, ArtworkCache
from app.exceptions import ServiceNotFoundError, ServiceValidationError


class TestAlbumCreation:
    """Test album creation from MusicBrainz data."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_album_success(self, db_session):
        """Test successfully creating an album from MusicBrainz."""
        service = RatingService()
        
        # Mock MusicBrainz service
        mock_mb_data = {
            "title": "Test Album",
            "artist": {
                "name": "Test Artist",
                "musicbrainz_id": "artist-mbid"
            },
            "year": 2024,
            "genre": "Rock",
            "tracks": [
                {"title": "Track 1", "number": 1, "length": 180000},
                {"title": "Track 2", "number": 2, "length": 200000}
            ]
        }
        
        with patch.object(service, 'musicbrainz_service') as mock_mb:
            mock_mb.get_album_details = AsyncMock(return_value=mock_mb_data)
            
            with patch('app.services.cover_art_service.get_cover_art_service') as mock_cover:
                mock_cover_service = Mock()
                mock_cover_service.get_cover_art_url = AsyncMock(return_value="http://cover.jpg")
                mock_cover.return_value = mock_cover_service
                
                result = await service.create_album_for_rating("test-mbid", db_session)
        
        assert result["title"] == "Test Album"
        assert result["artist"]["name"] == "Test Artist"
        assert result["is_rated"] is False
        assert result["total_tracks"] == 2
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_album_already_exists(self, db_session, created_album):
        """Test handling when album already exists."""
        service = RatingService()
        
        # Try to create the same album again
        result = await service.create_album_for_rating(
            created_album.musicbrainz_id, db_session
        )
        
        # Should return existing album
        assert result["id"] == created_album.id
        assert result["title"] == created_album.name
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_album_with_user_settings(self, db_session):
        """Test album creation respects user settings for album bonus."""
        service = RatingService()
        
        # Create user settings with custom album bonus
        settings = UserSettings(
            user_id=1,
            album_bonus=0.25,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(settings)
        db_session.commit()
        
        mock_mb_data = {
            "title": "Test Album",
            "artist": {"name": "Test Artist", "musicbrainz_id": "artist-mbid"},
            "year": 2024,
            "tracks": [{"title": "Track 1", "number": 1, "length": 180000}]
        }
        
        with patch.object(service, 'musicbrainz_service') as mock_mb:
            mock_mb.get_album_details = AsyncMock(return_value=mock_mb_data)
            
            with patch('app.services.cover_art_service.get_cover_art_service') as mock_cover:
                mock_cover_service = Mock()
                mock_cover_service.get_cover_art_url = AsyncMock(return_value="http://cover.jpg")
                mock_cover.return_value = mock_cover_service
                
                result = await service.create_album_for_rating("test-mbid", db_session)
        
        # Verify album was created with custom bonus
        album = db_session.query(Album).filter(Album.musicbrainz_id == "test-mbid").first()
        assert album.album_bonus == 0.25
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_album_fallback_to_env_bonus(self, db_session):
        """Test album creation falls back to environment variable for bonus."""
        service = RatingService()
        
        # Set environment variable
        os.environ["DEFAULT_ALBUM_BONUS"] = "0.35"
        
        mock_mb_data = {
            "title": "Test Album",
            "artist": {"name": "Test Artist", "musicbrainz_id": "artist-mbid"},
            "year": 2024,
            "tracks": [{"title": "Track 1", "number": 1, "length": 180000}]
        }
        
        with patch.object(service, 'musicbrainz_service') as mock_mb:
            mock_mb.get_album_details = AsyncMock(return_value=mock_mb_data)
            
            with patch('app.services.cover_art_service.get_cover_art_service') as mock_cover:
                mock_cover_service = Mock()
                mock_cover_service.get_cover_art_url = AsyncMock(return_value="http://cover.jpg")
                mock_cover.return_value = mock_cover_service
                
                result = await service.create_album_for_rating("test-mbid", db_session)
        
        # Verify album was created with env bonus
        album = db_session.query(Album).filter(Album.musicbrainz_id == "test-mbid").first()
        assert album.album_bonus == 0.35
        
        # Clean up
        del os.environ["DEFAULT_ALBUM_BONUS"]


class TestTrackRating:
    """Test track rating functionality."""
    
    @pytest.mark.unit
    def test_rate_track_success(self, db_session, created_album):
        """Test successfully rating a track."""
        service = RatingService()
        track = created_album.tracks[0]
        
        result = service.rate_track(track.id, 0.67, db_session)
        
        assert result["track"]["id"] == track.id
        assert result["track"]["rating"] == 0.67
        assert result["track"]["is_rated"] is True
        assert "album_progress" in result
    
    @pytest.mark.unit
    def test_rate_track_invalid_rating(self, db_session, created_album):
        """Test rating track with invalid value."""
        service = RatingService()
        track = created_album.tracks[0]
        
        with pytest.raises(ServiceValidationError) as exc_info:
            service.rate_track(track.id, 0.5, db_session)
        
        assert "Invalid rating value" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_rate_track_nonexistent(self, db_session):
        """Test rating non-existent track."""
        service = RatingService()
        
        with pytest.raises(ServiceNotFoundError) as exc_info:
            service.rate_track(99999, 0.67, db_session)
        
        assert "Track not found" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_rate_track_updates_album_progress(self, db_session, created_album):
        """Test that rating tracks updates album progress correctly."""
        service = RatingService()
        
        # Rate first track
        result1 = service.rate_track(created_album.tracks[0].id, 1.0, db_session)
        assert result1["album_progress"]["rated_tracks"] == 1
        assert result1["album_progress"]["total_tracks"] == len(created_album.tracks)
        
        # Rate second track
        result2 = service.rate_track(created_album.tracks[1].id, 0.67, db_session)
        assert result2["album_progress"]["rated_tracks"] == 2


class TestAlbumSubmission:
    """Test album submission and score calculation."""
    
    @pytest.mark.unit
    def test_submit_album_success(self, db_session, created_album):
        """Test successfully submitting a fully rated album."""
        service = RatingService()
        
        # Rate all tracks
        for track in created_album.tracks:
            service.rate_track(track.id, 1.0, db_session)
        
        # Submit album
        result = service.submit_album_rating(created_album.id, db_session)
        
        assert result["is_rated"] is True
        assert result["rating_score"] > 0
        assert result["rating_score"] <= 100
    
    @pytest.mark.unit
    def test_submit_album_incomplete(self, db_session, created_album):
        """Test submitting an album with unrated tracks."""
        service = RatingService()
        
        # Rate only first track
        service.rate_track(created_album.tracks[0].id, 1.0, db_session)
        
        # Try to submit
        with pytest.raises(ServiceValidationError) as exc_info:
            service.submit_album_rating(created_album.id, db_session)
        
        assert "Cannot submit incomplete album" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_submit_album_already_rated(self, db_session, created_album):
        """Test submitting an already rated album."""
        service = RatingService()
        
        # Rate all tracks and submit
        for track in created_album.tracks:
            service.rate_track(track.id, 0.67, db_session)
        service.submit_album_rating(created_album.id, db_session)
        
        # Try to submit again
        with pytest.raises(ServiceValidationError) as exc_info:
            service.submit_album_rating(created_album.id, db_session)
        
        assert "Album is already rated" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_submit_album_score_calculation(self, db_session, created_album):
        """Test correct score calculation on submission."""
        service = RatingService()
        calculator = RatingCalculator()
        
        # Set specific ratings
        ratings_map = {0: 1.0, 1: 0.67, 2: 0.33}
        for idx, track in enumerate(created_album.tracks[:3]):
            service.rate_track(track.id, ratings_map.get(idx, 0.0), db_session)
        
        # Rate remaining tracks
        for track in created_album.tracks[3:]:
            service.rate_track(track.id, 0.0, db_session)
        
        # Submit and check score
        result = service.submit_album_rating(created_album.id, db_session)
        
        # Calculate expected score
        all_ratings = [1.0, 0.67, 0.33] + [0.0] * (len(created_album.tracks) - 3)
        expected_score = calculator.calculate_album_score(
            all_ratings, created_album.album_bonus
        )
        
        assert result["rating_score"] == expected_score


class TestAlbumManagement:
    """Test album management operations."""
    
    @pytest.mark.unit
    def test_revert_album_to_draft(self, db_session, created_album):
        """Test reverting a rated album back to draft."""
        service = RatingService()
        
        # Rate and submit album
        for track in created_album.tracks:
            service.rate_track(track.id, 1.0, db_session)
        service.submit_album_rating(created_album.id, db_session)
        
        # Revert to draft
        result = service.revert_album_to_in_progress(created_album.id, db_session)
        
        assert result["is_rated"] is False
        assert result["rating_score"] is None
        
        # Check all tracks are unrated
        for track in created_album.tracks:
            db_session.refresh(track)
            assert track.is_rated is False
            assert track.rating is None
    
    @pytest.mark.unit
    def test_delete_album(self, db_session, created_album):
        """Test deleting an album and its tracks."""
        service = RatingService()
        album_id = created_album.id
        track_ids = [t.id for t in created_album.tracks]
        
        # Delete album
        service.delete_album(album_id, db_session)
        
        # Verify album deleted
        assert db_session.query(Album).filter(Album.id == album_id).first() is None
        
        # Verify tracks deleted (cascade)
        for track_id in track_ids:
            assert db_session.query(Track).filter(Track.id == track_id).first() is None
    
    @pytest.mark.unit
    def test_update_album_notes(self, db_session, created_album):
        """Test updating album notes."""
        service = RatingService()
        new_notes = "This is a great album!"
        
        result = service.update_album_notes(created_album.id, new_notes, db_session)
        
        assert result["notes"] == new_notes
        
        # Verify in database
        db_session.refresh(created_album)
        assert created_album.notes == new_notes


class TestAlbumQueries:
    """Test album query and listing operations."""
    
    @pytest.mark.unit
    def test_get_user_albums_all(self, db_session, sample_albums):
        """Test getting all user albums."""
        service = RatingService()
        
        result = service.get_user_albums(db_session)
        
        assert len(result) == len(sample_albums)
    
    @pytest.mark.unit
    def test_get_user_albums_rated_only(self, db_session, sample_albums):
        """Test getting only rated albums."""
        service = RatingService()
        
        # Rate one album
        album = sample_albums[0]
        for track in album.tracks:
            service.rate_track(track.id, 1.0, db_session)
        service.submit_album_rating(album.id, db_session)
        
        result = service.get_user_albums(db_session, rated_only=True)
        
        assert len(result) == 1
        assert result[0]["id"] == album.id
    
    @pytest.mark.unit
    def test_get_user_albums_unrated_only(self, db_session, sample_albums):
        """Test getting only unrated albums."""
        service = RatingService()
        
        # Rate one album
        album = sample_albums[0]
        for track in album.tracks:
            service.rate_track(track.id, 1.0, db_session)
        service.submit_album_rating(album.id, db_session)
        
        result = service.get_user_albums(db_session, unrated_only=True)
        
        assert len(result) == len(sample_albums) - 1
        assert all(r["id"] != album.id for r in result)
    
    @pytest.mark.unit
    def test_get_album_rating_details(self, db_session, created_album):
        """Test getting detailed album rating information."""
        service = RatingService()
        
        result = service.get_album_rating(created_album.id, db_session)
        
        assert result["id"] == created_album.id
        assert result["title"] == created_album.name
        assert "tracks" in result
        assert len(result["tracks"]) == len(created_album.tracks)
    
    @pytest.mark.unit
    def test_get_album_progress(self, db_session, created_album):
        """Test getting album rating progress."""
        service = RatingService()
        
        # Rate some tracks
        service.rate_track(created_album.tracks[0].id, 1.0, db_session)
        service.rate_track(created_album.tracks[1].id, 0.67, db_session)
        
        result = service.get_album_progress(created_album.id, db_session)
        
        assert result["rated_tracks"] == 2
        assert result["total_tracks"] == len(created_album.tracks)
        assert result["percentage"] == round(2 / len(created_album.tracks) * 100, 1)


class TestErrorHandling:
    """Test error handling in rating service."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_musicbrainz_fetch_error(self, db_session):
        """Test handling MusicBrainz API errors."""
        service = RatingService()
        
        with patch.object(service, 'musicbrainz_service') as mock_mb:
            mock_mb.get_album_details = AsyncMock(side_effect=Exception("API Error"))
            
            with pytest.raises(Exception) as exc_info:
                await service.create_album_for_rating("test-mbid", db_session)
            
            assert "API Error" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_database_integrity_error(self, db_session):
        """Test handling database integrity errors."""
        service = RatingService()
        
        # Mock a database error
        with patch.object(db_session, 'commit', side_effect=Exception("DB Error")):
            with pytest.raises(Exception) as exc_info:
                service.update_album_notes(1, "notes", db_session)
            
            assert "DB Error" in str(exc_info.value)


class TestRatingCalculatorExtended:
    """Extended tests for rating calculation logic."""
    
    @pytest.mark.unit
    def test_calculate_with_bonus_boundaries(self):
        """Test calculation with boundary bonus values."""
        calculator = RatingCalculator()
        ratings = [0.67, 0.67, 0.67]
        
        # Test minimum bonus
        score_min = calculator.calculate_album_score(ratings, 0.1)
        
        # Test maximum bonus
        score_max = calculator.calculate_album_score(ratings, 0.4)
        
        assert score_max > score_min
        assert score_min == 68  # (0.67 * 10 + 0.1) * 10
        assert score_max == 71  # (0.67 * 10 + 0.4) * 10
    
    @pytest.mark.unit
    def test_calculate_empty_album(self):
        """Test calculation with no tracks."""
        calculator = RatingCalculator()
        
        score = calculator.calculate_album_score([], 0.33)
        assert score == 3  # Only bonus: 0.33 * 10
    
    @pytest.mark.unit 
    def test_calculate_single_track(self):
        """Test calculation with single track."""
        calculator = RatingCalculator()
        
        score = calculator.calculate_album_score([1.0], 0.33)
        assert score == 100  # Capped at 100
    
    @pytest.mark.unit
    def test_calculate_large_album(self):
        """Test calculation with many tracks."""
        calculator = RatingCalculator()
        
        # Album with 20 tracks, mixed ratings
        ratings = [1.0] * 5 + [0.67] * 10 + [0.33] * 5
        score = calculator.calculate_album_score(ratings, 0.33)
        
        avg = sum(ratings) / len(ratings)  # 0.67
        expected = int((avg * 10 + 0.33) * 10)  # 70
        assert score == expected


class TestPrivateMethods:
    """Test private helper methods in rating service."""
    
    @pytest.mark.unit
    def test_create_or_get_artist_new(self, db_session):
        """Test creating a new artist."""
        service = RatingService()
        
        artist = service._create_or_get_artist("New Artist", "artist-mbid", db_session)
        
        assert artist.name == "New Artist"
        assert artist.musicbrainz_id == "artist-mbid"
        
        # Verify in database
        db_artist = db_session.query(Artist).filter(
            Artist.musicbrainz_id == "artist-mbid"
        ).first()
        assert db_artist is not None
    
    @pytest.mark.unit
    def test_create_or_get_artist_existing(self, db_session):
        """Test getting an existing artist."""
        service = RatingService()
        
        # Create artist first
        artist1 = service._create_or_get_artist("Artist", "artist-mbid", db_session)
        
        # Get same artist
        artist2 = service._create_or_get_artist("Artist", "artist-mbid", db_session)
        
        assert artist1.id == artist2.id
    
    @pytest.mark.unit
    def test_format_album_response(self, db_session, created_album):
        """Test formatting album response."""
        service = RatingService()
        
        response = service._format_album_response(created_album, db_session)
        
        assert response["id"] == created_album.id
        assert response["title"] == created_album.name
        assert response["artist"]["id"] == created_album.artist.id
        assert response["artist"]["name"] == created_album.artist.name
        assert response["is_rated"] == created_album.is_rated
        assert response["total_tracks"] == len(created_album.tracks)
    
    @pytest.mark.unit
    def test_format_track_response(self, db_session, created_album):
        """Test formatting track response."""
        service = RatingService()
        track = created_album.tracks[0]
        
        response = service._format_track_response(track)
        
        assert response["id"] == track.id
        assert response["title"] == track.title
        assert response["track_number"] == track.track_number
        assert response["is_rated"] == track.is_rated
        assert response["rating"] == track.rating