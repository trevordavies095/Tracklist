"""
MusicBrainz service layer with caching and data transformation
Provides high-level interface for album search and retrieval
"""

from typing import Dict, List, Optional, Any
import logging

from .musicbrainz_client import MusicBrainzClient, MusicBrainzAPIError
from .cache import get_cache
from .exceptions import TracklistException

logger = logging.getLogger(__name__)


class MusicBrainzService:
    """
    High-level service for MusicBrainz operations with caching
    """
    
    def __init__(self):
        self.cache = get_cache()
    
    async def search_albums(
        self, 
        query: str, 
        limit: int = 25, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Search for albums with caching
        
        Args:
            query: Search query string
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            Dict with formatted search results
        """
        # Check cache first
        cached_result = self.cache.get(f"search:{query}:{limit}:{offset}")
        if cached_result:
            logger.info(f"Returning cached search results for: {query}")
            return cached_result
        
        # Make API call
        async with MusicBrainzClient() as client:
            try:
                raw_data = await client.search_releases(query, limit, offset)
                result = self._format_search_results(raw_data)
                
                # Cache the result for 30 minutes (search results change more frequently)
                self.cache.set(result, 1800, f"search:{query}:{limit}:{offset}")
                
                logger.info(f"Search completed for '{query}': {len(result.get('releases', []))} results")
                return result
                
            except MusicBrainzAPIError as e:
                logger.error(f"MusicBrainz search failed for '{query}': {e.message}")
                raise TracklistException(
                    f"Album search failed: {e.message}",
                    {"query": query, "error": e.details}
                )
    
    async def get_album_details(self, release_id: str) -> Dict[str, Any]:
        """
        Get detailed album information with caching
        
        Args:
            release_id: MusicBrainz release ID
            
        Returns:
            Dict with formatted album details including tracks
        """
        # Check cache first
        cached_result = self.cache.get(f"album:{release_id}")
        if cached_result:
            logger.info(f"Returning cached album details for: {release_id}")
            return cached_result
        
        # Make API call
        async with MusicBrainzClient() as client:
            try:
                raw_data = await client.get_release_with_tracks(release_id)
                result = self._format_album_details(raw_data)
                
                # Cache album details for 24 hours (rarely change)
                self.cache.set(result, 86400, f"album:{release_id}")
                
                logger.info(f"Album details retrieved for: {release_id}")
                return result
                
            except MusicBrainzAPIError as e:
                logger.error(f"MusicBrainz album fetch failed for '{release_id}': {e.message}")
                raise TracklistException(
                    f"Album details fetch failed: {e.message}",
                    {"release_id": release_id, "error": e.details}
                )
    
    async def get_release_group_releases(self, release_group_id: str) -> List[Dict[str, Any]]:
        """
        Get all releases from a release group
        
        Args:
            release_group_id: MusicBrainz release group ID
            
        Returns:
            List of releases in the release group
        """
        cache_key = f"release_group:{release_group_id}"
        
        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for release group: {release_group_id}")
            return cached_result
        
        try:
            logger.info(f"Fetching releases for release group: {release_group_id}")
            
            # Query for releases in the release group
            async with MusicBrainzClient() as client:
                raw_data = await client.search_releases_by_release_group(release_group_id, limit=100)
            
            releases = []
            for release in raw_data.get("releases", []):
                # Extract artist name
                artist_name = "Unknown Artist"
                artist_mbid = None
                if release.get("artist-credit"):
                    artist_credit = release["artist-credit"][0]
                    artist_name = artist_credit.get("name", "Unknown Artist")
                    if artist_credit.get("artist"):
                        artist_mbid = artist_credit["artist"].get("id")
                
                # Calculate total track count
                track_count = 0
                formats = []
                for medium in release.get("media", []):
                    track_count += medium.get("track-count", 0)
                    if medium.get("format"):
                        formats.append(medium["format"])
                
                # Extract year from date
                year = None
                if release.get("date"):
                    try:
                        year = int(release["date"][:4])
                    except (ValueError, IndexError):
                        pass
                
                formatted_release = {
                    "musicbrainz_id": release.get("id"),
                    "title": release.get("title", "Unknown Title"),
                    "artist": {
                        "name": artist_name,
                        "musicbrainz_id": artist_mbid
                    },
                    "year": year,
                    "track_count": track_count,
                    "format": ", ".join(formats) if formats else None,
                    "country": release.get("country"),
                    "status": release.get("status")
                }
                
                releases.append(formatted_release)
            
            # Cache the result
            self.cache.set(releases, 3600, cache_key)  # Cache for 1 hour
            
            logger.info(f"Found {len(releases)} releases in release group: {release_group_id}")
            return releases
            
        except MusicBrainzAPIError as e:
            logger.error(f"MusicBrainz release group fetch failed for '{release_group_id}': {e.message}")
            raise TracklistException(
                f"Release group fetch failed: {e.message}",
                {"release_group_id": release_group_id, "error": e.details}
            )
    
    def _format_search_results(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw MusicBrainz search results into our standard format
        
        Args:
            raw_data: Raw MusicBrainz API response
            
        Returns:
            Formatted search results
        """
        releases = []
        
        for release in raw_data.get("releases", []):
            # Extract artist name
            artist_name = "Unknown Artist"
            if release.get("artist-credit"):
                artist_name = release["artist-credit"][0].get("name", "Unknown Artist")
            
            # Format release data
            formatted_release = {
                "musicbrainz_id": release.get("id"),
                "title": release.get("title", "Unknown Title"),
                "artist": artist_name,
                "date": release.get("date"),
                "country": release.get("country"),
                "status": release.get("status"),
                "packaging": release.get("packaging"),
                "track_count": release.get("track-count"),
                "media": []
            }
            
            # Extract media information
            for medium in release.get("media", []):
                formatted_release["media"].append({
                    "format": medium.get("format"),
                    "track_count": medium.get("track-count"),
                    "title": medium.get("title")
                })
            
            # Calculate release year
            if formatted_release["date"]:
                try:
                    formatted_release["year"] = int(formatted_release["date"][:4])
                except (ValueError, TypeError):
                    formatted_release["year"] = None
            else:
                formatted_release["year"] = None
            
            releases.append(formatted_release)
        
        return {
            "releases": releases,
            "count": raw_data.get("count", 0),
            "offset": raw_data.get("offset", 0)
        }
    
    def _format_album_details(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw MusicBrainz album details into our standard format
        
        Args:
            raw_data: Raw MusicBrainz API response
            
        Returns:
            Formatted album details with tracks
        """
        # Extract basic album info
        artist_name = "Unknown Artist"
        artist_id = None
        
        if raw_data.get("artist-credit"):
            artist_credit = raw_data["artist-credit"][0]
            artist_name = artist_credit.get("name", "Unknown Artist")
            if artist_credit.get("artist"):
                artist_id = artist_credit["artist"].get("id")
        
        album = {
            "musicbrainz_id": raw_data.get("id"),
            "title": raw_data.get("title", "Unknown Title"),
            "artist": {
                "name": artist_name,
                "musicbrainz_id": artist_id
            },
            "date": raw_data.get("date"),
            "country": raw_data.get("country"),
            "status": raw_data.get("status"),
            "packaging": raw_data.get("packaging"),
            "barcode": raw_data.get("barcode"),
            "release_group_id": raw_data.get("release-group", {}).get("id") if raw_data.get("release-group") else None,
            "tracks": [],
            "total_tracks": 0,
            "total_duration_ms": 0
        }
        
        # Calculate release year
        if album["date"]:
            try:
                album["year"] = int(album["date"][:4])
            except (ValueError, TypeError):
                album["year"] = None
        else:
            album["year"] = None
        
        # Extract track information
        track_number = 1
        total_duration = 0
        
        for medium in raw_data.get("media", []):
            for track in medium.get("tracks", []):
                track_title = track.get("title", f"Track {track_number}")
                
                # Extract track duration
                duration_ms = None
                if track.get("length"):
                    try:
                        duration_ms = int(track["length"])
                        total_duration += duration_ms
                    except (ValueError, TypeError):
                        pass
                
                # Extract recording ID
                recording_id = None
                if track.get("recording"):
                    recording_id = track["recording"].get("id")
                
                formatted_track = {
                    "track_number": track_number,
                    "title": track_title,
                    "duration_ms": duration_ms,
                    "musicbrainz_recording_id": recording_id
                }
                
                album["tracks"].append(formatted_track)
                track_number += 1
        
        album["total_tracks"] = len(album["tracks"])
        album["total_duration_ms"] = total_duration if total_duration > 0 else None
        
        return album
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()


# Global service instance
_musicbrainz_service = None


def get_musicbrainz_service() -> MusicBrainzService:
    """Get the global MusicBrainz service instance"""
    global _musicbrainz_service
    if _musicbrainz_service is None:
        _musicbrainz_service = MusicBrainzService()
    return _musicbrainz_service