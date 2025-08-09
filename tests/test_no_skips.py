"""
Unit tests for the no-skips functionality
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session

from app.reporting_service import ReportingService
from app.models import Album, Track, Artist
from app.exceptions import TracklistException


class TestNoSkipsFeature:
    """Test cases for no-skips album detection"""
    
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
        return Artist(
            id=1,
            name="Test Artist",
            musicbrainz_id="artist-mb-123"
        )
    
    @pytest.fixture
    def no_skip_album(self, sample_artist):
        """Create album with no skip-worthy tracks (all Good or Standout)"""
        album = Album(
            id=1,
            artist_id=1,
            artist=sample_artist,
            name="Perfect Album",
            release_year=2024,
            musicbrainz_id="album-mb-1",
            rating_score=92,
            is_rated=True,
            rated_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        )
        album.tracks = [
            Track(id=1, album_id=1, track_number=1, name="Track 1", track_rating=1.0),   # Standout
            Track(id=2, album_id=1, track_number=2, name="Track 2", track_rating=0.67),  # Good
            Track(id=3, album_id=1, track_number=3, name="Track 3", track_rating=1.0),   # Standout
            Track(id=4, album_id=1, track_number=4, name="Track 4", track_rating=0.67),  # Good
        ]
        return album
    
    @pytest.fixture
    def album_with_skips(self, sample_artist):
        """Create album with some skip-worthy tracks"""
        album = Album(
            id=2,
            artist_id=1,
            artist=sample_artist,
            name="Mixed Album",
            release_year=2024,
            musicbrainz_id="album-mb-2",
            rating_score=75,
            is_rated=True,
            rated_at=datetime(2024, 1, 14, 9, 0, 0, tzinfo=timezone.utc)
        )
        album.tracks = [
            Track(id=5, album_id=2, track_number=1, name="Track 1", track_rating=1.0),   # Standout
            Track(id=6, album_id=2, track_number=2, name="Track 2", track_rating=0.33),  # Filler (skip-worthy)
            Track(id=7, album_id=2, track_number=3, name="Track 3", track_rating=0.67),  # Good
            Track(id=8, album_id=2, track_number=4, name="Track 4", track_rating=0.0),   # Skip (skip-worthy)
        ]
        return album
    
    @pytest.fixture
    def album_all_standout(self, sample_artist):
        """Create album with all Standout tracks"""
        album = Album(
            id=3,
            artist_id=1,
            artist=sample_artist,
            name="Masterpiece",
            release_year=2024,
            musicbrainz_id="album-mb-3",
            rating_score=100,
            is_rated=True,
            rated_at=datetime(2024, 1, 16, 14, 20, 0, tzinfo=timezone.utc)
        )
        album.tracks = [
            Track(id=9, album_id=3, track_number=1, name="Track 1", track_rating=1.0),
            Track(id=10, album_id=3, track_number=2, name="Track 2", track_rating=1.0),
            Track(id=11, album_id=3, track_number=3, name="Track 3", track_rating=1.0),
        ]
        return album
    
    def test_get_no_skip_albums_basic(self, service, mock_db, no_skip_album, album_with_skips, album_all_standout):
        """Test basic no-skip album detection"""
        # Setup mock query with options for eager loading
        mock_query = MagicMock()
        mock_query.filter.return_value.options.return_value.options.return_value.all.return_value = [
            no_skip_album,
            album_with_skips,
            album_all_standout
        ]
        mock_db.query.return_value = mock_query
        
        # Execute with randomize=False for predictable results
        result = service.get_no_skip_albums(mock_db, randomize=False)
        
        # Verify results
        assert result["total_count"] == 2  # Only no_skip_album and album_all_standout
        assert result["percentage"] == 66.7  # 2 out of 3 albums (66.7%)
        assert result["total_rated_albums"] == 3
        assert len(result["albums"]) == 2
        
        # Verify correct albums were selected (sorted by score)
        assert result["albums"][0]["name"] == "Masterpiece"  # Score 100
        assert result["albums"][0]["score"] == 100
        assert result["albums"][1]["name"] == "Perfect Album"  # Score 92
        assert result["albums"][1]["score"] == 92
    
    def test_get_no_skip_albums_with_limit(self, service, mock_db, no_skip_album, album_all_standout):
        """Test no-skip albums with limit"""
        # Setup mock query with options for eager loading
        mock_query = MagicMock()
        mock_query.filter.return_value.options.return_value.options.return_value.all.return_value = [
            no_skip_album,
            album_all_standout
        ]
        mock_db.query.return_value = mock_query
        
        # Execute with limit and no randomization for predictable results
        result = service.get_no_skip_albums(mock_db, limit=1, randomize=False)
        
        # Verify results
        assert len(result["albums"]) == 1
        assert result["albums"][0]["name"] == "Masterpiece"  # Highest score
        assert result["total_count"] == 2  # Total count is still 2
        assert result["percentage"] == 100.0  # 2 out of 2 albums
    
    def test_get_no_skip_albums_randomization(self, service, mock_db, no_skip_album, album_with_skips, album_all_standout):
        """Test that randomization works"""
        # Create more albums for better randomization test
        albums = [no_skip_album, album_all_standout]
        for i in range(5, 10):
            album = Album(
                id=i,
                artist=no_skip_album.artist,
                name=f"No Skip Album {i}",
                is_rated=True,
                rating_score=80 + i
            )
            album.tracks = [
                Track(track_rating=0.67),
                Track(track_rating=1.0)
            ]
            albums.append(album)
        
        # Setup mock query with options for eager loading
        mock_query = MagicMock()
        mock_query.filter.return_value.options.return_value.options.return_value.all.return_value = albums
        mock_db.query.return_value = mock_query
        
        # Execute multiple times with randomization
        seen_ids = set()
        for _ in range(5):
            result = service.get_no_skip_albums(mock_db, limit=2, randomize=True)
            for album in result["albums"]:
                seen_ids.add(album["id"])
        
        # With randomization and multiple calls, we should see more than 2 different albums
        assert len(seen_ids) > 2
    
    def test_get_no_skip_albums_empty(self, service, mock_db):
        """Test no-skip albums when no albums exist"""
        # Setup mock query with options for eager loading
        mock_query = MagicMock()
        mock_query.filter.return_value.options.return_value.options.return_value.all.return_value = []
        mock_db.query.return_value = mock_query
        
        # Execute
        result = service.get_no_skip_albums(mock_db)
        
        # Verify results
        assert result["total_count"] == 0
        assert result["percentage"] == 0
        assert result["total_rated_albums"] == 0
        assert len(result["albums"]) == 0
    
    def test_get_no_skip_albums_all_have_skips(self, service, mock_db, album_with_skips):
        """Test when all albums have skip-worthy tracks"""
        # Setup mock query
        mock_db.query.return_value.filter.return_value.all.return_value = [album_with_skips]
        
        # Execute
        result = service.get_no_skip_albums(mock_db)
        
        # Verify results
        assert result["total_count"] == 0
        assert result["percentage"] == 0
        assert result["total_rated_albums"] == 1
        assert len(result["albums"]) == 0
    
    def test_no_skip_detection_logic(self, service, sample_artist):
        """Test the skip detection logic for various track ratings"""
        # Album with one Filler track (should have skips)
        album1 = Album(id=1, artist=sample_artist, name="Album 1", is_rated=True, rating_score=80)
        album1.tracks = [
            Track(track_rating=1.0),
            Track(track_rating=0.33),  # Filler - skip-worthy
            Track(track_rating=0.67)
        ]
        
        # Album with one Skip track (should have skips)
        album2 = Album(id=2, artist=sample_artist, name="Album 2", is_rated=True, rating_score=75)
        album2.tracks = [
            Track(track_rating=1.0),
            Track(track_rating=0.0),   # Skip - skip-worthy
            Track(track_rating=0.67)
        ]
        
        # Album with only Good and Standout (no skips)
        album3 = Album(id=3, artist=sample_artist, name="Album 3", is_rated=True, rating_score=90)
        album3.tracks = [
            Track(track_rating=1.0),
            Track(track_rating=0.67),
            Track(track_rating=0.67)
        ]
        
        # Test each album
        has_skips_1 = any(t.track_rating is not None and t.track_rating < 0.67 for t in album1.tracks)
        has_skips_2 = any(t.track_rating is not None and t.track_rating < 0.67 for t in album2.tracks)
        has_skips_3 = any(t.track_rating is not None and t.track_rating < 0.67 for t in album3.tracks)
        
        assert has_skips_1 == True   # Has Filler
        assert has_skips_2 == True   # Has Skip
        assert has_skips_3 == False  # No skips
    
    def test_cache_usage(self, service, mock_db, no_skip_album):
        """Test that caching works for no-skip albums"""
        # Setup mock query
        mock_db.query.return_value.filter.return_value.all.return_value = [no_skip_album]
        
        # First call with randomize=False - should hit database and cache
        result1 = service.get_no_skip_albums(mock_db, limit=5, randomize=False)
        
        # Reset mock
        mock_db.reset_mock()
        
        # Second call with same parameters - should use cache
        result2 = service.get_no_skip_albums(mock_db, limit=5, randomize=False)
        
        # Verify cache was used (database not queried)
        mock_db.query.assert_not_called()
        
        # Results should be the same
        assert result1 == result2
        
        # Reset mock again
        mock_db.reset_mock()
        mock_db.query.return_value.filter.return_value.all.return_value = [no_skip_album]
        
        # Call with randomize=True - should NOT use cache
        result3 = service.get_no_skip_albums(mock_db, limit=5, randomize=True)
        
        # Verify database was queried (not cached)
        mock_db.query.assert_called()
    
    def test_album_formatting(self, service, mock_db, no_skip_album):
        """Test album data formatting in results"""
        # Execute
        formatted = service._format_album_with_details(no_skip_album, mock_db)
        
        # Verify formatted data
        assert formatted["id"] == 1
        assert formatted["name"] == "Perfect Album"
        assert formatted["artist"] == "Test Artist"
        assert formatted["year"] == 2024
        assert formatted["score"] == 92
        assert formatted["total_tracks"] == 4
        assert formatted["musicbrainz_id"] == "album-mb-1"
        assert "average_track_rating" in formatted
        assert "rated_at" in formatted
    
    def test_error_handling(self, service, mock_db):
        """Test error handling in no-skip albums"""
        # Setup mock to raise exception
        mock_db.query.side_effect = Exception("Database error")
        
        # Execute and verify exception
        with pytest.raises(TracklistException) as exc_info:
            service.get_no_skip_albums(mock_db)
        
        assert "Failed to get no-skip albums" in str(exc_info.value)