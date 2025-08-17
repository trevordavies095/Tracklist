"""
Tests for the export API endpoints
"""

import json
import csv
from io import StringIO
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from app.main import app
from app.database import get_db, SessionLocal
from app.models import Album, Artist, Track, UserSettings

client = TestClient(app)


def setup_test_data(db):
    """Create test data for export tests"""
    # Create test artist
    artist = Artist(
        id=1,
        name="Test Artist",
        musicbrainz_id="test-artist-mbid"
    )
    db.add(artist)
    
    # Create rated album
    rated_album = Album(
        id=1,
        artist_id=1,
        name="Rated Album",
        musicbrainz_id="rated-album-mbid",
        release_year=2020,
        genre="Rock",
        total_tracks=3,
        total_duration_ms=600000,
        is_rated=True,
        rating_score=85,
        album_bonus=0.33,
        rated_at=datetime.now(timezone.utc),
        notes="Great album",
        cover_art_url="https://example.com/cover1.jpg"
    )
    db.add(rated_album)
    
    # Create tracks for rated album
    for i in range(1, 4):
        track = Track(
            album_id=1,
            track_number=i,
            name=f"Track {i}",
            duration_ms=200000,
            track_rating=0.67 if i != 2 else 1.0  # Track 2 is a standout
        )
        db.add(track)
    
    # Create unrated album
    unrated_album = Album(
        id=2,
        artist_id=1,
        name="Unrated Album",
        musicbrainz_id="unrated-album-mbid",
        release_year=2021,
        total_tracks=2,
        is_rated=False
    )
    db.add(unrated_album)
    
    # Create tracks for unrated album (no ratings)
    for i in range(1, 3):
        track = Track(
            album_id=2,
            track_number=i,
            name=f"Unrated Track {i}",
            duration_ms=180000
        )
        db.add(track)
    
    db.commit()


def test_export_statistics():
    """Test getting export statistics"""
    db = SessionLocal()
    try:
        # Clean up any existing data
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        
        # Setup test data
        setup_test_data(db)
        
        # Get export statistics
        response = client.get("/api/v1/reports/export/stats")
        assert response.status_code == 200
        
        stats = response.json()
        assert stats["total_albums"] == 2
        assert stats["rated_albums"] == 1
        assert stats["unrated_albums"] == 1
        assert stats["total_tracks"] == 5
        assert stats["rated_tracks"] == 3
        
    finally:
        db.close()


def test_export_json_rated_only():
    """Test exporting rated albums only in JSON format"""
    db = SessionLocal()
    try:
        # Clean up and setup
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        setup_test_data(db)
        
        # Export JSON (rated only)
        response = client.get("/api/v1/reports/export?format=json&include_unrated=false")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert "attachment" in response.headers.get("content-disposition", "")
        
        # Parse JSON response
        export_data = json.loads(response.content)
        
        # Verify structure
        assert "export_date" in export_data
        assert "version" in export_data
        assert export_data["album_count"] == 1
        assert len(export_data["albums"]) == 1
        
        # Verify album data
        album = export_data["albums"][0]
        assert album["title"] == "Rated Album"
        assert album["artist"]["name"] == "Test Artist"
        assert album["is_rated"] == True
        assert album["rating_score"] == 85
        assert len(album["tracks"]) == 3
        
        # Verify track data
        track2 = next(t for t in album["tracks"] if t["track_number"] == 2)
        assert track2["rating"] == 1.0
        
        # Verify statistics
        assert "statistics" in export_data
        assert export_data["statistics"]["rated_albums"] == 1
        
    finally:
        db.close()


def test_export_json_include_unrated():
    """Test exporting all albums including unrated in JSON format"""
    db = SessionLocal()
    try:
        # Clean up and setup
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        setup_test_data(db)
        
        # Export JSON (include unrated)
        response = client.get("/api/v1/reports/export?format=json&include_unrated=true")
        assert response.status_code == 200
        
        # Parse JSON response
        export_data = json.loads(response.content)
        
        # Verify both albums are included
        assert export_data["album_count"] == 2
        assert len(export_data["albums"]) == 2
        
        # Find unrated album
        unrated = next(a for a in export_data["albums"] if a["title"] == "Unrated Album")
        assert unrated["is_rated"] == False
        assert unrated["rating_score"] is None
        assert len(unrated["tracks"]) == 2
        
    finally:
        db.close()


def test_export_csv_rated_only():
    """Test exporting rated albums only in CSV format"""
    db = SessionLocal()
    try:
        # Clean up and setup
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        setup_test_data(db)
        
        # Export CSV (rated only)
        response = client.get("/api/v1/reports/export?format=csv&include_unrated=false")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv"
        assert "attachment" in response.headers.get("content-disposition", "")
        
        # Parse CSV response
        csv_content = response.content.decode('utf-8')
        csv_reader = csv.DictReader(StringIO(csv_content))
        rows = list(csv_reader)
        
        # Should have 3 rows (one per track in the rated album)
        assert len(rows) == 3
        
        # Verify first row has album info
        first_row = rows[0]
        assert first_row['Album Title'] == 'Rated Album'
        assert first_row['Artist'] == 'Test Artist'
        assert first_row['Album Score'] == '85'
        assert first_row['Track Number'] == '1'
        assert first_row['Track Title'] == 'Track 1'
        assert first_row['Track Rating'] == '0.67'
        
        # Verify track 2 is standout
        track2_row = rows[1]
        assert track2_row['Track Number'] == '2'
        assert track2_row['Track Rating'] == '1.0'
        
    finally:
        db.close()


def test_export_csv_include_unrated():
    """Test exporting all albums including unrated in CSV format"""
    db = SessionLocal()
    try:
        # Clean up and setup
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        setup_test_data(db)
        
        # Export CSV (include unrated)
        response = client.get("/api/v1/reports/export?format=csv&include_unrated=true")
        assert response.status_code == 200
        
        # Parse CSV response
        csv_content = response.content.decode('utf-8')
        csv_reader = csv.DictReader(StringIO(csv_content))
        rows = list(csv_reader)
        
        # Should have 5 rows (3 from rated album + 2 from unrated)
        assert len(rows) == 5
        
        # Find unrated album rows
        unrated_rows = [r for r in rows if r['Album Title'] == 'Unrated Album']
        assert len(unrated_rows) == 2
        assert unrated_rows[0]['Album Score'] == ''  # No score for unrated
        assert unrated_rows[0]['Track Rating'] == ''  # No track ratings
        
    finally:
        db.close()


def test_export_empty_collection():
    """Test exporting when there are no albums"""
    db = SessionLocal()
    try:
        # Clean up all data
        db.query(Track).delete()
        db.query(Album).delete()
        db.query(Artist).delete()
        db.commit()
        
        # Try to export
        response = client.get("/api/v1/reports/export?format=json")
        assert response.status_code == 404
        
        error = response.json()
        assert "No data to export" in error["detail"]["message"]
        
    finally:
        db.close()


def test_export_invalid_format():
    """Test exporting with invalid format parameter"""
    response = client.get("/api/v1/reports/export?format=xml")
    assert response.status_code == 422  # Validation error