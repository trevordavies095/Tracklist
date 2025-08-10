"""
Unit tests for artwork cache database models
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.models import Base, Album, Artist, ArtworkCache


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_artist(db_session):
    """Create a sample artist for testing"""
    artist = Artist(
        name="Test Artist",
        musicbrainz_id="test-artist-mb-id"
    )
    db_session.add(artist)
    db_session.commit()
    return artist


@pytest.fixture
def sample_album(db_session, sample_artist):
    """Create a sample album for testing"""
    album = Album(
        artist_id=sample_artist.id,
        name="Test Album",
        musicbrainz_id="test-album-mb-id",
        cover_art_url="https://example.com/artwork.jpg",
        release_year=2024,
        total_tracks=10
    )
    db_session.add(album)
    db_session.commit()
    return album


class TestArtworkCacheModel:
    """Test the ArtworkCache model"""
    
    def test_create_artwork_cache_entry(self, db_session, sample_album):
        """Test creating a basic artwork cache entry"""
        cache_entry = ArtworkCache(
            album_id=sample_album.id,
            original_url=sample_album.cover_art_url,
            cache_key="abc123def456",
            file_path="static/artwork_cache/original/abc123def456.jpg",
            size_variant="original",
            width=1000,
            height=1000,
            file_size_bytes=250000,
            content_type="image/jpeg",
            last_fetched_at=datetime.now(timezone.utc),
            last_accessed_at=datetime.now(timezone.utc)
        )
        
        db_session.add(cache_entry)
        db_session.commit()
        
        assert cache_entry.id is not None
        assert cache_entry.album_id == sample_album.id
        assert cache_entry.cache_key == "abc123def456"
        assert cache_entry.size_variant == "original"
        assert cache_entry.access_count == 0
        assert cache_entry.is_placeholder is False
    
    def test_unique_cache_key_constraint(self, db_session, sample_album):
        """Test that cache_key must be unique"""
        cache_key = "unique123"
        
        entry1 = ArtworkCache(
            album_id=sample_album.id,
            cache_key=cache_key,
            size_variant="original"
        )
        db_session.add(entry1)
        db_session.commit()
        
        # Try to create another entry with the same cache_key
        entry2 = ArtworkCache(
            album_id=sample_album.id,
            cache_key=cache_key,  # Same key
            size_variant="large"
        )
        db_session.add(entry2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_size_variant_values(self, db_session, sample_album):
        """Test all valid size_variant values"""
        valid_variants = ["original", "large", "medium", "small", "thumbnail"]
        
        for i, variant in enumerate(valid_variants):
            cache_entry = ArtworkCache(
                album_id=sample_album.id,
                cache_key=f"key_{variant}_{i}",
                size_variant=variant
            )
            db_session.add(cache_entry)
        
        db_session.commit()
        
        entries = db_session.query(ArtworkCache).all()
        assert len(entries) == len(valid_variants)
        assert set(e.size_variant for e in entries) == set(valid_variants)
    
    def test_cascade_delete(self, db_session, sample_album):
        """Test that artwork cache entries are deleted when album is deleted"""
        # Create multiple cache entries for the album
        for i, variant in enumerate(["original", "large", "medium"]):
            cache_entry = ArtworkCache(
                album_id=sample_album.id,
                cache_key=f"cascade_test_{i}",
                size_variant=variant
            )
            db_session.add(cache_entry)
        
        db_session.commit()
        
        # Verify entries exist
        assert db_session.query(ArtworkCache).count() == 3
        
        # Delete the album
        db_session.delete(sample_album)
        db_session.commit()
        
        # Verify cache entries were deleted
        assert db_session.query(ArtworkCache).count() == 0
    
    def test_album_relationship(self, db_session, sample_album):
        """Test the relationship between ArtworkCache and Album"""
        cache_entry = ArtworkCache(
            album_id=sample_album.id,
            cache_key="relationship_test",
            size_variant="original"
        )
        db_session.add(cache_entry)
        db_session.commit()
        
        # Test accessing album through cache entry
        assert cache_entry.album == sample_album
        assert cache_entry.album.name == "Test Album"
        
        # Test accessing cache entries through album
        assert len(sample_album.artwork_cache) == 1
        assert sample_album.artwork_cache[0] == cache_entry
    
    def test_default_values(self, db_session, sample_album):
        """Test default values for ArtworkCache fields"""
        cache_entry = ArtworkCache(
            album_id=sample_album.id,
            cache_key="defaults_test",
            size_variant="original"
        )
        db_session.add(cache_entry)
        db_session.commit()
        
        assert cache_entry.access_count == 0
        assert cache_entry.is_placeholder is False
        assert cache_entry.created_at is not None
        assert cache_entry.updated_at is not None
    
    def test_access_tracking(self, db_session, sample_album):
        """Test access count and last_accessed_at tracking"""
        cache_entry = ArtworkCache(
            album_id=sample_album.id,
            cache_key="access_test",
            size_variant="medium",
            access_count=0
        )
        db_session.add(cache_entry)
        db_session.commit()
        
        # Simulate access
        cache_entry.access_count += 1
        cache_entry.last_accessed_at = datetime.now(timezone.utc)
        db_session.commit()
        
        refreshed_entry = db_session.query(ArtworkCache).filter_by(
            cache_key="access_test"
        ).first()
        
        assert refreshed_entry.access_count == 1
        assert refreshed_entry.last_accessed_at is not None


class TestAlbumArtworkCacheColumns:
    """Test the new columns added to the Album model"""
    
    def test_artwork_cached_default(self, db_session, sample_artist):
        """Test that artwork_cached defaults to False"""
        album = Album(
            artist_id=sample_artist.id,
            name="Cache Test Album",
            musicbrainz_id="cache-test-mb-id"
        )
        db_session.add(album)
        db_session.commit()
        
        assert album.artwork_cached is False
        assert album.artwork_cache_date is None
    
    def test_update_artwork_cache_status(self, db_session, sample_album):
        """Test updating artwork cache status"""
        assert sample_album.artwork_cached is False
        
        # Mark as cached
        sample_album.artwork_cached = True
        sample_album.artwork_cache_date = datetime.now(timezone.utc)
        db_session.commit()
        
        # Refresh from database
        refreshed_album = db_session.query(Album).filter_by(
            id=sample_album.id
        ).first()
        
        assert refreshed_album.artwork_cached is True
        assert refreshed_album.artwork_cache_date is not None
    
    def test_multiple_size_variants_per_album(self, db_session, sample_album):
        """Test that an album can have multiple artwork cache entries for different sizes"""
        variants = ["original", "large", "medium", "small", "thumbnail"]
        
        for variant in variants:
            cache_entry = ArtworkCache(
                album_id=sample_album.id,
                cache_key=f"multi_{variant}",
                size_variant=variant,
                file_path=f"static/artwork_cache/{variant}/test.jpg"
            )
            db_session.add(cache_entry)
        
        db_session.commit()
        
        # Query all cache entries for this album
        cache_entries = db_session.query(ArtworkCache).filter_by(
            album_id=sample_album.id
        ).all()
        
        assert len(cache_entries) == 5
        assert set(e.size_variant for e in cache_entries) == set(variants)
        
        # Check via relationship
        assert len(sample_album.artwork_cache) == 5


class TestArtworkCacheQueries:
    """Test common query patterns for artwork cache"""
    
    def test_find_by_album_and_size(self, db_session, sample_album):
        """Test querying cache by album_id and size_variant"""
        # Create entries for different sizes
        for variant in ["original", "large", "medium"]:
            cache_entry = ArtworkCache(
                album_id=sample_album.id,
                cache_key=f"query_test_{variant}",
                size_variant=variant
            )
            db_session.add(cache_entry)
        
        db_session.commit()
        
        # Query for specific size
        medium_cache = db_session.query(ArtworkCache).filter_by(
            album_id=sample_album.id,
            size_variant="medium"
        ).first()
        
        assert medium_cache is not None
        assert medium_cache.size_variant == "medium"
        assert medium_cache.cache_key == "query_test_medium"
    
    def test_find_stale_cache_entries(self, db_session, sample_album):
        """Test finding cache entries that haven't been accessed recently"""
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=31)
        recent_date = now - timedelta(days=1)
        
        # Create old entry
        old_entry = ArtworkCache(
            album_id=sample_album.id,
            cache_key="old_entry",
            size_variant="original",
            last_accessed_at=old_date
        )
        
        # Create recent entry
        recent_entry = ArtworkCache(
            album_id=sample_album.id,
            cache_key="recent_entry",
            size_variant="large",
            last_accessed_at=recent_date
        )
        
        db_session.add_all([old_entry, recent_entry])
        db_session.commit()
        
        # Query for stale entries (not accessed in 30 days)
        threshold = now - timedelta(days=30)
        stale_entries = db_session.query(ArtworkCache).filter(
            ArtworkCache.last_accessed_at < threshold
        ).all()
        
        assert len(stale_entries) == 1
        assert stale_entries[0].cache_key == "old_entry"
    
    def test_find_placeholder_images(self, db_session, sample_album):
        """Test finding placeholder images"""
        # Create regular cache entry
        regular = ArtworkCache(
            album_id=sample_album.id,
            cache_key="regular",
            size_variant="original",
            is_placeholder=False
        )
        
        # Create placeholder entry
        placeholder = ArtworkCache(
            album_id=sample_album.id,
            cache_key="placeholder",
            size_variant="medium",
            is_placeholder=True
        )
        
        db_session.add_all([regular, placeholder])
        db_session.commit()
        
        # Query for placeholders
        placeholders = db_session.query(ArtworkCache).filter_by(
            is_placeholder=True
        ).all()
        
        assert len(placeholders) == 1
        assert placeholders[0].cache_key == "placeholder"