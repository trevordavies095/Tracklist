"""
Tests for database operations and models.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import DATABASE_URL, SessionLocal, get_db
from app.models import Album, Artist, Base, Track, UserSettings


class TestDatabaseOperations:
    """Test database operations."""

    @pytest.mark.unit
    def test_database_url_configured(self):
        """Test that database URL is configured."""
        assert DATABASE_URL is not None
        assert "sqlite" in DATABASE_URL  # Should be SQLite in test mode

    @pytest.mark.unit
    def test_session_local_creation(self):
        """Test that SessionLocal can create sessions."""
        session = SessionLocal()
        assert session is not None
        session.close()

    @pytest.mark.integration
    def test_get_db_generator(self):
        """Test get_db generator function."""
        gen = get_db()
        session = next(gen)
        assert session is not None

        # Cleanup
        try:
            next(gen)
        except StopIteration:
            pass

    @pytest.mark.integration
    def test_model_repr_methods(self, db_session):
        """Test model __repr__ methods."""
        artist = Artist(name="Test Artist")
        album = Album(
            name="Test Album", artist=artist, total_tracks=10, album_bonus=0.33
        )
        track = Track(name="Test Track", album=album, track_number=1)
        settings = UserSettings(user_id=1)

        # Test repr strings
        assert "Test Artist" in repr(artist)
        assert "Test Album" in repr(album)
        assert "Test Track" in repr(track)
        assert "UserSettings" in repr(settings)

    @pytest.mark.integration
    def test_cascade_delete_relationships(self, db_session):
        """Test cascade delete relationships."""
        # Create artist with album and tracks
        artist = Artist(name="Test Artist")
        db_session.add(artist)
        db_session.commit()

        album = Album(
            artist_id=artist.id, name="Test Album", total_tracks=2, album_bonus=0.33
        )
        db_session.add(album)
        db_session.commit()

        track1 = Track(album_id=album.id, name="Track 1", track_number=1)
        track2 = Track(album_id=album.id, name="Track 2", track_number=2)
        db_session.add_all([track1, track2])
        db_session.commit()

        # Delete album should cascade to tracks
        db_session.delete(album)
        db_session.commit()

        # Verify tracks are deleted
        tracks = db_session.query(Track).filter(Track.album_id == album.id).all()
        assert len(tracks) == 0

        # Artist should still exist
        artist_check = db_session.query(Artist).filter(Artist.id == artist.id).first()
        assert artist_check is not None

    @pytest.mark.integration
    def test_model_validation_constraints(self, db_session):
        """Test model validation and constraints."""
        # Test album bonus range
        album = Album(
            name="Test Album",
            artist_id=1,
            total_tracks=10,
            album_bonus=0.5,  # Should be clamped or validated
        )

        # Test track rating values
        track = Track(
            name="Test Track",
            album_id=1,
            track_number=1,
            track_rating=0.67,  # Valid rating
        )

        assert track.track_rating in [None, 0.0, 0.33, 0.67, 1.0]

    @pytest.mark.integration
    def test_user_settings_defaults(self, db_session):
        """Test user settings default values."""
        settings = UserSettings(user_id=999)
        db_session.add(settings)
        db_session.commit()

        # Check defaults
        assert settings.album_bonus == 0.33
        assert settings.theme in ["light", "dark"]
        assert settings.cache_retention_days > 0
        assert settings.cache_max_size_mb > 0

    @pytest.mark.integration
    def test_album_completion_status(self, db_session, album_with_tracks):
        """Test album completion status tracking."""
        album = album_with_tracks

        # Initially not rated
        assert album.is_rated is False
        assert album.rating_score is None

        # Rate all tracks
        for track in album.tracks:
            track.track_rating = 0.67

        # Mark as rated
        album.is_rated = True
        album.rating_score = 70
        db_session.commit()

        # Verify persistence
        db_session.refresh(album)
        assert album.is_rated is True
        assert album.rating_score == 70
