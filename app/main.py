from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
import logging
import os
import asyncio
from .database import create_tables, init_db
from .exceptions import TracklistException, NotFoundError, ValidationError, ConflictError
from .logging_config import setup_logging
from .routers import search, albums, templates, reports

# Setup logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE", "logs/tracklist.log") if os.getenv("ENABLE_FILE_LOGGING", "false").lower() == "true" else None
setup_logging(level=log_level, log_file=log_file)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Tracklist API",
    description="""
## Tracklist - Self-hostable Music Album Rating Application

Tracklist is a personal music rating system that allows you to rate albums track-by-track to generate precise album scores.

### Key Features

* Track-by-track rating system - Rate each track on a 4-point scale
* MusicBrainz integration - Search and import album data
* Precise scoring algorithm - Calculate album scores based on individual track ratings
* Album artwork - Automatic cover art fetching from Cover Art Archive
* Responsive design - Works on desktop and mobile devices

### API Sections

* **Albums** - Create, rate, and manage album ratings
* **Search** - Search for albums in the MusicBrainz database
* **System** - Health checks and system information

### Rating Scale

- **0.0** - Skip (worst songs)
- **0.33** - Filler (tolerable but not enjoyable)  
- **0.67** - Good (playlist-worthy tracks)
- **1.0** - Standout (album highlights)

### Authentication

This API currently does not require authentication as it's designed for personal use.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "albums",
            "description": "Album rating operations - create, rate tracks, submit ratings, and manage albums"
        },
        {
            "name": "search", 
            "description": "Search for albums in the MusicBrainz database"
        },
        {
            "name": "reports",
            "description": "User statistics and analytics - get insights into your album collection"
        }
    ]
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(templates.router)  # Template routes (no prefix)
app.include_router(search.router)     # API routes
app.include_router(albums.router)     # API routes
app.include_router(reports.router)    # API routes for reporting


async def auto_migrate_artwork_cache():
    """
    Automatically migrate existing albums to cached artwork in the background
    This runs on startup to ensure all albums have cached artwork
    """
    try:
        # Wait a bit for the application to fully start
        await asyncio.sleep(5)
        
        logger.info("Checking for albums that need artwork caching...")
        
        from .database import SessionLocal
        from .models import Album
        from .services.artwork_cache_background import get_artwork_cache_background_service
        
        db = SessionLocal()
        
        try:
            # Check how many albums need caching
            uncached_count = db.query(Album).filter(
                Album.artwork_cached == False
            ).count()
            
            if uncached_count == 0:
                logger.info("All albums already have cached artwork")
                return
            
            logger.info(f"Found {uncached_count} albums without cached artwork")
            
            # Check if auto-migration is enabled (default: true)
            auto_migrate = os.getenv("AUTO_MIGRATE_ARTWORK", "true").lower() == "true"
            
            if not auto_migrate:
                logger.info("Auto-migration is disabled (set AUTO_MIGRATE_ARTWORK=true to enable)")
                return
            
            logger.info(f"Starting automatic artwork migration for {uncached_count} albums...")
            
            # Get the background cache service
            cache_service = get_artwork_cache_background_service()
            
            # Process albums in batches to avoid overwhelming the system
            batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "10"))
            max_albums = int(os.getenv("MIGRATION_MAX_ALBUMS", "0"))  # 0 = no limit
            
            # Get albums to process
            query = db.query(Album).filter(
                Album.artwork_cached == False,
                Album.cover_art_url.isnot(None)  # Only process albums with URLs
            )
            
            if max_albums > 0:
                query = query.limit(max_albums)
            
            albums = query.all()
            
            if not albums:
                logger.info("No albums with cover art URLs to migrate")
                return
            
            # Queue albums for background processing
            queued = 0
            for i, album in enumerate(albums):
                try:
                    # Add to background queue with low priority
                    task_id = cache_service.trigger_album_cache(
                        album_id=album.id,
                        cover_art_url=album.cover_art_url,
                        priority=9  # Very low priority for auto-migration
                    )
                    queued += 1
                    
                    # Add delay between batches to avoid overwhelming
                    if (i + 1) % batch_size == 0:
                        await asyncio.sleep(2)  # Wait 2 seconds between batches
                        logger.info(f"Queued {queued}/{len(albums)} albums for caching...")
                        
                except Exception as e:
                    logger.warning(f"Failed to queue album {album.id} for caching: {e}")
            
            logger.info(f"✓ Auto-migration started: {queued} albums queued for background caching")
            logger.info("Artwork will be cached gradually in the background without affecting performance")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Auto-migration failed: {e}")
        # Don't crash the application if migration fails
        pass


@app.on_event("startup")
async def startup_event():
    """Initialize database, cache directories, and background tasks on startup"""
    logger.info("Starting Tracklist application...")
    try:
        # Initialize database
        create_tables()
        init_db()
        logger.info("Database initialized successfully")
        
        # Initialize artwork cache directories
        from .services.artwork_cache_utils import init_artwork_cache_directories
        init_artwork_cache_directories()
        
        # Start background task manager
        from .services.background_tasks import start_background_tasks
        await start_background_tasks()
        logger.info("Background task manager started")
        
        # Start scheduled tasks
        from .services.scheduled_tasks import start_scheduled_tasks
        await start_scheduled_tasks()
        logger.info("Scheduled task manager started")
        
        # Auto-migrate existing albums to cached artwork
        asyncio.create_task(auto_migrate_artwork_cache())
        
        # Warm artwork memory cache with frequently accessed albums
        try:
            from .services.artwork_memory_cache import get_artwork_memory_cache
            from .database import SessionLocal
            from .models import Album, ArtworkCache
            
            memory_cache = get_artwork_memory_cache()
            db = SessionLocal()
            
            # Get most frequently accessed cached artwork (top 50)
            frequent_artwork = db.query(
                ArtworkCache.album_id,
                ArtworkCache.size_variant,
                ArtworkCache.file_path
            ).filter(
                ArtworkCache.file_path.isnot(None)
            ).order_by(
                ArtworkCache.access_count.desc()
            ).limit(50).all()
            
            # Convert file paths to URLs and warm cache
            warm_entries = []
            for album_id, size, file_path in frequent_artwork:
                if file_path:
                    # Convert file path to web URL
                    web_path = f"/static/artwork_cache/{size}/{file_path.split('/')[-1]}"
                    warm_entries.append((album_id, size, web_path))
            
            if warm_entries:
                warmed = memory_cache.warm_cache(warm_entries)
                logger.info(f"Warmed artwork memory cache with {warmed} entries")
            
            db.close()
        except Exception as e:
            logger.warning(f"Could not warm artwork cache: {e}")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Tracklist application...")
    try:
        # Stop scheduled tasks
        from .services.scheduled_tasks import stop_scheduled_tasks
        await stop_scheduled_tasks()
        logger.info("Scheduled task manager stopped")
        
        # Stop background task manager
        from .services.background_tasks import stop_background_tasks
        await stop_background_tasks()
        logger.info("Background task manager stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "tracklist"}


@app.get("/api/v1/docs")
async def api_docs_redirect():
    """Redirect to the main docs"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# Root endpoint is handled by templates.router


@app.exception_handler(TracklistException)
async def tracklist_exception_handler(request: Request, exc: TracklistException):
    """Handle custom Tracklist exceptions"""
    logger.error(f"Tracklist exception: {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=500,
        content={
            "error": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)