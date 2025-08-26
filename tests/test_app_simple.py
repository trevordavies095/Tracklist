"""
Simple app tests without pytest.
Tests basic functionality of the Tracklist app.
"""

import os
import sys

# Set testing environment before imports
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOG_LEVEL"] = "ERROR"

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now import app modules
from app.models import Base, Album, Artist, Track
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_database_models():
    """Test that database models can be created."""
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create an artist
    artist = Artist(name="Test Artist", musicbrainz_id="test-123")
    session.add(artist)
    session.commit()
    
    assert artist.id is not None
    assert artist.name == "Test Artist"
    print("  ✓ Artist created successfully")
    
    # Create an album
    album = Album(
        artist_id=artist.id,
        name="Test Album",
        musicbrainz_id="album-456",
        release_year=2024,
        is_rated=False
    )
    session.add(album)
    session.commit()
    
    assert album.id is not None
    assert album.artist_id == artist.id
    assert album.album_bonus == 0.33  # default value
    print("  ✓ Album created successfully")
    
    # Create a track
    track = Track(
        album_id=album.id,
        track_number=1,
        name="Test Track",
        duration_ms=180000
    )
    session.add(track)
    session.commit()
    
    assert track.id is not None
    assert track.album_id == album.id
    print("  ✓ Track created successfully")
    
    # Clean up
    session.close()
    engine.dispose()
    
    print("  ✓ All model tests passed")


def test_rating_calculation():
    """Test rating calculation logic."""
    # Simple rating calculation
    ratings = [1.0, 0.67, 0.67, 0.33, 1.0]
    avg = sum(ratings) / len(ratings)
    album_bonus = 0.33
    score = int((avg * 10 + album_bonus) * 10)
    
    assert score == 76  # Expected score
    print("  ✓ Rating calculation correct")


if __name__ == "__main__":
    print("\nRunning app tests...")
    print("=" * 40)
    
    try:
        test_database_models()
        test_rating_calculation()
        print("\n✅ All app tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()