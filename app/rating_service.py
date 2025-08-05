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
    def calculate_album_score(track_ratings: List[float], album_bonus: float = 0.33) -> int:
        """
        Calculate album score using the PRD formula:
        Floor((Sum of track ratings / Total tracks × 10) + Album Bonus) × 10
        
        Args:
            track_ratings: List of track ratings (0.0, 0.33, 0.67, 1.0)
            album_bonus: Album bonus factor (0.1 to 0.4)
            
        Returns:
            Integer album score (0-100 scale)
        """
        if not track_ratings:
            return 0
        
        # Validate album bonus range
        album_bonus = max(0.1, min(0.4, album_bonus))
        
        # Calculate average rating
        avg_rating = sum(track_ratings) / len(track_ratings)
        
        # Apply formula: Floor(((avg_rating × 10) + album_bonus) × 10)
        raw_score = ((avg_rating * 10) + album_bonus) * 10
        final_score = int(raw_score)  # Floor operation
        
        # Ensure score is within bounds (0-100)
        return max(0, min(100, final_score))
    
    @staticmethod
    def get_completion_percentage(total_tracks: int, rated_tracks: int) -> float:
        """Calculate rating completion percentage"""
        if total_tracks == 0:
            return 100.0
        return round((rated_tracks / total_tracks) * 100.0, 2)
    
    @staticmethod
    def get_projected_score(
        track_ratings: List[Optional[float]], 
        album_bonus: float = 0.33
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
            album_bonus = settings.album_bonus if settings else 0.33
            
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
        filter_rated: Optional[bool] = None,
        sort: str = "created_desc",
        search: Optional[str] = None,
        artist_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get user's albums with optional filtering, sorting, and searching"""
        query = db.query(Album).join(Artist)
        
        if filter_rated is not None:
            query = query.filter(Album.is_rated == filter_rated)
        
        # Apply artist filter
        if artist_id is not None:
            query = query.filter(Album.artist_id == artist_id)
        
        # Apply search filter
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.filter(
                (Album.name.ilike(search_term)) | 
                (Artist.name.ilike(search_term))
            )
        
        # Apply sorting
        if sort == "created_desc":
            query = query.order_by(Album.created_at.desc())
        elif sort == "created_asc":
            query = query.order_by(Album.created_at.asc())
        elif sort == "artist_asc":
            query = query.order_by(Artist.name.asc())
        elif sort == "artist_desc":
            query = query.order_by(Artist.name.desc())
        elif sort == "album_asc":
            query = query.order_by(Album.name.asc())
        elif sort == "album_desc":
            query = query.order_by(Album.name.desc())
        elif sort == "rating_desc":
            # Only rated albums have scores, put unrated last
            query = query.order_by(Album.rating_score.desc().nulls_last())
        elif sort == "rating_asc":
            # Only rated albums have scores, put unrated last
            query = query.order_by(Album.rating_score.asc().nulls_last())
        elif sort == "year_desc":
            query = query.order_by(Album.release_year.desc().nulls_last())
        elif sort == "year_asc":
            query = query.order_by(Album.release_year.asc().nulls_last())
        elif sort == "rated_desc":
            # Recently rated first (completed albums sorted by rated_at desc, then in-progress)
            query = query.order_by(Album.rated_at.desc().nulls_last())
        else:
            # Default to created_desc for unknown sorts
            query = query.order_by(Album.created_at.desc())
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        albums = query.offset(offset).limit(limit).all()
        
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
                "id": album.artist.id,
                "name": album.artist.name,
                "musicbrainz_id": album.artist.musicbrainz_id
            },
            "year": album.release_year,
            "genre": album.genre,
            "total_tracks": album.total_tracks,
            "total_duration_ms": album.total_duration_ms,
            "cover_art_url": album.cover_art_url,
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
            "artist_id": album.artist.id,
            "year": album.release_year,
            "cover_art_url": album.cover_art_url,
            "is_rated": album.is_rated,
            "rating_score": album.rating_score,
            "rated_at": album.rated_at.isoformat() if album.rated_at else None
        }
    
    def delete_album(self, album_id: int, db: Session) -> Dict[str, Any]:
        """
        Delete album and all associated data (hard delete)
        
        Args:
            album_id: Album ID to delete
            db: Database session
            
        Returns:
            Dict with deletion confirmation
            
        Raises:
            NotFoundError: If album not found
        """
        logger.info(f"Deleting album {album_id}")
        
        # Get album first to verify it exists and get details for response
        album = db.query(Album).filter(Album.id == album_id).first()
        if not album:
            raise ServiceNotFoundError("Album", album_id)
        
        # Store album details for response
        album_info = {
            "id": album.id,
            "title": album.name,
            "artist": album.artist.name,
            "is_rated": album.is_rated,
            "rating_score": album.rating_score
        }
        
        try:
            # Get track count for logging
            track_count = db.query(Track).filter(Track.album_id == album_id).count()
            
            # Delete all tracks (ratings will be cascade deleted due to foreign key constraints)
            db.query(Track).filter(Track.album_id == album_id).delete()
            
            # Delete the album itself
            db.query(Album).filter(Album.id == album_id).delete()
            
            # Commit the transaction
            db.commit()
            
            logger.info(f"Successfully deleted album '{album_info['title']}' and {track_count} tracks")
            
            return {
                "success": True,
                "message": f"Album '{album_info['title']}' has been permanently deleted",
                "deleted_album": album_info,
                "deleted_tracks": track_count
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete album {album_id}: {e}")
            raise

    async def update_missing_cover_art(self, db: Session) -> Dict[str, Any]:
        """
        Update cover art for all albums that don't have it
        
        Fetches cover art from MusicBrainz Cover Art Archive API
        for albums with missing artwork.
        
        Returns:
            Dictionary with update statistics
        """
        from .services.cover_art_service import get_cover_art_service
        
        logger.info("Starting cover art update process")
        
        try:
            # Get all albums without cover art
            albums_without_art = db.query(Album).filter(
                (Album.cover_art_url == None) | (Album.cover_art_url == "")
            ).all()
            
            logger.info(f"Found {len(albums_without_art)} albums without cover art")
            
            cover_art_service = get_cover_art_service()
            updated_count = 0
            failed_count = 0
            
            for album in albums_without_art:
                try:
                    # Fetch cover art URL
                    cover_art_url = await cover_art_service.get_cover_art_url(album.musicbrainz_id)
                    
                    if cover_art_url:
                        album.cover_art_url = cover_art_url
                        db.add(album)
                        updated_count += 1
                        logger.info(f"Updated cover art for album '{album.name}'")
                    else:
                        logger.debug(f"No cover art found for album '{album.name}'")
                        
                except Exception as e:
                    logger.error(f"Failed to update cover art for album '{album.name}': {e}")
                    failed_count += 1
            
            # Commit all updates
            db.commit()
            
            logger.info(f"Cover art update completed: {updated_count} updated, {failed_count} failed")
            
            return {
                "success": True,
                "total_albums": len(albums_without_art),
                "updated": updated_count,
                "failed": failed_count,
                "message": f"Successfully updated cover art for {updated_count} albums"
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Cover art update process failed: {e}")
            raise ServiceException(f"Failed to update cover art: {str(e)}")


def get_rating_service() -> RatingService:
    """Get rating service instance"""
    return RatingService()