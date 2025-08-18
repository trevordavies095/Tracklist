"""
Tests for the album comparison service
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from app.services.comparison_service import ComparisonService, DIFFERENCE_THRESHOLDS
from app.models import Album, Artist, Track
from app.exceptions import ServiceValidationError, ServiceNotFoundError


class TestComparisonService:
    """Test cases for ComparisonService"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.service = ComparisonService()
        self.mock_db = Mock()
        
        # Create test artist
        self.test_artist = Artist(
            id=1,
            name="Test Artist",
            musicbrainz_id="test-artist-id"
        )
        
        # Create test albums
        self.album1 = Album(
            id=1,
            artist_id=1,
            name="Test Album 1",
            rating_score=75,
            is_rated=True,
            total_tracks=3,
            musicbrainz_id="album1-id"
        )
        self.album1.artist = self.test_artist
        
        self.album2 = Album(
            id=2,
            artist_id=1,
            name="Test Album 2", 
            rating_score=80,
            is_rated=True,
            total_tracks=3,
            musicbrainz_id="album2-id"
        )
        self.album2.artist = self.test_artist
        
        # Create test tracks for album 1
        self.tracks1 = [
            Track(id=1, album_id=1, track_number=1, name="Track 1", track_rating=0.67),
            Track(id=2, album_id=1, track_number=2, name="Track 2", track_rating=1.0),
            Track(id=3, album_id=1, track_number=3, name="Track 3", track_rating=0.33)
        ]
        self.album1.tracks = self.tracks1
        
        # Create test tracks for album 2
        self.tracks2 = [
            Track(id=4, album_id=2, track_number=1, name="Track A", track_rating=1.0),
            Track(id=5, album_id=2, track_number=2, name="Track B", track_rating=0.67),
            Track(id=6, album_id=2, track_number=3, name="Track C", track_rating=1.0)
        ]
        self.album2.tracks = self.tracks2
    
    def test_validate_comparison_request_same_album(self):
        """Test validation rejects same album comparison"""
        with pytest.raises(ServiceValidationError) as exc_info:
            self.service._validate_comparison_request(1, 1)
        
        assert "Cannot compare an album to itself" in str(exc_info.value)
    
    def test_validate_comparison_request_invalid_ids(self):
        """Test validation rejects invalid album IDs"""
        with pytest.raises(ServiceValidationError) as exc_info:
            self.service._validate_comparison_request(0, 1)
        
        assert "Invalid album IDs" in str(exc_info.value)
        
        with pytest.raises(ServiceValidationError) as exc_info:
            self.service._validate_comparison_request(1, -1)
        
        assert "Invalid album IDs" in str(exc_info.value)
    
    def test_get_cache_key_consistent_ordering(self):
        """Test cache key is consistent regardless of album order"""
        key1 = self.service._get_cache_key(1, 2)
        key2 = self.service._get_cache_key(2, 1)
        
        assert key1 == key2
        assert key1 == "comparison:1:2"
    
    def test_categorize_difference(self):
        """Test rating difference categorization"""
        # Test significant difference
        assert self.service._categorize_difference(0.35) == 'significant'
        assert self.service._categorize_difference(-0.40) == 'significant'
        
        # Test moderate difference
        assert self.service._categorize_difference(0.25) == 'moderate'
        assert self.service._categorize_difference(-0.20) == 'moderate'
        
        # Test slight difference
        assert self.service._categorize_difference(0.15) == 'slight'
        assert self.service._categorize_difference(-0.10) == 'slight'
        
        # Test tie
        assert self.service._categorize_difference(0.03) == 'tie'
        assert self.service._categorize_difference(-0.02) == 'tie'
        assert self.service._categorize_difference(0.0) == 'tie'
    
    def test_align_tracks_equal_length(self):
        """Test track alignment with equal length albums"""
        aligned = self.service._align_tracks(self.tracks1, self.tracks2)
        
        assert len(aligned) == 3
        for i, (track1, track2) in enumerate(aligned):
            assert track1.track_number == i + 1
            assert track2.track_number == i + 1
    
    def test_align_tracks_different_lengths(self):
        """Test track alignment with different length albums"""
        # Album with fewer tracks
        short_tracks = self.tracks1[:2]
        aligned = self.service._align_tracks(short_tracks, self.tracks2)
        
        assert len(aligned) == 3
        assert aligned[0][0] is not None and aligned[0][1] is not None
        assert aligned[1][0] is not None and aligned[1][1] is not None
        assert aligned[2][0] is None and aligned[2][1] is not None
    
    def test_get_track_comparison_matrix(self):
        """Test track comparison matrix generation"""
        matrix = self.service._get_track_comparison_matrix(self.tracks1, self.tracks2)
        
        assert len(matrix) == 3
        
        # Check first track comparison (0.67 vs 1.0 = -0.33 difference)
        track1_comparison = matrix[0]
        assert track1_comparison["track_number"] == 1
        assert track1_comparison["album1_track"]["rating"] == 0.67
        assert track1_comparison["album2_track"]["rating"] == 1.0
        assert track1_comparison["rating_difference"] == -0.33
        assert track1_comparison["better_album"] == "album2"
        assert track1_comparison["difference_category"] == "moderate"
        
        # Check second track comparison (1.0 vs 0.67 = 0.33 difference)
        track2_comparison = matrix[1]
        assert track2_comparison["rating_difference"] == 0.33
        assert track2_comparison["better_album"] == "album1"
    
    def test_calculate_comparison_statistics(self):
        """Test comparison statistics calculation"""
        matrix = self.service._get_track_comparison_matrix(self.tracks1, self.tracks2)
        stats = self.service._calculate_comparison_statistics(self.album1, self.album2, matrix)
        
        # Check winner (album2 has higher score: 80 vs 75)
        assert stats["winner"]["album"] == "album2"
        assert stats["winner"]["score_difference"] == -5
        
        # Check track wins (should be calculated based on matrix)
        assert "track_wins" in stats
        assert stats["track_wins"]["album1_wins"] == 1  # Track 2
        assert stats["track_wins"]["album2_wins"] == 2  # Tracks 1 and 3
        assert stats["track_wins"]["ties"] == 0
        
        # Check average ratings
        assert "average_ratings" in stats
        assert stats["average_ratings"]["album1"] == 0.667  # (0.67 + 1.0 + 0.33) / 3
        assert stats["average_ratings"]["album2"] == 0.889  # (1.0 + 0.67 + 1.0) / 3
        
        # Check rating differences
        assert "rating_differences" in stats
        assert len(matrix) == 3  # We should have differences for all tracks
    
    def test_identify_better_tracks(self):
        """Test identification of significantly better tracks"""
        matrix = self.service._get_track_comparison_matrix(self.tracks1, self.tracks2)
        better_tracks = self.service._identify_better_tracks(matrix, threshold=0.30)
        
        # Track 1: 0.67 vs 1.0 = -0.33 (album2 better)
        # Track 2: 1.0 vs 0.67 = 0.33 (album1 better)  
        # Track 3: 0.33 vs 1.0 = -0.67 (album2 better)
        
        assert len(better_tracks["album1_significantly_better"]) == 1
        assert len(better_tracks["album2_significantly_better"]) == 2
        
        # Check specific track data
        album1_better = better_tracks["album1_significantly_better"][0]
        assert album1_better["track_number"] == 2
        assert album1_better["track_name"] == "Track 2"
    
    @patch('app.services.comparison_service.ComparisonService._get_albums_for_comparison')
    def test_compare_albums_success(self, mock_get_albums):
        """Test successful album comparison"""
        # Mock the album retrieval
        mock_get_albums.return_value = (self.album1, self.album2)
        
        # Mock template utils
        with patch('app.services.comparison_service.get_artwork_url') as mock_artwork:
            mock_artwork.return_value = "http://example.com/cover.jpg"
            
            result = self.service.compare_albums(1, 2, self.mock_db)
        
        # Verify structure
        assert "albums" in result
        assert "track_comparison" in result
        assert "statistics" in result
        assert "better_tracks" in result
        assert "insights" in result
        
        # Verify album data
        assert result["albums"]["album1"]["name"] == "Test Album 1"
        assert result["albums"]["album2"]["name"] == "Test Album 2"
        
        # Verify track comparison
        assert len(result["track_comparison"]) == 3
        
        # Verify statistics
        assert result["statistics"]["winner"]["album"] == "album2"
    
    @patch('app.services.comparison_service.ComparisonService._get_albums_for_comparison')
    def test_compare_albums_not_found(self, mock_get_albums):
        """Test comparison with non-existent albums"""
        mock_get_albums.side_effect = ServiceNotFoundError("Albums not found")
        
        with pytest.raises(ServiceNotFoundError):
            self.service.compare_albums(1, 999, self.mock_db)
    
    def test_get_user_rated_albums(self):
        """Test getting rated albums for selection"""
        # Mock database query
        mock_query = Mock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [self.album1, self.album2]
        
        self.mock_db.query.return_value = mock_query
        
        albums = self.service.get_user_rated_albums(self.mock_db)
        
        assert len(albums) == 2
        assert albums[0]["name"] == "Test Album 1"
        assert albums[0]["artist"] == "Test Artist"
        assert albums[0]["score"] == 75
        assert albums[1]["score"] == 80


class TestComparisonHelpers:
    """Test helper functions and edge cases"""
    
    def test_difference_thresholds_constants(self):
        """Test that difference thresholds are properly defined"""
        assert DIFFERENCE_THRESHOLDS['significant'] == 0.34
        assert DIFFERENCE_THRESHOLDS['moderate'] == 0.20
        assert DIFFERENCE_THRESHOLDS['slight'] == 0.10
        assert DIFFERENCE_THRESHOLDS['tie'] == 0.05
    
    def test_comparison_with_unrated_tracks(self):
        """Test comparison with albums containing unrated tracks"""
        service = ComparisonService()
        
        # Create tracks with some unrated
        tracks1 = [
            Track(id=1, album_id=1, track_number=1, name="Track 1", track_rating=0.67),
            Track(id=2, album_id=1, track_number=2, name="Track 2", track_rating=None),
        ]
        
        tracks2 = [
            Track(id=3, album_id=2, track_number=1, name="Track A", track_rating=1.0),
            Track(id=4, album_id=2, track_number=2, name="Track B", track_rating=0.33),
        ]
        
        matrix = service._get_track_comparison_matrix(tracks1, tracks2)
        
        # First track should have comparison
        assert matrix[0]["rating_difference"] == -0.33
        
        # Second track should have no comparison (one is unrated)
        assert matrix[1]["rating_difference"] is None
        assert matrix[1]["better_album"] == "tie"
    
    def test_format_album_data(self):
        """Test album data formatting"""
        service = ComparisonService()
        
        # Create test album
        artist = Artist(id=1, name="Test Artist")
        album = Album(
            id=1,
            artist_id=1,
            name="Test Album",
            rating_score=75,
            total_tracks=3,
            release_year=2023,
            musicbrainz_id="test-id"
        )
        album.artist = artist
        album.tracks = [
            Track(track_rating=0.67),
            Track(track_rating=1.0),
            Track(track_rating=0.33)
        ]
        
        with patch('app.services.comparison_service.get_artwork_url') as mock_artwork:
            mock_artwork.return_value = "http://example.com/cover.jpg"
            
            formatted = service._format_album_data(album)
        
        assert formatted["id"] == 1
        assert formatted["name"] == "Test Album"
        assert formatted["artist"]["name"] == "Test Artist"
        assert formatted["year"] == 2023
        assert formatted["rating_score"] == 75
        assert formatted["total_tracks"] == 3
        assert formatted["average_track_rating"] == 0.667