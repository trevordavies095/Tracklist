"""
Tests for database models.
Tests model creation, relationships, and constraints.
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.models import Album, Artist, Track, UserSettings


class TestArtistModel:
    """Test Artist model functionality."""
    
    @pytest.mark.unit
    def test_create_artist(self, db_session, sample_artist_data):
        """Test creating a new artist."""
        artist = Artist(**sample_artist_data)
        db_session.add(artist)
        db_session.commit()
        
        assert artist.id is not None
        assert artist.name == sample_artist_data["name"]
        assert artist.musicbrainz_id == sample_artist_data["musicbrainz_id"]
        assert artist.created_at is not None
    
    @pytest.mark.unit
    def test_artist_album_relationship(self, db_session, created_artist, created_album):
        """Test one-to-many relationship between artist and albums."""
        # Refresh to load relationships
        db_session.refresh(created_artist)
        
        assert len(created_artist.albums) == 1
        assert created_artist.albums[0].id == created_album.id
        assert created_artist.albums[0].artist_id == created_artist.id
    
    @pytest.mark.unit
    def test_artist_unique_musicbrainz_id(self, db_session, sample_artist_data):
        """Test that musicbrainz_id must be unique."""
        artist1 = Artist(**sample_artist_data)
        db_session.add(artist1)
        db_session.commit()
        
        # Try to create another artist with same musicbrainz_id
        artist2 = Artist(**sample_artist_data)
        db_session.add(artist2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestAlbumModel:
    """Test Album model functionality."""
    
    @pytest.mark.unit
    def test_create_album(self, db_session, created_artist):
        """Test creating a new album."""
        album = Album(
            artist_id=created_artist.id,
            name="Test Album",
            release_year=2024,
            musicbrainz_id="test-mb-id",
            total_tracks=10,
            is_rated=False,
        )
        db_session.add(album)
        db_session.commit()
        
        assert album.id is not None
        assert album.artist_id == created_artist.id
        assert album.album_bonus == 0.33  # Default value
        assert album.is_rated is False
        assert album.created_at is not None
    
    @pytest.mark.unit
    def test_album_track_relationship(self, db_session, album_with_tracks):
        """Test one-to-many relationship between album and tracks."""
        assert len(album_with_tracks.tracks) == 10
        for i, track in enumerate(album_with_tracks.tracks, 1):
            assert track.album_id == album_with_tracks.id
            assert track.name == f"Track {i}"
    
    @pytest.mark.unit
    def test_album_cascade_delete(self, db_session, album_with_tracks):
        """Test that deleting an album deletes its tracks."""
        album_id = album_with_tracks.id
        track_ids = [t.id for t in album_with_tracks.tracks]
        
        # Delete the album
        db_session.delete(album_with_tracks)
        db_session.commit()
        
        # Check album is deleted
        assert db_session.query(Album).filter_by(id=album_id).first() is None
        
        # Check all tracks are deleted
        for track_id in track_ids:
            assert db_session.query(Track).filter_by(id=track_id).first() is None
    
    @pytest.mark.unit
    def test_album_rating_score_range(self, db_session, rated_album):
        """Test that album rating score is within valid range."""
        assert 0 <= rated_album.rating_score <= 100
        assert rated_album.is_rated is True
        assert rated_album.rated_at is not None


class TestTrackModel:
    """Test Track model functionality."""
    
    @pytest.mark.unit
    def test_create_track(self, db_session, created_album):
        """Test creating a new track."""
        track = Track(
            album_id=created_album.id,
            track_number=1,
            name="Test Track",
            duration_ms=180000,
        )
        db_session.add(track)
        db_session.commit()
        
        assert track.id is not None
        assert track.album_id == created_album.id
        assert track.track_rating is None  # Not rated yet
        assert track.created_at is not None
    
    @pytest.mark.unit
    def test_track_rating_values(self, db_session, created_track):
        """Test setting valid track rating values."""
        valid_ratings = [0.0, 0.33, 0.67, 1.0]
        
        for rating in valid_ratings:
            created_track.track_rating = rating
            db_session.commit()
            db_session.refresh(created_track)
            assert created_track.track_rating == pytest.approx(rating, rel=1e-2)
    
    @pytest.mark.unit
    def test_track_album_relationship(self, db_session, created_track, created_album):
        """Test many-to-one relationship between track and album."""
        assert created_track.album is not None
        assert created_track.album.id == created_album.id
        assert created_track.album.name == created_album.name


class TestUserSettingsModel:
    """Test UserSettings model functionality."""
    
    @pytest.mark.unit
    def test_create_user_settings(self, db_session):
        """Test creating user settings."""
        settings = UserSettings(
            user_id=1,
            album_bonus=0.25,
            theme="dark",
        )
        db_session.add(settings)
        db_session.commit()
        
        assert settings.id is not None
        assert settings.album_bonus == 0.25
        assert settings.theme == "dark"
        assert settings.created_at is not None
    
    @pytest.mark.unit
    def test_user_settings_defaults(self, db_session):
        """Test default values for user settings."""
        settings = UserSettings(user_id=2)
        db_session.add(settings)
        db_session.commit()
        
        assert settings.album_bonus == 0.33
        assert settings.theme == "light"
        assert settings.auto_migrate_artwork is True
        assert settings.cache_retention_days == 365
        assert settings.cache_max_size_mb == 5000
    
    @pytest.mark.unit
    def test_album_bonus_range(self, db_session):
        """Test that album bonus is within valid range."""
        settings = UserSettings(user_id=3, album_bonus=0.4)
        db_session.add(settings)
        db_session.commit()
        
        assert 0.1 <= settings.album_bonus <= 0.4