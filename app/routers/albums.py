"""
Album rating API endpoints
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import logging

from ..database import get_db
from ..rating_service import get_rating_service, RatingService
from ..exceptions import TracklistException, NotFoundError, ValidationError, ServiceNotFoundError, ServiceValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["albums"])


class TrackRatingRequest(BaseModel):
    """Request model for track rating"""
    rating: float = Field(..., description="Track rating (0.0, 0.33, 0.67, 1.0)")


@router.post("/albums")
async def create_album_for_rating(
    musicbrainz_id: str = Query(..., description="MusicBrainz release ID", min_length=36, max_length=36),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
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
    rating_request: TrackRatingRequest,
    track_id: int = Path(..., description="Track ID", gt=0),
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
        logger.info(f"Updating track {track_id} rating to {rating_request.rating}")
        
        result = service.rate_track(track_id, rating_request.rating, db)
        
        logger.info(f"Track rating updated successfully: {result['completion_percentage']:.1f}% complete")
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
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get user's albums
    
    Returns paginated list of user's albums with optional filtering:
    - rated=true: Only completed/submitted albums
    - rated=false: Only draft/in-progress albums
    - rated=null: All albums (default)
    
    Results are ordered by creation date (newest first).
    """
    try:
        logger.info(f"Getting user albums: limit={limit}, offset={offset}, rated={rated}")
        
        result = service.get_user_albums(db, limit, offset, rated)
        
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