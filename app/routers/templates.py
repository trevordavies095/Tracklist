"""
Template serving routes for the frontend UI
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Path, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import logging
import os

from ..database import get_db
from ..rating_service import get_rating_service, RatingService
from ..services.comparison_service import get_comparison_service, ComparisonService
from ..services.auth_service import get_auth_service
from ..exceptions import ServiceNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])
templates = Jinja2Templates(directory="templates")


def get_template_context(request: Request, db: Session = None) -> dict:
    """Get common template context including auth status."""
    context = {"request": request}
    
    # Check if user is authenticated
    auth_service = get_auth_service()
    
    # Check if auth is enabled (from database or environment)
    auth_enabled = False
    if db:
        from ..models import UserSettings
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if settings:
            auth_enabled = settings.auth_enabled or False
    
    # Fallback to environment variable if no DB settings
    if not auth_enabled:
        auth_enabled = os.getenv('ENABLE_AUTH', 'false').lower() == 'true'
    
    context["auth_enabled"] = auth_enabled
    
    # Only check authentication if auth is enabled
    if auth_enabled:
        token = request.cookies.get("tracklist_session")  # Fixed cookie name
        logger.info(f"Auth check - enabled: {auth_enabled}, token present: {bool(token)}, db present: {bool(db)}")
        if token and db:
            context["is_authenticated"] = auth_service.validate_session(db, token)
            logger.info(f"Session validation result: {context['is_authenticated']}")
        else:
            context["is_authenticated"] = False
            logger.info(f"No token or db - token: {bool(token)}, db: {bool(db)}")
    else:
        context["is_authenticated"] = False
        logger.info(f"Auth disabled - auth_enabled: {auth_enabled}")
    
    logger.info(f"Final context: auth_enabled={context.get('auth_enabled')}, is_authenticated={context.get('is_authenticated')}")
    return context


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db: Session = Depends(get_db)):
    """Homepage/Dashboard"""
    context = get_template_context(request, db)
    return templates.TemplateResponse("index.html", context)


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, db: Session = Depends(get_db)):
    """Album search page"""
    context = get_template_context(request, db)
    return templates.TemplateResponse("search.html", context)


@router.get("/albums", response_class=HTMLResponse)
async def albums_page(request: Request, db: Session = Depends(get_db)):
    """User's albums library page"""
    from ..models import UserSettings

    # Get user settings for default sort
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
    default_sort = "created_desc"  # fallback

    if settings and settings.default_sort_order:
        # Map settings sort names to API sort names
        sort_mapping = {
            "score_desc": "rating_desc",
            "score_asc": "rating_asc",
            "name_asc": "album_asc",
            "name_desc": "album_desc",
        }
        default_sort = sort_mapping.get(
            settings.default_sort_order, settings.default_sort_order
        )

    context = get_template_context(request, db)
    context["default_sort"] = default_sort
    return templates.TemplateResponse("albums.html", context)


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request, db: Session = Depends(get_db)):
    """User statistics dashboard page"""
    context = get_template_context(request, db)
    return templates.TemplateResponse("stats.html", context)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Application settings page"""
    from ..models import UserSettings

    # Get current settings or create defaults
    settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()

    if not settings:
        # Create default settings
        settings = UserSettings(user_id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    context = get_template_context(request, db)
    context["settings"] = settings
    return templates.TemplateResponse("settings.html", context)


@router.get("/test-export", response_class=HTMLResponse)
async def test_export_page(request: Request, db: Session = Depends(get_db)):
    """Test page for export functionality"""
    context = get_template_context(request, db)
    return templates.TemplateResponse("test_export.html", context)


@router.get("/artists/{artist_id}/albums", response_class=HTMLResponse)
async def artist_albums_page(
    request: Request,
    artist_id: int = Path(..., description="Artist ID", gt=0),
    db: Session = Depends(get_db),
):
    """Artist's albums page"""
    from ..models import Artist

    # Get artist details
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")

    context = get_template_context(request, db)
    context["artist"] = artist
    return templates.TemplateResponse("artist_albums.html", context)


@router.get("/years/{year}/albums", response_class=HTMLResponse)
async def year_albums_page(
    request: Request,
    year: int = Path(..., description="Year", ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    """Year's albums page"""
    context = get_template_context(request, db)
    context["year"] = year
    return templates.TemplateResponse("year_albums.html", context)


@router.get("/albums/{album_id}/rate", response_class=HTMLResponse)
async def rating_page(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db),
):
    """Track-by-track rating page for an album"""
    try:
        # Get album details
        album_data = service.get_album_rating(album_id, db)
        logger.info(f"Album data loaded for {album_id}: {album_data.get('title')}")

        # Get current progress
        progress_data = service.get_album_progress(album_id, db)
        logger.info(
            f"Progress data loaded for {album_id}: {progress_data.get('completion_percentage', 0)}%"
        )

        # Try to render original template
        context = get_template_context(request, db)
        context.update({
            "album": album_data,
            "tracks": album_data.get("tracks", []),
            "progress": progress_data,
        })
        return templates.TemplateResponse("album/rating.html", context)

    except ServiceNotFoundError:
        logger.warning(f"Album not found for rating page: {album_id}")
        raise HTTPException(status_code=404, detail="Album not found")
    except Exception as e:
        logger.error(
            f"Error loading rating page for album {album_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Error loading rating page: {str(e)}"
        )


@router.get("/albums/{album_id}/completed", response_class=HTMLResponse)
async def completed_page(
    request: Request,
    album_id: int = Path(..., description="Album ID", gt=0),
    service: RatingService = Depends(get_rating_service),
    db: Session = Depends(get_db),
):
    """Album completion/results page"""
    try:
        # Get album details
        album_data = service.get_album_rating(album_id, db)

        # Ensure album is actually completed
        if not album_data.get("is_rated"):
            # Redirect to rating page if not completed
            context = get_template_context(request, db)
            context.update({
                "album": album_data,
                "tracks": album_data.get("tracks", []),
                "progress": service.get_album_progress(album_id, db),
            })
            return templates.TemplateResponse("album/rating.html", context)

        context = get_template_context(request, db)
        context.update({
            "album": album_data,
            "tracks": album_data.get("tracks", []),
        })
        return templates.TemplateResponse("album/completed.html", context)

    except ServiceNotFoundError:
        logger.warning(f"Album not found for completed page: {album_id}")
        raise HTTPException(status_code=404, detail="Album not found")
    except Exception as e:
        logger.error(f"Error loading completed page for album {album_id}: {e}")
        raise HTTPException(status_code=500, detail="Error loading completed page")


@router.get("/albums/compare", response_class=HTMLResponse)
async def compare_albums_page(
    request: Request,
    album1: int = Query(None, description="First album ID"),
    album2: int = Query(None, description="Second album ID"),
    comparison_service: ComparisonService = Depends(get_comparison_service),
    db: Session = Depends(get_db),
):
    """Album comparison page"""
    comparison_data = None
    error_message = None

    logger.info(
        f"Compare albums page accessed with params: album1={album1}, album2={album2}"
    )

    try:
        # If both album IDs provided, generate comparison
        if album1 and album2:
            logger.info(
                f"Both albums provided, generating comparison for {album1} vs {album2}"
            )
            comparison_data = comparison_service.compare_albums(album1, album2, db)
            logger.info(
                f"Comparison data generated successfully: {bool(comparison_data)}"
            )
        else:
            logger.info(f"Missing album parameters: album1={album1}, album2={album2}")

    except Exception as e:
        logger.error(
            f"Error generating comparison for albums {album1} vs {album2}: {e}",
            exc_info=True,
        )
        error_message = str(e)

    logger.info(
        f"Returning template with comparison_data={bool(comparison_data)}, error_message={bool(error_message)}"
    )

    context = get_template_context(request, db)
    context.update({
        "comparison": comparison_data,
        "error_message": error_message,
        "page_title": "Compare Albums",
    })
    return templates.TemplateResponse("albums/compare.html", context)


# Helper function to add custom filters to Jinja2
def setup_template_filters(template_env):
    """Add custom filters and globals to Jinja2 environment"""

    # Import template utilities
    from ..template_utils import (
        get_artwork_url,
        get_lazy_image_html,
        get_cache_stats,
        format_file_size,
        format_cache_age,
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
    template_env.globals["get_lazy_image_html"] = get_lazy_image_html
    template_env.globals["get_cache_stats"] = get_cache_stats


# Setup filters when router is imported
setup_template_filters(templates.env)
