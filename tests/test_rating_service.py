import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.rating_service import RatingService, RatingCalculator, get_rating_service
from app.models import Artist, Album, Track, UserSettings
from app.exceptions import ServiceNotFoundError, ServiceValidationError, TracklistException


class TestRatingCalculator:
    """Test the RatingCalculator class"""
    
    def test_calculate_album_score_basic(self):
        """Test basic album score calculation"""
        track_ratings = [1.0, 0.67, 0.33, 1.0]  # Average = 0.75
        result = RatingCalculator.calculate_album_score(track_ratings, 0.25)
        
        # (0.75 * 10) + 0.25 = 7.75, floor = 7, * 10 = 70
        assert result == 70
    
    def test_calculate_album_score_edge_cases(self):
        """Test album score calculation edge cases"""
        # Empty ratings
        assert RatingCalculator.calculate_album_score([], 0.25) == 0
        
        # All perfect ratings
        track_ratings = [1.0, 1.0, 1.0, 1.0]
        result = RatingCalculator.calculate_album_score(track_ratings, 0.25)
        # (1.0 * 10) + 0.25 = 10.25, floor = 10, * 10 = 100
        assert result == 100
        
        # All worst ratings
        track_ratings = [0.0, 0.0, 0.0, 0.0]
        result = RatingCalculator.calculate_album_score(track_ratings, 0.25)
        # (0.0 * 10) + 0.25 = 0.25, floor = 0, * 10 = 0
        assert result == 0
    
    def test_calculate_album_score_bonus_limits(self):
        """Test album bonus is clamped to valid range"""
        track_ratings = [1.0, 1.0, 1.0, 1.0]
        
        # Below minimum (should use 0.1)
        result = RatingCalculator.calculate_album_score(track_ratings, 0.05)
        # (1.0 * 10) + 0.1 = 10.1, floor = 10, * 10 = 100
        assert result == 100
        
        # Above maximum (should use 0.4)
        result = RatingCalculator.calculate_album_score(track_ratings, 0.5)
        # (1.0 * 10) + 0.4 = 10.4, floor = 10, * 10 = 100
        assert result == 100
    
    def test_get_completion_percentage(self):
        """Test completion percentage calculation"""
        assert RatingCalculator.get_completion_percentage(10, 5) == 50.0
        assert RatingCalculator.get_completion_percentage(10, 10) == 100.0
        assert RatingCalculator.get_completion_percentage(10, 0) == 0.0
        assert RatingCalculator.get_completion_percentage(0, 0) == 100.0
    
    def test_get_projected_score(self):
        """Test projected score calculation"""
        # No ratings yet
        track_ratings = [None, None, None, None]
        assert RatingCalculator.get_projected_score(track_ratings) is None
        
        # Partial ratings
        track_ratings = [1.0, 0.67, None, None]
        result = RatingCalculator.get_projected_score(track_ratings, 0.25)
        # Only uses rated tracks: [1.0, 0.67], average = 0.835
        # (0.835 * 10) + 0.25 = 8.6, floor = 8, * 10 = 80
        assert result == 80


class TestRatingService:
    """Test the RatingService class"""
    
    def setup_method(self):
        """Setup for each test"""
        self.service = RatingService()
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()
        db.query.return_value = db
        db.filter.return_value = db
        db.first.return_value = None
        db.add = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        db.flush = MagicMock()
        return db
    
    @pytest.fixture
    def mock_album(self):
        """Mock album object"""
        album = MagicMock()
        album.id = 1
        album.name = "Test Album"
        album.musicbrainz_id = "test-mb-id"
        album.total_tracks = 4
        album.album_bonus = 0.25
        album.is_rated = False
        album.rating_score = None
        album.rated_at = None
        album.created_at = datetime.now(timezone.utc)
        
        # Mock artist
        artist = MagicMock()
        artist.name = "Test Artist"
        artist.musicbrainz_id = "test-artist-mb-id"
        album.artist = artist
        
        return album
    
    @pytest.fixture
    def mock_tracks(self):
        """Mock track objects"""
        tracks = []
        for i in range(4):
            track = MagicMock()
            track.id = i + 1
            track.album_id = 1
            track.track_number = i + 1
            track.name = f"Track {i + 1}"
            track.track_rating = None
            tracks.append(track)
        return tracks
    
    @pytest.mark.asyncio
    async def test_create_album_for_rating_new_album(self, mock_db):
        """Test creating new album for rating"""
        mock_mb_service = AsyncMock()
        mock_mb_album = {
            "title": "Test Album",
            "artist": {"name": "Test Artist", "musicbrainz_id": "artist-mb-id"},
            "year": 2023,
            "country": "US",
            "total_tracks": 2,
            "total_duration_ms": 180000,
            "tracks": [
                {"track_number": 1, "title": "Track 1", "duration_ms": 90000},
                {"track_number": 2, "title": "Track 2", "duration_ms": 90000}
            ]
        }
        mock_mb_service.get_album_details.return_value = mock_mb_album
        
        # Mock database responses
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing album
        
        # Mock user settings
        mock_settings = MagicMock()
        mock_settings.album_bonus = 0.30
        mock_db.query.return_value.filter.return_value.first.side_effect = [None, mock_settings]
        
        # Mock artist creation
        mock_artist = MagicMock()
        mock_artist.id = 1
        mock_artist.name = "Test Artist"
        
        with patch.object(self.service, 'musicbrainz_service', mock_mb_service):
            with patch.object(self.service, '_create_or_get_artist', return_value=mock_artist):
                with patch.object(self.service, '_format_album_response', return_value={"id": 1, "title": "Test Album"}):
                    result = await self.service.create_album_for_rating("test-mb-id", mock_db)
        
        assert result["id"] == 1
        assert result["title"] == "Test Album"
        mock_db.add.assert_called()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_album_for_rating_existing_album(self, mock_db, mock_album):
        """Test returning existing album"""
        mock_mb_service = AsyncMock()
        
        # Mock existing album found
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        
        with patch.object(self.service, 'musicbrainz_service', mock_mb_service):
            with patch.object(self.service, '_format_album_response', return_value={"id": 1, "title": "Test Album"}):
                result = await self.service.create_album_for_rating("test-mb-id", mock_db)
        
        assert result["id"] == 1
        mock_mb_service.get_album_details.assert_not_called()
        mock_db.add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_create_album_for_rating_musicbrainz_error(self, mock_db):
        """Test handling MusicBrainz service error"""
        mock_mb_service = AsyncMock()
        mock_mb_service.get_album_details.side_effect = TracklistException("MusicBrainz error")
        
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing album
        
        with patch.object(self.service, 'musicbrainz_service', mock_mb_service):
            with pytest.raises(TracklistException):
                await self.service.create_album_for_rating("test-mb-id", mock_db)
        
        mock_db.rollback.assert_called_once()
    
    def test_rate_track_success(self, mock_db, mock_tracks):
        """Test successful track rating"""
        track = mock_tracks[0]
        mock_db.query.return_value.filter.return_value.first.side_effect = [track, MagicMock()]
        
        with patch.object(self.service, 'get_album_progress', return_value={"completion_percentage": 25.0}):
            result = self.service.rate_track(1, 0.67, mock_db)
        
        assert track.track_rating == 0.67
        assert result["completion_percentage"] == 25.0
        mock_db.commit.assert_called_once()
    
    def test_rate_track_invalid_rating(self, mock_db):
        """Test rating track with invalid rating"""
        with pytest.raises(ServiceValidationError) as exc_info:
            self.service.rate_track(1, 0.5, mock_db)  # Invalid rating
        
        assert "Invalid rating" in str(exc_info.value.message)
        mock_db.commit.assert_not_called()
    
    def test_rate_track_not_found(self, mock_db):
        """Test rating non-existent track"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(ServiceNotFoundError):
            self.service.rate_track(999, 1.0, mock_db)
    
    def test_get_album_progress(self, mock_db, mock_album, mock_tracks):
        """Test getting album progress"""
        # Set some ratings
        mock_tracks[0].track_rating = 1.0
        mock_tracks[1].track_rating = 0.67
        mock_tracks[2].track_rating = None
        mock_tracks[3].track_rating = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_tracks
        
        result = self.service.get_album_progress(1, mock_db)
        
        assert result["album_id"] == 1
        assert result["album_title"] == "Test Album"
        assert result["total_tracks"] == 4
        assert result["rated_tracks"] == 2
        assert result["completion_percentage"] == 50.0
        assert result["is_complete"] is False
        assert result["projected_score"] == 80  # Based on [1.0, 0.67] average
        assert result["is_submitted"] is False
    
    def test_get_album_progress_not_found(self, mock_db):
        """Test getting progress for non-existent album"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(ServiceNotFoundError):
            self.service.get_album_progress(999, mock_db)
    
    def test_submit_album_rating_success(self, mock_db, mock_album, mock_tracks):
        """Test successful album rating submission"""
        # Set all track ratings
        for i, track in enumerate(mock_tracks):
            track.track_rating = [1.0, 0.67, 0.33, 1.0][i]
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_tracks
        
        with patch.object(self.service, '_format_album_response', return_value={"id": 1, "rating_score": 70}):
            result = self.service.submit_album_rating(1, mock_db)
        
        assert mock_album.rating_score == 70
        assert mock_album.is_rated is True
        assert mock_album.rated_at is not None
        assert result["rating_score"] == 70
        mock_db.commit.assert_called_once()
    
    def test_submit_album_rating_incomplete(self, mock_db, mock_album, mock_tracks):
        """Test submitting incomplete album rating"""
        # Leave some tracks unrated
        mock_tracks[0].track_rating = 1.0
        mock_tracks[1].track_rating = None  # Unrated
        mock_tracks[2].track_rating = 0.67
        mock_tracks[3].track_rating = None  # Unrated
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_tracks
        
        with pytest.raises(ServiceValidationError) as exc_info:
            self.service.submit_album_rating(1, mock_db)
        
        assert "Cannot submit incomplete rating" in str(exc_info.value.message)
        assert "2, 4" in str(exc_info.value.message)  # Unrated track numbers
        mock_db.commit.assert_not_called()
    
    def test_submit_album_rating_already_submitted(self, mock_db, mock_album):
        """Test submitting already submitted album"""
        mock_album.is_rated = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        
        with patch.object(self.service, '_format_album_response', return_value={"id": 1, "already_submitted": True}):
            result = self.service.submit_album_rating(1, mock_db)
        
        assert result["already_submitted"] is True
        # Should not recalculate score
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.assert_not_called()
    
    def test_get_album_rating(self, mock_db, mock_album):
        """Test getting complete album rating"""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_album
        
        with patch.object(self.service, '_format_album_response', return_value={"id": 1, "with_tracks": True}):
            result = self.service.get_album_rating(1, mock_db)
        
        assert result["with_tracks"] is True
    
    def test_get_user_albums(self, mock_db):
        """Test getting user's albums"""
        mock_albums = [MagicMock(), MagicMock()]
        mock_db.query.return_value.join.return_value = mock_db
        mock_db.count.return_value = 10
        mock_db.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_albums
        
        with patch.object(self.service, '_format_album_summary', return_value={"id": 1}):
            result = self.service.get_user_albums(mock_db, limit=5, offset=0)
        
        assert result["total"] == 10
        assert result["limit"] == 5
        assert result["offset"] == 0
        assert result["has_more"] is True
        assert len(result["albums"]) == 2
    
    def test_get_user_albums_filtered(self, mock_db):
        """Test getting user's albums with filter"""
        mock_albums = [MagicMock()]
        mock_db.query.return_value.join.return_value = mock_db
        mock_db.filter.return_value = mock_db
        mock_db.count.return_value = 5
        mock_db.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_albums
        
        with patch.object(self.service, '_format_album_summary', return_value={"id": 1}):
            result = self.service.get_user_albums(mock_db, filter_rated=True)
        
        mock_db.filter.assert_called_once()  # Should filter by is_rated
        assert len(result["albums"]) == 1
    
    def test_create_or_get_artist_existing_by_mbid(self, mock_db):
        """Test getting existing artist by MusicBrainz ID"""
        mock_artist = MagicMock()
        mock_artist.name = "Test Artist"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_artist
        
        result = self.service._create_or_get_artist("Test Artist", "mb-id", mock_db)
        
        assert result == mock_artist
        mock_db.add.assert_not_called()
    
    def test_create_or_get_artist_existing_by_name(self, mock_db):
        """Test getting existing artist by name"""
        mock_artist = MagicMock()
        mock_artist.name = "Test Artist"
        mock_db.query.return_value.filter.return_value.first.side_effect = [None, mock_artist]
        
        result = self.service._create_or_get_artist("Test Artist", "mb-id", mock_db)
        
        assert result == mock_artist
        mock_db.add.assert_not_called()
    
    def test_create_or_get_artist_new(self, mock_db):
        """Test creating new artist"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = self.service._create_or_get_artist("New Artist", "mb-id", mock_db)
        
        assert result.name == "New Artist"
        assert result.musicbrainz_id == "mb-id"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()


def test_get_rating_service():
    """Test the rating service factory function"""
    service = get_rating_service()
    assert isinstance(service, RatingService)