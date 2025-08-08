#!/usr/bin/env python3
"""
Reset cover art cache references in database when files are missing
Use this if the cache files were deleted but database still has references
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models import Album
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_missing_cache_references():
    """
    Check all albums with cover_art_local_path and clear the reference
    if the actual file doesn't exist
    """
    db = SessionLocal()
    
    try:
        # Get all albums with local cache references
        albums_with_cache = db.query(Album).filter(
            (Album.cover_art_local_path != None) & 
            (Album.cover_art_local_path != "")
        ).all()
        
        print(f"Checking {len(albums_with_cache)} albums with cache references...")
        
        reset_count = 0
        for album in albums_with_cache:
            # Convert web path to file path
            # e.g., "/static/covers/medium/album_1_medium.webp" -> "static/covers/medium/album_1_medium.webp"
            file_path = album.cover_art_local_path.lstrip('/')
            full_path = Path(file_path)
            
            if not full_path.exists():
                print(f"  ✗ Missing file for album '{album.name}': {album.cover_art_local_path}")
                album.cover_art_local_path = None
                db.add(album)
                reset_count += 1
            else:
                print(f"  ✓ File exists for album '{album.name}'")
        
        if reset_count > 0:
            db.commit()
            print(f"\n✓ Reset {reset_count} invalid cache references")
            print("Run the cache-all-covers endpoint to re-cache the artwork")
        else:
            print("\n✓ All cache references are valid")
        
        return reset_count
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Error resetting cache references: {e}")
        return -1
    finally:
        db.close()


def main():
    """Main function"""
    print("Tracklist Cache Reference Reset Tool")
    print("=" * 40)
    
    reset_count = reset_missing_cache_references()
    
    if reset_count > 0:
        print("\nTo re-cache the artwork, run:")
        print("  curl -X POST http://localhost:8000/api/v1/albums/cache-all-covers")
    
    return 0 if reset_count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())