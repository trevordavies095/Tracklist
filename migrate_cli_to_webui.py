#!/usr/bin/env python3
"""
Migration script to import CLI rankings to WebUI
Converts from old 0.5-based rating system to new 0.33-based system
"""

import sys
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.database import SessionLocal
from app.models import Album, Track, Artist, UserSettings
from app.rating_service import RatingCalculator
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class CLIToWebUIMigrator:
    """Migrates rankings from CLI database to WebUI database"""
    
    # Rating conversion mapping from CLI to WebUI
    RATING_CONVERSION = {
        0.0: 0.0,    # Skip -> Skip
        0.5: 0.33,   # Filler -> Filler (0.33)
        0.75: 0.67,  # Good -> Good (0.67)  
        1.0: 1.0,    # Standout -> Standout (1.0)
    }
    
    def __init__(self, cli_db_path: str):
        self.cli_db_path = cli_db_path
        self.webui_db = SessionLocal()
        self.stats = {
            'artists_processed': 0,
            'albums_processed': 0,
            'tracks_processed': 0,
            'albums_with_ratings': 0,
            'albums_skipped': 0,
            'conversion_counts': {0.0: 0, 0.5: 0, 0.75: 0, 1.0: 0}
        }
    
    def connect_cli_db(self) -> sqlite3.Connection:
        """Connect to CLI database"""
        if not Path(self.cli_db_path).exists():
            raise FileNotFoundError(f"CLI database not found: {self.cli_db_path}")
        
        logger.info(f"Connecting to CLI database: {self.cli_db_path}")
        return sqlite3.connect(self.cli_db_path)
    
    def get_cli_data(self) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Extract all data from CLI database"""
        conn = self.connect_cli_db()
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        
        try:
            cursor = conn.cursor()
            
            # Get all artists
            cursor.execute("SELECT * FROM artist")
            artists = [dict(row) for row in cursor.fetchall()]
            
            # Get all albums with ratings
            cursor.execute("""
                SELECT a.*, ar.name as artist_name 
                FROM album a 
                JOIN artist ar ON a.artist_id = ar.id 
                WHERE a.rating IS NOT NULL
                ORDER BY a.id
            """)
            albums = [dict(row) for row in cursor.fetchall()]
            
            # Get all tracks with ratings
            cursor.execute("""
                SELECT t.*, a.name as album_name, ar.name as artist_name
                FROM track t
                JOIN album a ON t.album_id = a.id
                JOIN artist ar ON a.artist_id = ar.id
                WHERE t.track_score IS NOT NULL
                ORDER BY t.album_id, t.id
            """)
            tracks = [dict(row) for row in cursor.fetchall()]
            
            logger.info(f"CLI data summary:")
            logger.info(f"  Artists: {len(artists)}")
            logger.info(f"  Albums with ratings: {len(albums)}")
            logger.info(f"  Tracks with ratings: {len(tracks)}")
            
            return artists, albums, tracks
            
        finally:
            conn.close()
    
    def convert_track_rating(self, cli_rating: float) -> float:
        """Convert CLI track rating to WebUI rating"""
        if cli_rating not in self.RATING_CONVERSION:
            logger.warning(f"Unknown CLI rating: {cli_rating}, defaulting to 0.0")
            return 0.0
        
        webui_rating = self.RATING_CONVERSION[cli_rating]
        self.stats['conversion_counts'][cli_rating] += 1
        return webui_rating
    
    def create_or_get_artist(self, cli_artist: Dict) -> Artist:
        """Create or get existing artist in WebUI database"""
        # Check if artist already exists
        existing = self.webui_db.query(Artist).filter(Artist.name == cli_artist['name']).first()
        if existing:
            return existing
        
        # Create new artist
        artist = Artist(
            name=cli_artist['name'],
            musicbrainz_id=None  # CLI doesn't have MusicBrainz IDs
        )
        self.webui_db.add(artist)
        self.webui_db.flush()  # Get ID
        self.stats['artists_processed'] += 1
        return artist
    
    def migrate_album(self, cli_album: Dict, cli_tracks: List[Dict]) -> Optional[Album]:
        """Migrate a single album with its tracks"""
        try:
            # Create or get artist
            artist_data = {'name': cli_album['artist_name']}
            artist = self.create_or_get_artist(artist_data)
            
            # Check if album already exists (by name and artist)
            existing_album = self.webui_db.query(Album).filter(
                Album.name == cli_album['name'],
                Album.artist_id == artist.id
            ).first()
            
            if existing_album:
                logger.info(f"Skipping existing album: {cli_album['name']} by {cli_album['artist_name']}")
                self.stats['albums_skipped'] += 1
                return existing_album
            
            # Filter tracks for this album
            album_tracks = [t for t in cli_tracks if t['album_id'] == cli_album['id']]
            
            if not album_tracks:
                logger.warning(f"No tracks found for album: {cli_album['name']}")
                return None
            
            # Generate a temporary MusicBrainz ID if not present
            mb_id = cli_album.get('musicbrainz_id')
            if not mb_id:
                # Create a temporary ID based on artist and album name
                import hashlib
                hash_input = f"{artist.name}-{cli_album['name']}-{cli_album.get('year', '')}"
                hash_hex = hashlib.md5(hash_input.encode()).hexdigest()
                # Format as UUID-like string
                mb_id = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
            
            # Create album
            album = Album(
                artist_id=artist.id,
                name=cli_album['name'],
                release_year=cli_album.get('year'),
                musicbrainz_id=mb_id,
                total_tracks=len(album_tracks),
                album_bonus=0.33,  # Use new bonus system
                is_rated=True,  # Mark as completed since CLI albums have ratings
                rated_at=datetime.now(timezone.utc)
            )
            
            self.webui_db.add(album)
            self.webui_db.flush()  # Get album ID
            
            # Create tracks with converted ratings
            converted_ratings = []
            for i, cli_track in enumerate(sorted(album_tracks, key=lambda x: x['id'])):
                # Convert rating
                webui_rating = self.convert_track_rating(cli_track['track_score'])
                converted_ratings.append(webui_rating)
                
                track = Track(
                    album_id=album.id,
                    track_number=i + 1,  # Sequential numbering
                    name=cli_track['name'],
                    track_rating=webui_rating,
                    duration_ms=None,  # CLI doesn't have duration
                    musicbrainz_id=None  # CLI doesn't have MusicBrainz IDs
                )
                self.webui_db.add(track)
                self.stats['tracks_processed'] += 1
            
            # Calculate new album score using WebUI formula
            if converted_ratings:
                new_score = RatingCalculator.calculate_album_score(converted_ratings, 0.33)
                album.rating_score = new_score
                
                logger.info(f"Migrated: '{album.name}' by {artist.name}")
                logger.info(f"  CLI score: {cli_album['rating']}")
                logger.info(f"  New score: {new_score}")
                logger.info(f"  Tracks: {len(converted_ratings)}")
                logger.info(f"  Rating distribution: {self._get_rating_distribution(converted_ratings)}")
            
            self.stats['albums_processed'] += 1
            self.stats['albums_with_ratings'] += 1
            
            return album
            
        except Exception as e:
            logger.error(f"Error migrating album '{cli_album['name']}': {e}")
            self.webui_db.rollback()  # Rollback this transaction
            return None
    
    def _get_rating_distribution(self, ratings: List[float]) -> str:
        """Get a summary of rating distribution"""
        counts = {0.0: 0, 0.33: 0, 0.67: 0, 1.0: 0}
        for rating in ratings:
            counts[rating] = counts.get(rating, 0) + 1
        
        return f"Skip:{counts[0.0]}, Filler:{counts[0.33]}, Good:{counts[0.67]}, Standout:{counts[1.0]}"
    
    def migrate(self) -> bool:
        """Execute the full migration"""
        try:
            logger.info("Starting CLI to WebUI migration...")
            
            # Get CLI data
            _, cli_albums, cli_tracks = self.get_cli_data()
            
            if not cli_albums:
                logger.warning("No rated albums found in CLI database")
                return False
            
            # Ensure user settings exist with new bonus
            settings = self.webui_db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                settings = UserSettings(user_id=1, album_bonus=0.33)
                self.webui_db.add(settings)
            else:
                settings.album_bonus = 0.33
            
            # Process each album
            for cli_album in cli_albums:
                self.migrate_album(cli_album, cli_tracks)
            
            # Commit all changes
            self.webui_db.commit()
            logger.info("Migration committed successfully")
            
            # Print summary
            self.print_summary()
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.webui_db.rollback()
            return False
        
        finally:
            self.webui_db.close()
    
    def print_summary(self):
        """Print migration summary"""
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        print(f"Artists processed: {self.stats['artists_processed']}")
        print(f"Albums processed: {self.stats['albums_processed']}")
        print(f"Albums with ratings: {self.stats['albums_with_ratings']}")
        print(f"Albums skipped (duplicates): {self.stats['albums_skipped']}")
        print(f"Tracks processed: {self.stats['tracks_processed']}")
        print()
        print("Rating Conversions:")
        print(f"  Skip (0.0→0.0): {self.stats['conversion_counts'][0.0]} tracks")
        print(f"  Filler (0.5→0.33): {self.stats['conversion_counts'][0.5]} tracks")
        print(f"  Good (0.75→0.67): {self.stats['conversion_counts'][0.75]} tracks")
        print(f"  Standout (1.0→1.0): {self.stats['conversion_counts'][1.0]} tracks")
        print("="*50)


def main():
    """Main function"""
    if len(sys.argv) != 2:
        print("Usage: python migrate_cli_to_webui.py <path_to_cli_database>")
        print("Example: python migrate_cli_to_webui.py ~/music_rankings.db")
        sys.exit(1)
    
    cli_db_path = sys.argv[1]
    
    print("CLI to WebUI Migration Tool")
    print("="*40)
    print(f"CLI Database: {cli_db_path}")
    print(f"WebUI Database: tracklist.db")
    print()
    print("This will:")
    print("- Import all rated albums from CLI to WebUI")
    print("- Convert ratings: 0.0→0.0, 0.5→0.33, 0.75→0.67, 1.0→1.0")
    print("- Recalculate album scores with new formula")
    print("- Skip duplicate albums")
    print()
    
    # Confirm with user
    response = input("Do you want to proceed? (y/N): ").strip().lower()
    if response != 'y':
        print("Migration cancelled.")
        return
    
    # Execute migration
    migrator = CLIToWebUIMigrator(cli_db_path)
    success = migrator.migrate()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("You can now view your imported albums in the WebUI.")
    else:
        print("\n❌ Migration failed. Check the logs above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()