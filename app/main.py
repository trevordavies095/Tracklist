from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
import logging
import os
import asyncio
from .database import create_tables, init_db
from .exceptions import TracklistException
from .logging_config import setup_logging
from .routers import search, albums, templates, reports, settings

# Setup logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = (
    os.getenv("LOG_FILE", "logs/tracklist.log")
    if os.getenv("ENABLE_FILE_LOGGING", "false").lower() == "true"
    else None
)
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
            "description": "Album rating operations - create, rate tracks, submit ratings, and manage albums",
        },
        {
            "name": "search",
            "description": "Search for albums in the MusicBrainz database",
        },
        {
            "name": "reports",
            "description": "User statistics and analytics - get insights into your album collection",
        },
    ],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(templates.router)  # Template routes (no prefix)
app.include_router(search.router)  # API routes
app.include_router(albums.router)  # API routes
app.include_router(reports.router)  # API routes for reporting
app.include_router(settings.router)  # API routes for settings


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
        from .models import Album, ArtworkCache
        from .services.artwork_cache_background import (
            get_artwork_cache_background_service,
        )

        db = SessionLocal()

        try:
            # More robust check: Look for albums without actual cache entries
            # This handles cases where artwork_cached might be incorrectly set
            from sqlalchemy import exists

            # Subquery to check if album has any artwork cache entries
            has_cache = exists().where(ArtworkCache.album_id == Album.id)

            # Count albums that don't have cache entries
            uncached_count = (
                db.query(Album)
                .filter(
                    ~has_cache,
                    Album.cover_art_url.isnot(None),  # Only count albums with URLs
                )
                .count()
            )

            # Also log total albums for context
            total_albums = db.query(Album).count()
            albums_with_urls = (
                db.query(Album).filter(Album.cover_art_url.isnot(None)).count()
            )

            logger.info(
                f"Album cache status: {total_albums} total albums, {albums_with_urls} with artwork URLs"
            )

            if uncached_count == 0:
                logger.info("All albums with artwork URLs already have cached entries")
                return

            logger.info(f"Found {uncached_count} albums without cached artwork")

            # Check if auto-migration is enabled (default: true)
            auto_migrate = os.getenv("AUTO_MIGRATE_ARTWORK", "true").lower() == "true"

            if not auto_migrate:
                logger.info(
                    "Auto-migration is disabled (set AUTO_MIGRATE_ARTWORK=true to enable)"
                )
                return

            logger.info(
                f"Starting automatic artwork migration for {uncached_count} albums..."
            )

            # Get the background cache service
            cache_service = get_artwork_cache_background_service()

            # Process albums in batches to avoid overwhelming the system
            batch_size = int(os.getenv("MIGRATION_BATCH_SIZE", "10"))
            max_albums = int(os.getenv("MIGRATION_MAX_ALBUMS", "0"))  # 0 = no limit

            # Get albums to process - those without cache entries
            query = db.query(Album).filter(
                ~has_cache,
                Album.cover_art_url.isnot(None),  # Only process albums with URLs
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
                        priority=9,  # Very low priority for auto-migration
                    )
                    queued += 1

                    # Add delay between batches to avoid overwhelming
                    if (i + 1) % batch_size == 0:
                        await asyncio.sleep(2)  # Wait 2 seconds between batches
                        logger.info(
                            f"Queued {queued}/{len(albums)} albums for caching..."
                        )

                except Exception as e:
                    logger.warning(f"Failed to queue album {album.id} for caching: {e}")

            logger.info(
                f"✓ Auto-migration started: {queued} albums queued for background caching"
            )
            logger.info(
                "Artwork will be cached gradually in the background without affecting performance"
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Auto-migration failed: {e}")
        # Don't crash the application if migration fails
        pass


async def fix_genre_country_codes():
    """
    One-time fix for albums with country codes or NULL genres
    This will fetch proper genre data from MusicBrainz

    NOTE: This migration can be removed in a future version (e.g., v2.0+) once we're
    confident all users have upgraded and run this fix. After the fix runs once,
    it will find no albums to update on subsequent startups.
    """
    try:
        # Wait a bit for application to start
        await asyncio.sleep(10)

        logger.info("Checking for albums with missing or incorrect genres...")

        from .database import SessionLocal
        from .models import Album
        from .musicbrainz_client import MusicBrainzClient
        from sqlalchemy import or_, and_
        import re

        db = SessionLocal()

        try:
            # Find albums with NULL genre or country code pattern (2-3 uppercase letters)
            # Country codes are typically 2 letters, but some special codes are 3 (like XWW for worldwide)
            country_code_pattern = re.compile(r"^[A-Z]{2,3}$")

            # Get all albums to check
            all_albums = db.query(Album).all()
            albums_to_fix = []

            for album in all_albums:
                if album.genre is None:
                    albums_to_fix.append(album)
                elif country_code_pattern.match(album.genre):
                    albums_to_fix.append(album)

            if not albums_to_fix:
                logger.info("All albums have proper genre data")
                return

            logger.info(
                f"Found {len(albums_to_fix)} albums with missing or incorrect genres"
            )

            # Fix them one by one with rate limiting
            fixed_count = 0
            failed_count = 0

            async with MusicBrainzClient() as client:
                for album in albums_to_fix:
                    try:
                        logger.debug(
                            f"Fetching genre for album: {album.name} (current: {album.genre})"
                        )

                        # Fetch release details with tags
                        release_data = await client.get_release_with_tracks(
                            album.musicbrainz_id
                        )

                        # Extract genres from release data
                        genres = []
                        if release_data.get("release-group") and release_data[
                            "release-group"
                        ].get("tags"):
                            tags = release_data["release-group"]["tags"]
                            # Sort by count and take top 5
                            sorted_tags = sorted(
                                tags, key=lambda x: x.get("count", 0), reverse=True
                            )[:5]
                            genres = [
                                tag["name"] for tag in sorted_tags if "name" in tag
                            ]

                        if genres:
                            # Format genres
                            formatted_genres = []
                            for genre in genres:
                                formatted_genre = " ".join(
                                    word.capitalize() for word in genre.split("-")
                                )
                                formatted_genres.append(formatted_genre)
                            new_genre = ", ".join(formatted_genres)

                            album.genre = new_genre
                            fixed_count += 1
                            logger.info(
                                f"Updated genre for '{album.name}': {new_genre}"
                            )
                        else:
                            # No genre data available, set to NULL
                            album.genre = None
                            fixed_count += 1
                            logger.debug(
                                f"No genre data available for '{album.name}', set to NULL"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch genre for album {album.id}: {e}"
                        )
                        failed_count += 1
                        # Continue with next album

            # Commit all changes
            if fixed_count > 0:
                db.commit()
                logger.info(
                    f"✓ Genre migration completed: {fixed_count} albums updated, {failed_count} failed"
                )
            else:
                logger.info("No albums were updated")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Genre migration failed: {e}")
        # Don't crash the application


@app.on_event("startup")
async def startup_event():
    """Initialize database, cache directories, and background tasks on startup"""
    logger.info("Starting Tracklist application...")
    try:
        # Initialize database
        create_tables()
        init_db()
        logger.info("Database initialized successfully")

        # Validate and fix artwork_cached flags
        try:
            from .services.artwork_cache_validator import (
                validate_artwork_cache_on_startup,
            )

            logger.info("Validating artwork cache flags...")
            validation_stats = validate_artwork_cache_on_startup()
            if validation_stats.get("fixed", 0) > 0:
                logger.info(
                    f"Fixed {validation_stats['fixed']} incorrect artwork_cached flags"
                )
            else:
                logger.info("All artwork_cached flags are correct")
        except Exception as e:
            logger.warning(f"Could not validate artwork cache flags: {e}")

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

        # Fix genre country codes (can be removed in v2.0+)
        asyncio.create_task(fix_genre_country_codes())

        # Warm artwork memory cache with frequently accessed albums
        try:
            from .services.artwork_memory_cache import get_artwork_memory_cache
            from .database import SessionLocal
            from .models import Album, ArtworkCache

            memory_cache = get_artwork_memory_cache()
            db = SessionLocal()

            # Get most frequently accessed cached artwork (top 50)
            frequent_artwork = (
                db.query(
                    ArtworkCache.album_id,
                    ArtworkCache.size_variant,
                    ArtworkCache.file_path,
                )
                .filter(ArtworkCache.file_path.isnot(None))
                .order_by(ArtworkCache.access_count.desc())
                .limit(50)
                .all()
            )

            # Convert file paths to URLs and warm cache
            warm_entries = []
            for album_id, size, file_path in frequent_artwork:
                if file_path:
                    # Convert file path to web URL
                    web_path = (
                        f"/static/artwork_cache/{size}/{file_path.split('/')[-1]}"
                    )
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
        status_code=500, content={"error": exc.message, "details": exc.details}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422, content={"error": "Validation error", "details": exc.errors()}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
