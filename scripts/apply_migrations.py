#!/usr/bin/env python3
"""
Manual migration script for Tracklist database
Run this if you're upgrading from an older version and experiencing database errors
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine
from app.migrations import run_migrations
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Apply all necessary database migrations"""
    print("Tracklist Database Migration Tool")
    print("=" * 40)
    
    # Check if database exists
    from app.database import DATABASE_URL
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if not Path(db_path).exists():
            print(f"Database not found at: {db_path}")
            print("Please ensure your database exists before running migrations.")
            return 1
    
    print(f"Database: {DATABASE_URL}")
    print("\nApplying migrations...")
    
    try:
        migrations = run_migrations(engine)
        
        if migrations:
            print(f"\n✓ Successfully applied {len(migrations)} migrations:")
            for migration in migrations:
                print(f"  - {migration}")
        else:
            print("\n✓ Database is already up to date - no migrations needed")
        
        print("\nMigration complete!")
        return 0
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print("\nIf the problem persists, please report this issue.")
        return 1


if __name__ == "__main__":
    sys.exit(main())