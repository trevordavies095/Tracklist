"""
Unit tests for ArtworkCacheService
"""

import pytest
import tempfile
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
from io import BytesIO
from PIL import Image
import httpx

from app.services.artwork_cache_service import (
    ArtworkCacheService,
    ArtworkCacheError,
    get_artwork_cache_service
)
from app.services.artwork_cache_utils import ArtworkCacheFileSystem
from app.models import Album, ArtworkCache


class TestArtworkCacheService:
    """Test the ArtworkCacheService class"""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_cache_fs(self, temp_cache_dir):
        """Create a mock cache filesystem"""
        cache_fs = ArtworkCacheFileSystem(base_path=temp_cache_dir)
        return cache_fs
    
    @pytest.fixture
    def mock_album(self):
        """Create a mock album"""
        album = Mock(spec=Album)
        album.id = 1
        album.musicbrainz_id = "test-mb-123"
        album.cover_art_url = "https://example.com/artwork.jpg"
        album.artwork_cached = False
        album.artwork_cache_date = None
        return album
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session"""
        session = Mock()
        session.query = Mock()
        session.add = Mock()
        session.commit = Mock()
        session.rollback = Mock()
        return session
    
    @pytest.fixture
    def service(self, mock_cache_fs):
        """Create a service instance with mock filesystem"""
        with patch('app.services.artwork_cache_service.get_cover_art_service'):
            service = ArtworkCacheService(cache_fs=mock_cache_fs)
            # Mock the HTTP client
            service.client = AsyncMock()
            return service
    
    @pytest.fixture
    def sample_image_data(self):
        """Generate sample image data"""
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        return buffer.getvalue()
    
    def test_generate_cache_key(self, service, mock_album):
        """Test cache key generation"""
        key1 = service.generate_cache_key(mock_album)
        key2 = service.generate_cache_key(mock_album)
        
        # Should be consistent
        assert key1 == key2
        
        # Should be 16 characters
        assert len(key1) == 16
        
        # Should be hexadecimal
        assert all(c in '0123456789abcdef' for c in key1)
        
        # Different album should generate different key
        mock_album2 = Mock(spec=Album)
        mock_album2.id = 2
        mock_album2.musicbrainz_id = "different-mb-456"
        key3 = service.generate_cache_key(mock_album2)
        
        assert key1 != key3
    
    @pytest.mark.asyncio
    async def test_download_image_success(self, service, sample_image_data):
        """Test successful image download"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(len(sample_image_data))}
        mock_response.content = sample_image_data
        
        service.client.get = AsyncMock(return_value=mock_response)
        
        result = await service._download_image("https://example.com/image.jpg")
        
        assert result == sample_image_data
        service.client.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_image_http_error(self, service):
        """Test image download with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 404
        
        service.client.get = AsyncMock(return_value=mock_response)
        
        result = await service._download_image("https://example.com/404.jpg")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_download_image_too_large(self, service):
        """Test image download rejection for too large files"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": str(20 * 1024 * 1024)}  # 20MB
        
        service.client.get = AsyncMock(return_value=mock_response)
        
        result = await service._download_image("https://example.com/huge.jpg")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_download_image_timeout(self, service):
        """Test image download timeout handling"""
        service.client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        
        result = await service._download_image("https://example.com/slow.jpg")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_save_original(self, service, sample_image_data, temp_cache_dir):
        """Test saving original image"""
        cache_key = "test123"
        
        result = await service._save_original(cache_key, sample_image_data)
        
        assert result is not None
        assert result.exists()
        assert result.parent.name == "original"
        
        # Verify file content
        with open(result, 'rb') as f:
            saved_data = f.read()
        assert len(saved_data) == len(sample_image_data)
    
    @pytest.mark.asyncio
    async def test_generate_all_variants(self, service, sample_image_data, temp_cache_dir):
        """Test generating all size variants"""
        cache_key = "test123"
        
        variants = await service._generate_all_variants(cache_key, sample_image_data)
        
        # Should create all variants
        assert "original" in variants
        assert "large" in variants
        assert "medium" in variants
        assert "small" in variants
        assert "thumbnail" in variants
        
        # Verify files exist
        for variant in ["large", "medium", "small", "thumbnail"]:
            path = Path(temp_cache_dir) / variant / f"{cache_key}.jpg"
            assert path.exists()
            
            # Verify image dimensions
            img = Image.open(path)
            expected_size = service.cache_fs.SIZE_SPECS[variant]
            assert img.size[0] <= expected_size[0]
            assert img.size[1] <= expected_size[1]
    
    @pytest.mark.asyncio
    async def test_generate_variant_from_original(self, service, sample_image_data, temp_cache_dir):
        """Test generating specific variant from cached original"""
        cache_key = "test123"
        
        # Save original first
        await service._save_original(cache_key, sample_image_data)
        
        # Generate medium variant
        result = await service._generate_variant_from_original(cache_key, "medium")
        
        assert result is True
        
        # Verify file exists
        path = Path(temp_cache_dir) / "medium" / f"{cache_key}.jpg"
        assert path.exists()
    
    @pytest.mark.asyncio
    async def test_get_or_cache_artwork_cache_hit(self, service, mock_album, mock_db_session):
        """Test getting artwork when already cached"""
        cache_key = service.generate_cache_key(mock_album)
        
        # Mock cache exists
        service.cache_fs.exists = Mock(return_value=True)
        service.cache_fs.get_web_path = Mock(return_value="/static/cache/test.jpg")
        service._update_access_tracking = AsyncMock()
        
        result = await service.get_or_cache_artwork(mock_album, "medium", mock_db_session)
        
        assert result == "/static/cache/test.jpg"
        service.cache_fs.exists.assert_called_with(cache_key, "medium")
        service._update_access_tracking.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_or_cache_artwork_cache_miss(self, service, mock_album, mock_db_session, sample_image_data):
        """Test getting artwork when not cached"""
        cache_key = service.generate_cache_key(mock_album)
        
        # Mock cache miss
        service.cache_fs.exists = Mock(return_value=False)
        service.cache_fs.get_web_path = Mock(return_value="/static/cache/test.jpg")
        
        # Mock successful caching
        service.cache_artwork = AsyncMock(return_value=True)
        
        result = await service.get_or_cache_artwork(mock_album, "medium", mock_db_session)
        
        assert result == "/static/cache/test.jpg"
        service.cache_artwork.assert_called_once_with(mock_album, mock_album.cover_art_url, mock_db_session)
    
    @pytest.mark.asyncio
    async def test_cache_artwork_success(self, service, mock_album, mock_db_session, sample_image_data):
        """Test successful artwork caching"""
        # Mock download
        service._download_image = AsyncMock(return_value=sample_image_data)
        service._save_original = AsyncMock(return_value=Path("/tmp/test.jpg"))
        service._generate_all_variants = AsyncMock(return_value=["original", "medium"])
        service._update_cache_records = AsyncMock()
        
        result = await service.cache_artwork(mock_album, "https://example.com/art.jpg", mock_db_session)
        
        assert result is True
        assert mock_album.artwork_cached is True
        assert mock_album.artwork_cache_date is not None
        mock_db_session.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_cache_artwork_download_failure(self, service, mock_album, mock_db_session):
        """Test artwork caching with download failure"""
        # Mock download failure
        service._download_image = AsyncMock(return_value=None)
        
        result = await service.cache_artwork(mock_album, "https://example.com/art.jpg", mock_db_session)
        
        assert result is False
        # Download failure returns False but doesn't rollback (nothing to rollback)
    
    @pytest.mark.asyncio
    async def test_update_cache_records(self, service, mock_album, mock_db_session):
        """Test updating database cache records"""
        cache_key = "test123"
        variants = ["original", "medium"]
        
        # Mock query results
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query
        
        # Mock file info
        service.cache_fs.get_file_info = Mock(return_value={
            "path": "/test/path",
            "size_bytes": 1024
        })
        
        await service._update_cache_records(
            mock_album, cache_key, "https://example.com/art.jpg", variants, mock_db_session
        )
        
        # Should add new records
        assert mock_db_session.add.call_count == 2
        mock_db_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_access_tracking(self, service, mock_db_session):
        """Test updating access tracking"""
        # Mock existing cache record
        mock_record = Mock(spec=ArtworkCache)
        mock_record.last_accessed_at = None
        mock_record.access_count = 5
        
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = mock_record
        mock_db_session.query.return_value = mock_query
        
        await service._update_access_tracking(1, "medium", mock_db_session)
        
        assert mock_record.access_count == 6
        assert mock_record.last_accessed_at is not None
        mock_db_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_stale_cache(self, service, mock_db_session):
        """Test cleaning up stale cache entries"""
        # Mock stale records
        mock_record = Mock(spec=ArtworkCache)
        mock_record.cache_key = "test123_medium"
        mock_record.size_variant = "medium"
        mock_record.last_accessed_at = datetime.now(timezone.utc) - timedelta(days=40)
        
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [mock_record]
        mock_db_session.query.return_value = mock_query
        
        # Mock file deletion
        service.cache_fs.delete_cache = Mock(return_value=1)
        
        result = await service.cleanup_stale_cache(30, mock_db_session)
        
        assert result == 1
        service.cache_fs.delete_cache.assert_called_with("test123", "medium")
        mock_db_session.delete.assert_called_with(mock_record)
        mock_db_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_clear_album_cache(self, service, mock_album, mock_db_session):
        """Test clearing cache for specific album"""
        cache_key = service.generate_cache_key(mock_album)
        
        # Mock file deletion
        service.cache_fs.delete_cache = Mock(return_value=3)
        
        # Mock query
        mock_query = Mock()
        mock_query.filter_by.return_value.delete.return_value = 3
        mock_db_session.query.return_value = mock_query
        
        result = await service.clear_album_cache(mock_album, mock_db_session)
        
        assert result is True
        assert mock_album.artwork_cached is False
        assert mock_album.artwork_cache_date is None
        service.cache_fs.delete_cache.assert_called_with(cache_key)
        mock_db_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_cache_statistics(self, service, mock_db_session):
        """Test getting cache statistics"""
        # Mock filesystem stats
        service.cache_fs.get_cache_statistics = Mock(return_value={
            "total_files": 100,
            "total_size_mb": 50.5
        })
        
        # Mock database queries
        mock_query = Mock()
        mock_query.count.return_value = 100
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.limit.return_value.all.return_value = []
        mock_db_session.query.return_value = mock_query
        
        stats = await service.get_cache_statistics(mock_db_session)
        
        assert "filesystem" in stats
        assert "database" in stats
        assert stats["filesystem"]["total_files"] == 100
    
    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test closing the service"""
        service.client = AsyncMock()
        service.client.aclose = AsyncMock()
        
        await service.close()
        
        service.client.aclose.assert_called_once()


class TestErrorHandling:
    """Test error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_cache_artwork_with_exception(self):
        """Test cache_artwork handles exceptions gracefully"""
        service = ArtworkCacheService()
        service.client = AsyncMock()
        
        mock_album = Mock(spec=Album)
        mock_album.id = 1
        mock_db = Mock()
        
        # Mock exception during download
        service._download_image = AsyncMock(side_effect=Exception("Network error"))
        
        result = await service.cache_artwork(mock_album, "https://example.com/art.jpg", mock_db)
        
        assert result is False
        mock_db.rollback.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_or_cache_with_exception(self):
        """Test get_or_cache_artwork handles exceptions"""
        service = ArtworkCacheService()
        
        mock_album = Mock(spec=Album)
        mock_album.id = 1
        mock_album.cover_art_url = "https://example.com/fallback.jpg"
        mock_db = Mock()
        
        # Mock exception
        service.generate_cache_key = Mock(side_effect=Exception("Key error"))
        
        result = await service.get_or_cache_artwork(mock_album, "medium", mock_db)
        
        # Should fallback to external URL
        assert result == mock_album.cover_art_url


class TestGlobalInstance:
    """Test global instance management"""
    
    def test_get_artwork_cache_service_singleton(self):
        """Test that get_artwork_cache_service returns singleton"""
        service1 = get_artwork_cache_service()
        service2 = get_artwork_cache_service()
        
        assert service1 is service2