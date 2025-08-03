#!/usr/bin/env python3
"""
Script to recalculate album scores with new bonus value (0.33)
Updates all existing rated albums to use the new bonus calculation.
"""

import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent / "app"))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Album, Track, UserSettings
from app.rating_service import RatingCalculator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def recalculate_album_scores():
    """Recalculate scores for all rated albums with new bonus (0.33)"""
    db = SessionLocal()
    try:
        # Get all rated albums
        rated_albums = db.query(Album).filter(Album.is_rated == True).all()
        
        if not rated_albums:
            logger.info("No rated albums found to recalculate")
            return
        
        logger.info(f"Found {len(rated_albums)} rated albums to recalculate")
        
        # Update user settings to new bonus if it exists
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if settings and settings.album_bonus != 0.33:
            logger.info(f"Updating user settings album bonus from {settings.album_bonus} to 0.33")
            settings.album_bonus = 0.33
        
        updated_count = 0
        
        for album in rated_albums:
            # Get all tracks for this album
            tracks = db.query(Track).filter(Track.album_id == album.id).all()
            
            # Get track ratings
            track_ratings = [track.track_rating for track in tracks if track.track_rating is not None]
            
            if not track_ratings:
                logger.warning(f"Album {album.id} ({album.name}) has no track ratings, skipping")
                continue
            
            # Calculate new score with 0.33 bonus
            old_score = album.rating_score
            old_bonus = album.album_bonus
            
            # Update album bonus
            album.album_bonus = 0.33
            
            # Calculate new score
            new_score = RatingCalculator.calculate_album_score(track_ratings, 0.33)
            album.rating_score = new_score
            
            logger.info(f"Album '{album.name}' by {album.artist.name}:")
            logger.info(f"  Old: {old_score}/100 (bonus: {old_bonus})")
            logger.info(f"  New: {new_score}/100 (bonus: 0.33)")
            logger.info(f"  Change: {new_score - old_score:+d} points")
            
            updated_count += 1
        
        # Commit all changes
        db.commit()
        logger.info(f"Successfully recalculated scores for {updated_count} albums")
        
    except Exception as e:
        logger.error(f"Error recalculating scores: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """Main function"""
    print("Tracklist Album Score Recalculation")
    print("===================================")
    print("This will update all rated albums to use the new bonus value (0.33)")
    print()
    
    try:
        recalculate_album_scores()
        print("\n✅ Score recalculation completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during recalculation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()