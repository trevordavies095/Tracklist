"""
Search API endpoints for MusicBrainz integration
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
import logging

from ..musicbrainz_service import get_musicbrainz_service, MusicBrainzService
from ..exceptions import TracklistException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search/albums")
async def search_albums(
    q: str = Query(..., description="Search query for albums", min_length=1, max_length=200),
    limit: int = Query(25, description="Maximum number of results", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    service: MusicBrainzService = Depends(get_musicbrainz_service)
) -> Dict[str, Any]:
    """
    Search for albums using MusicBrainz
    
    Returns paginated search results with album information including:
    - Album title and artist
    - Release year and country
    - Track count and media format
    - MusicBrainz ID for detailed lookup
    
    Query examples:
    - Artist and album: "radiohead ok computer"
    - Album only: "ok computer"
    - Artist only: "radiohead"
    """
    try:
        logger.info(f"Album search request: '{q}' (limit={limit}, offset={offset})")
        
        results = await service.search_albums(q, limit, offset)
        
        # Add pagination metadata
        results["pagination"] = {
            "limit": limit,
            "offset": offset,
            "total": results.get("count", 0),
            "has_more": (offset + limit) < results.get("count", 0)
        }
        
        logger.info(f"Search completed: {len(results.get('releases', []))} results returned")
        return results
        
    except TracklistException as e:
        logger.error(f"Search failed: {e.message}")
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Search service unavailable",
                "message": "Unable to search albums at this time. Please try again later.",
                "details": e.details
            }
        )
    except Exception as e:
        logger.error(f"Unexpected search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred during search"
            }
        )


@router.get("/albums/{musicbrainz_id}/details")
async def get_album_details(
    musicbrainz_id: str,
    service: MusicBrainzService = Depends(get_musicbrainz_service)
) -> Dict[str, Any]:
    """
    Get detailed album information by MusicBrainz ID
    
    Returns complete album information including:
    - Album and artist details
    - Complete track listing with durations
    - Release information (year, country, format)
    - MusicBrainz metadata
    
    Use this endpoint after getting a MusicBrainz ID from search results
    to get the full album details needed for rating.
    """
    try:
        logger.info(f"Album details request: {musicbrainz_id}")
        
        # Validate MusicBrainz ID format (36 character UUID)
        if len(musicbrainz_id) != 36 or musicbrainz_id.count('-') != 4:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid MusicBrainz ID",
                    "message": "MusicBrainz ID must be a valid UUID format"
                }
            )
        
        album_details = await service.get_album_details(musicbrainz_id)
        
        logger.info(f"Album details retrieved: {album_details.get('title', 'Unknown')} - {album_details.get('total_tracks', 0)} tracks")
        return album_details
        
    except TracklistException as e:
        logger.error(f"Album details fetch failed: {e.message}")
        
        # Check if it's a "not found" type error
        if "not found" in e.message.lower() or any(
            error_code in str(e.details) for error_code in ["404", "400"]
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Album not found",
                    "message": f"Album with MusicBrainz ID '{musicbrainz_id}' not found",
                    "musicbrainz_id": musicbrainz_id
                }
            )
        
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Music service unavailable",
                "message": "Unable to fetch album details at this time. Please try again later.",
                "details": e.details
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected album details error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred while fetching album details"
            }
        )


@router.get("/cache/stats")
async def get_cache_stats(
    service: MusicBrainzService = Depends(get_musicbrainz_service)
) -> Dict[str, Any]:
    """
    Get cache statistics for monitoring and debugging
    
    Returns information about cached MusicBrainz responses including:
    - Total number of cached entries
    - Active vs expired entries
    - Cache configuration
    """
    try:
        stats = service.get_cache_stats()
        logger.debug(f"Cache stats requested: {stats}")
        return {
            "cache_stats": stats,
            "status": "healthy"
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unable to get cache statistics",
                "message": str(e)
            }
        )


@router.delete("/cache")
async def clear_cache(
    service: MusicBrainzService = Depends(get_musicbrainz_service)
) -> Dict[str, str]:
    """
    Clear all cached MusicBrainz data
    
    Useful for debugging or when cached data becomes stale.
    This will force fresh API calls for subsequent requests.
    """
    try:
        service.clear_cache()
        logger.info("Cache cleared via API request")
        return {
            "message": "Cache cleared successfully",
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unable to clear cache",
                "message": str(e)
            }
        )