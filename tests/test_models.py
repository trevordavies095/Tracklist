import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.models import Artist, Album, Track, UserSettings


class TestArtist:
    def test_create_artist(self, db_session):
        """Test creating an artist"""
        artist = Artist(
            name="The Beatles",
            musicbrainz_id="b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
        )
        db_session.add(artist)
        db_session.commit()
        
        assert artist.id is not None
        assert artist.name == "The Beatles"
        assert artist.musicbrainz_id == "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d"
        assert artist.created_at is not None
        assert artist.updated_at is not None

    def test_artist_unique_musicbrainz_id(self, db_session):
        """Test that musicbrainz_id is unique"""
        artist1 = Artist(name="Artist 1", musicbrainz_id="test-id")
        artist2 = Artist(name="Artist 2", musicbrainz_id="test-id")
        
        db_session.add(artist1)
        db_session.commit()
        
        db_session.add(artist2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestAlbum:
    def test_create_album(self, db_session):
        """Test creating an album"""
        artist = Artist(name="Test Artist")
        db_session.add(artist)
        db_session.commit()
        
        album = Album(
            artist_id=artist.id,
            name="Test Album",
            release_year=2023,
            musicbrainz_id="test-album-id",
            cover_art_url="http://example.com/cover.jpg",
            genre="Rock",
            total_tracks=10,
            total_duration_ms=2400000,
            album_bonus=0.25
        )
        db_session.add(album)
        db_session.commit()
        
        assert album.id is not None
        assert album.name == "Test Album"
        assert album.release_year == 2023
        assert album.musicbrainz_id == "test-album-id"
        assert album.album_bonus == 0.25
        assert album.is_rated is False
        assert album.rating_score is None
        assert album.rated_at is None

    def test_album_artist_relationship(self, db_session):
        """Test album-artist relationship"""
        artist = Artist(name="Test Artist")
        db_session.add(artist)
        db_session.commit()
        
        album = Album(
            artist_id=artist.id,
            name="Test Album",
            musicbrainz_id="test-album-id"
        )
        db_session.add(album)
        db_session.commit()
        
        assert album.artist.name == "Test Artist"
        assert artist.albums[0].name == "Test Album"

    def test_album_unique_musicbrainz_id(self, db_session):
        """Test that album musicbrainz_id is unique"""
        artist = Artist(name="Test Artist")
        db_session.add(artist)
        db_session.commit()
        
        album1 = Album(artist_id=artist.id, name="Album 1", musicbrainz_id="test-id")
        album2 = Album(artist_id=artist.id, name="Album 2", musicbrainz_id="test-id")
        
        db_session.add(album1)
        db_session.commit()
        
        db_session.add(album2)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestTrack:
    def test_create_track(self, db_session):
        """Test creating a track"""
        artist = Artist(name="Test Artist")
        album = Album(artist=artist, name="Test Album", musicbrainz_id="test-album-id")
        db_session.add(album)
        db_session.commit()
        
        track = Track(
            album_id=album.id,
            track_number=1,
            name="Test Track",
            duration_ms=180000,
            musicbrainz_id="test-track-id",
            track_rating=0.67
        )
        db_session.add(track)
        db_session.commit()
        
        assert track.id is not None
        assert track.track_number == 1
        assert track.name == "Test Track"
        assert track.duration_ms == 180000
        assert track.track_rating == 0.67

    def test_track_album_relationship(self, db_session):
        """Test track-album relationship"""
        artist = Artist(name="Test Artist")
        album = Album(artist=artist, name="Test Album", musicbrainz_id="test-album-id")
        db_session.add(album)
        db_session.commit()
        
        track = Track(
            album_id=album.id,
            track_number=1,
            name="Test Track"
        )
        db_session.add(track)
        db_session.commit()
        
        assert track.album.name == "Test Album"
        assert album.tracks[0].name == "Test Track"

    def test_track_cascade_delete(self, db_session):
        """Test that tracks are deleted when album is deleted"""
        artist = Artist(name="Test Artist")
        album = Album(artist=artist, name="Test Album", musicbrainz_id="test-album-id")
        track = Track(album=album, track_number=1, name="Test Track")
        
        db_session.add(album)
        db_session.commit()
        
        track_id = track.id
        
        # Delete album
        db_session.delete(album)
        db_session.commit()
        
        # Track should be deleted too
        deleted_track = db_session.query(Track).filter(Track.id == track_id).first()
        assert deleted_track is None


class TestUserSettings:
    def test_create_user_settings(self, db_session):
        """Test creating user settings"""
        settings = UserSettings(
            user_id=1,
            album_bonus=0.3,
            theme='dark'
        )
        db_session.add(settings)
        db_session.commit()
        
        assert settings.id is not None
        assert settings.user_id == 1
        assert settings.album_bonus == 0.3
        assert settings.theme == 'dark'

    def test_default_user_settings(self, db_session):
        """Test default values for user settings"""
        settings = UserSettings()
        db_session.add(settings)
        db_session.commit()
        
        assert settings.user_id == 1
        assert settings.album_bonus == 0.25
        assert settings.theme == 'light'