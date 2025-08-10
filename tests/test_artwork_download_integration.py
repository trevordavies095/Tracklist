"""
Integration tests for artwork downloading with rate limiting and retry logic
"""

import pytest
import asyncio
import httpx
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from app.services.artwork_downloader import (
    ArtworkDownloader,
    BatchArtworkDownloader,
    ArtworkDownloadError
)
from app.services.rate_limiter import RateLimiter, DomainRateLimiter
from app.services.artwork_cache_service import ArtworkCacheService
from app.models import Album, ArtworkCache


class TestRateLimiter:
    """Test the rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting"""
        limiter = RateLimiter(calls_per_second=2.0)  # 2 requests per second
        
        start = asyncio.get_event_loop().time()
        
        # First request should be immediate
        wait1 = await limiter.acquire()
        assert wait1 < 0.1
        
        # Second request should be immediate (within burst)
        wait2 = await limiter.acquire()
        assert wait2 < 0.1
        
        # Third request should wait
        wait3 = await limiter.acquire()
        
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed >= 0.4  # Should wait at least 0.5 seconds
    
    @pytest.mark.asyncio
    async def test_domain_rate_limiter(self):
        """Test domain-specific rate limiting"""
        limiter = DomainRateLimiter()
        
        # Test Cover Art Archive domain
        start = asyncio.get_event_loop().time()
        
        wait1 = await limiter.acquire("https://coverartarchive.org/release/123")
        assert wait1 < 0.1
        
        wait2 = await limiter.acquire("https://coverartarchive.org/release/456")
        
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed >= 0.9  # Should wait at least 1 second for Cover Art Archive
    
    def test_domain_extraction(self):
        """Test domain extraction from URLs"""
        limiter = DomainRateLimiter()
        
        assert limiter._get_domain("https://coverartarchive.org/release/123") == "coverartarchive.org"
        assert limiter._get_domain("https://www.example.com/image.jpg") == "example.com"
        assert limiter._get_domain("http://musicbrainz.org/api/v2/") == "musicbrainz.org"


class TestArtworkDownloader:
    """Test the enhanced artwork downloader"""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock HTTP client"""
        return AsyncMock(spec=httpx.AsyncClient)
    
    @pytest.fixture
    def downloader(self, mock_client):
        """Create a downloader with mock client"""
        return ArtworkDownloader(client=mock_client)
    
    @pytest.fixture
    def sample_image_data(self):
        """Create sample image data"""
        from PIL import Image
        from io import BytesIO
        
        img = Image.new('RGB', (200, 200), color='blue')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        return buffer.getvalue()
    
    @pytest.mark.asyncio
    async def test_successful_download(self, downloader, mock_client, sample_image_data):
        """Test successful image download"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            'content-type': 'image/jpeg',
            'content-length': str(len(sample_image_data)),
            'etag': '"abc123"'
        }
        mock_response.content = sample_image_data
        mock_response.url = "https://example.com/image.jpg"
        mock_response.raise_for_status = Mock()
        
        mock_client.get.return_value = mock_response
        
        # Download
        image_data, metadata = await downloader.download_with_retry("https://example.com/image.jpg")
        
        assert image_data == sample_image_data
        assert metadata['content_type'] == 'image/jpeg'
        assert metadata['etag'] == '"abc123"'
        assert metadata['format'] == 'JPEG'
        assert metadata['width'] == 200
        assert metadata['height'] == 200
    
    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, downloader, mock_client, sample_image_data):
        """Test retry logic on timeout"""
        # First two attempts timeout, third succeeds
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'image/jpeg'}
        mock_response.content = sample_image_data
        mock_response.url = "https://example.com/image.jpg"
        mock_response.raise_for_status = Mock()
        
        mock_client.get.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.TimeoutException("Timeout"),
            mock_response
        ]
        
        # Should succeed after retries
        image_data, metadata = await downloader.download_with_retry("https://example.com/image.jpg")
        
        assert image_data == sample_image_data
        assert mock_client.get.call_count == 3
    
    @pytest.mark.asyncio
    async def test_no_retry_on_404(self, downloader, mock_client):
        """Test that 404 errors don't trigger retry"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_response
        )
        
        mock_client.get.return_value = mock_response
        
        with pytest.raises(ArtworkDownloadError, match="not found"):
            await downloader.download_with_retry("https://example.com/missing.jpg")
        
        # Should only try once for 404
        assert mock_client.get.call_count == 1
    
    @pytest.mark.asyncio
    async def test_content_validation(self, downloader, mock_client):
        """Test content type and format validation"""
        # Invalid content (not an image)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.content = b"<html>Not an image</html>"
        mock_response.url = "https://example.com/page.html"
        mock_response.raise_for_status = Mock()
        
        mock_client.get.return_value = mock_response
        
        with pytest.raises(ArtworkDownloadError, match="Failed to download"):
            await downloader.download_with_retry("https://example.com/page.html")
    
    @pytest.mark.asyncio
    async def test_file_size_limit(self, downloader, mock_client):
        """Test file size limit enforcement"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            'content-type': 'image/jpeg',
            'content-length': str(20 * 1024 * 1024)  # 20MB
        }
        mock_response.raise_for_status = Mock()
        
        mock_client.get.return_value = mock_response
        
        with pytest.raises(ArtworkDownloadError, match="Failed to download"):
            await downloader.download_with_retry("https://example.com/huge.jpg")


class TestBatchDownloader:
    """Test batch downloading functionality"""
    
    @pytest.fixture
    def sample_image_data(self):
        """Create sample image data"""
        from PIL import Image
        from io import BytesIO
        
        img = Image.new('RGB', (100, 100), color='green')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    
    @pytest.mark.asyncio
    async def test_batch_download(self, sample_image_data):
        """Test downloading multiple images concurrently"""
        batch_downloader = BatchArtworkDownloader(max_concurrent=2)
        
        # Mock the downloader
        mock_download = AsyncMock(return_value=(sample_image_data, {'format': 'PNG'}))
        batch_downloader.downloader.download_with_retry = mock_download
        
        urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg"
        ]
        
        results = await batch_downloader.download_batch(urls)
        
        assert len(results) == 3
        for url in urls:
            assert url in results
            assert results[url][0] == sample_image_data
        
        # Cleanup
        await batch_downloader.close()
    
    @pytest.mark.asyncio
    async def test_batch_with_failures(self):
        """Test batch download with some failures"""
        batch_downloader = BatchArtworkDownloader(max_concurrent=2)
        
        # Mock mixed results
        async def mock_download(url):
            if "fail" in url:
                raise ArtworkDownloadError("Failed")
            return (b"image_data", {'format': 'JPEG'})
        
        batch_downloader.downloader.download_with_retry = mock_download
        
        urls = [
            "https://example.com/good1.jpg",
            "https://example.com/fail.jpg",
            "https://example.com/good2.jpg"
        ]
        
        results = await batch_downloader.download_batch(urls)
        
        assert results["https://example.com/good1.jpg"][0] == b"image_data"
        assert results["https://example.com/fail.jpg"][0] is None
        assert results["https://example.com/good2.jpg"][0] == b"image_data"
        
        await batch_downloader.close()


class TestIntegratedCacheService:
    """Test the integrated cache service with enhanced downloading"""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        db = Mock()
        db.query = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db
    
    @pytest.fixture
    def mock_album(self):
        """Create mock album"""
        album = Mock(spec=Album)
        album.id = 1
        album.musicbrainz_id = "test-mb-123"
        album.cover_art_url = "https://coverartarchive.org/release/test-mb-123/front"
        album.artwork_cached = False
        album.artwork_cache_date = None
        return album
    
    @pytest.mark.asyncio
    async def test_cache_with_rate_limiting(self, mock_db, mock_album, tmp_path):
        """Test caching with rate limiting applied"""
        from app.services.artwork_cache_utils import ArtworkCacheFileSystem
        
        # Create service with temp directory
        cache_fs = ArtworkCacheFileSystem(base_path=str(tmp_path))
        service = ArtworkCacheService(cache_fs=cache_fs)
        
        # Mock the downloader
        sample_data = b"test_image_data"
        metadata = {
            'content_type': 'image/jpeg',
            'width': 500,
            'height': 500,
            'etag': '"test123"'
        }
        
        service.downloader = Mock()
        service.downloader.download_with_retry = AsyncMock(
            return_value=(sample_data, metadata)
        )
        
        # Mock database query for cache records
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.query.return_value = mock_query
        
        # Mock PIL Image operations
        with patch('app.services.artwork_cache_service.Image') as mock_image:
            mock_img = Mock()
            mock_img.format = 'JPEG'
            mock_img.mode = 'RGB'
            mock_img.size = (500, 500)
            mock_img.copy.return_value = mock_img
            mock_image.open.return_value = mock_img
            
            # Cache artwork
            success = await service.cache_artwork(
                mock_album,
                mock_album.cover_art_url,
                mock_db
            )
            
            assert success is True
            assert mock_album.artwork_cached is True
            assert mock_album.artwork_cache_date is not None
            
            # Verify rate limiting was applied
            service.downloader.download_with_retry.assert_called_once_with(
                mock_album.cover_art_url
            )
    
    @pytest.mark.asyncio
    async def test_metadata_storage(self, mock_db, mock_album, tmp_path):
        """Test that download metadata is properly stored"""
        from app.services.artwork_cache_utils import ArtworkCacheFileSystem
        
        cache_fs = ArtworkCacheFileSystem(base_path=str(tmp_path))
        service = ArtworkCacheService(cache_fs=cache_fs)
        
        # Mock database query
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db.query.return_value = mock_query
        
        # Mock download with metadata
        metadata = {
            'content_type': 'image/png',
            'width': 1000,
            'height': 1000,
            'etag': '"abc-xyz-123"',
            'checksum': 'md5hash123',
            'format': 'PNG'
        }
        
        service._download_image = AsyncMock(return_value=(b"image", metadata))
        service._save_original = AsyncMock(return_value=tmp_path / "test.png")
        service._generate_all_variants = AsyncMock(return_value=["original"])
        
        # Update cache records
        await service._update_cache_records(
            mock_album, "cache123", "https://example.com/art.png",
            ["original"], mock_db, metadata
        )
        
        # Verify metadata was added to cache record
        assert mock_db.add.called
        cache_record = mock_db.add.call_args[0][0]
        assert cache_record.etag == '"abc-xyz-123"'
        assert cache_record.content_type == 'image/png'