"""
Album rating API endpoints
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import logging
import json

from ..database import get_db
from ..rating_service import get_rating_service, RatingService
from ..exceptions import TracklistException, NotFoundError, ValidationError, ServiceNotFoundError, ServiceValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["albums"])
templates = Jinja2Templates(directory="templates")


class TrackRatingRequest(BaseModel):
    """Request model for track rating"""
    rating: float = Field(..., description="Track rating (0.0, 0.33, 0.67, 1.0)")


class AlbumCreateRequest(BaseModel):
    """Request model for creating album"""
    musicbrainz_id: str = Field(..., description="MusicBrainz release ID", min_length=36, max_length=36)


@router.post("/albums")
async def create_album_for_rating(
    request: Request,
    musicbrainz_id: str = Form(...),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
):
    """
    Create album for rating from MusicBrainz data
    
    Creates a local album record with all tracks from MusicBrainz,
    ready for track-by-track rating. If album already exists,
    returns existing album information.
    
    The album starts in draft mode (is_rated=False) until all
    tracks are rated and the final score is submitted.
    """
    try:
        logger.info(f"Creating album for rating: {musicbrainz_id}")
        
        result = await service.create_album_for_rating(musicbrainz_id, db)
        
        logger.info(f"Album created/retrieved: {result['title']} by {result['artist']['name']}")
        
        # Check if this is an HTMX request
        hx_request = request.headers.get("HX-Request")
        if hx_request:
            # Return HTML button for HTMX
            return HTMLResponse(
                f'''<button class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 cursor-default transition-colors">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Added - <a href="/albums/{result['id']}/rate" class="underline">Rate Now</a>
                </button>'''
            )
        
        # Return JSON for API calls
        return result
        
    except ServiceValidationError as e:
        logger.warning(f"Album creation validation error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Validation error",
                "message": e.message
            }
        )
    except TracklistException as e:
        logger.error(f"Album creation failed: {e.message}")
        
        # Check if it's a MusicBrainz not found error
        if "not found" in e.message.lower():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Album not found",
                    "message": f"Album with MusicBrainz ID '{musicbrainz_id}' not found"
                }
            )
        
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Music service unavailable",
                "message": "Unable to create album for rating. Please try again later."
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error creating album: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred"
            }
        )



@router.put("/tracks/{track_id}/rating")
async def update_track_rating(
    request: Request,
    track_id: int = Path(..., description="Track ID", gt=0),
    rating: float = Form(None),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update track rating (auto-save)
    
    Immediately saves the track rating and returns updated
    album progress including completion percentage and
    projected final score.
    
    Valid ratings:
    - 0.0: Skip always (worst songs)
    - 0.33: Filler/tolerable (don't enjoy but won't skip)
    - 0.67: Good/playlist-worthy (like the track)
    - 1.0: Standout/love it (album highlights)
    """
    try:
        # Handle both JSON and form data
        if rating is None:
            # Try to parse JSON body
            try:
                body = await request.json()
                rating = body.get("rating")
                if rating is None:
                    raise ValueError("Missing rating in request body")
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid request",
                        "message": "Rating value is required"
                    }
                )
        
        logger.info(f"Updating track {track_id} rating to {rating}")
        
        result = service.rate_track(track_id, rating, db)
        
        logger.info(f"Track rating updated successfully: {result['completion_percentage']:.1f}% complete")
        
        # Check if this is an HTMX request
        hx_request = request.headers.get("HX-Request")
        if hx_request:
            # Return a simple success message for HTMX
            # We'll handle the progress update separately through Alpine.js
            return HTMLResponse(
                f'''<span class="text-green-600 text-sm animate-pulse">✓ Saved</span>
                <script>
                    // Dispatch event with progress data
                    window.dispatchEvent(new CustomEvent('rating-updated', {{
                        detail: {{
                            trackId: {track_id},
                            rating: {rating},
                            progress: {json.dumps(result)}
                        }}
                    }}));
                </script>'''
            )
        
        return result
        
    except ServiceNotFoundError as e:
        logger.warning(f"Track not found: {track_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Track not found",
                "message": f"Track with ID {track_id} not found"
            }
        )
    except ServiceValidationError as e:
        logger.warning(f"Invalid track rating: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid rating",
                "message": e.message,
                "valid_ratings": [0.0, 0.33, 0.67, 1.0]
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error rating track: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to save track rating"
            }
        )


@router.get("/albums/{album_id}/progress")
async def get_album_progress(
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get album rating progress
    
    Returns current rating status including:
    - Completion percentage
    - Projected final score (based on current ratings)
    - Track rating summary
    - Whether album is ready for submission
    """
    try:
        logger.info(f"Getting progress for album {album_id}")
        
        result = service.get_album_progress(album_id, db)
        
        logger.debug(f"Album progress: {result['completion_percentage']:.1f}% complete")
        return result
        
    except ServiceNotFoundError as e:
        logger.warning(f"Album not found: {album_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Album not found",
                "message": f"Album with ID {album_id} not found"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting album progress: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to get album progress"
            }
        )


@router.post("/albums/{album_id}/submit")
async def submit_album_rating(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Submit final album rating
    
    Calculates and saves the final album score using the formula:
    Floor((Sum of track ratings / Total tracks × 10) + Album Bonus) × 10
    
    Requirements:
    - All tracks must be rated
    - Album must not be already submitted
    
    Once submitted, the album is marked as completed and
    the final score cannot be changed.
    """
    try:
        logger.info(f"Submitting album rating for album {album_id}")
        
        result = service.submit_album_rating(album_id, db)
        
        logger.info(f"Album rating submitted: {result['title']} - Score: {result['rating_score']}")
        
        # Check if this is an HTMX request
        hx_request = request.headers.get("HX-Request")
        if hx_request:
            # Return success HTML for HTMX
            return HTMLResponse(
                f'''<div class="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                    <div class="flex items-center">
                        <svg class="w-5 h-5 text-green-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <span class="font-semibold text-green-800">Album Rating Submitted!</span>
                    </div>
                    <div class="mt-2 text-sm text-green-700">
                        <p><strong>{result['title']}</strong> by {result['artist']['name']}</p>
                        <p class="text-lg mt-1">Final Score: <span class="font-bold text-xl">{result['rating_score']}</span>/100</p>
                    </div>
                    <div class="mt-3">
                        <a href="/albums/{album_id}/completed" 
                           class="inline-flex items-center px-4 py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-md transition-colors">
                            View Results
                            <svg class="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                            </svg>
                        </a>
                    </div>
                </div>
                <script>
                    // Update the submit button state
                    document.querySelector('.submit-button').style.display = 'none';
                    // Dispatch completion event
                    window.dispatchEvent(new CustomEvent('album-submitted', {{
                        detail: {{
                            albumId: {album_id},
                            finalScore: {result['rating_score']}
                        }}
                    }}));
                </script>'''
            )
        
        return result
        
    except ServiceNotFoundError as e:
        logger.warning(f"Album not found: {album_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Album not found",
                "message": f"Album with ID {album_id} not found"
            }
        )
    except ServiceValidationError as e:
        logger.warning(f"Album submission validation error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Cannot submit album",
                "message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error submitting album: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to submit album rating"
            }
        )


@router.get("/albums/{album_id}")
async def get_album_rating(
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get complete album rating information
    
    Returns full album details including:
    - Album and artist information
    - All track ratings
    - Final score (if submitted)
    - Rating metadata
    """
    try:
        logger.info(f"Getting album rating for album {album_id}")
        
        result = service.get_album_rating(album_id, db)
        
        logger.debug(f"Album rating retrieved: {result['title']}")
        return result
        
    except ServiceNotFoundError as e:
        logger.warning(f"Album not found: {album_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Album not found",
                "message": f"Album with ID {album_id} not found"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting album rating: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to get album rating"
            }
        )


@router.get("/albums")
async def get_user_albums(
    limit: int = Query(50, description="Maximum number of results", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    rated: Optional[bool] = Query(None, description="Filter by rated status (true=rated, false=draft, null=all)"),
    sort: str = Query("created_desc", description="Sort order (created_desc, created_asc, artist_asc, artist_desc, album_asc, album_desc, rating_desc, rating_asc, year_desc, year_asc, rated_desc)"),
    search: Optional[str] = Query(None, description="Search query for album title or artist name"),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get user's albums
    
    Returns paginated list of user's albums with optional filtering, sorting, and searching:
    - rated=true: Only completed/submitted albums
    - rated=false: Only draft/in-progress albums
    - rated=null: All albums (default)
    - search: Filter by album title or artist name (case-insensitive partial match)
    
    Sorting options:
    - created_desc/created_asc: By date added (default: newest first)
    - artist_asc/artist_desc: By artist name (A→Z / Z→A)
    - album_asc/album_desc: By album name (A→Z / Z→A)
    - rating_desc/rating_asc: By rating score (100→0 / 0→100)
    - year_desc/year_asc: By release year (newest/oldest first)
    - rated_desc: By recently rated (completed albums first)
    """
    try:
        logger.info(f"Getting user albums: limit={limit}, offset={offset}, rated={rated}, sort={sort}, search={search}")
        
        result = service.get_user_albums(db, limit, offset, rated, sort, search)
        
        logger.debug(f"Retrieved {len(result['albums'])} albums (total: {result['total']})")
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error getting user albums: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to get user albums"
            }
        )


@router.delete("/albums/{album_id}")
async def delete_album(
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Delete album and all associated data
    
    Performs a hard delete of:
    - Album record
    - All associated tracks and ratings
    - All metadata and scores
    
    This action cannot be undone.
    """
    try:
        logger.info(f"Deleting album {album_id}")
        
        result = service.delete_album(album_id, db)
        
        logger.info(f"Album {album_id} deleted successfully")
        return result
        
    except ServiceNotFoundError as e:
        logger.warning(f"Album not found for deletion: {album_id}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Album not found",
                "message": f"Album with ID {album_id} not found"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting album: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to delete album"
            }
        )