"""
Rating service for album and track rating operations
Handles album creation, track rating, and score calculation
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
import logging
from datetime import datetime, timezone

from .models import Artist, Album, Track, UserSettings
from .musicbrainz_service import get_musicbrainz_service
from .exceptions import TracklistException, ServiceNotFoundError, ServiceValidationError

logger = logging.getLogger(__name__)

VALID_RATINGS = [0.0, 0.33, 0.67, 1.0]


class RatingCalculator:
    """Handles album score calculation with configurable bonus"""
    
    @staticmethod
    def calculate_album_score(track_ratings: List[float], album_bonus: float = 0.25) -> int:
        """
        Calculate album score using the PRD formula:
        Floor((Sum of track ratings / Total tracks × 10) + Album Bonus) × 10
        
        Args:
            track_ratings: List of track ratings (0.0, 0.33, 0.67, 1.0)
            album_bonus: Album bonus factor (0.1 to 0.4)
            
        Returns:
            Integer album score (0-140 scale)
        """
        if not track_ratings:
            return 0
        
        # Validate album bonus range
        album_bonus = max(0.1, min(0.4, album_bonus))
        
        # Calculate average rating
        avg_rating = sum(track_ratings) / len(track_ratings)
        
        # Apply formula: Floor((avg_rating × 10) + album_bonus) × 10
        raw_score = (avg_rating * 10) + album_bonus
        floored_score = int(raw_score)  # Floor operation
        final_score = floored_score * 10
        
        # Ensure score is within bounds
        return max(0, min(140, final_score))
    
    @staticmethod
    def get_completion_percentage(total_tracks: int, rated_tracks: int) -> float:
        """Calculate rating completion percentage"""
        if total_tracks == 0:
            return 100.0
        return (rated_tracks / total_tracks) * 100.0
    
    @staticmethod
    def get_projected_score(
        track_ratings: List[Optional[float]], 
        album_bonus: float = 0.25
    ) -> Optional[int]:
        """
        Calculate projected album score based on current ratings
        Returns None if no tracks are rated yet
        """
        rated_values = [rating for rating in track_ratings if rating is not None]
        
        if not rated_values:
            return None
        
        return RatingCalculator.calculate_album_score(rated_values, album_bonus)


class RatingService:
    """Service for album rating operations"""
    
    def __init__(self):
        self.musicbrainz_service = get_musicbrainz_service()
    
    async def create_album_for_rating(
        self, 
        musicbrainz_id: str, 
        db: Session
    ) -> Dict[str, Any]:
        """
        Create album in database from MusicBrainz data for rating
        
        Args:
            musicbrainz_id: MusicBrainz release ID
            db: Database session
            
        Returns:
            Dict with created album information
            
        Raises:
            ValidationError: If album already exists or MusicBrainz ID invalid
            TracklistException: If MusicBrainz fetch fails
        """
        logger.info(f"Creating album for rating: {musicbrainz_id}")
        
        # Check if album already exists
        existing_album = db.query(Album).filter(
            Album.musicbrainz_id == musicbrainz_id
        ).first()
        
        if existing_album:
            logger.info(f"Album already exists: {musicbrainz_id}")
            return self._format_album_response(existing_album, db)
        
        try:
            # Fetch album details from MusicBrainz
            mb_album = await self.musicbrainz_service.get_album_details(musicbrainz_id)
            
            # Create or get artist
            artist = self._create_or_get_artist(
                mb_album["artist"]["name"],
                mb_album["artist"]["musicbrainz_id"],
                db
            )
            
            # Get user settings for album bonus
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            album_bonus = settings.album_bonus if settings else 0.25
            
            # Create album
            album = Album(
                artist_id=artist.id,
                name=mb_album["title"],
                release_year=mb_album.get("year"),
                musicbrainz_id=musicbrainz_id,
                genre=mb_album.get("country"),  # Temporary mapping
                total_tracks=mb_album["total_tracks"],
                total_duration_ms=mb_album.get("total_duration_ms"),
                album_bonus=album_bonus,
                is_rated=False
            )
            
            db.add(album)
            db.flush()  # Get album ID
            
            # Create tracks
            for track_data in mb_album["tracks"]:
                track = Track(
                    album_id=album.id,
                    track_number=track_data["track_number"],
                    name=track_data["title"],
                    duration_ms=track_data.get("duration_ms"),
                    musicbrainz_id=track_data.get("musicbrainz_recording_id")
                )
                db.add(track)
            
            db.commit()
            
            logger.info(f"Album created successfully: {album.name} by {artist.name}")
            return self._format_album_response(album, db)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create album {musicbrainz_id}: {e}")
            if isinstance(e, TracklistException):
                raise
            raise TracklistException(f"Failed to create album: {str(e)}")
    
    def rate_track(
        self, 
        track_id: int, 
        rating: float, 
        db: Session
    ) -> Dict[str, Any]:
        """
        Rate a track (auto-save functionality)
        
        Args:
            track_id: Track ID
            rating: Rating value (0.0, 0.33, 0.67, 1.0)
            db: Database session
            
        Returns:
            Dict with updated track and album progress
            
        Raises:
            NotFoundError: If track not found
            ValidationError: If rating invalid
        """
        logger.info(f"Rating track {track_id} with rating {rating}")
        
        # Validate rating
        if rating not in VALID_RATINGS:
            raise ServiceValidationError(
                f"Invalid rating: {rating}. Must be one of {VALID_RATINGS}"
            )
        
        # Get track
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            raise ServiceNotFoundError("Track", track_id)
        
        # Update track rating
        track.track_rating = rating
        
        # Get album for progress calculation
        album = db.query(Album).filter(Album.id == track.album_id).first()
        
        db.commit()
        
        logger.info(f"Track {track_id} rated successfully: {rating}")
        
        # Return updated progress
        return self.get_album_progress(album.id, db)
    
    def get_album_progress(self, album_id: int, db: Session) -> Dict[str, Any]:
        """
        Get album rating progress
        
        Args:
            album_id: Album ID
            db: Database session
            
        Returns:
            Dict with progress information and projected score
        """
        album = db.query(Album).filter(Album.id == album_id).first()
        if not album:
            raise ServiceNotFoundError("Album", album_id)
        
        tracks = db.query(Track).filter(Track.album_id == album_id).order_by(Track.track_number).all()
        
        # Calculate progress
        total_tracks = len(tracks)
        rated_tracks = sum(1 for track in tracks if track.track_rating is not None)
        completion_pct = RatingCalculator.get_completion_percentage(total_tracks, rated_tracks)
        
        # Get projected score
        track_ratings = [track.track_rating for track in tracks]
        projected_score = RatingCalculator.get_projected_score(track_ratings, album.album_bonus)
        
        return {
            "album_id": album_id,
            "album_title": album.name,
            "artist_name": album.artist.name,
            "total_tracks": total_tracks,
            "rated_tracks": rated_tracks,
            "completion_percentage": completion_pct,
            "is_complete": completion_pct == 100.0,
            "projected_score": projected_score,
            "is_submitted": album.is_rated,
            "final_score": album.rating_score,
            "album_bonus": album.album_bonus
        }
    
    def submit_album_rating(self, album_id: int, db: Session) -> Dict[str, Any]:
        """
        Submit final album rating (calculate and save final score)
        
        Args:
            album_id: Album ID
            db: Database session
            
        Returns:
            Dict with final album rating information
            
        Raises:
            NotFoundError: If album not found
            ValidationError: If album rating incomplete
        """
        logger.info(f"Submitting album rating for album {album_id}")
        
        album = db.query(Album).filter(Album.id == album_id).first()
        if not album:
            raise ServiceNotFoundError("Album", album_id)
        
        if album.is_rated:
            logger.info(f"Album {album_id} already submitted")
            return self._format_album_response(album, db, include_tracks=True)
        
        # Get all tracks
        tracks = db.query(Track).filter(Track.album_id == album_id).order_by(Track.track_number).all()
        
        # Verify all tracks are rated
        unrated_tracks = [track for track in tracks if track.track_rating is None]
        if unrated_tracks:
            track_numbers = [str(track.track_number) for track in unrated_tracks]
            raise ServiceValidationError(
                f"Cannot submit incomplete rating. Unrated tracks: {', '.join(track_numbers)}"
            )
        
        # Calculate final score
        track_ratings = [track.track_rating for track in tracks]
        final_score = RatingCalculator.calculate_album_score(track_ratings, album.album_bonus)
        
        # Update album
        album.rating_score = final_score
        album.is_rated = True
        album.rated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(f"Album {album_id} submitted with final score: {final_score}")
        
        return self._format_album_response(album, db, include_tracks=True)
    
    def get_album_rating(self, album_id: int, db: Session) -> Dict[str, Any]:
        """Get complete album rating information"""
        album = db.query(Album).filter(Album.id == album_id).first()
        if not album:
            raise ServiceNotFoundError("Album", album_id)
        
        return self._format_album_response(album, db, include_tracks=True)
    
    def get_user_albums(
        self, 
        db: Session, 
        limit: int = 50, 
        offset: int = 0,
        filter_rated: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Get user's albums with optional filtering"""
        query = db.query(Album).join(Artist)
        
        if filter_rated is not None:
            query = query.filter(Album.is_rated == filter_rated)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        albums = query.order_by(Album.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "albums": [self._format_album_summary(album) for album in albums],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }
    
    def _create_or_get_artist(
        self, 
        name: str, 
        musicbrainz_id: Optional[str], 
        db: Session
    ) -> Artist:
        """Create or get existing artist"""
        if musicbrainz_id:
            artist = db.query(Artist).filter(Artist.musicbrainz_id == musicbrainz_id).first()
            if artist:
                return artist
        
        # Check by name if no MusicBrainz ID match
        artist = db.query(Artist).filter(Artist.name == name).first()
        if artist:
            return artist
        
        # Create new artist
        artist = Artist(name=name, musicbrainz_id=musicbrainz_id)
        db.add(artist)
        db.flush()
        return artist
    
    def _format_album_response(
        self, 
        album: Album, 
        db: Session, 
        include_tracks: bool = False
    ) -> Dict[str, Any]:
        """Format album for API response"""
        response = {
            "id": album.id,
            "musicbrainz_id": album.musicbrainz_id,
            "title": album.name,
            "artist": {
                "name": album.artist.name,
                "musicbrainz_id": album.artist.musicbrainz_id
            },
            "year": album.release_year,
            "genre": album.genre,
            "total_tracks": album.total_tracks,
            "total_duration_ms": album.total_duration_ms,
            "album_bonus": album.album_bonus,
            "is_rated": album.is_rated,
            "rating_score": album.rating_score,
            "rated_at": album.rated_at.isoformat() if album.rated_at else None,
            "created_at": album.created_at.isoformat()
        }
        
        if include_tracks:
            tracks = db.query(Track).filter(Track.album_id == album.id).order_by(Track.track_number).all()
            response["tracks"] = [
                {
                    "id": track.id,
                    "track_number": track.track_number,
                    "title": track.name,
                    "duration_ms": track.duration_ms,
                    "rating": track.track_rating
                }
                for track in tracks
            ]
        
        return response
    
    def _format_album_summary(self, album: Album) -> Dict[str, Any]:
        """Format album summary for lists"""
        return {
            "id": album.id,
            "musicbrainz_id": album.musicbrainz_id,
            "title": album.name,
            "artist": album.artist.name,
            "year": album.release_year,
            "is_rated": album.is_rated,
            "rating_score": album.rating_score,
            "rated_at": album.rated_at.isoformat() if album.rated_at else None
        }


def get_rating_service() -> RatingService:
    """Get rating service instance"""
    return RatingService()