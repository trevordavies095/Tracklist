from sqlalchemy import Column, Integer, Text, REAL, Boolean, DateTime, ForeignKey
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
    album_bonus = Column(REAL, default=0.25)
    is_rated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    rated_at = Column(DateTime)
    
    # Relationships
    artist = relationship("Artist", back_populates="albums")
    tracks = relationship("Track", back_populates="album", cascade="all, delete-orphan")


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
    album_bonus = Column(REAL, default=0.25)
    theme = Column(Text, default='light')
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())