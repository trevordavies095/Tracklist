"""
Reporting service for generating user statistics and reports
Provides endpoints for retrieving album statistics and analytics
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import logging
import random
from datetime import datetime

from .models import Album, Track, Artist
from .exceptions import TracklistException
from .cache import SimpleCache

logger = logging.getLogger(__name__)


class ReportingService:
    """Service for generating user statistics and reports"""
    
    def __init__(self):
        """Initialize reporting service with cache"""
        self.cache = SimpleCache(default_ttl=300, max_size=100)  # 5 minute cache for reports
    
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
        limit: int = 10,
        randomize: bool = False,
        pool_size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top rated albums
        
        Args:
            db: Database session
            limit: Maximum number of albums to return
            randomize: Whether to randomly select from top albums
            pool_size: Size of top album pool to select from when randomizing
            
        Returns:
            List of top rated albums with scores
        """
        try:
            if randomize:
                # Get a larger pool of top albums
                top_album_pool = (
                    db.query(Album)
                    .filter(Album.is_rated == True)
                    .order_by(Album.rating_score.desc())
                    .limit(pool_size)
                    .all()
                )
                
                # Randomly select from the pool
                if len(top_album_pool) <= limit:
                    selected_albums = top_album_pool
                else:
                    selected_albums = random.sample(top_album_pool, limit)
                    # Sort selected albums by score for display
                    selected_albums.sort(key=lambda x: x.rating_score or 0, reverse=True)
            else:
                # Get top albums in order
                selected_albums = (
                    db.query(Album)
                    .filter(Album.is_rated == True)
                    .order_by(Album.rating_score.desc())
                    .limit(limit)
                    .all()
                )
            
            return [
                self._format_album_summary(album)
                for album in selected_albums
            ]
            
        except Exception as e:
            logger.error(f"Failed to get top albums: {e}")
            raise TracklistException(f"Failed to get top albums: {str(e)}")
    
    def get_score_distribution(self, db: Session) -> Dict[str, Any]:
        """
        Get distribution of album scores across different ranges
        
        Args:
            db: Database session
            
        Returns:
            Dict with score distribution data, total rated albums, and statistics
        """
        try:
            # Get all fully rated albums
            rated_albums = (
                db.query(Album)
                .filter(
                    Album.is_rated == True,
                    Album.rating_score.isnot(None)
                )
                .all()
            )
            
            if not rated_albums:
                return {
                    "distribution": [
                        {"range": "0-20", "label": "Very Poor", "count": 0, "percentage": 0, "color": "#dc2626"},
                        {"range": "21-40", "label": "Poor", "count": 0, "percentage": 0, "color": "#f97316"},
                        {"range": "41-60", "label": "Average", "count": 0, "percentage": 0, "color": "#eab308"},
                        {"range": "61-80", "label": "Good", "count": 0, "percentage": 0, "color": "#84cc16"},
                        {"range": "81-100", "label": "Excellent", "count": 0, "percentage": 0, "color": "#22c55e"}
                    ],
                    "total_rated": 0,
                    "average_score": None,
                    "median_score": None
                }
            
            # Define score ranges with colors (red to green gradient)
            ranges = [
                {"range": "0-20", "label": "Very Poor", "min": 0, "max": 20, "color": "#dc2626"},
                {"range": "21-40", "label": "Poor", "min": 21, "max": 40, "color": "#f97316"},
                {"range": "41-60", "label": "Average", "min": 41, "max": 60, "color": "#eab308"},
                {"range": "61-80", "label": "Good", "min": 61, "max": 80, "color": "#84cc16"},
                {"range": "81-100", "label": "Excellent", "min": 81, "max": 100, "color": "#22c55e"}
            ]
            
            # Count albums in each range
            distribution = []
            scores = []
            
            for album in rated_albums:
                if album.rating_score is not None:
                    scores.append(album.rating_score)
            
            total_rated = len(scores)
            
            for range_def in ranges:
                count = sum(
                    1 for score in scores 
                    if range_def["min"] <= score <= range_def["max"]
                )
                percentage = round((count / total_rated) * 100, 1) if total_rated > 0 else 0
                
                distribution.append({
                    "range": range_def["range"],
                    "label": range_def["label"],
                    "count": count,
                    "percentage": percentage,
                    "color": range_def["color"]
                })
            
            # Calculate average and median
            average_score = round(sum(scores) / len(scores), 1) if scores else None
            median_score = round(sorted(scores)[len(scores) // 2], 1) if scores else None
            
            result = {
                "distribution": distribution,
                "total_rated": total_rated,
                "average_score": average_score,
                "median_score": median_score
            }
            
            logger.info(f"Generated score distribution for {total_rated} albums")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get score distribution: {e}")
            raise TracklistException(f"Failed to get score distribution: {str(e)}")
    
    def get_no_skip_albums(
        self, 
        db: Session, 
        limit: Optional[int] = None,
        randomize: bool = True
    ) -> Dict[str, Any]:
        """
        Get albums with no skip-worthy tracks (all tracks rated >= 0.67)
        
        Args:
            db: Database session
            limit: Optional limit on number of albums to return
            randomize: Whether to randomize the selection (default: True)
            
        Returns:
            Dict with no-skip albums list, count, and percentage
        """
        # Don't cache randomized results
        if not randomize:
            cache_key = f"no_skips_{limit}"
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Returning cached no-skip albums (limit={limit})")
                return cached_result
        
        try:
            # Get fully rated albums with their tracks eagerly loaded to avoid N+1 queries
            from sqlalchemy.orm import joinedload
            
            fully_rated_albums = (
                db.query(Album)
                .filter(Album.is_rated == True)
                .options(joinedload(Album.tracks))
                .options(joinedload(Album.artist))
                .all()
            )
            
            no_skip_albums = []
            
            for album in fully_rated_albums:
                # Check if all tracks have rating >= 0.67 (Good or Standout)
                has_skips = any(
                    track.track_rating is not None and track.track_rating < 0.67 
                    for track in album.tracks
                )
                
                if not has_skips and album.tracks:  # Ensure album has tracks
                    no_skip_albums.append(album)
            
            # Store total count before limiting
            total_no_skip_count = len(no_skip_albums)
            
            # Randomize or sort by score
            if randomize and limit and len(no_skip_albums) > limit:
                # Randomly select albums when limit is specified
                no_skip_albums = random.sample(no_skip_albums, limit)
                # Then sort the random selection by score for display
                no_skip_albums.sort(key=lambda x: x.rating_score or 0, reverse=True)
            else:
                # Sort by rating score descending
                no_skip_albums.sort(key=lambda x: x.rating_score or 0, reverse=True)
                # Apply limit if specified
                if limit:
                    no_skip_albums = no_skip_albums[:limit]
            
            # Calculate percentage
            total_rated = len(fully_rated_albums)
            percentage = (
                round((total_no_skip_count / total_rated) * 100, 1) 
                if total_rated > 0 else 0
            )
            
            result = {
                "albums": [
                    self._format_album_with_details(album, db)
                    for album in no_skip_albums
                ],
                "total_count": total_no_skip_count,
                "percentage": percentage,
                "total_rated_albums": total_rated
            }
            
            # Only cache non-randomized results
            if not randomize:
                self.cache.set(result, None, cache_key)
            
            logger.info(f"Found {total_no_skip_count} no-skip albums ({percentage}% of rated) - returning {len(no_skip_albums)} {'random' if randomize else 'top'} albums")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get no-skip albums: {e}")
            raise TracklistException(f"Failed to get no-skip albums: {str(e)}")
    
    def _format_album_with_details(
        self, 
        album: Album, 
        db: Session
    ) -> Dict[str, Any]:
        """Format album data with additional details for no-skip display"""
        track_ratings = [
            track.track_rating for track in album.tracks 
            if track.track_rating is not None
        ]
        
        return {
            "id": album.id,
            "name": album.name,
            "artist": album.artist.name if album.artist else "Unknown Artist",
            "artist_id": album.artist_id,
            "year": album.release_year,
            "score": album.rating_score,
            "cover_art_url": album.cover_art_url,
            "rated_at": album.rated_at.isoformat() if album.rated_at else None,
            "total_tracks": len(album.tracks),
            "average_track_rating": round(sum(track_ratings) / len(track_ratings), 2) if track_ratings else 0,
            "musicbrainz_id": album.musicbrainz_id
        }


# Singleton instance
_reporting_service = None


def get_reporting_service() -> ReportingService:
    """Get singleton instance of ReportingService"""
    global _reporting_service
    if _reporting_service is None:
        _reporting_service = ReportingService()
    return _reporting_service