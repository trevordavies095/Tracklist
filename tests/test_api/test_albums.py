"""
Tests for album API endpoints.
Tests CRUD operations, filtering, and album management.
"""

import pytest
from fastapi.testclient import TestClient


class TestAlbumCRUD:
    """Test album CRUD operations."""
    
    @pytest.mark.integration
    def test_create_album(self, client: TestClient, sample_album_data):
        """Test creating a new album via API."""
        response = client.post("/api/v1/albums", json=sample_album_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_album_data["name"]
        assert data["artist_name"] == sample_album_data["artist_name"]
        assert data["id"] is not None
        assert data["is_rated"] is False
    
    @pytest.mark.integration
    def test_get_album_by_id(self, client: TestClient, created_album):
        """Test fetching a specific album."""
        response = client.get(f"/api/v1/albums/{created_album.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == created_album.id
        assert data["name"] == created_album.name
    
    @pytest.mark.integration
    def test_get_nonexistent_album(self, client: TestClient):
        """Test fetching an album that doesn't exist."""
        response = client.get("/api/v1/albums/99999")
        assert response.status_code == 404
    
    @pytest.mark.integration
    def test_update_album(self, client: TestClient, created_album):
        """Test updating album information."""
        update_data = {
            "name": "Updated Album Name",
            "genre": "Jazz",
        }
        response = client.put(f"/api/v1/albums/{created_album.id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Album Name"
        assert data["genre"] == "Jazz"
    
    @pytest.mark.integration
    def test_delete_album(self, client: TestClient, created_album):
        """Test deleting an album."""
        album_id = created_album.id
        
        # Delete the album
        response = client.delete(f"/api/v1/albums/{album_id}")
        assert response.status_code == 204
        
        # Verify it's deleted
        response = client.get(f"/api/v1/albums/{album_id}")
        assert response.status_code == 404


class TestAlbumListing:
    """Test album listing and filtering."""
    
    @pytest.mark.integration
    def test_list_albums(self, client: TestClient, db_session):
        """Test listing all albums."""
        # Create multiple albums
        from app.models import Artist, Album
        
        artist = Artist(name="Test Artist", musicbrainz_id="test-mb-1")
        db_session.add(artist)
        db_session.commit()
        
        for i in range(5):
            album = Album(
                artist_id=artist.id,
                name=f"Album {i}",
                musicbrainz_id=f"mb-{i}",
                release_year=2020 + i,
                is_rated=(i % 2 == 0),
            )
            db_session.add(album)
        db_session.commit()
        
        # Get all albums
        response = client.get("/api/v1/albums")
        assert response.status_code == 200
        
        data = response.json()
        assert "albums" in data
        assert len(data["albums"]) >= 5
    
    @pytest.mark.integration
    def test_list_albums_with_pagination(self, client: TestClient):
        """Test album listing with limit and offset."""
        response = client.get("/api/v1/albums?limit=2&offset=0")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["albums"]) <= 2
    
    @pytest.mark.integration
    def test_filter_rated_albums(self, client: TestClient, rated_album):
        """Test filtering for rated albums only."""
        response = client.get("/api/v1/albums?rated=true")
        assert response.status_code == 200
        
        data = response.json()
        if data["albums"]:
            assert all(album["is_rated"] for album in data["albums"])
    
    @pytest.mark.integration
    def test_filter_unrated_albums(self, client: TestClient, created_album):
        """Test filtering for unrated albums only."""
        response = client.get("/api/v1/albums?rated=false")
        assert response.status_code == 200
        
        data = response.json()
        if data["albums"]:
            assert not any(album["is_rated"] for album in data["albums"])
    
    @pytest.mark.integration
    def test_sort_albums(self, client: TestClient):
        """Test sorting albums by different criteria."""
        sort_options = ["created_desc", "created_asc", "rating_desc", "name_asc"]
        
        for sort in sort_options:
            response = client.get(f"/api/v1/albums?sort={sort}")
            assert response.status_code == 200


class TestTrackRating:
    """Test track rating endpoints."""
    
    @pytest.mark.integration
    @pytest.mark.parametrize("rating", [0.0, 0.33, 0.67, 1.0])
    def test_rate_track_valid_values(self, client: TestClient, created_track, rating):
        """Test rating a track with all valid values."""
        response = client.put(
            f"/api/v1/tracks/{created_track.id}/rate",
            json={"rating": rating}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["track_rating"] == rating
    
    @pytest.mark.integration
    def test_rate_track_invalid_value(self, client: TestClient, created_track):
        """Test that invalid rating values are rejected."""
        response = client.put(
            f"/api/v1/tracks/{created_track.id}/rate",
            json={"rating": 0.5}
        )
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.integration
    def test_rate_nonexistent_track(self, client: TestClient):
        """Test rating a track that doesn't exist."""
        response = client.put(
            "/api/v1/tracks/99999/rate",
            json={"rating": 0.67}
        )
        
        assert response.status_code == 404


class TestAlbumSubmission:
    """Test album rating submission."""
    
    @pytest.mark.integration
    def test_submit_fully_rated_album(self, client: TestClient, album_with_tracks):
        """Test submitting a fully rated album."""
        # Rate all tracks first
        for track in album_with_tracks.tracks:
            client.put(
                f"/api/v1/tracks/{track.id}/rate",
                json={"rating": 0.67}
            )
        
        # Submit the album
        response = client.post(f"/api/v1/albums/{album_with_tracks.id}/submit")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["is_rated"] is True
        assert data["rating_score"] is not None
    
    @pytest.mark.integration
    def test_submit_incomplete_album(self, client: TestClient, album_with_tracks):
        """Test that submitting an incomplete album fails."""
        # Rate only some tracks
        for track in album_with_tracks.tracks[:3]:
            client.put(
                f"/api/v1/tracks/{track.id}/rate",
                json={"rating": 0.67}
            )
        
        # Try to submit
        response = client.post(f"/api/v1/albums/{album_with_tracks.id}/submit")
        
        assert response.status_code == 400  # Bad request
        assert "incomplete" in response.json()["detail"].lower()