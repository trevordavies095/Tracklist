"""
MusicBrainz API client with rate limiting and caching
Respects the MusicBrainz API limit of 1 call per second
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
import httpx
import logging
from urllib.parse import urlencode

from .exceptions import TracklistException

logger = logging.getLogger(__name__)


class MusicBrainzRateLimiter:
    """Rate limiter that enforces 1 call per second to MusicBrainz API"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to make an API call"""
        async with self._lock:
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            
            if time_since_last_call < self.min_interval:
                sleep_time = self.min_interval - time_since_last_call
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
            
            self.last_call_time = time.time()


class MusicBrainzAPIError(TracklistException):
    """Exception raised when MusicBrainz API calls fail"""
    pass


class MusicBrainzClient:
    """
    Async MusicBrainz API client with rate limiting and error handling
    """
    
    BASE_URL = "https://musicbrainz.org/ws/2"
    USER_AGENT = "Tracklist/1.0.0 (https://github.com/tracklist/tracklist)"
    
    def __init__(self):
        self.rate_limiter = MusicBrainzRateLimiter(calls_per_second=1.0)
        self.client = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            headers={"User-Agent": self.USER_AGENT},
            timeout=httpx.Timeout(30.0)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a rate-limited request to MusicBrainz API
        
        Args:
            endpoint: API endpoint (e.g., 'release')
            params: Query parameters
            
        Returns:
            Dict containing the API response
            
        Raises:
            MusicBrainzAPIError: If the API request fails
        """
        if not self.client:
            raise MusicBrainzAPIError("Client not initialized. Use async context manager.")
        
        # Ensure rate limiting
        await self.rate_limiter.acquire()
        
        # Add format parameter
        params = {**params, "fmt": "json"}
        
        url = f"{self.BASE_URL}/{endpoint}"
        query_string = urlencode(params)
        full_url = f"{url}?{query_string}"
        
        logger.info(f"Making MusicBrainz API request: {endpoint}")
        logger.debug(f"Full URL: {full_url}")
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"MusicBrainz API response received: {len(str(data))} characters")
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"MusicBrainz API HTTP error: {e.response.status_code} - {e.response.text}")
            raise MusicBrainzAPIError(
                f"MusicBrainz API HTTP error: {e.response.status_code}",
                {"status_code": e.response.status_code, "response": e.response.text}
            )
        except httpx.RequestError as e:
            logger.error(f"MusicBrainz API request error: {e}")
            raise MusicBrainzAPIError(
                f"MusicBrainz API request failed: {str(e)}",
                {"error_type": type(e).__name__}
            )
        except ValueError as e:
            logger.error(f"MusicBrainz API JSON parsing error: {e}")
            raise MusicBrainzAPIError(
                "Failed to parse MusicBrainz API response",
                {"error": str(e)}
            )
    
    async def search_releases(
        self, 
        query: str, 
        limit: int = 25, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Search for album releases
        
        Args:
            query: Search query string
            limit: Maximum number of results (default 25, max 100)
            offset: Offset for pagination
            
        Returns:
            Dict containing search results with releases
        """
        limit = min(limit, 100)  # MusicBrainz API limit
        
        params = {
            "query": query,
            "limit": limit,
            "offset": offset
        }
        
        return await self._make_request("release", params)
    
    async def search_releases_structured(
        self,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 25,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Search for releases using structured Lucene query
        
        Args:
            artist: Artist name to search for
            album: Album title to search for
            year: Release year to filter by
            limit: Maximum number of results (default 25, max 100)
            offset: Offset for pagination
            
        Returns:
            Dict containing search results with releases
        """
        limit = min(limit, 100)  # MusicBrainz API limit
        
        # Build Lucene query
        query_parts = []
        
        if artist:
            # Escape special characters and quote the artist name
            escaped_artist = artist.replace('"', '\\"')
            query_parts.append(f'artist:"{escaped_artist}"')
        
        if album:
            # Escape special characters and quote the album title
            escaped_album = album.replace('"', '\\"')
            query_parts.append(f'release:"{escaped_album}"')
        
        if year:
            # Use date field for year filtering
            # MusicBrainz accepts date:YYYY or date:[YYYY-01-01 TO YYYY-12-31]
            query_parts.append(f'date:{year}')
        
        # Join query parts with AND operator
        query = " AND ".join(query_parts)
        
        # Fallback to empty query if no parts
        if not query:
            query = "*"
        
        logger.debug(f"Structured Lucene query: {query}")
        
        params = {
            "query": query,
            "limit": limit,
            "offset": offset
        }
        
        return await self._make_request("release", params)
    
    async def search_releases_by_release_group(
        self, 
        release_group_id: str, 
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Search for releases in a specific release group
        
        Args:
            release_group_id: MusicBrainz release group ID
            limit: Maximum number of results (default 100, max 100)
            
        Returns:
            Dict containing releases in the release group
        """
        limit = min(limit, 100)  # MusicBrainz API limit
        
        params = {
            "query": f"rgid:{release_group_id}",
            "limit": limit,
            "offset": 0
        }
        
        return await self._make_request("release", params)
    
    async def get_release_details(
        self, 
        release_id: str, 
        include: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a release
        
        Args:
            release_id: MusicBrainz release ID
            include: List of additional data to include (e.g., ['artist-credits', 'recordings'])
            
        Returns:
            Dict containing detailed release information
        """
        params = {}
        
        if include:
            # Common includes: artist-credits, recordings, release-groups
            params["inc"] = "+".join(include)
        
        return await self._make_request(f"release/{release_id}", params)
    
    async def get_release_with_tracks(self, release_id: str) -> Dict[str, Any]:
        """
        Get release with full track listing
        
        Args:
            release_id: MusicBrainz release ID
            
        Returns:
            Dict containing release with complete track information
        """
        include = ["artist-credits", "recordings", "media", "release-groups"]
        return await self.get_release_details(release_id, include)


# Global client instance for dependency injection
_musicbrainz_client = None


async def get_musicbrainz_client() -> MusicBrainzClient:
    """
    Dependency function to get MusicBrainz client instance
    """
    global _musicbrainz_client
    if _musicbrainz_client is None:
        _musicbrainz_client = MusicBrainzClient()
    return _musicbrainz_client