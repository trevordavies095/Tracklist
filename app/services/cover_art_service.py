"""
Cover Art Archive API service for fetching album artwork
"""

import logging
from typing import Optional, Dict, Any
from ..exceptions import TracklistException

logger = logging.getLogger(__name__)

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available - cover art fetching will be disabled")


class CoverArtService:
    """Service for interacting with the Cover Art Archive API"""

    BASE_URL = "https://coverartarchive.org"
    TIMEOUT = 10.0

    def __init__(self):
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(
                timeout=self.TIMEOUT,
                follow_redirects=True,  # Follow redirects automatically
                headers={
                    "User-Agent": "Tracklist/1.0 (https://github.com/yourusername/tracklist)"
                },
            )
        else:
            self.client = None

    async def get_cover_art_url(self, musicbrainz_id: str) -> Optional[str]:
        """
        Fetch cover art URL for an album from Cover Art Archive

        Args:
            musicbrainz_id: MusicBrainz release ID

        Returns:
            URL of the front cover image, or None if not available
        """
        if not HTTPX_AVAILABLE or not self.client:
            logger.debug("httpx not available - skipping cover art fetch")
            return None

        try:
            url = f"{self.BASE_URL}/release/{musicbrainz_id}"
            response = await self.client.get(url)

            if response.status_code == 404:
                logger.info(f"No cover art found for release {musicbrainz_id}")
                return None

            if response.status_code not in [200, 307, 308]:  # Allow redirects
                logger.warning(
                    f"Cover Art API returned {response.status_code} for {musicbrainz_id}"
                )
                return None

            data = response.json()

            # Look for front cover first
            for image in data.get("images", []):
                if "Front" in image.get("types", []):
                    # Prefer thumbnails for performance
                    if "thumbnails" in image and "large" in image["thumbnails"]:
                        return image["thumbnails"]["large"]
                    elif "thumbnails" in image and "small" in image["thumbnails"]:
                        return image["thumbnails"]["small"]
                    else:
                        return image.get("image")

            # If no front cover, use first available image
            if data.get("images"):
                first_image = data["images"][0]
                if "thumbnails" in first_image and "large" in first_image["thumbnails"]:
                    return first_image["thumbnails"]["large"]
                elif (
                    "thumbnails" in first_image and "small" in first_image["thumbnails"]
                ):
                    return first_image["thumbnails"]["small"]
                else:
                    return first_image.get("image")

            logger.info(f"No suitable cover art found for {musicbrainz_id}")
            return None

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching cover art for {musicbrainz_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching cover art for {musicbrainz_id}: {e}")
            return None

    async def close(self):
        """Close the HTTP client"""
        if self.client:
            await self.client.aclose()


# Global instance
_cover_art_service = None


def get_cover_art_service() -> CoverArtService:
    """Get or create the global Cover Art service instance"""
    global _cover_art_service
    if _cover_art_service is None:
        _cover_art_service = CoverArtService()
    return _cover_art_service
