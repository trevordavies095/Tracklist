"""
Reporting API endpoints for user statistics and analytics
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from ..database import get_db
from ..reporting_service import get_reporting_service, ReportingService
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
    service: ReportingService = Depends(get_reporting_service),
    db: Session = Depends(get_db)
):
    """
    Get top rated albums
    
    Returns the highest scored albums in the collection.
    
    Query Parameters:
    - limit: Maximum number of albums to return (1-100, default: 10)
    
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
        logger.info(f"Fetching top {limit} albums")
        top_albums = service.get_top_albums(db, limit=limit)
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