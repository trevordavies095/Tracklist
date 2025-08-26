"""
Tests for the rating service.
Tests rating calculations, track rating, and album completion.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from app.rating_service import RatingService
from app.models import Album, Track


class TestRatingCalculation:
    """Test album rating score calculation."""
    
    @pytest.mark.unit
    def test_calculate_perfect_album_score(self):
        """Test calculating score for a perfect album (all tracks rated 1.0)."""
        service = RatingService()
        
        # Mock album with all perfect tracks
        tracks = [Mock(track_rating=1.0) for _ in range(10)]
        album = Mock(tracks=tracks, album_bonus=0.33)
        
        # Calculate score: (1.0 * 10 + 0.33) * 10 = 103.3, capped at 100
        score = service.calculate_album_score(album)
        assert score == 100
    
    @pytest.mark.unit
    def test_calculate_mixed_rating_score(self):
        """Test calculating score for album with mixed ratings."""
        service = RatingService()
        
        # Mock album with mixed ratings
        ratings = [1.0, 0.67, 0.67, 0.33, 1.0]
        tracks = [Mock(track_rating=r) for r in ratings]
        album = Mock(tracks=tracks, album_bonus=0.33)
        
        # Calculate expected score
        avg = sum(ratings) / len(ratings)  # 0.734
        expected_score = int((avg * 10 + 0.33) * 10)  # 76
        
        score = service.calculate_album_score(album)
        assert score == expected_score
    
    @pytest.mark.unit
    def test_calculate_low_rating_score(self):
        """Test calculating score for poorly rated album."""
        service = RatingService()
        
        # Mock album with low ratings
        ratings = [0.0, 0.0, 0.33, 0.0, 0.33]
        tracks = [Mock(track_rating=r) for r in ratings]
        album = Mock(tracks=tracks, album_bonus=0.33)
        
        score = service.calculate_album_score(album)
        assert 0 <= score < 30  # Should be low score
    
    @pytest.mark.unit
    def test_calculate_score_no_bonus(self):
        """Test calculating score with no album bonus."""
        service = RatingService()
        
        ratings = [0.67, 0.67, 0.67]
        tracks = [Mock(track_rating=r) for r in ratings]
        album = Mock(tracks=tracks, album_bonus=0.0)
        
        # Score should be exactly 67
        score = service.calculate_album_score(album)
        assert score == 67
    
    @pytest.mark.unit
    def test_album_bonus_effect(self):
        """Test that album bonus properly affects score."""
        service = RatingService()
        
        ratings = [0.67, 0.67, 0.67]
        tracks = [Mock(track_rating=r) for r in ratings]
        
        # Test with different bonus values
        bonuses = [0.1, 0.2, 0.33, 0.4]
        scores = []
        
        for bonus in bonuses:
            album = Mock(tracks=tracks, album_bonus=bonus)
            score = service.calculate_album_score(album)
            scores.append(score)
        
        # Scores should increase with bonus
        assert scores == sorted(scores)
        assert scores[0] < scores[-1]


class TestTrackRating:
    """Test individual track rating functionality."""
    
    @pytest.mark.unit
    def test_rate_track_valid_values(self, db_session, created_track):
        """Test rating a track with valid values."""
        service = RatingService()
        valid_ratings = [0.0, 0.33, 0.67, 1.0]
        
        for rating in valid_ratings:
            result = service.rate_track(created_track.id, rating, db_session)
            
            assert result["success"] is True
            assert result["track_id"] == created_track.id
            assert result["track_rating"] == rating
            assert "completion_percentage" in result
    
    @pytest.mark.unit
    def test_rate_track_invalid_value(self, db_session, created_track):
        """Test that invalid rating values are rejected."""
        service = RatingService()
        invalid_ratings = [0.5, 0.25, 1.5, -1.0, 2.0]
        
        for rating in invalid_ratings:
            with pytest.raises(ValueError):
                service.rate_track(created_track.id, rating, db_session)
    
    @pytest.mark.unit
    def test_rate_nonexistent_track(self, db_session):
        """Test rating a track that doesn't exist."""
        service = RatingService()
        
        with pytest.raises(Exception):  # Should raise when track not found
            service.rate_track(99999, 0.67, db_session)
    
    @pytest.mark.unit
    def test_track_rating_updates_completion(self, db_session, album_with_tracks):
        """Test that rating tracks updates completion percentage."""
        service = RatingService()
        album = album_with_tracks
        tracks = album.tracks
        
        # Rate half the tracks
        for i, track in enumerate(tracks[:5]):
            result = service.rate_track(track.id, 0.67, db_session)
            expected_percentage = ((i + 1) / 10) * 100
            assert result["completion_percentage"] == pytest.approx(expected_percentage, rel=1)
        
        # Rate remaining tracks
        for i, track in enumerate(tracks[5:], start=5):
            result = service.rate_track(track.id, 0.67, db_session)
            expected_percentage = ((i + 1) / 10) * 100
            assert result["completion_percentage"] == pytest.approx(expected_percentage, rel=1)


class TestAlbumCompletion:
    """Test album rating completion and submission."""
    
    @pytest.mark.unit
    def test_submit_completed_album(self, db_session, album_with_tracks):
        """Test submitting a fully rated album."""
        service = RatingService()
        album = album_with_tracks
        
        # Rate all tracks
        for track in album.tracks:
            service.rate_track(track.id, 0.67, db_session)
        
        # Submit album
        result = service.submit_album_rating(album.id, db_session)
        
        assert result["success"] is True
        assert result["is_rated"] is True
        assert result["rating_score"] is not None
        assert 60 <= result["rating_score"] <= 80  # Expected range for 0.67 ratings
    
    @pytest.mark.unit
    def test_submit_incomplete_album(self, db_session, album_with_tracks):
        """Test that submitting incomplete album fails."""
        service = RatingService()
        album = album_with_tracks
        
        # Rate only some tracks
        for track in album.tracks[:3]:
            service.rate_track(track.id, 0.67, db_session)
        
        # Try to submit album
        with pytest.raises(ValueError, match="incomplete"):
            service.submit_album_rating(album.id, db_session)
    
    @pytest.mark.unit
    def test_check_album_completion(self, db_session, album_with_tracks):
        """Test checking if album rating is complete."""
        service = RatingService()
        album = album_with_tracks
        
        # Initially incomplete
        assert service.is_album_complete(album) is False
        
        # Rate all tracks
        for track in album.tracks:
            track.track_rating = 0.67
        db_session.commit()
        
        # Now complete
        assert service.is_album_complete(album) is True
    
    @pytest.mark.unit
    def test_get_album_progress(self, db_session, album_with_tracks):
        """Test getting album rating progress."""
        service = RatingService()
        album = album_with_tracks
        
        # No tracks rated
        progress = service.get_album_progress(album)
        assert progress["rated_tracks"] == 0
        assert progress["total_tracks"] == 10
        assert progress["percentage"] == 0
        
        # Rate some tracks
        for track in album.tracks[:4]:
            track.track_rating = 0.67
        db_session.commit()
        
        progress = service.get_album_progress(album)
        assert progress["rated_tracks"] == 4
        assert progress["total_tracks"] == 10
        assert progress["percentage"] == 40