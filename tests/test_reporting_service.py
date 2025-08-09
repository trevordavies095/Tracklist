"""
Unit tests for the reporting service
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session

from app.reporting_service import ReportingService, get_reporting_service
from app.models import Album, Track, Artist
from app.exceptions import TracklistException


class TestReportingService:
    """Test cases for ReportingService"""
    
    @pytest.fixture
    def service(self):
        """Create ReportingService instance"""
        return ReportingService()
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        return MagicMock(spec=Session)
    
    @pytest.fixture
    def sample_artist(self):
        """Create sample artist"""
        artist = Artist(
            id=1,
            name="Test Artist",
            musicbrainz_id="artist-mb-123"
        )
        return artist
    
    @pytest.fixture
    def sample_albums(self, sample_artist):
        """Create sample albums with different states"""
        # Fully rated album with high score
        album1 = Album(
            id=1,
            artist_id=1,
            artist=sample_artist,
            name="Great Album",
            release_year=2020,
            musicbrainz_id="album-mb-1",
            rating_score=85,
            is_rated=True,
            rated_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        )
        album1.tracks = [
            Track(id=1, album_id=1, track_number=1, name="Track 1", track_rating=1.0),
            Track(id=2, album_id=1, track_number=2, name="Track 2", track_rating=0.67),
            Track(id=3, album_id=1, track_number=3, name="Track 3", track_rating=1.0)
        ]
        
        # Fully rated album with medium score
        album2 = Album(
            id=2,
            artist_id=1,
            artist=sample_artist,
            name="Good Album",
            release_year=2021,
            musicbrainz_id="album-mb-2",
            rating_score=65,
            is_rated=True,
            rated_at=datetime(2024, 1, 14, 9, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 14, 9, 0, 0, tzinfo=timezone.utc)
        )
        album2.tracks = [
            Track(id=4, album_id=2, track_number=1, name="Track 1", track_rating=0.67),
            Track(id=5, album_id=2, track_number=2, name="Track 2", track_rating=0.33),
            Track(id=6, album_id=2, track_number=3, name="Track 3", track_rating=0.67)
        ]
        
        # In-progress album
        album3 = Album(
            id=3,
            artist_id=1,
            artist=sample_artist,
            name="In Progress Album",
            release_year=2022,
            musicbrainz_id="album-mb-3",
            is_rated=False,
            updated_at=datetime(2024, 1, 16, 14, 20, 0, tzinfo=timezone.utc)
        )
        album3.tracks = [
            Track(id=7, album_id=3, track_number=1, name="Track 1", track_rating=0.33),
            Track(id=8, album_id=3, track_number=2, name="Track 2", track_rating=0.0),
            Track(id=9, album_id=3, track_number=3, name="Track 3", track_rating=None),
            Track(id=10, album_id=3, track_number=4, name="Track 4", track_rating=None)
        ]
        
        # Unrated album
        album4 = Album(
            id=4,
            artist_id=1,
            artist=sample_artist,
            name="Unrated Album",
            release_year=2023,
            musicbrainz_id="album-mb-4",
            is_rated=False
        )
        album4.tracks = [
            Track(id=11, album_id=4, track_number=1, name="Track 1", track_rating=None),
            Track(id=12, album_id=4, track_number=2, name="Track 2", track_rating=None)
        ]
        
        return [album1, album2, album3, album4]
    
    def test_get_overview_statistics(self, service, mock_db, sample_albums):
        """Test getting overview statistics"""
        # Setup mock queries
        mock_db.query.return_value.count.return_value = 4  # Total albums
        
        # Mock fully rated albums query
        fully_rated_mock = MagicMock()
        fully_rated_mock.filter.return_value.all.return_value = [
            sample_albums[0], sample_albums[1]  # Two fully rated albums
        ]
        
        # Mock in-progress albums query
        in_progress_mock = MagicMock()
        in_progress_mock.join.return_value.filter.return_value.distinct.return_value.all.return_value = [
            sample_albums[2]  # One in-progress album
        ]
        
        # Setup query chain for different calls
        mock_db.query.side_effect = [
            MagicMock(count=MagicMock(return_value=4)),  # Total albums
            fully_rated_mock,  # Fully rated albums
            in_progress_mock,  # In-progress albums
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=8)))),  # Total tracks rated
            # Rating distribution queries
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=1)))),  # skip (0.0)
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=2)))),  # filler (0.33)
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=3)))),  # good (0.67)
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=2))))   # standout (1.0)
        ]
        
        # Execute
        stats = service.get_overview_statistics(mock_db)
        
        # Verify results
        assert stats["total_albums"] == 4
        assert stats["fully_rated_count"] == 2
        assert stats["in_progress_count"] == 1
        assert stats["average_album_score"] == 75.0  # (85 + 65) / 2
        assert stats["total_tracks_rated"] == 8
        assert stats["unrated_albums_count"] == 1  # 4 - 2 - 1
        assert stats["rating_distribution"]["skip"] == 1
        assert stats["rating_distribution"]["filler"] == 2
        assert stats["rating_distribution"]["good"] == 3
        assert stats["rating_distribution"]["standout"] == 2
    
    def test_get_overview_statistics_no_rated_albums(self, service, mock_db):
        """Test overview statistics when no albums are rated"""
        # Setup mock queries
        mock_db.query.return_value.count.return_value = 2  # Total albums
        
        # No fully rated albums
        fully_rated_mock = MagicMock()
        fully_rated_mock.filter.return_value.all.return_value = []
        
        # No in-progress albums
        in_progress_mock = MagicMock()
        in_progress_mock.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
        
        mock_db.query.side_effect = [
            MagicMock(count=MagicMock(return_value=2)),  # Total albums
            fully_rated_mock,  # No fully rated albums
            in_progress_mock,  # No in-progress albums
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=0)))),  # No tracks rated
            # All rating counts are 0
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=0)))),
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=0)))),
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=0)))),
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=0))))
        ]
        
        # Execute
        stats = service.get_overview_statistics(mock_db)
        
        # Verify results
        assert stats["total_albums"] == 2
        assert stats["fully_rated_count"] == 0
        assert stats["in_progress_count"] == 0
        assert stats["average_album_score"] is None
        assert stats["total_tracks_rated"] == 0
        assert stats["unrated_albums_count"] == 2
    
    def test_get_overview_statistics_error_handling(self, service, mock_db):
        """Test error handling in overview statistics"""
        # Setup mock to raise exception
        mock_db.query.side_effect = Exception("Database error")
        
        # Execute and verify exception
        with pytest.raises(TracklistException) as exc_info:
            service.get_overview_statistics(mock_db)
        
        assert "Failed to generate statistics" in str(exc_info.value)
    
    def test_get_recent_activity(self, service, mock_db, sample_albums):
        """Test getting recent activity"""
        # Mock recently rated query
        recently_rated_mock = MagicMock()
        recently_rated_mock.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            sample_albums[0], sample_albums[1]
        ]
        
        # Mock in-progress query
        in_progress_mock = MagicMock()
        in_progress_mock.join.return_value.filter.return_value.order_by.return_value.distinct.return_value.limit.return_value.all.return_value = [
            sample_albums[2]
        ]
        
        mock_db.query.side_effect = [recently_rated_mock, in_progress_mock]
        
        # Execute
        activity = service.get_recent_activity(mock_db, limit=10)
        
        # Verify results
        assert len(activity["recently_rated"]) == 2
        assert activity["recently_rated"][0]["name"] == "Great Album"
        assert activity["recently_rated"][0]["score"] == 85
        
        assert len(activity["in_progress"]) == 1
        assert activity["in_progress"][0]["name"] == "In Progress Album"
        assert activity["in_progress"][0]["progress"]["rated_tracks"] == 2
        assert activity["in_progress"][0]["progress"]["total_tracks"] == 4
        assert activity["in_progress"][0]["progress"]["percentage"] == 50.0
    
    def test_get_top_albums(self, service, mock_db, sample_albums):
        """Test getting top rated albums"""
        # Mock top albums query
        top_albums_mock = MagicMock()
        top_albums_mock.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            sample_albums[0],  # Score 85
            sample_albums[1]   # Score 65
        ]
        
        mock_db.query.return_value = top_albums_mock
        
        # Execute
        top_albums = service.get_top_albums(mock_db, limit=10)
        
        # Verify results
        assert len(top_albums) == 2
        assert top_albums[0]["name"] == "Great Album"
        assert top_albums[0]["score"] == 85
        assert top_albums[1]["name"] == "Good Album"
        assert top_albums[1]["score"] == 65
    
    def test_format_album_summary(self, service, sample_albums):
        """Test album summary formatting"""
        album = sample_albums[0]
        summary = service._format_album_summary(album)
        
        assert summary["id"] == 1
        assert summary["name"] == "Great Album"
        assert summary["artist"] == "Test Artist"
        assert summary["year"] == 2020
        assert summary["score"] == 85
        assert summary["rated_at"] == "2024-01-15T10:30:00+00:00"
    
    def test_format_album_with_progress(self, service, mock_db, sample_albums):
        """Test album formatting with progress information"""
        album = sample_albums[2]  # In-progress album
        formatted = service._format_album_with_progress(album, mock_db)
        
        assert formatted["id"] == 3
        assert formatted["name"] == "In Progress Album"
        assert formatted["progress"]["rated_tracks"] == 2
        assert formatted["progress"]["total_tracks"] == 4
        assert formatted["progress"]["percentage"] == 50.0
    
    def test_get_rating_distribution(self, service, mock_db):
        """Test getting rating distribution"""
        # Mock count queries for each rating value
        mock_db.query.side_effect = [
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=5)))),   # skip
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=10)))),  # filler
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=15)))),  # good
            MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=8))))    # standout
        ]
        
        distribution = service._get_rating_distribution(mock_db)
        
        assert distribution["skip"] == 5
        assert distribution["filler"] == 10
        assert distribution["good"] == 15
        assert distribution["standout"] == 8
    
    def test_get_rating_distribution_error_handling(self, service, mock_db):
        """Test rating distribution error handling"""
        # Mock to raise exception
        mock_db.query.side_effect = Exception("Database error")
        
        # Should return zeros on error
        distribution = service._get_rating_distribution(mock_db)
        
        assert distribution["skip"] == 0
        assert distribution["filler"] == 0
        assert distribution["good"] == 0
        assert distribution["standout"] == 0
    
    def test_singleton_instance(self):
        """Test that get_reporting_service returns singleton"""
        service1 = get_reporting_service()
        service2 = get_reporting_service()
        
        assert service1 is service2