#!/usr/bin/env python3
"""
Migration script to add cover_art_url column to existing albums table
"""

import sqlite3
import os
from pathlib import Path


def add_cover_art_column(db_path: str):
    """Add cover_art_url column to albums table if it doesn't exist"""
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(albums)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'cover_art_url' in columns:
            print(f"✓ cover_art_url column already exists in {db_path}")
            conn.close()
            return True
        
        # Add the column
        print(f"Adding cover_art_url column to {db_path}...")
        cursor.execute("ALTER TABLE albums ADD COLUMN cover_art_url TEXT")
        
        # Commit changes
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(albums)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'cover_art_url' in columns:
            print(f"✓ Successfully added cover_art_url column to {db_path}")
            success = True
        else:
            print(f"✗ Failed to add cover_art_url column to {db_path}")
            success = False
        
        conn.close()
        return success
        
    except Exception as e:
        print(f"✗ Error updating {db_path}: {e}")
        return False


def main():
    """Main migration function"""
    print("🎨 Adding cover_art_url column to existing databases...")
    
    # List of potential database locations
    db_paths = [
        "./data/tracklist.db",
        "./tracklist.db",
        "data/tracklist.db",
        "tracklist.db"
    ]
    
    # Check environment variables for custom paths
    custom_db_path = os.getenv("TRACKLIST_DB_PATH")
    if custom_db_path:
        db_paths.insert(0, custom_db_path)
    
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("sqlite:///"):
        sqlite_path = database_url.replace("sqlite:///", "")
        db_paths.insert(0, sqlite_path)
    
    updated_count = 0
    found_count = 0
    
    for db_path in db_paths:
        # Resolve relative paths
        resolved_path = str(Path(db_path).resolve())
        
        # Skip duplicates
        if found_count > 0 and any(str(Path(p).resolve()) == resolved_path for p in db_paths[:db_paths.index(db_path)]):
            continue
            
        if os.path.exists(db_path):
            found_count += 1
            print(f"\nFound database: {db_path}")
            if add_cover_art_column(db_path):
                updated_count += 1
    
    if found_count == 0:
        print("No SQLite databases found. This is normal for new installations.")
    else:
        print(f"\n🎉 Migration complete!")
        print(f"   📊 Found {found_count} database(s)")
        print(f"   ✅ Updated {updated_count} database(s)")
        
        if updated_count > 0:
            print(f"\n💡 You can now use the 'Update Cover Art' button in the albums page")
            print(f"   to fetch artwork for existing albums.")


if __name__ == "__main__":
    main()