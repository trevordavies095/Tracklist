"""
Reporting API endpoints for user statistics and analytics
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
import logging
import asyncio
import io

from ..database import get_db
from ..reporting_service import get_reporting_service, ReportingService
from ..services.collage_service import get_collage_service, CollageService
from ..exceptions import TracklistException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/overview")
async def get_overview_statistics(
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get overview statistics for the user's album collection

    Returns comprehensive statistics including:
    - Total number of albums in collection
    - Count of fully rated albums
    - Count of in-progress albums
    - Average score of rated albums
    - Total tracks rated
    - Distribution of track ratings

    Example response:
    ```json
    {
        "total_albums": 150,
        "fully_rated_count": 87,
        "in_progress_count": 23,
        "average_album_score": 73.5,
        "total_tracks_rated": 1024,
        "rating_distribution": {
            "skip": 120,
            "filler": 340,
            "good": 380,
            "standout": 184
        },
        "unrated_albums_count": 40
    }
    ```
    """
    try:
        logger.info("Fetching overview statistics")
        statistics = service.get_overview_statistics(db)
        return statistics

    except TracklistException as e:
        logger.error(f"Failed to get overview statistics: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to generate statistics",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting overview statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve statistics"
            }
        )


@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of items to return"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get recent rating activity

    Returns recently rated albums and albums currently in progress.

    Query Parameters:
    - limit: Maximum number of items per category (1-50, default: 10)

    Example response:
    ```json
    {
        "recently_rated": [
            {
                "id": 123,
                "name": "Abbey Road",
                "artist": "The Beatles",
                "year": 1969,
                "score": 88,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-15T10:30:00"
            }
        ],
        "in_progress": [
            {
                "id": 124,
                "name": "The Dark Side of the Moon",
                "artist": "Pink Floyd",
                "year": 1973,
                "cover_art_url": "https://...",
                "progress": {
                    "rated_tracks": 5,
                    "total_tracks": 10,
                    "percentage": 50.0
                },
                "updated_at": "2024-01-15T09:15:00"
            }
        ]
    }
    ```
    """
    try:
        logger.info(f"Fetching recent activity with limit={limit}")
        activity = service.get_recent_activity(db, limit=limit)
        return activity

    except TracklistException as e:
        logger.error(f"Failed to get recent activity: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get recent activity",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting recent activity: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve recent activity"
            }
        )


@router.get("/top-albums")
async def get_top_albums(
    limit: int = Query(default=10, ge=1, le=100, description="Maximum number of albums to return"),
    randomize: bool = Query(default=False, description="Randomly select from top-rated albums"),
    pool_size: int = Query(default=20, ge=5, le=100, description="Size of top album pool to select from when randomizing"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get top rated albums

    Returns the highest scored albums in the collection.

    Query Parameters:
    - limit: Maximum number of albums to return (1-100, default: 10)
    - randomize: Whether to randomly select from top albums (default: false)
    - pool_size: When randomizing, size of top album pool to select from (5-100, default: 20)

    Example response:
    ```json
    [
        {
            "id": 45,
            "name": "OK Computer",
            "artist": "Radiohead",
            "year": 1997,
            "score": 95,
            "cover_art_url": "https://...",
            "rated_at": "2024-01-10T14:22:00"
        },
        {
            "id": 67,
            "name": "In Rainbows",
            "artist": "Radiohead",
            "year": 2007,
            "score": 93,
            "cover_art_url": "https://...",
            "rated_at": "2024-01-12T16:45:00"
        }
    ]
    ```
    """
    try:
        logger.info(f"Fetching top {limit} albums (randomize={randomize}, pool_size={pool_size})")
        top_albums = service.get_top_albums(db, limit=limit, randomize=randomize, pool_size=pool_size)
        return top_albums

    except TracklistException as e:
        logger.error(f"Failed to get top albums: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get top albums",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting top albums: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve top albums"
            }
        )


@router.get("/distribution")
async def get_score_distribution(
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get distribution of album scores

    Returns the count and percentage of albums in different score ranges.
    Score ranges:
    - 0-20: Very Poor
    - 21-40: Poor
    - 41-60: Average
    - 61-80: Good
    - 81-100: Excellent

    Example response:
    ```json
    {
        "distribution": [
            {
                "range": "0-20",
                "label": "Very Poor",
                "count": 2,
                "percentage": 2.3,
                "color": "#dc2626"
            },
            {
                "range": "21-40",
                "label": "Poor",
                "count": 8,
                "percentage": 9.2,
                "color": "#f97316"
            },
            {
                "range": "41-60",
                "label": "Average",
                "count": 25,
                "percentage": 28.7,
                "color": "#eab308"
            },
            {
                "range": "61-80",
                "label": "Good",
                "count": 35,
                "percentage": 40.2,
                "color": "#84cc16"
            },
            {
                "range": "81-100",
                "label": "Excellent",
                "count": 17,
                "percentage": 19.5,
                "color": "#22c55e"
            }
        ],
        "total_rated": 87,
        "average_score": 62.5,
        "median_score": 65
    }
    ```
    """
    try:
        logger.info("Fetching score distribution")
        distribution = service.get_score_distribution(db)
        return distribution

    except TracklistException as e:
        logger.error(f"Failed to get score distribution: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get score distribution",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting score distribution: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve score distribution"
            }
        )


@router.get("/worst-albums")
async def get_worst_albums(
    limit: int = Query(default=5, ge=1, le=100, description="Maximum number of albums to return"),
    randomize: bool = Query(default=True, description="Randomly select from worst-rated albums"),
    pool_size: int = Query(default=20, ge=5, le=100, description="Size of worst album pool to select from when randomizing"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get lowest rated albums

    Returns the lowest scored albums in the collection.

    Query Parameters:
    - limit: Maximum number of albums to return (1-100, default: 5)
    - randomize: Whether to randomly select from worst albums (default: true)
    - pool_size: When randomizing, size of worst album pool to select from (5-100, default: 20)

    Example response:
    ```json
    [
        {
            "id": 45,
            "name": "Bad Album",
            "artist": "Some Artist",
            "year": 2010,
            "score": 15,
            "cover_art_url": "https://...",
            "rated_at": "2024-01-10T14:22:00"
        },
        {
            "id": 67,
            "name": "Another Bad Album",
            "artist": "Another Artist",
            "year": 2005,
            "score": 22,
            "cover_art_url": "https://...",
            "rated_at": "2024-01-12T16:45:00"
        }
    ]
    ```
    """
    try:
        logger.info(f"Fetching worst {limit} albums (randomize={randomize}, pool_size={pool_size})")
        worst_albums = service.get_worst_albums(db, limit=limit, randomize=randomize, pool_size=pool_size)
        return worst_albums

    except TracklistException as e:
        logger.error(f"Failed to get worst albums: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get worst albums",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting worst albums: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve worst albums"
            }
        )


@router.get("/top-artist")
async def get_top_artist(
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get the artist with the most rated albums

    Returns information about the artist you've rated the most, including:
    - Artist name and ID
    - Number of albums rated
    - Average score across their albums
    - Their top 5 highest-rated albums
    - Any artists tied with the same album count

    Example response:
    ```json
    {
        "artist_name": "Radiohead",
        "artist_id": 123,
        "album_count": 8,
        "average_score": 82.5,
        "top_albums": [
            {
                "id": 45,
                "name": "OK Computer",
                "year": 1997,
                "score": 95,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-10T14:22:00"
            },
            {
                "id": 67,
                "name": "In Rainbows",
                "year": 2007,
                "score": 93,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-12T16:45:00"
            }
        ],
        "tied_with": [
            {
                "name": "Pink Floyd",
                "id": 124,
                "average_score": 79.3
            }
        ]
    }
    ```
    """
    try:
        logger.info("Fetching top artist statistics")
        top_artist = service.get_top_artist(db)
        return top_artist

    except TracklistException as e:
        logger.error(f"Failed to get top artist: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get top artist",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting top artist: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve top artist"
            }
        )


@router.get("/top-albums-by-year")
async def get_top_albums_by_year(
    year: int = Query(..., ge=1900, le=2100, description="Year to filter albums by"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of albums to return"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get top rated albums from a specific year

    Returns the highest scored albums from the specified release year.

    Query Parameters:
    - year: Release year to filter by (1900-2100, required)
    - limit: Maximum number of albums to return (1-50, default: 10)

    Example response:
    ```json
    {
        "year": 1997,
        "albums": [
            {
                "id": 45,
                "name": "OK Computer",
                "artist": "Radiohead",
                "year": 1997,
                "score": 95,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-10T14:22:00"
            },
            {
                "id": 67,
                "name": "The Colour and the Shape",
                "artist": "Foo Fighters",
                "year": 1997,
                "score": 87,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-12T16:45:00"
            }
        ],
        "total_albums_in_year": 15,
        "rated_albums_in_year": 8
    }
    ```
    """
    try:
        logger.info(f"Fetching top {limit} albums from year {year}")
        top_albums_by_year = service.get_top_albums_by_year(db, year=year, limit=limit)
        return top_albums_by_year

    except TracklistException as e:
        logger.error(f"Failed to get top albums by year: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get top albums by year",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting top albums by year: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve top albums by year"
            }
        )


@router.get("/available-years")
async def get_available_years(
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get list of years for which rated albums exist

    Returns a list of years that have at least one rated album,
    sorted in descending order (newest first).

    Example response:
    ```json
    {
        "years": [2023, 2022, 2021, 2020, 1997, 1995, 1991],
        "total_years": 7
    }
    ```
    """
    try:
        logger.info("Fetching available years for top albums by year report")
        available_years = service.get_available_years(db)
        return available_years

    except TracklistException as e:
        logger.error(f"Failed to get available years: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get available years",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting available years: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve available years"
            }
        )


@router.get("/no-skips")
async def get_no_skip_albums(
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="Optional limit on number of albums to return"),
    randomize: bool = Query(default=True, description="Randomize album selection (default: true)"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get albums with no skip-worthy tracks

    Returns albums where all tracks are rated Good (0.67) or Standout (1.0).
    These are albums with no Skip (0.0) or Filler (0.33) tracks.

    Query Parameters:
    - limit: Optional maximum number of albums to return (1-100, default: all)
    - randomize: Whether to randomize selection (default: true)

    Example response:
    ```json
    {
        "albums": [
            {
                "id": 45,
                "name": "OK Computer",
                "artist": "Radiohead",
                "artist_id": 12,
                "year": 1997,
                "score": 95,
                "cover_art_url": "https://...",
                "rated_at": "2024-01-10T14:22:00",
                "total_tracks": 12,
                "average_track_rating": 0.89,
                "musicbrainz_id": "..."
            }
        ],
        "total_count": 15,
        "percentage": 12.5,
        "total_rated_albums": 120
    }
    ```
    """
    try:
        logger.info(f"Fetching no-skip albums (limit={limit}, randomize={randomize})")
        no_skip_data = service.get_no_skip_albums(db, limit=limit, randomize=randomize)
        return no_skip_data

    except TracklistException as e:
        logger.error(f"Failed to get no-skip albums: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get no-skip albums",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting no-skip albums: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve no-skip albums"
            }
        )


@router.get("/highest-rated-artists")
async def get_highest_rated_artists(
    min_albums: int = Query(default=3, ge=1, le=10, description="Minimum number of rated albums an artist must have"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of artists to return"),
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get highest rated artists based on their average album scores

    Returns artists ranked by their average album rating, filtered by minimum album count.
    Only artists with at least 'min_albums' rated albums are considered.
    Shows up to 'min_albums' top-rated albums for each qualifying artist.

    Query Parameters:
    - min_albums: Minimum albums required to qualify AND maximum albums to display (1-10, default: 3)
    - limit: Maximum number of artists to return (1-20, default: 5)

    Example response:
    ```json
    {
        "artists": [
            {
                "artist_id": 123,
                "artist_name": "Radiohead",
                "album_count": 8,
                "average_score": 87.5,
                "displayed_albums": [
                    {
                        "id": 45,
                        "name": "OK Computer",
                        "year": 1997,
                        "score": 95,
                        "cover_art_url": "https://..."
                    }
                ],
                "albums_displayed_count": 3
            }
        ],
        "total_qualifying_artists": 25,
        "min_albums_filter": 3
    }
    ```
    """
    try:
        logger.info(f"Fetching highest rated artists (min_albums={min_albums}, limit={limit})")
        highest_rated_artists = service.get_highest_rated_artists(db, min_albums=min_albums, limit=limit)
        return highest_rated_artists

    except TracklistException as e:
        logger.error(f"Failed to get highest rated artists: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to get highest rated artists",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error getting highest rated artists: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to retrieve highest rated artists"
            }
        )


@router.get("/years/{year}/collage")
async def generate_year_collage(
    year: int,
    include_ranking: bool = Query(default=True, description="Include ranking list on the side"),
    include_scores: bool = Query(default=True, description="Include scores in ranking list"),
    max_albums: Optional[int] = Query(default=None, ge=1, le=100, description="Maximum number of albums to include"),
    service: CollageService = Depends(get_collage_service),
    db: Session = Depends(get_db)
):
    """
    Generate a visual collage of top-rated albums for a specific year
    
    Creates a Topsters-style collage image with album artwork arranged in a grid.
    Albums are sorted by rating score (highest first) and placed left-to-right,
    top-to-bottom. Optionally includes a numbered ranking list on the right side.
    
    Query Parameters:
    - include_ranking: Whether to include the ranking list (default: true)
    - include_scores: Whether to show scores in the ranking list (default: true)
    - max_albums: Maximum number of albums to include (default: all, max: 100)
    
    Returns:
    - PNG image file as a download
    
    Grid Layout:
    - 1-4 albums: 2x2 grid
    - 5-9 albums: 3x3 grid
    - 10-16 albums: 4x4 grid
    - 17-25 albums: 5x5 grid
    - 26-36 albums: 6x6 grid
    - 37-49 albums: 7x7 grid
    - 50-64 albums: 8x8 grid
    - 65-81 albums: 9x9 grid
    - 82-100 albums: 10x10 grid
    """
    try:
        logger.info(f"Generating collage for year {year} (max_albums={max_albums})")
        
        # Generate the collage
        image_bytes = await service.generate_year_collage(
            year=year,
            db=db,
            include_ranking=include_ranking,
            include_scores=include_scores,
            max_albums=max_albums
        )
        
        # Return as downloadable image
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename=tracklist_{year}_yearend.png"
            }
        )
        
    except ValueError as e:
        logger.warning(f"Invalid request for year {year} collage: {e}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "No albums found",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Failed to generate collage for year {year}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Collage generation failed",
                "message": "Failed to generate the year-end collage"
            }
        )
