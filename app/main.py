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
from .routers import search, albums, templates

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
        }
    ]
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(templates.router)  # Template routes (no prefix)
app.include_router(search.router)     # API routes
app.include_router(albums.router)     # API routes


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting Tracklist application...")
    try:
        create_tables()
        init_db()
        logger.info("Database initialized successfully")
        
        # Start background cover art caching task
        from .startup_tasks import cache_cover_art_on_startup
        
        # Check if cover art caching is enabled (default: enabled)
        cache_on_startup = os.getenv("CACHE_COVER_ART_ON_STARTUP", "true").lower() == "true"
        max_albums_to_cache = int(os.getenv("MAX_ALBUMS_TO_CACHE_ON_STARTUP", "50"))
        
        if cache_on_startup:
            logger.info(f"Starting background cover art caching (max {max_albums_to_cache} albums)...")
            # Run as background task so it doesn't block startup
            asyncio.create_task(cache_cover_art_on_startup(limit=max_albums_to_cache))
        else:
            logger.info("Cover art caching on startup is disabled")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


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