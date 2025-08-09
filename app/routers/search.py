"""
Search API endpoints for MusicBrainz integration
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import logging

from ..musicbrainz_service import get_musicbrainz_service, MusicBrainzService
from ..exceptions import TracklistException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["search"])
templates = Jinja2Templates(directory="templates")


@router.get("/search/albums")
async def search_albums(
    request: Request,
    q: Optional[str] = Query(None, description="General search query for albums", min_length=1, max_length=200),
    artist: Optional[str] = Query(None, description="Artist name for structured search", max_length=200),
    album: Optional[str] = Query(None, description="Album title for structured search", max_length=200),
    year: Optional[int] = Query(None, description="Release year for structured search", ge=1900, le=2100),
    mbid: Optional[str] = Query(None, description="MusicBrainz Release ID for direct lookup", regex="^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"),
    limit: int = Query(25, description="Maximum number of results", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    service: MusicBrainzService = Depends(get_musicbrainz_service)
):
    """
    Search for albums using MusicBrainz
    
    Supports multiple search methods:
    1. General search: Uses the 'q' parameter for full-text search
    2. Structured search: Uses artist, album, and/or year fields for precise queries
    3. Direct lookup: Uses mbid for immediate album fetch
    
    Returns paginated search results with album information including:
    - Album title and artist
    - Release year and country
    - Track count and media format
    - MusicBrainz ID for detailed lookup
    """
    try:
        # Validate that at least one search method is provided
        if not any([q, artist, album, mbid]):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Missing search parameters",
                    "message": "Please provide at least one search parameter (q, artist, album, or mbid)"
                }
            )
        
        # Handle direct MusicBrainz ID lookup
        if mbid:
            logger.info(f"Direct album lookup request: {mbid}")
            
            # Use the existing album details endpoint internally
            album_details = await service.get_album_details(mbid)
            
            # Format as search results for consistency
            results = {
                "releases": [{
                    "musicbrainz_id": album_details["musicbrainz_id"],
                    "title": album_details["title"],
                    "artist": album_details["artist"]["name"],
                    "date": album_details["date"],
                    "year": album_details["year"],
                    "country": album_details["country"],
                    "status": album_details["status"],
                    "packaging": album_details["packaging"],
                    "track_count": album_details["total_tracks"],
                    "media": []
                }],
                "count": 1,
                "offset": 0,
                "search_context": {
                    "type": "direct_lookup",
                    "mbid": mbid
                }
            }
        
        # Handle structured search
        elif artist or album:
            search_params = {
                "artist": artist,
                "album": album,
                "year": year
            }
            logger.info(f"Structured album search request: {search_params}")
            
            results = await service.search_albums_structured(
                artist=artist,
                album=album,
                year=year,
                limit=limit,
                offset=offset
            )
            
            results["search_context"] = {
                "type": "structured",
                "artist": artist,
                "album": album,
                "year": year
            }
        
        # Handle general search
        else:
            logger.info(f"General album search request: '{q}' (limit={limit}, offset={offset})")
            
            results = await service.search_albums(q, limit, offset)
            
            results["search_context"] = {
                "type": "general",
                "query": q
            }
        
        # Add pagination metadata
        results["pagination"] = {
            "limit": limit,
            "offset": offset,
            "total": results.get("count", 0),
            "has_more": (offset + limit) < results.get("count", 0)
        }
        
        logger.info(f"Search completed: {len(results.get('releases', []))} results returned")
        
        # Check if this is an HTMX request
        hx_request = request.headers.get("HX-Request")
        if hx_request:
            # Prepare template context
            template_context = {
                "request": request,
                "albums": results.get("releases", []),
                "total": results.get("count", 0),
                "offset": offset,
                "limit": limit,
                "has_more": (offset + limit) < results.get("count", 0),
                "search_context": results.get("search_context"),
                "query": q,
                "artist": artist,
                "album": album,
                "year": year,
                "mbid": mbid
            }
            
            # Return HTML template for HTMX
            return templates.TemplateResponse(
                "components/search_results.html",
                template_context
            )
        
        # Return JSON for API calls
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