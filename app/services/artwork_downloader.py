"""
Enhanced artwork downloader with validation, retry logic, and rate limiting
"""

import asyncio
import logging
import hashlib
from typing import Optional, Tuple, Dict, Any
from io import BytesIO
import httpx
from PIL import Image

from .rate_limiter import get_domain_rate_limiter
from ..exceptions import TracklistException

logger = logging.getLogger(__name__)


class ArtworkDownloadError(TracklistException):
    """Exception for artwork download failures"""
    pass


class ArtworkDownloader:
    """
    Enhanced artwork downloader with validation and retry logic
    """

    # Valid image content types
    VALID_CONTENT_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png',
        'image/gif', 'image/webp', 'image/bmp'
    }

    # Valid image formats (PIL format names)
    VALID_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'MPO'}

    # Download settings
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    TIMEOUT = 30  # seconds
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        """
        Initialize downloader

        Args:
            client: Optional HTTP client to use
        """
        self.client = client or httpx.AsyncClient(
            timeout=self.TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5),
            headers={
                'User-Agent': 'Tracklist/1.0 (https://github.com/tracklist)'
            }
        )
        self.rate_limiter = get_domain_rate_limiter()

    async def download_with_retry(
        self,
        url: str,
        max_retries: Optional[int] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Download image with retry logic and validation

        Args:
            url: URL to download from
            max_retries: Maximum number of retries (uses default if None)

        Returns:
            Tuple of (image_data, metadata)

        Raises:
            ArtworkDownloadError: If download fails after all retries
        """
        max_retries = max_retries or self.MAX_RETRIES
        last_error = None

        for attempt in range(max_retries):
            try:
                # Apply rate limiting
                wait_time = await self.rate_limiter.acquire(url)
                if wait_time > 0:
                    logger.debug(f"Rate limited: waited {wait_time:.2f}s for {url}")

                # Attempt download
                image_data, metadata = await self._download_once(url)

                # Validate the image
                if not await self._validate_image(image_data, metadata):
                    raise ArtworkDownloadError(f"Invalid image from {url}")

                logger.info(f"Successfully downloaded artwork from {url} (attempt {attempt + 1})")
                return image_data, metadata

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Timeout downloading {url} (attempt {attempt + 1}/{max_retries})")

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 404:
                    # Don't retry 404s
                    logger.info(f"Artwork not found (404): {url}")
                    raise ArtworkDownloadError(f"Artwork not found: {url}")
                logger.warning(f"HTTP error {e.response.status_code} downloading {url}")

            except Exception as e:
                last_error = e
                logger.warning(f"Error downloading {url} (attempt {attempt + 1}): {e}")

            # Wait before retry (exponential backoff)
            if attempt < max_retries - 1:
                delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                logger.debug(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        # All retries failed
        error_msg = f"Failed to download {url} after {max_retries} attempts"
        logger.error(f"{error_msg}: {last_error}")
        raise ArtworkDownloadError(error_msg)

    async def _download_once(self, url: str) -> Tuple[bytes, Dict[str, Any]]:
        """
        Single download attempt

        Args:
            url: URL to download from

        Returns:
            Tuple of (image_data, metadata)

        Raises:
            Various httpx exceptions
        """
        response = await self.client.get(url)
        response.raise_for_status()

        # Check content length
        content_length = int(response.headers.get('content-length', 0))
        if content_length > self.MAX_FILE_SIZE:
            raise ArtworkDownloadError(f"File too large: {content_length} bytes")

        # Get content type
        content_type = response.headers.get('content-type', '').lower().split(';')[0]

        # Download content
        image_data = response.content

        # Check actual size
        if len(image_data) > self.MAX_FILE_SIZE:
            raise ArtworkDownloadError(f"Downloaded file too large: {len(image_data)} bytes")

        # Calculate checksum
        checksum = hashlib.md5(image_data).hexdigest()

        # Build metadata
        metadata = {
            'url': str(response.url),  # Final URL after redirects
            'content_type': content_type,
            'content_length': len(image_data),
            'checksum': checksum,
            'etag': response.headers.get('etag'),
            'last_modified': response.headers.get('last-modified'),
            'cache_control': response.headers.get('cache-control')
        }

        logger.debug(f"Downloaded {len(image_data)} bytes from {url}")
        return image_data, metadata

    async def _validate_image(self, image_data: bytes, metadata: Dict[str, Any]) -> bool:
        """
        Validate image data

        Args:
            image_data: Raw image bytes
            metadata: Download metadata

        Returns:
            True if valid, False otherwise
        """
        # Check content type
        content_type = metadata.get('content_type', '')
        if content_type and content_type not in self.VALID_CONTENT_TYPES:
            logger.warning(f"Invalid content type: {content_type}")
            # Don't fail immediately - try to validate the actual image data

        # Validate with PIL
        try:
            img = Image.open(BytesIO(image_data))

            # Check format
            if img.format not in self.VALID_FORMATS:
                logger.warning(f"Invalid image format: {img.format}")
                return False

            # Verify the image
            img.verify()

            # Re-open for further checks (verify() closes the file)
            img = Image.open(BytesIO(image_data))

            # Check dimensions
            width, height = img.size
            if width < 10 or height < 10:
                logger.warning(f"Image too small: {width}x{height}")
                return False

            if width > 5000 or height > 5000:
                logger.warning(f"Image too large: {width}x{height}")
                return False

            # Update metadata with image info
            metadata['format'] = img.format
            metadata['width'] = width
            metadata['height'] = height
            metadata['mode'] = img.mode

            logger.debug(f"Valid image: {img.format} {width}x{height}")
            return True

        except Exception as e:
            logger.warning(f"Image validation failed: {e}")
            return False

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        Simple download method for compatibility

        Args:
            url: URL to download from

        Returns:
            Image data as bytes, or None if failed
        """
        try:
            image_data, _ = await self.download_with_retry(url)
            return image_data
        except ArtworkDownloadError:
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            return None

    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()


class BatchArtworkDownloader:
    """
    Batch artwork downloader with concurrent downloads and rate limiting
    """

    def __init__(self, max_concurrent: int = 3):
        """
        Initialize batch downloader

        Args:
            max_concurrent: Maximum concurrent downloads
        """
        self.max_concurrent = max_concurrent
        self.downloader = ArtworkDownloader()
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def download_batch(
        self,
        urls: list[str],
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Tuple[Optional[bytes], Optional[Dict]]]:
        """
        Download multiple images concurrently

        Args:
            urls: List of URLs to download
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary mapping URL to (image_data, metadata) or (None, None) for failures
        """
        results = {}
        tasks = []

        async def download_with_semaphore(url: str):
            async with self.semaphore:
                try:
                    image_data, metadata = await self.downloader.download_with_retry(url)
                    results[url] = (image_data, metadata)
                except Exception as e:
                    logger.error(f"Failed to download {url}: {e}")
                    results[url] = (None, None)

                if progress_callback:
                    await progress_callback(url, results[url][0] is not None)

        # Create tasks for all downloads
        for url in urls:
            task = asyncio.create_task(download_with_semaphore(url))
            tasks.append(task)

        # Wait for all downloads to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def close(self):
        """Close resources"""
        await self.downloader.close()
