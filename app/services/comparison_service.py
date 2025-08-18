"""
Album comparison service for side-by-side album analysis
Provides comprehensive track-by-track comparison with statistics and insights
"""

import logging
import statistics
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from ..models import Album, Track, Artist
from ..exceptions import TracklistException, ServiceNotFoundError, ServiceValidationError
from ..cache import SimpleCache

logger = logging.getLogger(__name__)

# Rating difference categorization thresholds
DIFFERENCE_THRESHOLDS = {
    'significant': 0.34,  # One full rating level
    'moderate': 0.20,     # Substantial difference
    'slight': 0.10,       # Minor difference
    'tie': 0.05          # Essentially equal
}


class ComparisonService:
    """Service for album comparison operations"""
    
    def __init__(self):
        """Initialize comparison service with cache"""
        self.cache = SimpleCache(default_ttl=300, max_size=50)  # 5 minute cache
        
    def compare_albums(
        self, 
        album1_id: int, 
        album2_id: int, 
        db: Session
    ) -> Dict[str, Any]:
        """
        Generate comprehensive album comparison data
        
        Args:
            album1_id: ID of first album to compare
            album2_id: ID of second album to compare
            db: Database session
            
        Returns:
            Dict with comprehensive comparison data including albums info,
            track-by-track comparison, statistics, and insights
            
        Raises:
            ServiceValidationError: If validation fails
            ServiceNotFoundError: If albums not found
        """
        try:
            # Validate request
            self._validate_comparison_request(album1_id, album2_id)
            
            # Check cache first (cache generates its own key from the arguments)
            cached_result = self.cache.get(album1_id, album2_id)
            if cached_result:
                logger.debug(f"Returning cached comparison for albums {album1_id} vs {album2_id}")
                return cached_result
            
            logger.info(f"Generating comparison for albums {album1_id} vs {album2_id}")
            
            # Load albums with all required data
            album1, album2 = self._get_albums_for_comparison(album1_id, album2_id, db)
            
            # Generate track comparison matrix
            track_matrix = self._get_track_comparison_matrix(album1.tracks, album2.tracks)
            
            # Calculate comparison statistics
            statistics_data = self._calculate_comparison_statistics(album1, album2, track_matrix)
            
            # Identify better tracks
            better_tracks = self._identify_better_tracks(track_matrix)
            
            # Generate insights
            insights = self._generate_insights(album1, album2, statistics_data, better_tracks)
            
            # Build comprehensive response
            comparison_data = {
                "albums": {
                    "album1": self._format_album_data(album1),
                    "album2": self._format_album_data(album2)
                },
                "track_comparison": track_matrix,
                "statistics": statistics_data,
                "better_tracks": better_tracks,
                "insights": insights
            }
            
            # Cache the result (cache generates its own key from the arguments)
            # set(data, ttl, *args) - where args are used to generate the key
            self.cache.set(comparison_data, 300, album1_id, album2_id)  # 5 minute TTL
            
            logger.info(f"Comparison generated successfully for albums {album1_id} vs {album2_id}")
            return comparison_data
            
        except (ServiceValidationError, ServiceNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to generate comparison for albums {album1_id} vs {album2_id}: {e}")
            raise TracklistException(f"Failed to generate album comparison: {str(e)}")
    
    def get_user_rated_albums(self, db: Session, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get list of user's rated albums for comparison selection
        
        Args:
            db: Database session
            limit: Maximum number of albums to return (None for all)
            
        Returns:
            List of album dictionaries with basic info
        """
        try:
            query = (
                db.query(Album)
                .options(joinedload(Album.artist))
                .filter(Album.is_rated == True)
                .order_by(Album.rating_score.desc(), Album.name)
            )
            
            if limit:
                query = query.limit(limit)
                
            albums = query.all()
            
            return [
                {
                    "id": album.id,
                    "name": album.name,
                    "artist": album.artist.name if album.artist else "Unknown Artist",
                    "year": album.release_year,
                    "score": album.rating_score
                }
                for album in albums
            ]
            
        except Exception as e:
            logger.error(f"Failed to get rated albums: {e}")
            raise TracklistException(f"Failed to get rated albums: {str(e)}")
    
    def _validate_comparison_request(self, album1_id: int, album2_id: int) -> None:
        """Validate comparison request parameters"""
        if album1_id == album2_id:
            raise ServiceValidationError("Cannot compare an album to itself")
            
        if album1_id <= 0 or album2_id <= 0:
            raise ServiceValidationError("Invalid album IDs provided")
    
    def _get_cache_key(self, album1_id: int, album2_id: int) -> str:
        """Generate consistent cache key regardless of album order"""
        return f"comparison:{min(album1_id, album2_id)}:{max(album1_id, album2_id)}"
    
    def _get_albums_for_comparison(self, album1_id: int, album2_id: int, db: Session) -> Tuple[Album, Album]:
        """
        Efficiently load albums with all required data for comparison
        
        Args:
            album1_id: First album ID
            album2_id: Second album ID
            db: Database session
            
        Returns:
            Tuple of (album1, album2)
            
        Raises:
            ServiceNotFoundError: If albums not found or not rated
        """
        albums = (
            db.query(Album)
            .options(
                joinedload(Album.artist),
                joinedload(Album.tracks)
            )
            .filter(Album.id.in_([album1_id, album2_id]))
            .filter(Album.is_rated == True)
            .all()
        )
        
        if len(albums) != 2:
            missing_albums = []
            found_ids = [a.id for a in albums]
            if album1_id not in found_ids:
                missing_albums.append(str(album1_id))
            if album2_id not in found_ids:
                missing_albums.append(str(album2_id))
            
            raise ServiceNotFoundError(
                f"Albums not found or not rated: {', '.join(missing_albums)}"
            )
        
        album1 = next(a for a in albums if a.id == album1_id)
        album2 = next(a for a in albums if a.id == album2_id)
        
        return album1, album2
    
    def _get_track_comparison_matrix(
        self, 
        tracks1: List[Track], 
        tracks2: List[Track]
    ) -> List[Dict[str, Any]]:
        """
        Create track-by-track comparison matrix
        
        Args:
            tracks1: Tracks from first album
            tracks2: Tracks from second album
            
        Returns:
            List of track comparison dictionaries
        """
        # Sort tracks by track number
        tracks1_sorted = sorted(tracks1, key=lambda t: t.track_number)
        tracks2_sorted = sorted(tracks2, key=lambda t: t.track_number)
        
        # Align tracks for comparison
        aligned_pairs = self._align_tracks(tracks1_sorted, tracks2_sorted)
        
        track_matrix = []
        for track_num, (track1, track2) in enumerate(aligned_pairs, 1):
            comparison_row = {
                "track_number": track_num,
                "album1_track": self._format_track_data(track1) if track1 else None,
                "album2_track": self._format_track_data(track2) if track2 else None,
                "rating_difference": None,
                "better_album": "tie",
                "difference_category": "tie"
            }
            
            # Calculate rating difference if both tracks exist and are rated
            if (track1 and track2 and 
                track1.track_rating is not None and 
                track2.track_rating is not None):
                
                diff = track1.track_rating - track2.track_rating
                comparison_row["rating_difference"] = round(diff, 2)
                comparison_row["difference_category"] = self._categorize_difference(diff)
                
                if abs(diff) > DIFFERENCE_THRESHOLDS['tie']:
                    comparison_row["better_album"] = "album1" if diff > 0 else "album2"
            
            track_matrix.append(comparison_row)
        
        return track_matrix
    
    def _align_tracks(self, tracks1: List[Track], tracks2: List[Track]) -> List[Tuple[Optional[Track], Optional[Track]]]:
        """
        Align tracks for comparison using track number matching
        
        Args:
            tracks1: First album tracks (sorted by track_number)
            tracks2: Second album tracks (sorted by track_number)
            
        Returns:
            List of (track1, track2) tuples aligned by track number
        """
        aligned_pairs = []
        max_tracks = max(len(tracks1), len(tracks2))
        
        for i in range(max_tracks):
            track1 = tracks1[i] if i < len(tracks1) else None
            track2 = tracks2[i] if i < len(tracks2) else None
            aligned_pairs.append((track1, track2))
        
        return aligned_pairs
    
    def _categorize_difference(self, diff: float) -> str:
        """Categorize rating difference magnitude"""
        abs_diff = abs(diff)
        
        if abs_diff >= DIFFERENCE_THRESHOLDS['significant']:
            return 'significant'
        elif abs_diff >= DIFFERENCE_THRESHOLDS['moderate']:
            return 'moderate'
        elif abs_diff >= DIFFERENCE_THRESHOLDS['slight']:
            return 'slight'
        else:
            return 'tie'
    
    def _calculate_comparison_statistics(
        self, 
        album1: Album, 
        album2: Album, 
        track_matrix: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive comparison statistics
        
        Args:
            album1: First album
            album2: Second album
            track_matrix: Track comparison matrix
            
        Returns:
            Dict with comparison statistics
        """
        # Count track wins
        album1_wins = sum(1 for row in track_matrix if row["better_album"] == "album1")
        album2_wins = sum(1 for row in track_matrix if row["better_album"] == "album2")
        ties = sum(1 for row in track_matrix if row["better_album"] == "tie")
        
        # Calculate average ratings
        album1_ratings = [t.track_rating for t in album1.tracks if t.track_rating is not None]
        album2_ratings = [t.track_rating for t in album2.tracks if t.track_rating is not None]
        
        avg_rating1 = statistics.mean(album1_ratings) if album1_ratings else 0
        avg_rating2 = statistics.mean(album2_ratings) if album2_ratings else 0
        
        # Calculate rating differences for statistics
        differences = [
            row["rating_difference"] for row in track_matrix 
            if row["rating_difference"] is not None
        ]
        
        # Determine overall winner
        score_diff = album1.rating_score - album2.rating_score
        if abs(score_diff) <= 2:  # Within 2 points is considered a tie
            winner = "tie"
        else:
            winner = "album1" if score_diff > 0 else "album2"
        
        statistics_data = {
            "winner": {
                "album": winner,
                "score_difference": score_diff
            },
            "track_wins": {
                "album1_wins": album1_wins,
                "album2_wins": album2_wins,
                "ties": ties
            },
            "average_ratings": {
                "album1": round(avg_rating1, 3),
                "album2": round(avg_rating2, 3)
            }
        }
        
        # Add rating difference statistics if we have differences
        if differences:
            statistics_data["rating_differences"] = {
                "mean": round(statistics.mean(differences), 3),
                "max": round(max(differences), 2),
                "min": round(min(differences), 2),
                "std_dev": round(statistics.stdev(differences), 3) if len(differences) > 1 else 0
            }
        
        return statistics_data
    
    def _identify_better_tracks(
        self, 
        track_matrix: List[Dict[str, Any]], 
        threshold: float = 0.34
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Identify tracks where one album significantly outperforms the other
        
        Args:
            track_matrix: Track comparison matrix
            threshold: Minimum difference to consider "significantly better"
            
        Returns:
            Dict with lists of significantly better tracks for each album
        """
        album1_better = []
        album2_better = []
        
        for row in track_matrix:
            if (row["rating_difference"] is not None and 
                abs(row["rating_difference"]) >= threshold):
                
                track_info = {
                    "track_number": row["track_number"],
                    "rating_difference": row["rating_difference"],
                    "difference_category": row["difference_category"]
                }
                
                if row["rating_difference"] > 0:
                    track_info["track_name"] = row["album1_track"]["name"] if row["album1_track"] else f"Track {row['track_number']}"
                    track_info["rating"] = row["album1_track"]["rating"] if row["album1_track"] else None
                    album1_better.append(track_info)
                else:
                    track_info["track_name"] = row["album2_track"]["name"] if row["album2_track"] else f"Track {row['track_number']}"
                    track_info["rating"] = row["album2_track"]["rating"] if row["album2_track"] else None
                    album2_better.append(track_info)
        
        return {
            "album1_significantly_better": album1_better,
            "album2_significantly_better": album2_better
        }
    
    def _generate_insights(
        self, 
        album1: Album, 
        album2: Album, 
        statistics: Dict[str, Any],
        better_tracks: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        Generate comparison insights and summary
        
        Args:
            album1: First album
            album2: Second album
            statistics: Comparison statistics
            better_tracks: Better tracks analysis
            
        Returns:
            Dict with insights and highlights
        """
        highlights = []
        
        # Winner insight
        winner_data = statistics["winner"]
        if winner_data["album"] == "tie":
            summary = f"Close match! Both albums scored very similarly (difference: {abs(winner_data['score_difference'])} points)."
        elif winner_data["album"] == "album1":
            summary = f"{album1.name} wins with a {winner_data['score_difference']}-point advantage."
        else:
            summary = f"{album2.name} wins with a {abs(winner_data['score_difference'])}-point advantage."
        
        # Track wins insight
        track_wins = statistics["track_wins"]
        if track_wins["album1_wins"] > track_wins["album2_wins"]:
            highlights.append(f"{album1.name} has better individual tracks ({track_wins['album1_wins']} vs {track_wins['album2_wins']} track wins)")
        elif track_wins["album2_wins"] > track_wins["album1_wins"]:
            highlights.append(f"{album2.name} has better individual tracks ({track_wins['album2_wins']} vs {track_wins['album1_wins']} track wins)")
        else:
            highlights.append(f"Even track performance ({track_wins['album1_wins']} wins each)")
        
        # Better tracks insights
        album1_better_count = len(better_tracks["album1_significantly_better"])
        album2_better_count = len(better_tracks["album2_significantly_better"])
        
        if album1_better_count > 0:
            highlights.append(f"{album1.name} has {album1_better_count} standout track(s)")
        if album2_better_count > 0:
            highlights.append(f"{album2.name} has {album2_better_count} standout track(s)")
        
        # Rating consistency insight
        if "rating_differences" in statistics:
            std_dev = statistics["rating_differences"]["std_dev"]
            if std_dev < 0.15:
                highlights.append("Very consistent rating differences across tracks")
            elif std_dev > 0.35:
                highlights.append("Highly variable track preferences between albums")
        
        return {
            "summary": summary,
            "highlights": highlights
        }
    
    def _format_album_data(self, album: Album) -> Dict[str, Any]:
        """Format album data for comparison response"""
        # Get cached artwork URL if available
        from ..template_utils import get_artwork_url
        cached_artwork_url = get_artwork_url(album, size='large')
        
        # Calculate average track rating
        rated_tracks = [t.track_rating for t in album.tracks if t.track_rating is not None]
        avg_track_rating = statistics.mean(rated_tracks) if rated_tracks else 0
        
        return {
            "id": album.id,
            "name": album.name,
            "artist": {
                "name": album.artist.name if album.artist else "Unknown Artist",
                "id": album.artist.id if album.artist else None
            },
            "year": album.release_year,
            "rating_score": album.rating_score,
            "total_tracks": album.total_tracks,
            "cover_art_url": cached_artwork_url,
            "average_track_rating": round(avg_track_rating, 3),
            "musicbrainz_id": album.musicbrainz_id
        }
    
    def _format_track_data(self, track: Track) -> Dict[str, Any]:
        """Format track data for comparison response"""
        return {
            "id": track.id,
            "name": track.name,
            "track_number": track.track_number,
            "rating": track.track_rating,
            "duration_ms": track.duration_ms
        }


# Global service instance
_comparison_service = None


def get_comparison_service() -> ComparisonService:
    """Get or create the global comparison service instance"""
    global _comparison_service
    if _comparison_service is None:
        _comparison_service = ComparisonService()
    return _comparison_service