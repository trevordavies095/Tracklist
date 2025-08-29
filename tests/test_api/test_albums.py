"""
Tests for album API endpoints.
Tests CRUD operations, filtering, and album management.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.exceptions import ServiceNotFoundError


class TestAlbumCRUD:
    """Test album CRUD operations."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_album(self, client: TestClient):
        """Test creating a new album via API."""
        # Mock the rating service
        with patch("app.routers.albums.get_rating_service") as mock_rating_service:
            mock_service = Mock()
            mock_service.create_album_for_rating = AsyncMock(
                return_value={
                    "id": 1,
                    "musicbrainz_id": "test-mbid",
                    "title": "Test Album",
                    "artist": {"name": "Test Artist"},
                    "is_rated": False,
                    "total_tracks": 10,
                }
            )
            mock_rating_service.return_value = mock_service

            response = client.post(
                "/api/v1/albums", data={"musicbrainz_id": "test-mbid"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["musicbrainz_id"] == "test-mbid"
            assert data["title"] == "Test Album"
            assert data["is_rated"] is False

    @pytest.mark.integration
    def test_get_album_by_id(self, client: TestClient, created_album, db_session):
        """Test fetching a specific album."""
        # The endpoint uses RatingService which needs the album in the same session
        db_session.commit()  # Ensure album is committed to the test DB

        # Mock the rating service to return our test album
        with patch("app.routers.albums.get_rating_service") as mock_rating_service:
            mock_service = Mock()
            mock_service.get_album_rating.return_value = {
                "id": created_album.id,
                "title": created_album.name,
                "artist": {
                    "id": created_album.artist.id,
                    "name": created_album.artist.name,
                },
                "is_rated": created_album.is_rated,
                "rating_score": created_album.rating_score,
                "total_tracks": created_album.total_tracks,
            }
            mock_rating_service.return_value = mock_service

            response = client.get(f"/api/v1/albums/{created_album.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == created_album.id
            assert "title" in data
            assert "artist" in data

    @pytest.mark.integration
    def test_get_nonexistent_album(self, client: TestClient):
        """Test fetching an album that doesn't exist."""
        response = client.get("/api/v1/albums/99999")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_update_album_notes(self, client: TestClient, created_album):
        """Test updating album notes."""
        with patch("app.routers.albums.get_rating_service") as mock_rating_service:
            mock_service = Mock()
            mock_service.update_album_notes.return_value = {
                "success": True,
                "album_id": created_album.id,
                "notes": "This is a great album!",
            }
            mock_rating_service.return_value = mock_service

            update_data = {"notes": "This is a great album!"}
            response = client.put(
                f"/api/v1/albums/{created_album.id}/notes", json=update_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["notes"] == "This is a great album!"

    @pytest.mark.integration
    def test_delete_album(self, client: TestClient, created_album):
        """Test deleting an album."""
        album_id = created_album.id

        with patch("app.routers.albums.get_rating_service") as mock_rating_service:
            mock_service = Mock()
            mock_service.delete_album.return_value = {
                "success": True,
                "deleted_tracks": 10,
                "message": "Album deleted",
            }
            # For the second call (verification)
            mock_service.get_album_rating.side_effect = ServiceNotFoundError(
                "Album", album_id
            )
            mock_rating_service.return_value = mock_service

            # Delete the album
            response = client.delete(f"/api/v1/albums/{album_id}")
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "deleted_tracks" in data

            # Verify it's deleted
            response = client.get(f"/api/v1/albums/{album_id}")
            assert response.status_code == 404


class TestAlbumListing:
    """Test album listing and filtering."""

    @pytest.mark.integration
    def test_list_albums(self, client: TestClient, db_session):
        """Test listing all albums."""
        # Create multiple albums
        from app.models import Album, Artist

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
                total_tracks=10,
                album_bonus=0.33,
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
        response = client.get("/api/v1/albums/rated")
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
        sort_options = ["created_desc", "created_asc", "rating_desc", "artist_asc"]

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
            f"/api/v1/tracks/{created_track.id}/rating", json={"rating": rating}
        )

        assert response.status_code == 200
        data = response.json()
        assert "completion_percentage" in data
        assert "projected_score" in data

    @pytest.mark.integration
    def test_rate_track_invalid_value(self, client: TestClient, created_track):
        """Test that invalid rating values are rejected."""
        response = client.put(
            f"/api/v1/tracks/{created_track.id}/rating", json={"rating": 0.5}
        )

        assert response.status_code == 400  # Bad request for invalid rating

    @pytest.mark.integration
    def test_rate_nonexistent_track(self, client: TestClient):
        """Test rating a track that doesn't exist."""
        response = client.put("/api/v1/tracks/99999/rating", json={"rating": 0.67})

        assert response.status_code == 404


class TestAlbumSubmission:
    """Test album rating submission."""

    @pytest.mark.integration
    def test_submit_fully_rated_album(self, client: TestClient, album_with_tracks):
        """Test submitting a fully rated album."""
        # Rate all tracks first
        for track in album_with_tracks.tracks:
            client.put(f"/api/v1/tracks/{track.id}/rating", json={"rating": 0.67})

        # Submit the album
        response = client.post(f"/api/v1/albums/{album_with_tracks.id}/submit")

        assert response.status_code == 200
        data = response.json()
        assert data["is_rated"] is True
        assert data["rating_score"] is not None

    @pytest.mark.integration
    def test_submit_incomplete_album(self, client: TestClient, album_with_tracks):
        """Test that submitting an incomplete album fails."""
        # Rate only some tracks
        for track in album_with_tracks.tracks[:3]:
            client.put(f"/api/v1/tracks/{track.id}/rating", json={"rating": 0.67})

        # Try to submit
        response = client.post(f"/api/v1/albums/{album_with_tracks.id}/submit")

        assert response.status_code == 400  # Bad request
        assert "incomplete" in response.json()["detail"].lower()

    @pytest.mark.integration
    def test_get_album_progress(self, client: TestClient, album_with_tracks):
        """Test getting album rating progress."""
        response = client.get(f"/api/v1/albums/{album_with_tracks.id}/progress")

        assert response.status_code == 200
        data = response.json()
        assert "rated_tracks" in data
        assert "total_tracks" in data
        assert "completion_percentage" in data
        assert data["total_tracks"] == 10


class TestAlbumManagement:
    """Test album management endpoints."""

    @pytest.mark.integration
    def test_revert_album_to_in_progress(self, client: TestClient, rated_album):
        """Test reverting a completed album."""
        response = client.put(f"/api/v1/albums/{rated_album.id}/revert")

        assert response.status_code == 200
        data = response.json()
        assert data["is_rated"] is False
        assert data["rating_score"] is None

    @pytest.mark.integration
    def test_compare_albums(self, client: TestClient, rated_album, created_album):
        """Test album comparison endpoint."""
        response = client.get(
            f"/api/v1/albums/compare?album_ids={rated_album.id},{created_album.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "albums" in data
        assert len(data["albums"]) == 2

    @pytest.mark.integration
    def test_get_artwork_url(self, client: TestClient, created_album):
        """Test getting album artwork URL."""
        response = client.get(f"/api/v1/albums/{created_album.id}/artwork-url")

        assert response.status_code == 200
        data = response.json()
        assert "artwork_url" in data

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_update_cover_art(self, client: TestClient):
        """Test updating missing cover art."""
        with patch("app.routers.albums.get_rating_service") as mock_rating_service:
            mock_service = Mock()
            mock_service.update_missing_cover_art = AsyncMock(
                return_value={"success": True, "updated": 5, "failed": 0}
            )
            mock_rating_service.return_value = mock_service

            response = client.post("/api/v1/albums/update-cover-art")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "updated" in data


class TestSystemEndpoints:
    """Test system management endpoints."""

    @pytest.mark.integration
    def test_get_system_info(self, client: TestClient):
        """Test getting system information."""
        response = client.get("/api/v1/system/info")

        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert "cache" in data

    @pytest.mark.integration
    def test_get_cache_cleanup_status(self, client: TestClient):
        """Test getting cache cleanup status."""
        response = client.get("/api/v1/system/cache-cleanup")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data

    @pytest.mark.integration
    def test_get_scheduled_tasks(self, client: TestClient):
        """Test getting scheduled tasks status."""
        response = client.get("/api/v1/system/scheduled-tasks")

        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data

    @pytest.mark.integration
    def test_get_memory_cache_stats(self, client: TestClient):
        """Test getting memory cache statistics."""
        response = client.get("/api/v1/system/memory-cache")

        assert response.status_code == 200
        data = response.json()
        assert "total_size" in data
        assert "total_entries" in data
