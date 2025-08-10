"""
Template serving routes for the frontend UI
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Path
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import logging

from ..database import get_db
from ..rating_service import get_rating_service, RatingService
from ..exceptions import ServiceNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Homepage/Dashboard"""
    return templates.TemplateResponse("index.html", {
        "request": request
    })


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Album search page"""
    return templates.TemplateResponse("search.html", {
        "request": request
    })


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request):
    """User's albums library page"""
    return templates.TemplateResponse("albums.html", {
        "request": request
    })


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    """User statistics dashboard page"""
    return templates.TemplateResponse("stats.html", {
        "request": request
    })


@router.get("/artists/{artist_id}/albums", response_class=HTMLResponse)
async def artist_albums_page(
    request: Request,
    artist_id: int = Path(..., description="Artist ID", gt=0),
    db: Session = Depends(get_db)
):
    """Artist's albums page"""
    from ..models import Artist
    
    # Get artist details
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    return templates.TemplateResponse("artist_albums.html", {
        "request": request,
        "artist": artist
    })


@router.get("/years/{year}/albums", response_class=HTMLResponse)
async def year_albums_page(
    request: Request,
    year: int = Path(..., description="Year", ge=1900, le=2100),
    db: Session = Depends(get_db)
):
    """Year's albums page"""
    return templates.TemplateResponse("year_albums.html", {
        "request": request,
        "year": year
    })


@router.get("/albums/{album_id}/rate", response_class=HTMLResponse)
async def rating_page(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
):
    """Track-by-track rating page for an album"""
    try:
        # Get album details
        album_data = service.get_album_rating(album_id, db)
        logger.info(f"Album data loaded for {album_id}: {album_data.get('title')}")
        
        # Get current progress
        progress_data = service.get_album_progress(album_id, db)
        logger.info(f"Progress data loaded for {album_id}: {progress_data.get('completion_percentage', 0)}%")
        
        # Try to render original template
        return templates.TemplateResponse("album/rating.html", {
            "request": request,
            "album": album_data,
            "tracks": album_data.get("tracks", []),
            "progress": progress_data
        })
        
    except ServiceNotFoundError:
        logger.warning(f"Album not found for rating page: {album_id}")
        raise HTTPException(status_code=404, detail="Album not found")
    except Exception as e:
        logger.error(f"Error loading rating page for album {album_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading rating page: {str(e)}")


@router.get("/albums/{album_id}/completed", response_class=HTMLResponse)
async def completed_page(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db)
):
    """Album completion/results page"""
    try:
        # Get album details
        album_data = service.get_album_rating(album_id, db)
        
        # Ensure album is actually completed
        if not album_data.get("is_rated"):
            # Redirect to rating page if not completed
            return templates.TemplateResponse("album/rating.html", {
                "request": request,
                "album": album_data,
                "tracks": album_data.get("tracks", []),
                "progress": service.get_album_progress(album_id, db)
            })
        
        return templates.TemplateResponse("album/completed.html", {
            "request": request,
            "album": album_data,
            "tracks": album_data.get("tracks", [])
        })
        
    except ServiceNotFoundError:
        logger.warning(f"Album not found for completed page: {album_id}")
        raise HTTPException(status_code=404, detail="Album not found")
    except Exception as e:
        logger.error(f"Error loading completed page for album {album_id}: {e}")
        raise HTTPException(status_code=500, detail="Error loading completed page")


# Helper function to add custom filters to Jinja2
def setup_template_filters(template_env):
    """Add custom filters and globals to Jinja2 environment"""
    
    # Import template utilities
    from ..template_utils import (
        get_artwork_url,
        get_cache_stats,
        format_file_size,
        format_cache_age
    )
    
    def format_duration(milliseconds):
        """Convert milliseconds to MM:SS format"""
        if not milliseconds:
            return "0:00"
        
        seconds = int(milliseconds / 1000)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def format_rating_label(rating):
        """Convert numeric rating to label"""
        if rating == 0.0:
            return "Skip"
        elif rating == 0.33:
            return "Filler"
        elif rating == 0.67:
            return "Good"
        elif rating == 1.0:
            return "Standout"
        else:
            return str(rating)
    
    def rating_color_class(rating):
        """Get CSS class for rating color"""
        if rating == 0.0:
            return "text-red-600"
        elif rating == 0.33:
            return "text-amber-600"
        elif rating == 0.67:
            return "text-green-600"
        elif rating == 1.0:
            return "text-green-800"
        else:
            return "text-gray-600"
    
    # Add filters to template environment
    template_env.filters["format_duration"] = format_duration
    template_env.filters["format_rating_label"] = format_rating_label
    template_env.filters["rating_color_class"] = rating_color_class
    template_env.filters["format_file_size"] = format_file_size
    template_env.filters["format_cache_age"] = format_cache_age
    
    # Add global functions for templates
    template_env.globals["get_artwork_url"] = get_artwork_url
    template_env.globals["get_cache_stats"] = get_cache_stats


# Setup filters when router is imported
setup_template_filters(templates.env)