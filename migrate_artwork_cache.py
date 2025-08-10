#!/usr/bin/env python3
"""
Migration script to cache artwork for all existing albums
Processes albums in batches with progress tracking and resume capability
"""

import os
import sys
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import time

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, create_tables, init_db
from app.models import Album, ArtworkCache
from app.services.artwork_cache_service import ArtworkCacheService
from app.services.artwork_memory_cache import get_artwork_memory_cache

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/artwork_migration.log')
    ]
)
logger = logging.getLogger(__name__)

# Migration configuration
BATCH_SIZE = 5  # Process 5 albums at a time (smaller for testing)
PROGRESS_FILE = "logs/artwork_migration_progress.json"
REPORT_FILE = "logs/artwork_migration_report.json"
RETRY_FAILED = True  # Whether to retry previously failed albums
MAX_RETRIES = 3  # Maximum retries per album
DELAY_BETWEEN_BATCHES = 2  # Seconds to wait between batches (rate limiting)


class ArtworkMigration:
    """Handles migration of existing albums to cached artwork"""
    
    def __init__(self):
        """Initialize the migration handler"""
        self.db = SessionLocal()
        self.cache_service = ArtworkCacheService()
        self.memory_cache = get_artwork_memory_cache()
        self.progress = self.load_progress()
        self.report = {
            'started_at': None,
            'completed_at': None,
            'total_albums': 0,
            'processed': 0,
            'cached': 0,
            'skipped': 0,
            'failed': 0,
            'errors': [],
            'processing_time_seconds': 0,
            'bytes_cached': 0,
            'variants_created': 0
        }
        
    def load_progress(self) -> Dict[str, Any]:
        """Load progress from file if exists"""
        progress_path = Path(PROGRESS_FILE)
        if progress_path.exists():
            try:
                with open(progress_path, 'r') as f:
                    progress = json.load(f)
                    logger.info(f"Loaded progress from previous run: {progress['processed']}/{progress['total']} albums processed")
                    return progress
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        
        return {
            'processed_album_ids': [],
            'failed_album_ids': {},  # {album_id: retry_count}
            'total': 0,
            'processed': 0,
            'last_batch_id': 0
        }
    
    def save_progress(self):
        """Save current progress to file"""
        try:
            progress_path = Path(PROGRESS_FILE)
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(progress_path, 'w') as f:
                json.dump(self.progress, f, indent=2)
            
            logger.debug(f"Progress saved: {self.progress['processed']}/{self.progress['total']}")
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def save_report(self):
        """Save final report to file"""
        try:
            report_path = Path(REPORT_FILE)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(report_path, 'w') as f:
                json.dump(self.report, f, indent=2, default=str)
            
            logger.info(f"Report saved to {report_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
    
    async def get_albums_to_process(self) -> List[Album]:
        """Get list of albums that need processing"""
        try:
            # Get all albums
            all_albums = self.db.query(Album).all()
            
            # Filter out already processed and already cached
            albums_to_process = []
            
            for album in all_albums:
                # Skip if already processed in this run
                if album.id in self.progress['processed_album_ids']:
                    continue
                
                # Skip if already has cached artwork (unless we're retrying failed)
                if album.artwork_cached and album.id not in self.progress.get('failed_album_ids', {}):
                    logger.debug(f"Album {album.id} already has cached artwork, skipping")
                    continue
                
                # Check if we should retry failed albums
                if album.id in self.progress.get('failed_album_ids', {}):
                    retry_count = self.progress['failed_album_ids'][album.id]
                    if retry_count >= MAX_RETRIES:
                        logger.debug(f"Album {album.id} has failed {retry_count} times, skipping")
                        continue
                
                # Check if album has cover art URL
                if not album.cover_art_url:
                    logger.debug(f"Album {album.id} has no cover art URL, will try to fetch")
                
                albums_to_process.append(album)
            
            logger.info(f"Found {len(albums_to_process)} albums to process (out of {len(all_albums)} total)")
            return albums_to_process
            
        except Exception as e:
            logger.error(f"Failed to get albums: {e}")
            return []
    
    async def process_album(self, album: Album) -> Dict[str, Any]:
        """Process a single album"""
        result = {
            'album_id': album.id,
            'title': album.name,
            'artist': album.artist.name if album.artist else 'Unknown',
            'success': False,
            'cached': False,
            'error': None,
            'variants': 0,
            'bytes': 0,
            'time_seconds': 0
        }
        
        start_time = time.time()
        
        try:
            # Check if already has cached files
            existing_cache = self.db.query(ArtworkCache).filter_by(
                album_id=album.id
            ).first()
            
            if existing_cache and existing_cache.file_path:
                file_path = Path(existing_cache.file_path)
                if file_path.exists():
                    logger.info(f"Album {album.id} already has cached files, marking as cached")
                    album.artwork_cached = True
                    album.artwork_cache_date = existing_cache.last_fetched_at or datetime.now(timezone.utc)
                    self.db.commit()
                    result['success'] = True
                    result['cached'] = True
                    result['variants'] = self.db.query(ArtworkCache).filter_by(album_id=album.id).count()
                    return result
            
            # Get or fetch cover art URL if not present
            if not album.cover_art_url:
                logger.info(f"Fetching cover art URL for album {album.id}")
                from app.services.cover_art_service import get_cover_art_service
                cover_art_service = get_cover_art_service()
                
                try:
                    cover_url = await cover_art_service.get_cover_art_url(album.musicbrainz_id)
                    if cover_url:
                        album.cover_art_url = cover_url
                        self.db.commit()
                        logger.info(f"Found cover art URL for album {album.id}")
                    else:
                        logger.warning(f"No cover art found for album {album.id}")
                        result['error'] = "No cover art available"
                        return result
                except Exception as e:
                    logger.warning(f"Could not fetch cover art URL for album {album.id}: {e}")
                    result['error'] = f"Cover art fetch failed: {str(e)}"
                    return result
            
            # Cache the artwork
            logger.info(f"Caching artwork for album {album.id}: {album.name}")
            success = await self.cache_service.cache_artwork(
                album=album,
                artwork_url=album.cover_art_url,
                db=self.db
            )
            
            if success:
                # Count variants created
                variants = self.db.query(ArtworkCache).filter_by(album_id=album.id).all()
                total_bytes = sum(v.file_size_bytes or 0 for v in variants)
                
                result['success'] = True
                result['cached'] = True
                result['variants'] = len(variants)
                result['bytes'] = total_bytes
                
                logger.info(f"✓ Cached {len(variants)} variants for album {album.id} ({total_bytes / 1024:.1f} KB)")
            else:
                result['error'] = "Cache operation failed"
                logger.warning(f"Failed to cache artwork for album {album.id}")
            
        except Exception as e:
            logger.error(f"Error processing album {album.id}: {e}")
            result['error'] = str(e)
        finally:
            result['time_seconds'] = time.time() - start_time
        
        return result
    
    async def process_batch(self, albums: List[Album]) -> List[Dict[str, Any]]:
        """Process a batch of albums concurrently"""
        logger.info(f"Processing batch of {len(albums)} albums...")
        
        # Create tasks for all albums in batch
        tasks = [self.process_album(album) for album in albums]
        
        # Process concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task failed for album {albums[i].id}: {result}")
                processed_results.append({
                    'album_id': albums[i].id,
                    'success': False,
                    'error': str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def run(self):
        """Run the migration"""
        logger.info("=" * 60)
        logger.info("Starting Artwork Cache Migration")
        logger.info("=" * 60)
        
        self.report['started_at'] = datetime.now(timezone.utc)
        
        try:
            # Initialize database
            create_tables()
            init_db()
            
            # Get albums to process
            albums_to_process = await self.get_albums_to_process()
            
            if not albums_to_process:
                logger.info("No albums to process")
                return
            
            self.progress['total'] = len(albums_to_process)
            self.report['total_albums'] = len(albums_to_process)
            
            # Process in batches
            for i in range(0, len(albums_to_process), BATCH_SIZE):
                batch = albums_to_process[i:i + BATCH_SIZE]
                batch_num = (i // BATCH_SIZE) + 1
                total_batches = (len(albums_to_process) + BATCH_SIZE - 1) // BATCH_SIZE
                
                logger.info(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} albums)")
                
                # Process batch
                results = await self.process_batch(batch)
                
                # Update progress and report
                for result in results:
                    album_id = result['album_id']
                    
                    if result['success']:
                        self.progress['processed_album_ids'].append(album_id)
                        if album_id in self.progress.get('failed_album_ids', {}):
                            del self.progress['failed_album_ids'][album_id]
                        
                        if result['cached']:
                            self.report['cached'] += 1
                            self.report['bytes_cached'] += result.get('bytes', 0)
                            self.report['variants_created'] += result.get('variants', 0)
                        else:
                            self.report['skipped'] += 1
                    else:
                        # Track failures
                        if 'failed_album_ids' not in self.progress:
                            self.progress['failed_album_ids'] = {}
                        
                        if album_id not in self.progress['failed_album_ids']:
                            self.progress['failed_album_ids'][album_id] = 1
                        else:
                            self.progress['failed_album_ids'][album_id] += 1
                        
                        self.report['failed'] += 1
                        self.report['errors'].append({
                            'album_id': album_id,
                            'title': result.get('title', 'Unknown'),
                            'error': result.get('error', 'Unknown error')
                        })
                
                self.progress['processed'] = len(self.progress['processed_album_ids'])
                self.report['processed'] = self.progress['processed']
                
                # Save progress after each batch
                self.save_progress()
                
                # Print progress
                progress_pct = (self.progress['processed'] / self.progress['total'] * 100) if self.progress['total'] > 0 else 0
                logger.info(
                    f"Progress: {self.progress['processed']}/{self.progress['total']} "
                    f"({progress_pct:.1f}%) | "
                    f"Cached: {self.report['cached']} | "
                    f"Failed: {self.report['failed']}"
                )
                
                # Rate limiting delay between batches
                if i + BATCH_SIZE < len(albums_to_process):
                    logger.debug(f"Waiting {DELAY_BETWEEN_BATCHES} seconds before next batch...")
                    await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Complete
            self.report['completed_at'] = datetime.now(timezone.utc)
            self.report['processing_time_seconds'] = (
                self.report['completed_at'] - self.report['started_at']
            ).total_seconds()
            
            # Save final report
            self.save_report()
            
            # Print summary
            self.print_summary()
            
            # Clear progress file on successful completion
            if self.report['failed'] == 0:
                try:
                    Path(PROGRESS_FILE).unlink()
                    logger.info("Progress file deleted (migration complete)")
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            self.report['error'] = str(e)
            self.save_report()
        finally:
            # Close resources
            if self.cache_service.client:
                await self.cache_service.close()
            self.db.close()
    
    def print_summary(self):
        """Print migration summary"""
        logger.info("\n" + "=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        
        duration = self.report['processing_time_seconds']
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        
        logger.info(f"Total albums:      {self.report['total_albums']}")
        logger.info(f"Processed:         {self.report['processed']}")
        logger.info(f"Successfully cached: {self.report['cached']}")
        logger.info(f"Skipped (already cached): {self.report['skipped']}")
        logger.info(f"Failed:            {self.report['failed']}")
        logger.info(f"Variants created:  {self.report['variants_created']}")
        logger.info(f"Total cached:      {self.report['bytes_cached'] / (1024*1024):.2f} MB")
        logger.info(f"Processing time:   {hours}h {minutes}m {seconds}s")
        
        if self.report['cached'] > 0:
            avg_time = duration / self.report['cached']
            logger.info(f"Average time per album: {avg_time:.2f} seconds")
        
        if self.report['failed'] > 0:
            logger.warning(f"\n{self.report['failed']} albums failed to cache:")
            for error in self.report['errors'][:10]:  # Show first 10 errors
                logger.warning(f"  - Album {error['album_id']} ({error['title']}): {error['error']}")
            if len(self.report['errors']) > 10:
                logger.warning(f"  ... and {len(self.report['errors']) - 10} more")
            logger.info(f"\nFull error details saved in {REPORT_FILE}")
        
        if self.report['failed'] == 0:
            logger.info("\n✅ Migration completed successfully!")
        elif self.report['cached'] > 0:
            logger.info(f"\n⚠️ Migration completed with {self.report['failed']} failures")
            logger.info("Run the script again to retry failed albums")
        else:
            logger.error("\n❌ Migration failed - no albums were cached")


async def main():
    """Main entry point"""
    migration = ArtworkMigration()
    await migration.run()


if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--reset":
            # Reset progress
            try:
                Path(PROGRESS_FILE).unlink()
                logger.info("Progress file reset")
            except:
                pass
        elif sys.argv[1] == "--help":
            print("Usage: python migrate_artwork_cache.py [options]")
            print("Options:")
            print("  --reset    Reset progress and start fresh")
            print("  --help     Show this help message")
            sys.exit(0)
    
    # Run migration
    asyncio.run(main())