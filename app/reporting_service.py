"""
Reporting service for generating user statistics and reports
Provides endpoints for retrieving album statistics and analytics
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging
from datetime import datetime

from .models import Album, Track, Artist
from .exceptions import TracklistException

logger = logging.getLogger(__name__)


class ReportingService:
    """Service for generating user statistics and reports"""
    
    def get_overview_statistics(self, db: Session) -> Dict[str, Any]:
        """
        Get overview statistics for user's album collection
        
        Returns:
            Dict with:
            - total_albums: Total number of albums in collection
            - fully_rated_count: Number of albums with all tracks rated
            - in_progress_count: Number of albums with partial ratings
            - average_album_score: Average score of all fully rated albums
            - total_tracks_rated: Total number of rated tracks
            - rating_distribution: Distribution of track ratings
        """
        try:
            # Get total albums count
            total_albums = db.query(Album).count()
            
            # Get fully rated albums (is_rated = True)
            fully_rated_albums = db.query(Album).filter(Album.is_rated == True).all()
            fully_rated_count = len(fully_rated_albums)
            
            # Get in-progress albums (has at least one rated track but not completed)
            in_progress_albums = (
                db.query(Album)
                .join(Track)
                .filter(
                    Album.is_rated == False,
                    Track.track_rating.isnot(None)
                )
                .distinct()
                .all()
            )
            in_progress_count = len(in_progress_albums)
            
            # Calculate average album score for fully rated albums
            average_album_score = None
            if fully_rated_count > 0:
                total_score = sum(
                    album.rating_score for album in fully_rated_albums 
                    if album.rating_score is not None
                )
                average_album_score = round(total_score / fully_rated_count, 1)
            
            # Get total tracks rated
            total_tracks_rated = db.query(Track).filter(
                Track.track_rating.isnot(None)
            ).count()
            
            # Get rating distribution
            rating_distribution = self._get_rating_distribution(db)
            
            # Get additional statistics
            stats = {
                "total_albums": total_albums,
                "fully_rated_count": fully_rated_count,
                "in_progress_count": in_progress_count,
                "average_album_score": average_album_score,
                "total_tracks_rated": total_tracks_rated,
                "rating_distribution": rating_distribution,
                "unrated_albums_count": total_albums - fully_rated_count - in_progress_count
            }
            
            logger.info(f"Generated overview statistics: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to generate overview statistics: {e}")
            raise TracklistException(f"Failed to generate statistics: {str(e)}")
    
    def _get_rating_distribution(self, db: Session) -> Dict[str, int]:
        """
        Get distribution of track ratings
        
        Returns:
            Dict with rating values as keys and counts as values
        """
        try:
            distribution = {
                "skip": 0,      # 0.0
                "filler": 0,    # 0.33
                "good": 0,      # 0.67
                "standout": 0   # 1.0
            }
            
            # Query for each rating value
            skip_count = db.query(Track).filter(Track.track_rating == 0.0).count()
            filler_count = db.query(Track).filter(Track.track_rating == 0.33).count()
            good_count = db.query(Track).filter(Track.track_rating == 0.67).count()
            standout_count = db.query(Track).filter(Track.track_rating == 1.0).count()
            
            distribution["skip"] = skip_count
            distribution["filler"] = filler_count
            distribution["good"] = good_count
            distribution["standout"] = standout_count
            
            return distribution
            
        except Exception as e:
            logger.error(f"Failed to get rating distribution: {e}")
            return {
                "skip": 0,
                "filler": 0,
                "good": 0,
                "standout": 0
            }
    
    def get_recent_activity(
        self, 
        db: Session, 
        limit: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get recent rating activity
        
        Args:
            db: Database session
            limit: Maximum number of items to return
            
        Returns:
            Dict with recently rated and in-progress albums
        """
        try:
            # Get recently rated albums
            recently_rated = (
                db.query(Album)
                .filter(Album.is_rated == True)
                .order_by(Album.rated_at.desc())
                .limit(limit)
                .all()
            )
            
            # Get in-progress albums (most recently updated)
            in_progress = (
                db.query(Album)
                .join(Track)
                .filter(
                    Album.is_rated == False,
                    Track.track_rating.isnot(None)
                )
                .order_by(Album.updated_at.desc())
                .distinct()
                .limit(limit)
                .all()
            )
            
            return {
                "recently_rated": [
                    self._format_album_summary(album) 
                    for album in recently_rated
                ],
                "in_progress": [
                    self._format_album_with_progress(album, db) 
                    for album in in_progress
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get recent activity: {e}")
            raise TracklistException(f"Failed to get recent activity: {str(e)}")
    
    def _format_album_summary(self, album: Album) -> Dict[str, Any]:
        """Format album data for summary response"""
        return {
            "id": album.id,
            "name": album.name,
            "artist": album.artist.name if album.artist else "Unknown Artist",
            "year": album.release_year,
            "score": album.rating_score,
            "cover_art_url": album.cover_art_url,
            "rated_at": album.rated_at.isoformat() if album.rated_at else None
        }
    
    def _format_album_with_progress(
        self, 
        album: Album, 
        db: Session
    ) -> Dict[str, Any]:
        """Format album data with rating progress"""
        rated_tracks = sum(
            1 for track in album.tracks 
            if track.track_rating is not None
        )
        total_tracks = len(album.tracks)
        progress_percentage = (
            round((rated_tracks / total_tracks) * 100, 1) 
            if total_tracks > 0 else 0
        )
        
        return {
            "id": album.id,
            "name": album.name,
            "artist": album.artist.name if album.artist else "Unknown Artist",
            "year": album.release_year,
            "cover_art_url": album.cover_art_url,
            "progress": {
                "rated_tracks": rated_tracks,
                "total_tracks": total_tracks,
                "percentage": progress_percentage
            },
            "updated_at": album.updated_at.isoformat() if album.updated_at else None
        }
    
    def get_top_albums(
        self, 
        db: Session, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top rated albums
        
        Args:
            db: Database session
            limit: Maximum number of albums to return
            
        Returns:
            List of top rated albums with scores
        """
        try:
            top_albums = (
                db.query(Album)
                .filter(Album.is_rated == True)
                .order_by(Album.rating_score.desc())
                .limit(limit)
                .all()
            )
            
            return [
                self._format_album_summary(album)
                for album in top_albums
            ]
            
        except Exception as e:
            logger.error(f"Failed to get top albums: {e}")
            raise TracklistException(f"Failed to get top albums: {str(e)}")


# Singleton instance
_reporting_service = None


def get_reporting_service() -> ReportingService:
    """Get singleton instance of ReportingService"""
    global _reporting_service
    if _reporting_service is None:
        _reporting_service = ReportingService()
    return _reporting_service