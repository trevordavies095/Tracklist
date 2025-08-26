"""
Tests for the rating service.
Tests rating calculations, track rating, and album completion.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from app.rating_service import RatingService, RatingCalculator, VALID_RATINGS
from app.models import Album, Track, Artist, UserSettings
from app.exceptions import ServiceNotFoundError, ServiceValidationError


class TestRatingCalculation:
    """Test album rating score calculation."""
    
    @pytest.mark.unit
    def test_calculate_perfect_album_score(self):
        """Test calculating score for a perfect album (all tracks rated 1.0)."""
        calculator = RatingCalculator()
        
        # All perfect tracks
        track_ratings = [1.0] * 10
        
        # Calculate score: (1.0 * 10 + 0.33) * 10 = 103.3, capped at 100
        score = calculator.calculate_album_score(track_ratings, album_bonus=0.33)
        assert score == 100  # Should be capped at 100
    
    @pytest.mark.unit
    def test_calculate_mixed_rating_score(self):
        """Test calculating score for album with mixed ratings."""
        calculator = RatingCalculator()
        
        # Mixed ratings
        ratings = [1.0, 0.67, 0.67, 0.33, 1.0]
        
        # Calculate expected score
        avg = sum(ratings) / len(ratings)  # 0.734
        expected_score = int((avg * 10 + 0.33) * 10)  # 76
        
        score = calculator.calculate_album_score(ratings, album_bonus=0.33)
        assert score == expected_score
    
    @pytest.mark.unit
    def test_calculate_low_rating_score(self):
        """Test calculating score for poorly rated album."""
        calculator = RatingCalculator()
        
        # Low ratings
        ratings = [0.0, 0.0, 0.33, 0.0, 0.33]
        
        score = calculator.calculate_album_score(ratings, album_bonus=0.33)
        assert 0 <= score < 30  # Should be low score
        # Average: (0 + 0 + 0.33 + 0 + 0.33) / 5 = 0.132
        # Score: (0.132 * 10 + 0.33) * 10 = 16.5 -> 16
        assert score == 16
    
    @pytest.mark.unit
    def test_calculate_score_no_bonus(self):
        """Test calculating score with minimum album bonus."""
        calculator = RatingCalculator()
        
        ratings = [0.67, 0.67, 0.67]
        
        # With minimum bonus (0.1)
        score = calculator.calculate_album_score(ratings, album_bonus=0.1)
        assert score == 68  # (0.67 * 10 + 0.1) * 10 = 68
    
    @pytest.mark.unit
    def test_album_bonus_effect(self):
        """Test that album bonus properly affects score."""
        calculator = RatingCalculator()
        
        ratings = [0.67, 0.67, 0.67]
        
        # Test with different bonus values
        bonuses = [0.1, 0.2, 0.33, 0.4]
        scores = []
        
        for bonus in bonuses:
            score = calculator.calculate_album_score(ratings, album_bonus=bonus)
            scores.append(score)
        
        # Scores should increase with bonus
        assert scores == sorted(scores)
        assert scores[0] < scores[-1]
        assert scores == [68, 69, 70, 71]  # Expected values
    
    @pytest.mark.unit
    def test_empty_album_score(self):
        """Test calculating score for empty album."""
        calculator = RatingCalculator()
        
        # Empty ratings list
        score = calculator.calculate_album_score([], album_bonus=0.33)
        assert score == 0
    
    @pytest.mark.unit
    def test_bonus_clamping(self):
        """Test that album bonus is clamped to valid range."""
        calculator = RatingCalculator()
        
        ratings = [0.67, 0.67, 0.67]
        
        # Test with out-of-range bonuses
        score_low = calculator.calculate_album_score(ratings, album_bonus=-1.0)
        score_high = calculator.calculate_album_score(ratings, album_bonus=5.0)
        
        # Should be clamped to 0.1 and 0.4
        assert score_low == 68  # Using minimum 0.1
        assert score_high == 71  # Using maximum 0.4
    
    @pytest.mark.unit
    def test_get_completion_percentage(self):
        """Test completion percentage calculation."""
        calculator = RatingCalculator()
        
        assert calculator.get_completion_percentage(10, 0) == 0.0
        assert calculator.get_completion_percentage(10, 5) == 50.0
        assert calculator.get_completion_percentage(10, 10) == 100.0
        assert calculator.get_completion_percentage(0, 0) == 100.0  # Edge case
    
    @pytest.mark.unit
    def test_get_projected_score(self):
        """Test projected score calculation."""
        calculator = RatingCalculator()
        
        # No ratings yet
        assert calculator.get_projected_score([None, None, None]) is None
        
        # Some ratings
        track_ratings = [0.67, None, 1.0, None, 0.33]
        projected = calculator.get_projected_score(track_ratings, album_bonus=0.33)
        
        # Should calculate based on rated tracks only
        rated = [0.67, 1.0, 0.33]
        expected = calculator.calculate_album_score(rated, album_bonus=0.33)
        assert projected == expected


class TestTrackRating:
    """Test individual track rating functionality."""
    
    @pytest.mark.integration
    def test_rate_track_valid_values(self, db_session, created_track):
        """Test rating a track with valid values."""
        service = RatingService()
        
        for rating in VALID_RATINGS:
            result = service.rate_track(created_track.id, rating, db_session)
            
            assert "album_id" in result
            assert "completion_percentage" in result
            assert "projected_score" in result
            
            # Verify track was updated
            db_session.refresh(created_track)
            assert created_track.track_rating == rating
    
    @pytest.mark.integration
    def test_rate_track_invalid_value(self, db_session, created_track):
        """Test that invalid rating values are rejected."""
        service = RatingService()
        invalid_ratings = [0.5, 0.25, 1.5, -1.0, 2.0]
        
        for rating in invalid_ratings:
            with pytest.raises(ServiceValidationError, match="Invalid rating"):
                service.rate_track(created_track.id, rating, db_session)
    
    @pytest.mark.integration
    def test_rate_nonexistent_track(self, db_session):
        """Test rating a track that doesn't exist."""
        service = RatingService()
        
        with pytest.raises(ServiceNotFoundError, match="Track"):
            service.rate_track(99999, 0.67, db_session)
    
    @pytest.mark.integration
    def test_track_rating_updates_completion(self, db_session, album_with_tracks):
        """Test that rating tracks updates completion percentage."""
        service = RatingService()
        album = album_with_tracks
        tracks = album.tracks
        
        # Rate half the tracks
        for i, track in enumerate(tracks[:5]):
            result = service.rate_track(track.id, 0.67, db_session)
            expected_percentage = ((i + 1) / 10) * 100
            assert result["completion_percentage"] == expected_percentage
        
        # Rate remaining tracks
        for i, track in enumerate(tracks[5:], start=5):
            result = service.rate_track(track.id, 0.67, db_session)
            expected_percentage = ((i + 1) / 10) * 100
            assert result["completion_percentage"] == expected_percentage


class TestAlbumCompletion:
    """Test album rating completion and submission."""
    
    @pytest.mark.integration
    def test_submit_completed_album(self, db_session, album_with_tracks, user_settings):
        """Test submitting a fully rated album."""
        service = RatingService()
        album = album_with_tracks
        
        # Rate all tracks
        for track in album.tracks:
            service.rate_track(track.id, 0.67, db_session)
        
        # Submit album
        result = service.submit_album_rating(album.id, db_session)
        
        assert result["is_rated"] is True
        assert result["rating_score"] is not None
        assert 60 <= result["rating_score"] <= 80  # Expected range for 0.67 ratings
        
        # Verify album is marked as rated
        db_session.refresh(album)
        assert album.is_rated is True
        assert album.rated_at is not None
    
    @pytest.mark.integration
    def test_submit_incomplete_album(self, db_session, album_with_tracks):
        """Test that submitting incomplete album fails."""
        service = RatingService()
        album = album_with_tracks
        
        # Rate only some tracks
        for track in album.tracks[:3]:
            service.rate_track(track.id, 0.67, db_session)
        
        # Try to submit album
        with pytest.raises(ServiceValidationError, match="incomplete"):
            service.submit_album_rating(album.id, db_session)
    
    @pytest.mark.integration
    def test_submit_already_rated_album(self, db_session, rated_album):
        """Test that resubmitting already rated album returns existing data."""
        service = RatingService()
        
        original_score = rated_album.rating_score
        original_rated_at = rated_album.rated_at
        
        # Try to submit again
        result = service.submit_album_rating(rated_album.id, db_session)
        
        assert result["is_rated"] is True
        assert result["rating_score"] == original_score
        assert result["rated_at"] == original_rated_at.isoformat()
    
    @pytest.mark.integration
    def test_get_album_progress(self, db_session, album_with_tracks):
        """Test getting album rating progress."""
        service = RatingService()
        album = album_with_tracks
        
        # No tracks rated
        progress = service.get_album_progress(album.id, db_session)
        assert progress["rated_tracks"] == 0
        assert progress["total_tracks"] == 10
        assert progress["completion_percentage"] == 0
        assert progress["projected_score"] is None
        
        # Rate some tracks
        for track in album.tracks[:4]:
            service.rate_track(track.id, 0.67, db_session)
        
        progress = service.get_album_progress(album.id, db_session)
        assert progress["rated_tracks"] == 4
        assert progress["total_tracks"] == 10
        assert progress["completion_percentage"] == 40
        assert progress["projected_score"] is not None
    
    @pytest.mark.integration
    def test_get_album_progress_nonexistent(self, db_session):
        """Test getting progress for nonexistent album."""
        service = RatingService()
        
        with pytest.raises(ServiceNotFoundError, match="Album"):
            service.get_album_progress(99999, db_session)


class TestAlbumCRUD:
    """Test album CRUD operations."""
    
    @pytest.mark.integration
    def test_delete_album(self, db_session, album_with_tracks):
        """Test deleting an album."""
        service = RatingService()
        album_id = album_with_tracks.id
        
        # Delete the album
        result = service.delete_album(album_id, db_session)
        
        assert result["success"] is True
        assert "deleted_tracks" in result
        assert result["deleted_tracks"] == 10
        
        # Verify album is deleted
        album = db_session.query(Album).filter(Album.id == album_id).first()
        assert album is None
        
        # Verify tracks are deleted
        tracks = db_session.query(Track).filter(Track.album_id == album_id).all()
        assert len(tracks) == 0
    
    @pytest.mark.integration
    def test_delete_nonexistent_album(self, db_session):
        """Test deleting nonexistent album."""
        service = RatingService()
        
        with pytest.raises(ServiceNotFoundError, match="Album"):
            service.delete_album(99999, db_session)
    
    @pytest.mark.integration
    def test_revert_album_to_in_progress(self, db_session, rated_album):
        """Test reverting completed album to in-progress."""
        service = RatingService()
        
        original_score = rated_album.rating_score
        
        # Mock get_artwork_url to avoid DB issues
        with patch('app.rating_service.get_artwork_url') as mock_artwork:
            mock_artwork.return_value = "http://example.com/cover.jpg"
            
            # Revert album
            result = service.revert_album_to_in_progress(rated_album.id, db_session)
            
            assert result["is_rated"] is False
            assert result["rating_score"] is None
            assert result["rated_at"] is None
            
            # Verify tracks still have ratings
            assert all(track["rating"] is not None for track in result["tracks"])
            
            # Verify database state
            db_session.refresh(rated_album)
            assert rated_album.is_rated is False
            assert rated_album.rating_score is None
    
    @pytest.mark.integration
    def test_revert_unrated_album_fails(self, db_session, created_album):
        """Test that reverting unrated album fails."""
        service = RatingService()
        
        with pytest.raises(ServiceValidationError, match="already in progress"):
            service.revert_album_to_in_progress(created_album.id, db_session)
    
    @pytest.mark.integration
    def test_update_album_notes(self, db_session, created_album):
        """Test updating album notes."""
        service = RatingService()
        
        notes = "This is a great album!"
        result = service.update_album_notes(created_album.id, notes, db_session)
        
        assert result["success"] is True
        assert result["notes"] == notes
        
        # Verify in database
        db_session.refresh(created_album)
        assert created_album.notes == notes
    
    @pytest.mark.integration
    def test_update_album_notes_too_long(self, db_session, created_album):
        """Test that overly long notes are rejected."""
        service = RatingService()
        
        # Create notes exceeding 5000 characters
        long_notes = "x" * 5001
        
        with pytest.raises(ServiceValidationError, match="5000 characters"):
            service.update_album_notes(created_album.id, long_notes, db_session)
    
    @pytest.mark.integration
    def test_get_user_albums(self, db_session, created_album, rated_album):
        """Test getting user's albums with filtering."""
        service = RatingService()
        
        # Mock get_artwork_url to avoid DB issues
        with patch('app.rating_service.get_artwork_url') as mock_artwork:
            mock_artwork.return_value = "http://example.com/cover.jpg"
            
            # Get all albums
            result = service.get_user_albums(db_session)
            assert result["total"] >= 2
            assert len(result["albums"]) >= 2
            
            # Filter rated albums
            result = service.get_user_albums(db_session, filter_rated=True)
            assert all(album["is_rated"] for album in result["albums"])
            
            # Filter unrated albums
            result = service.get_user_albums(db_session, filter_rated=False)
            assert not any(album["is_rated"] for album in result["albums"])
            
            # Test pagination
            result = service.get_user_albums(db_session, limit=1)
            assert len(result["albums"]) <= 1
            assert result["has_more"] == (result["total"] > 1)
    
    @pytest.mark.integration
    def test_get_user_albums_search(self, db_session, created_album):
        """Test searching user albums."""
        service = RatingService()
        
        # Search by album name
        result = service.get_user_albums(
            db_session, 
            search=created_album.name[:5]
        )
        assert len(result["albums"]) >= 1
        assert any(
            created_album.name in album["title"] 
            for album in result["albums"]
        )
    
    @pytest.mark.integration
    def test_get_user_albums_sorting(self, db_session, created_album, rated_album):
        """Test sorting user albums."""
        service = RatingService()
        
        # Test different sort options
        sort_options = [
            "created_desc", "created_asc", 
            "rating_desc", "rating_asc",
            "artist_asc", "album_asc"
        ]
        
        for sort in sort_options:
            result = service.get_user_albums(db_session, sort=sort)
            assert "albums" in result
            assert isinstance(result["albums"], list)


class TestMusicBrainzIntegration:
    """Test MusicBrainz integration for album creation."""
    
    @pytest.mark.integration 
    def test_create_album_for_rating(self, db_session):
        """Test creating album from MusicBrainz data."""
        # Skip async tests for now - they need special setup
        pytest.skip("Async tests need special runner setup")
    
    @pytest.mark.integration
    def test_create_duplicate_album(self, db_session, created_album):
        """Test that creating duplicate album returns existing."""
        # Skip async tests for now - they need special setup
        pytest.skip("Async tests need special runner setup")
    
    @pytest.mark.integration
    def test_update_missing_cover_art(self, db_session, created_album):
        """Test updating missing cover art."""
        # Skip async tests for now - they need special setup
        pytest.skip("Async tests need special runner setup")


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.unit
    def test_large_album_calculation(self):
        """Test calculation with very large album (100+ tracks)."""
        calculator = RatingCalculator()
        
        # Create large album with mixed ratings
        import random
        random.seed(42)
        ratings = [random.choice(VALID_RATINGS) for _ in range(150)]
        
        score = calculator.calculate_album_score(ratings, album_bonus=0.33)
        
        assert 0 <= score <= 100
        assert isinstance(score, int)
    
    @pytest.mark.unit
    def test_single_track_album(self):
        """Test calculation for single track album."""
        calculator = RatingCalculator()
        
        score = calculator.calculate_album_score([1.0], album_bonus=0.33)
        assert score == 100  # (1.0 * 10 + 0.33) * 10 = 103.3, capped at 100
        
        score = calculator.calculate_album_score([0.0], album_bonus=0.33)
        assert score == 3  # (0.0 * 10 + 0.33) * 10 = 3.3 -> 3
    
    @pytest.mark.integration
    def test_concurrent_track_rating(self, db_session, album_with_tracks):
        """Test rating multiple tracks in sequence."""
        service = RatingService()
        album = album_with_tracks
        
        # Rate all tracks rapidly
        for track in album.tracks:
            service.rate_track(track.id, 0.67, db_session)
        
        # Verify all ratings were saved
        db_session.refresh(album)
        assert all(track.track_rating == 0.67 for track in album.tracks)
        
        # Verify album can be submitted
        result = service.submit_album_rating(album.id, db_session)
        assert result["is_rated"] is True