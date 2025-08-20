"""
Album rating API endpoints
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field
import logging
import json
import asyncio

from ..database import get_db, get_db_info, SessionLocal
from ..rating_service import get_rating_service, RatingService
from ..services.comparison_service import get_comparison_service, ComparisonService
from ..exceptions import TracklistException, ServiceNotFoundError, ServiceValidationError

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
                f'''<a href="/albums/{result['id']}/rate" class="flex-1 sm:flex-none inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 transition-colors">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    Rate Now
                </a>'''
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
            # Return an empty response for HTMX
            # We'll handle the progress update separately through Alpine.js
            return HTMLResponse(
                f'''<script>
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


@router.put("/albums/{album_id}/notes")
async def update_album_notes(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update notes for an album

    Allows adding or updating personal notes for an album.
    Notes are limited to 5000 characters and can be updated
    at any time during or after the rating process.
    """
    try:
        # Get notes from request body
        if request.headers.get("content-type") == "application/x-www-form-urlencoded":
            form = await request.form()
            notes = form.get("notes", "")
        else:
            try:
                body = await request.json()
                notes = body.get("notes", "")
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid request",
                        "message": "Notes value is required"
                    }
                )

        logger.info(f"Updating notes for album {album_id}")

        result = service.update_album_notes(album_id, notes, db)

        logger.info(f"Notes updated successfully for album {album_id}")

        # Check if this is an HTMX request
        hx_request = request.headers.get("HX-Request")
        if hx_request:
            # Return a simple success response for HTMX
            return HTMLResponse(
                '''<div class="text-green-600">Notes saved</div>'''
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
        logger.warning(f"Invalid notes: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid notes",
                "message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error updating album notes: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to save album notes"
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


@router.get("/albums/{album_id}/artwork-url")
async def get_album_artwork_url(
    album_id: int = Path(..., description="Album ID", gt=0),
    size: str = Query("medium", description="Size variant"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get cached artwork URL for an album

    Returns the cached URL if available, otherwise returns the external URL
    """
    from ..template_utils import get_artwork_url as get_cached_url
    from ..models import Album

    # Get album
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    # Get artwork URL using the template utility
    url = get_cached_url(album, size)

    return {
        "url": url,
        "cached": url and not url.startswith("http"),  # Cached URLs are local paths
        "size": size
    }


@router.get("/albums/compare")
async def compare_albums(
    album1: int = Query(..., description="First album ID", gt=0),
    album2: int = Query(..., description="Second album ID", gt=0),
    format: str = Query("json", description="Response format (html|json)"),
    comparison_service: ComparisonService = Depends(get_comparison_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Compare two albums side-by-side
    
    Provides detailed track-by-track comparison with statistics,
    visual indicators, and insights about rating differences.
    
    Query Parameters:
    - album1: ID of first album to compare
    - album2: ID of second album to compare  
    - format: Response format (html for web view, json for API)
    
    Validation:
    - Both albums must exist and be rated
    - Albums must be different
    - User must have permission to view both albums
    
    Returns comprehensive comparison data including:
    - Album metadata and cover art
    - Track-by-track comparison matrix
    - Winner determination and statistics
    - Rating difference analysis
    - Better tracks identification
    - Comparison insights and highlights
    """
    try:
        logger.info(f"Comparing albums {album1} vs {album2}")
        
        # Generate comparison data
        comparison_data = comparison_service.compare_albums(album1, album2, db)
        
        logger.info(f"Comparison generated successfully for albums {album1} vs {album2}")
        return comparison_data
        
    except ServiceValidationError as e:
        logger.warning(f"Album comparison validation error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Validation error",
                "message": e.message
            }
        )
    except ServiceNotFoundError as e:
        logger.warning(f"Album comparison not found error: {e.message}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Albums not found",
                "message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error comparing albums: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to compare albums"
            }
        )


@router.get("/albums/rated")
async def get_rated_albums_for_comparison(
    comparison_service: ComparisonService = Depends(get_comparison_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get list of user's rated albums for comparison selection
    
    Returns list of albums that can be used in comparisons,
    filtered to only rated albums with basic metadata.
    """
    try:
        logger.info("Getting rated albums for comparison")
        
        albums = comparison_service.get_user_rated_albums(db)
        
        return {
            "albums": albums,
            "total": len(albums)
        }
        
    except Exception as e:
        logger.error(f"Error getting rated albums: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to get rated albums"
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
    sort: Optional[str] = Query(None, description="Sort order (created_desc, created_asc, artist_asc, artist_desc, album_asc, album_desc, rating_desc, rating_asc, year_desc, year_asc, rated_desc, rating_desc_status)"),
    search: Optional[str] = Query(None, description="Search query for album title or artist name"),
    artist_id: Optional[int] = Query(None, description="Filter by artist ID"),
    year: Optional[int] = Query(None, description="Filter by release year"),
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
    - rating_desc_status: By rating score desc with in-progress albums first
    """
    try:
        # Get user settings for default sort if not provided
        from ..models import UserSettings
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        
        if sort is None:
            if settings and settings.default_sort_order:
                # Map settings sort names to API sort names
                sort_mapping = {
                    'score_desc': 'rating_desc',  # Score (High to Low) -> rating_desc
                    'score_asc': 'rating_asc',    # Score (Low to High) -> rating_asc
                    'name_asc': 'album_asc',       # Name (A-Z) -> album_asc
                    'name_desc': 'album_desc'      # Name (Z-A) -> album_desc
                }
                sort = sort_mapping.get(settings.default_sort_order, settings.default_sort_order)
            else:
                sort = 'created_desc'
        
        logger.info(f"Getting user albums: limit={limit}, offset={offset}, rated={rated}, sort={sort}, search={search}, artist_id={artist_id}, year={year}")

        result = service.get_user_albums(db, limit, offset, rated, sort, search, artist_id, year)

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


@router.post("/albums/update-cover-art")
async def update_album_cover_art(
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update cover art for all albums that don't have it

    Fetches cover art from MusicBrainz Cover Art Archive API
    for albums with missing artwork.

    Returns statistics about the update process.
    """
    try:
        logger.info("Starting cover art update for albums")

        result = await service.update_missing_cover_art(db)

        logger.info(f"Cover art update completed: {result['updated']} albums updated")
        return result

    except Exception as e:
        logger.error(f"Error updating cover art: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Cover art update failed",
                "message": "Failed to update album cover art"
            }
        )


@router.get("/albums/{album_id}/release-group-releases")
async def get_release_group_releases(
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get all releases from the same release group with matching track count

    Returns releases that could be alternative versions of the current album
    """
    try:
        logger.info(f"Getting release group releases for album {album_id}")

        result = await service.get_release_group_releases(album_id, db)

        logger.info(f"Found {len(result.get('releases', []))} matching releases")
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
        logger.error(f"Error getting release group releases: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to get release group releases"
            }
        )


class RetagRequest(BaseModel):
    """Request model for retagging album"""
    new_musicbrainz_id: str = Field(..., description="New MusicBrainz release ID", min_length=36, max_length=36)


@router.put("/albums/{album_id}/revert")
async def revert_album_to_in_progress(
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Revert completed album to 'In Progress' status for re-rating

    This endpoint:
    - Changes album status from completed to in-progress
    - Preserves all existing track ratings
    - Clears the final score and rated_at timestamp
    - Allows user to modify ratings and resubmit

    Args:
        album_id: Album ID to revert

    Returns:
        Dict with updated album information
    """
    try:
        logger.info(f"Reverting album {album_id} to in-progress status")

        result = service.revert_album_to_in_progress(album_id, db)

        logger.info(f"Successfully reverted album {album_id} to in-progress")
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
        logger.warning(f"Revert validation error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Cannot revert album",
                "message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Error reverting album: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to revert album"
            }
        )


@router.put("/albums/{album_id}/retag")
async def retag_album_musicbrainz_id(
    retag_request: RetagRequest,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update album's MusicBrainz ID while preserving all ratings and submission data

    Args:
        album_id: Album ID to update
        request: JSON body with new_musicbrainz_id
    """
    try:
        new_mbid = retag_request.new_musicbrainz_id

        logger.info(f"Retagging album {album_id} to MusicBrainz ID {new_mbid}")

        result = await service.retag_album_musicbrainz_id(album_id, new_mbid, db)

        logger.info(f"Successfully retagged album {album_id}")
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
        logger.warning(f"Retag validation error: {e.message}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Validation error",
                "message": e.message
            }
        )
    except Exception as e:
        logger.error(f"Error retagging album: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retag album"
            }
        )


@router.post("/albums/{album_id}/refresh-artwork")
async def refresh_album_artwork(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Manually refresh artwork cache for a specific album

    This endpoint clears the existing cached artwork and re-downloads
    fresh images from the source. Rate limited to prevent abuse.

    Rate limits:
    - 5 refreshes per hour per session
    - 20 refreshes per day per session

    Args:
        album_id: Album ID to refresh artwork for
    """
    try:
        from ..services.user_rate_limiter import get_artwork_refresh_limiter
        from ..services.artwork_memory_cache import get_artwork_memory_cache
        from ..services.artwork_cache_background import get_artwork_cache_background_service
        from ..models import Album

        # Get session ID for rate limiting (use IP address as fallback)
        session_id = request.headers.get("X-Session-Id", request.client.host)

        # Check rate limit
        refresh_limiter = get_artwork_refresh_limiter()
        allowed, limit_info = refresh_limiter.check_limit(session_id)

        if not allowed:
            logger.warning(f"Artwork refresh rate limit exceeded for session {session_id}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": limit_info.get("message", "Too many refresh requests"),
                    "retry_after": limit_info.get("reset_in_seconds", 3600),
                    "limit_info": limit_info
                }
            )

        # Get album
        album = db.query(Album).filter(Album.id == album_id).first()
        if not album:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Album not found",
                    "message": f"Album with ID {album_id} not found"
                }
            )

        if not album.cover_art_url:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "No artwork available",
                    "message": "Album has no cover art URL to refresh"
                }
            )

        logger.info(f"Refreshing artwork for album {album_id}: {album.name}")

        # Clear existing cache
        from ..services.artwork_cache_service import get_artwork_cache_service
        cache_service = get_artwork_cache_service()
        memory_cache = get_artwork_memory_cache()

        # Clear from database and filesystem
        clear_result = cache_service.clear_album_cache_sync(album_id, db)

        # Clear from memory cache
        memory_cache.clear_album(album_id)

        # Clear from template cache
        from ..template_utils import get_artwork_resolver
        template_resolver = get_artwork_resolver()
        template_resolver.clear_template_cache()

        # Mark album as not cached
        album.artwork_cached = False
        db.commit()

        # Record the refresh request
        refresh_limiter.record_refresh(session_id)

        # Queue for re-caching with high priority
        background_service = get_artwork_cache_background_service()
        task_id = background_service.trigger_album_cache(
            album_id=album_id,
            cover_art_url=album.cover_art_url,
            priority=2  # High priority for manual refresh
        )

        logger.info(f"Artwork refresh queued for album {album_id}, task: {task_id}")

        return {
            "success": True,
            "message": "Artwork refresh initiated",
            "album_id": album_id,
            "album_name": album.name,
            "task_id": task_id,
            "cleared": clear_result,
            "rate_limit": limit_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing artwork for album {album_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Refresh failed",
                "message": f"Failed to refresh artwork: {str(e)}"
            }
        )


@router.get("/system/cache-cleanup")
async def get_cache_cleanup_status() -> Dict[str, Any]:
    """
    Get cache cleanup status and recommendations

    Returns information about:
    - Total cache entries
    - Old entries to clean
    - Cache size
    - Cleanup recommendations
    """
    try:
        from ..services.cache_cleanup_service import get_cleanup_service

        cleanup_service = get_cleanup_service()
        return cleanup_service.get_cleanup_status()

    except Exception as e:
        logger.error(f"Error getting cache cleanup status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve cache cleanup status"
            }
        )


@router.post("/system/cache-cleanup")
async def trigger_cache_cleanup(
    dry_run: bool = Query(False, description="If true, only simulate cleanup without deleting"),
    retention_days: Optional[int] = Query(None, description="Override retention period in days")
) -> Dict[str, Any]:
    """
    Manually trigger cache cleanup

    Runs the cache cleanup process immediately with optional parameters.

    Args:
        dry_run: If true, only simulate cleanup without actually deleting files
        retention_days: Override the default retention period
    """
    try:
        from ..services.scheduled_tasks import get_scheduled_task_manager

        manager = get_scheduled_task_manager()
        result = await manager.trigger_cleanup_now(dry_run=dry_run)

        return result

    except Exception as e:
        logger.error(f"Error triggering cache cleanup: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Cleanup failed",
                "message": f"Failed to trigger cache cleanup: {str(e)}"
            }
        )


@router.get("/system/scheduled-tasks")
async def get_scheduled_tasks_status() -> Dict[str, Any]:
    """
    Get scheduled tasks status

    Returns information about:
    - Task configuration
    - Last run times
    - Next scheduled runs
    """
    try:
        from ..services.scheduled_tasks import get_scheduled_task_manager

        manager = get_scheduled_task_manager()
        return manager.get_status()

    except Exception as e:
        logger.error(f"Error getting scheduled tasks status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve scheduled tasks status"
            }
        )


@router.get("/system/memory-cache")
async def get_memory_cache_status() -> Dict[str, Any]:
    """
    Get status of artwork memory cache

    Returns information about:
    - Cache hit rate
    - Memory usage
    - Top accessed entries
    - Performance metrics
    """
    try:
        from ..services.artwork_memory_cache import get_artwork_memory_cache

        memory_cache = get_artwork_memory_cache()
        return memory_cache.get_stats()

    except Exception as e:
        logger.error(f"Error getting memory cache status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve memory cache status"
            }
        )


@router.post("/system/migrate-artwork")
async def trigger_artwork_migration(
    batch_size: int = Query(10, description="Number of albums per batch", ge=1, le=50),
    limit: Optional[int] = Query(None, description="Limit total albums to process")
) -> Dict[str, Any]:
    """
    Trigger artwork migration for existing albums

    Processes existing albums that don't have cached artwork.
    The migration runs in the background and can be resumed if interrupted.

    Args:
        batch_size: Number of albums to process per batch (default 10)
        limit: Optional limit on total albums to process
    """
    try:
        from ..services.artwork_cache_background import get_artwork_cache_background_service
        from ..models import Album

        db = SessionLocal()

        try:
            # Get albums that need caching
            query = db.query(Album).filter(
                or_(
                    Album.artwork_cached == False,
                    Album.artwork_cached == None
                )
            )

            if limit:
                query = query.limit(limit)

            albums_to_process = query.all()

            if not albums_to_process:
                return {
                    'status': 'complete',
                    'message': 'All albums already have cached artwork',
                    'albums_to_process': 0
                }

            # Queue albums for background processing
            cache_service = get_artwork_cache_background_service()
            task_ids = []

            for i, album in enumerate(albums_to_process):
                if album.cover_art_url:
                    # Add to background queue with lower priority
                    task_id = cache_service.trigger_album_cache(
                        album_id=album.id,
                        cover_art_url=album.cover_art_url,
                        priority=8  # Lower priority for migration
                    )
                    task_ids.append(task_id)

                    # Add small delay between queueing to avoid overwhelming
                    if (i + 1) % batch_size == 0:
                        await asyncio.sleep(0.1)

            return {
                'status': 'started',
                'message': f'Migration started for {len(albums_to_process)} albums',
                'albums_queued': len(task_ids),
                'batch_size': batch_size,
                'task_ids': task_ids[:10]  # Return first 10 task IDs as sample
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error starting artwork migration: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Migration failed",
                "message": f"Failed to start artwork migration: {str(e)}"
            }
        )


@router.get("/system/integrity-status")
async def get_integrity_status() -> Dict[str, Any]:
    """
    Get cache integrity status

    Returns the latest integrity check results and quick check status
    """
    try:
        from pathlib import Path
        import json

        # Get latest integrity report
        reports_dir = Path("logs/scheduled_tasks")
        latest_full = None
        latest_quick = None

        if reports_dir.exists():
            # Find latest full check
            full_reports = list(reports_dir.glob("integrity_check_*.json"))
            if full_reports:
                latest_full_file = max(full_reports, key=lambda p: p.stat().st_mtime)
                with open(latest_full_file, 'r') as f:
                    latest_full = json.load(f)

            # Find latest quick check
            quick_reports = list(reports_dir.glob("integrity_quick_check_*.json"))
            if quick_reports:
                latest_quick_file = max(quick_reports, key=lambda p: p.stat().st_mtime)
                with open(latest_quick_file, 'r') as f:
                    latest_quick = json.load(f)

        # Get scheduled task status
        from ..services.scheduled_tasks import get_scheduled_manager
        scheduled_manager = get_scheduled_manager()
        task_status = scheduled_manager.get_status()

        integrity_task = task_status.get('tasks', {}).get('integrity_check', {})
        quick_task = task_status.get('tasks', {}).get('integrity_quick_check', {})

        return {
            'latest_full_check': latest_full,
            'latest_quick_check': latest_quick,
            'scheduled_task': {
                'enabled': task_status.get('config', {}).get('integrity_check', {}).get('enabled', False),
                'last_run': integrity_task.get('last_run'),
                'running': integrity_task.get('running', False)
            },
            'quick_check': {
                'enabled': task_status.get('config', {}).get('integrity_check', {}).get('quick_check_daily', False),
                'last_run': quick_task.get('last_run'),
                'running': quick_task.get('running', False)
            }
        }

    except Exception as e:
        logger.error(f"Error getting integrity status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve integrity status"
            }
        )


@router.post("/system/integrity-check")
async def trigger_integrity_check(
    repair: bool = Query(False, description="Attempt to repair issues"),
    quick: bool = Query(False, description="Run quick check instead of full"),
    verbose: bool = Query(False, description="Include detailed information")
) -> Dict[str, Any]:
    """
    Manually trigger cache integrity check

    Args:
        repair: Whether to attempt repairs (full check only)
        quick: Run quick sample-based check instead of full check
        verbose: Include detailed information in response
    """
    try:
        from ..services.cache_integrity_service import get_integrity_service

        integrity_service = get_integrity_service()

        if quick:
            # Run quick check
            result = integrity_service.quick_check()
            logger.info(f"Quick integrity check completed: {result['estimated_integrity_score']}%")
        else:
            # Run full check
            result = integrity_service.verify_integrity(
                repair=repair,
                verbose=verbose
            )
            logger.info(
                f"Full integrity check completed: score={result['integrity_score']}%, "
                f"issues={result['summary']['issues_found']}"
            )

        return result

    except Exception as e:
        logger.error(f"Error running integrity check: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Check failed",
                "message": f"Failed to run integrity check: {str(e)}"
            }
        )


@router.get("/system/migration-status")
async def get_migration_status() -> Dict[str, Any]:
    """
    Get artwork migration status

    Returns information about ongoing or completed migration
    """
    try:
        from pathlib import Path
        import json

        progress_file = Path("logs/artwork_migration_progress.json")
        report_file = Path("logs/artwork_migration_report.json")

        status = {
            'in_progress': False,
            'progress': None,
            'last_report': None
        }

        # Check progress file
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress = json.load(f)
                    status['progress'] = {
                        'processed': progress.get('processed', 0),
                        'total': progress.get('total', 0),
                        'percentage': round(
                            progress.get('processed', 0) / progress.get('total', 1) * 100, 1
                        ),
                        'failed': len(progress.get('failed_album_ids', {}))
                    }
                    status['in_progress'] = progress.get('processed', 0) < progress.get('total', 0)
            except Exception as e:
                logger.warning(f"Could not read progress file: {e}")

        # Check report file
        if report_file.exists():
            try:
                with open(report_file, 'r') as f:
                    report = json.load(f)
                    status['last_report'] = {
                        'completed_at': report.get('completed_at'),
                        'albums_cached': report.get('cached', 0),
                        'failed': report.get('failed', 0),
                        'bytes_cached': report.get('bytes_cached', 0),
                        'processing_time_seconds': report.get('processing_time_seconds', 0)
                    }
            except Exception as e:
                logger.warning(f"Could not read report file: {e}")

        return status

    except Exception as e:
        logger.error(f"Error getting migration status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve migration status"
            }
        )


@router.get("/system/background-tasks")
async def get_background_tasks_status() -> Dict[str, Any]:
    """
    Get status of background tasks including artwork caching

    Returns information about:
    - Queued tasks
    - Running tasks
    - Completed tasks
    - Failed tasks
    """
    try:
        from ..services.artwork_cache_background import get_artwork_cache_background_service

        cache_service = get_artwork_cache_background_service()
        return cache_service.get_overall_status()

    except Exception as e:
        logger.error(f"Error getting background tasks status: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Status unavailable",
                "message": "Unable to retrieve background tasks status"
            }
        )


@router.get("/system/info")
async def get_system_info() -> Dict[str, Any]:
    """
    Get system information including database details

    Returns information about:
    - Database location and status
    - Application configuration
    - System health
    """
    import sys
    import os

    try:
        db_info = get_db_info()

        return {
            "database": db_info,
            "application": {
                "name": "Tracklist",
                "version": "1.0.0",
                "environment": os.getenv("ENVIRONMENT", "development")
            },
            "system": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": os.name
            }
        }

    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "System info unavailable",
                "message": "Unable to retrieve system information"
            }
        )
