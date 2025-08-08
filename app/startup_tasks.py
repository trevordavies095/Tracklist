"""
Background tasks that run on application startup
"""

import asyncio
import logging
from typing import Optional
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Album
from .services.cover_art_cache_service import get_cover_art_cache_service

logger = logging.getLogger(__name__)


async def cache_cover_art_on_startup(limit: Optional[int] = None):
    """
    Background task to cache cover art for albums that have URLs but no local cache
    
    Args:
        limit: Optional limit on number of albums to cache (for testing/batching)
    """
    logger.info("Starting background cover art caching task...")
    
    db = SessionLocal()
    cache_service = get_cover_art_cache_service()
    
    try:
        # Get albums with URLs but no local cache
        query = db.query(Album).filter(
            (Album.cover_art_url != None) & 
            (Album.cover_art_url != "") &
            ((Album.cover_art_local_path == None) | (Album.cover_art_local_path == ""))
        )
        
        if limit:
            query = query.limit(limit)
        
        albums_to_cache = query.all()
        
        if not albums_to_cache:
            logger.info("No albums need cover art caching")
            return
        
        logger.info(f"Found {len(albums_to_cache)} albums to cache cover art for")
        
        cached_count = 0
        failed_count = 0
        
        for album in albums_to_cache:
            try:
                logger.debug(f"Caching cover art for album: {album.name}")
                cached_paths = await cache_service.download_and_cache(
                    album.id, album.cover_art_url
                )
                
                if cached_paths and 'medium' in cached_paths:
                    album.cover_art_local_path = cached_paths['medium']
                    db.add(album)
                    cached_count += 1
                    
                    # Commit every 10 albums to avoid long transactions
                    if cached_count % 10 == 0:
                        db.commit()
                        logger.info(f"Cached {cached_count} album covers so far...")
                        
            except Exception as e:
                logger.warning(f"Failed to cache cover art for album '{album.name}': {e}")
                failed_count += 1
                
                # Continue with next album even if one fails
                continue
        
        # Final commit for remaining albums
        db.commit()
        
        logger.info(f"Cover art caching complete: {cached_count} cached, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Error in cover art caching task: {e}")
        db.rollback()
    finally:
        db.close()
        # Don't close the cache service as it's a singleton that will be reused


def start_background_tasks():
    """
    Start all background tasks
    This is called after the FastAPI app starts
    """
    # Create a new event loop for background tasks
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Schedule the cover art caching task
    try:
        # Run with a limit to avoid overwhelming the system on first startup
        # You can adjust or remove the limit based on your needs
        loop.run_until_complete(cache_cover_art_on_startup(limit=50))
    except Exception as e:
        logger.error(f"Background task failed: {e}")
    finally:
        loop.close()