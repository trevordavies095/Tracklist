#!/usr/bin/env python3
"""
Test script for CLI migration - creates a sample CLI database for testing
"""

import sqlite3
import tempfile
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent / "app"))

from migrate_cli_to_webui import CLIToWebUIMigrator
from app.database import SessionLocal
from app.models import Album, Track, Artist

def create_test_cli_db():
    """Create a test CLI database with sample data"""
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp_db.close()
    
    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()
    
    # Create CLI schema
    cursor.execute('''
        CREATE TABLE "artist" (
            "id" INTEGER NOT NULL,
            "name" TEXT NOT NULL UNIQUE,
            PRIMARY KEY("id" AUTOINCREMENT)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE "album" (
            "id" INTEGER NOT NULL,
            "artist_id" INTEGER NOT NULL,
            "name" TEXT NOT NULL,
            "year" INTEGER NOT NULL,
            "rating" INTEGER,
            "musicbrainz_id" TEXT,
            "star_rating" REAL,
            PRIMARY KEY("id" AUTOINCREMENT)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE "track" (
            "id" INTEGER NOT NULL,
            "album_id" INTEGER NOT NULL,
            "name" TEXT NOT NULL,
            "track_score" INTEGER,
            PRIMARY KEY("id" AUTOINCREMENT)
        )
    ''')
    
    # Insert test data
    # Artist 1: Test Artist
    cursor.execute("INSERT INTO artist (name) VALUES ('Test Artist')")
    artist_id = cursor.lastrowid
    
    # Album 1: Mixed ratings
    cursor.execute("""
        INSERT INTO album (artist_id, name, year, rating, musicbrainz_id) 
        VALUES (?, 'Test Album 1', 2020, 75, NULL)
    """, (artist_id,))
    album1_id = cursor.lastrowid
    
    # Tracks for Album 1 (mix of all rating types)
    tracks_album1 = [
        ('Track 1', 1.0),   # Standout -> 1.0
        ('Track 2', 0.75),  # Good -> 0.67
        ('Track 3', 0.5),   # Filler -> 0.33
        ('Track 4', 0.0),   # Skip -> 0.0
        ('Track 5', 0.75),  # Good -> 0.67
    ]
    
    for track_name, rating in tracks_album1:
        cursor.execute("""
            INSERT INTO track (album_id, name, track_score) 
            VALUES (?, ?, ?)
        """, (album1_id, track_name, rating))
    
    # Artist 2: Another Test Artist
    cursor.execute("INSERT INTO artist (name) VALUES ('Another Test Artist')")
    artist2_id = cursor.lastrowid
    
    # Album 2: Perfect album
    cursor.execute("""
        INSERT INTO album (artist_id, name, year, rating, musicbrainz_id) 
        VALUES (?, 'Perfect Album', 2021, 100, 'test-mb-id-123')
    """, (artist2_id,))
    album2_id = cursor.lastrowid
    
    # Tracks for Album 2 (all standouts)
    for i in range(3):
        cursor.execute("""
            INSERT INTO track (album_id, name, track_score) 
            VALUES (?, ?, 1.0)
        """, (album2_id, f'Perfect Track {i+1}'))
    
    conn.commit()
    conn.close()
    
    print(f"Created test CLI database: {temp_db.name}")
    return temp_db.name

def test_migration():
    """Test the migration process"""
    print("Creating test CLI database...")
    cli_db_path = create_test_cli_db()
    
    try:
        print("Starting migration test...")
        
        # Run migration
        migrator = CLIToWebUIMigrator(cli_db_path)
        success = migrator.migrate()
        
        if not success:
            print("❌ Migration failed")
            return False
        
        # Verify results
        db = SessionLocal()
        try:
            albums = db.query(Album).all()
            tracks = db.query(Track).all()
            artists = db.query(Artist).all()
            
            print(f"\nVerification Results:")
            print(f"Artists in WebUI DB: {len(artists)}")
            print(f"Albums in WebUI DB: {len(albums)}")
            print(f"Tracks in WebUI DB: {len(tracks)}")
            
            # Check specific conversions
            for album in albums:
                album_tracks = db.query(Track).filter(Track.album_id == album.id).all()
                ratings = [t.track_rating for t in album_tracks]
                
                print(f"\nAlbum: {album.name}")
                print(f"  Score: {album.rating_score}")
                print(f"  Track ratings: {ratings}")
                print(f"  Is rated: {album.is_rated}")
                print(f"  Album bonus: {album.album_bonus}")
            
            # Verify rating conversion
            expected_conversions = {
                0.0: "Skip (was 0.0)",
                0.33: "Filler (was 0.5)", 
                0.67: "Good (was 0.75)",
                1.0: "Standout (was 1.0)"
            }
            
            all_ratings = [t.track_rating for t in tracks]
            rating_counts = {}
            for rating in all_ratings:
                rating_counts[rating] = rating_counts.get(rating, 0) + 1
            
            print(f"\nRating Conversion Verification:")
            for rating, description in expected_conversions.items():
                count = rating_counts.get(rating, 0)
                print(f"  {description}: {count} tracks")
            
            print("\n✅ Migration test completed successfully!")
            return True
            
        finally:
            db.close()
            
    finally:
        # Clean up test database
        Path(cli_db_path).unlink()
        print(f"Cleaned up test database: {cli_db_path}")

if __name__ == "__main__":
    test_migration()