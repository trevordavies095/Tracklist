from sqlalchemy import Column, Integer, Text, REAL, Boolean, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Artist(Base):
    """
    Represents a music artist in the database.

    Stores artist information including MusicBrainz IDs for external API integration.
    Artists can have multiple albums associated with them.

    Attributes:
        id: Primary key identifier
        name: Artist's display name
        musicbrainz_id: Unique MusicBrainz identifier for API lookups
        created_at: Timestamp when the artist was added
        updated_at: Timestamp of the last update
        albums: Related Album objects (one-to-many relationship)
    """
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    musicbrainz_id = Column(Text, unique=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    albums = relationship("Album", back_populates="artist", cascade="all, delete-orphan")


class Album(Base):
    """
    Represents a music album with rating and metadata.

    Core entity storing album information, ratings, and artwork references.
    Albums belong to artists and contain tracks that can be individually rated.

    Attributes:
        id: Primary key identifier
        artist_id: Foreign key to Artist table
        name: Album title
        release_year: Year of album release
        musicbrainz_id: Unique MusicBrainz identifier (required)
        cover_art_url: URL to external album artwork
        genre: Musical genre classification
        total_tracks: Number of tracks in the album
        total_duration_ms: Total album duration in milliseconds
        rating_score: Calculated album rating score (0-100)
        album_bonus: Bonus points for cohesive albums (default: 0.33)
        is_rated: Whether the album has been fully rated
        notes: User notes about the album
        rated_at: Timestamp when rating was completed
        artwork_cached: Whether artwork is locally cached
        artwork_cache_date: When artwork was cached
    """
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    name = Column(Text, nullable=False)
    release_year = Column(Integer)
    musicbrainz_id = Column(Text, unique=True, nullable=False)
    cover_art_url = Column(Text)
    genre = Column(Text)
    total_tracks = Column(Integer)
    total_duration_ms = Column(Integer)
    rating_score = Column(Integer)
    album_bonus = Column(REAL, default=0.33)
    is_rated = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    rated_at = Column(DateTime)
    # Artwork cache columns
    artwork_cached = Column(Boolean, default=False)
    artwork_cache_date = Column(DateTime)

    # Relationships
    artist = relationship("Artist", back_populates="albums")
    tracks = relationship("Track", back_populates="album", cascade="all, delete-orphan")
    artwork_cache = relationship("ArtworkCache", back_populates="album", cascade="all, delete-orphan")


class Track(Base):
    """
    Represents an individual track within an album.

    Tracks are rated on a 4-point scale which contributes to the album's overall score.
    Each track belongs to exactly one album.

    Attributes:
        id: Primary key identifier
        album_id: Foreign key to Album table (cascade delete)
        track_number: Position in the album tracklist
        name: Track title
        duration_ms: Track duration in milliseconds
        musicbrainz_id: Optional MusicBrainz track identifier
        track_rating: Rating value (0.0, 0.33, 0.67, or 1.0)
        created_at: Timestamp when track was added
        updated_at: Timestamp of last modification
    """
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    album_id = Column(Integer, ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    track_number = Column(Integer, nullable=False)
    name = Column(Text, nullable=False)
    duration_ms = Column(Integer)
    musicbrainz_id = Column(Text)
    track_rating = Column(REAL)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    album = relationship("Album", back_populates="tracks")


class UserSettings(Base):
    """
    Stores user preferences and application settings.

    Configuration for user-specific preferences like theme and rating parameters.
    Currently supports single-user mode (user_id defaults to 1).

    Attributes:
        id: Primary key identifier
        user_id: User identifier (default: 1 for single-user mode)
        album_bonus: Default bonus points for albums
        theme: UI theme preference ('light' or 'dark')
        created_at: Settings creation timestamp
        updated_at: Last settings modification timestamp
    """
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    album_bonus = Column(REAL, default=0.33)
    theme = Column(Text, default='light')
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())


class ArtworkCache(Base):
    """
    Manages cached album artwork in multiple size variants.

    Stores metadata and file paths for locally cached album artwork images.
    Supports multiple size variants (thumbnail, small, medium, large, original)
    with access tracking for cache optimization.

    Attributes:
        id: Primary key identifier
        album_id: Foreign key to Album table (cascade delete)
        original_url: Source URL of the artwork
        cache_key: Unique identifier for cached file
        file_path: Local filesystem path to cached image
        size_variant: Image size variant (thumbnail/small/medium/large/original)
        width: Image width in pixels
        height: Image height in pixels
        file_size_bytes: File size in bytes
        content_type: MIME type of the image
        etag: HTTP ETag for cache validation
        last_fetched_at: When image was downloaded
        last_accessed_at: Most recent access timestamp
        access_count: Number of times accessed
        is_placeholder: Whether this is a placeholder image
        created_at: Cache entry creation timestamp
        updated_at: Last modification timestamp
    """
    __tablename__ = "artwork_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    album_id = Column(Integer, ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    original_url = Column(Text)
    cache_key = Column(Text, unique=True, nullable=False)
    file_path = Column(Text)
    size_variant = Column(
        Text,
        nullable=False,
        # SQLAlchemy will create CHECK constraint from this
    )
    width = Column(Integer)
    height = Column(Integer)
    file_size_bytes = Column(Integer)
    content_type = Column(Text)
    etag = Column(Text)
    last_fetched_at = Column(DateTime)
    last_accessed_at = Column(DateTime)
    access_count = Column(Integer, default=0)
    is_placeholder = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    album = relationship("Album", back_populates="artwork_cache")

    # Table arguments for constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "size_variant IN ('original', 'large', 'medium', 'small', 'thumbnail')",
            name="check_size_variant"
        ),
        Index('idx_artwork_cache_album_size', 'album_id', 'size_variant'),
        Index('idx_artwork_cache_key', 'cache_key'),
        Index('idx_artwork_cache_last_accessed', 'last_accessed_at'),
        Index('idx_artwork_cache_album_id', 'album_id'),
    )
