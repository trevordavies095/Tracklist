from sqlalchemy import Column, Integer, Text, REAL, Boolean, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Artist(Base):
    __tablename__ = "artists"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    musicbrainz_id = Column(Text, unique=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    albums = relationship("Album", back_populates="artist", cascade="all, delete-orphan")


class Album(Base):
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
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    album_bonus = Column(REAL, default=0.33)
    theme = Column(Text, default='light')
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())


class ArtworkCache(Base):
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