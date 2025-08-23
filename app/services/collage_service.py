"""
Collage Service for generating album collages in Topsters format
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
from pathlib import Path
from sqlalchemy.orm import Session
import asyncio

logger = logging.getLogger(__name__)

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available - direct download fallback will not work")

from ..models import Album, ArtworkCache
from .artwork_cache_service import ArtworkCacheService, get_artwork_cache_service


class CollageService:
    """
    Service for generating album collages in Topsters format
    Creates visual grids of album artwork with optional ranking lists
    """

    # Album tile size in pixels
    TILE_SIZE = 300

    # Spacing between albums
    SPACING = 2

    # Background color
    BG_COLOR = (18, 18, 18)  # Dark background

    # Text color for ranking list
    TEXT_COLOR = (255, 255, 255)

    # Ranking list width (if included)
    RANKING_WIDTH = 500  # Increased from 400 to prevent cutoff

    # Font settings
    FONT_SIZE = 16
    RANKING_FONT_SIZE = 14  # Increased for better readability

    def __init__(self):
        """Initialize the collage service"""
        self.artwork_cache_service = get_artwork_cache_service()
        self.placeholder_path = Path("static/img/album-placeholder.svg")

    def calculate_grid_dimensions(self, album_count: int) -> Tuple[int, int]:
        """
        Calculate optimal grid dimensions for near-square layout

        Args:
            album_count: Number of albums to include

        Returns:
            Tuple of (columns, rows)
        """
        if album_count <= 0:
            return (0, 0)

        # Calculate the square root to find the ideal square size
        import math

        sqrt = math.sqrt(album_count)

        # Start with the ceiling of the square root for columns
        cols = math.ceil(sqrt)

        # Calculate rows needed
        rows = math.ceil(album_count / cols)

        # Try to make it more square by adjusting if we have too many empty spots
        # If we have a lot of empty spaces, try reducing columns
        while cols > 1 and (cols - 1) * rows >= album_count:
            cols -= 1
            rows = math.ceil(album_count / cols)

        # Cap at 10x10 maximum
        if cols > 10:
            cols = 10
            rows = math.ceil(album_count / 10)

        return (cols, rows)

    def get_placeholder_image(self) -> Image.Image:
        """
        Get a placeholder image for missing artwork

        Returns:
            PIL Image object with placeholder
        """
        # Create a simple gray placeholder
        placeholder = Image.new(
            "RGB", (self.TILE_SIZE, self.TILE_SIZE), color=(60, 60, 60)
        )

        # Add a music note icon or text
        draw = ImageDraw.Draw(placeholder)
        try:
            # Try to load a basic font
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        except:
            font = ImageFont.load_default()

        # Draw "?" in center
        text = "♪"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = (
            (self.TILE_SIZE - text_width) // 2,
            (self.TILE_SIZE - text_height) // 2,
        )
        draw.text(position, text, fill=(100, 100, 100), font=font)

        return placeholder

    async def load_album_artwork(self, album: Album, db: Session) -> Image.Image:
        """
        Load album artwork from cache

        Args:
            album: Album model instance
            db: Database session

        Returns:
            PIL Image object
        """
        try:
            # Try to get the original artwork from cache
            cache_record = (
                db.query(ArtworkCache)
                .filter_by(album_id=album.id, size_variant="original")
                .first()
            )

            if cache_record and cache_record.file_path:
                # The file_path in DB is already the full relative path (e.g., "static/artwork_cache/original/xxx.jpg")
                image_path = Path(cache_record.file_path)

                if image_path.exists():
                    with Image.open(image_path) as img:
                        # Convert to RGB and resize to tile size
                        img = img.convert("RGB")
                        img = img.resize(
                            (self.TILE_SIZE, self.TILE_SIZE), Image.Resampling.LANCZOS
                        )
                        return img.copy()  # Return a copy to avoid file lock issues
                else:
                    logger.warning(
                        f"Cached file not found at {image_path} for album {album.id}"
                    )

            # If no cached original, try to find any cached size and use that
            for size in ["large", "medium", "small"]:
                cache_record = (
                    db.query(ArtworkCache)
                    .filter_by(album_id=album.id, size_variant=size)
                    .first()
                )

                if cache_record and cache_record.file_path:
                    # The file_path in DB is already the full relative path
                    image_path = Path(cache_record.file_path)

                    if image_path.exists():
                        logger.info(
                            f"Using {size} variant for album {album.id} as original not found"
                        )
                        with Image.open(image_path) as img:
                            img = img.convert("RGB")
                            img = img.resize(
                                (self.TILE_SIZE, self.TILE_SIZE),
                                Image.Resampling.LANCZOS,
                            )
                            return img.copy()

            # If no cached artwork but we have a URL, download directly
            if album.cover_art_url and HTTPX_AVAILABLE:
                logger.info(
                    f"No cached artwork found for album {album.id}, downloading from URL directly"
                )
                try:
                    # Download the image directly
                    async with httpx.AsyncClient(
                        timeout=10.0, follow_redirects=True
                    ) as client:
                        response = await client.get(album.cover_art_url)
                        if response.status_code == 200:
                            # Load the image from downloaded bytes
                            img = Image.open(BytesIO(response.content))
                            img = img.convert("RGB")
                            img = img.resize(
                                (self.TILE_SIZE, self.TILE_SIZE),
                                Image.Resampling.LANCZOS,
                            )

                            logger.info(
                                f"Successfully downloaded and resized artwork for album {album.id}"
                            )

                            # Optionally try to cache it in the background (but don't wait)
                            try:
                                asyncio.create_task(
                                    self.artwork_cache_service.get_or_cache_artwork(
                                        album, "original", db
                                    )
                                )
                            except Exception as cache_error:
                                logger.debug(
                                    f"Could not trigger background caching: {cache_error}"
                                )

                            return img
                        else:
                            logger.warning(
                                f"Failed to download artwork for album {album.id}: HTTP {response.status_code}"
                            )

                except Exception as download_error:
                    logger.error(
                        f"Error downloading artwork for album {album.id}: {download_error}"
                    )

            # Return placeholder if all else fails
            logger.warning(
                f"Using placeholder for album {album.id} - no artwork available"
            )
            return self.get_placeholder_image()

        except Exception as e:
            logger.error(f"Failed to load artwork for album {album.id}: {e}")
            return self.get_placeholder_image()

    async def generate_collage(
        self,
        albums: List[Album],
        db: Session,
        include_ranking: bool = True,
        include_scores: bool = True,
        max_albums: Optional[int] = None,
        title: Optional[str] = None,
    ) -> bytes:
        """
        Generate a collage image from a list of albums

        Args:
            albums: List of Album objects sorted by rating
            db: Database session
            include_ranking: Whether to include ranking list
            include_scores: Whether to include scores in ranking
            max_albums: Maximum number of albums to include
            title: Optional title for the collage

        Returns:
            Bytes of the generated image (PNG format)
        """
        # Limit albums if specified
        if max_albums:
            albums = albums[:max_albums]

        album_count = len(albums)
        if album_count == 0:
            raise ValueError("No albums provided for collage generation")

        # Calculate grid dimensions
        cols, rows = self.calculate_grid_dimensions(album_count)

        # Calculate image dimensions
        collage_width = cols * self.TILE_SIZE + (cols - 1) * self.SPACING
        collage_height = rows * self.TILE_SIZE + (rows - 1) * self.SPACING

        # Add space for ranking list if included
        total_width = collage_width
        if include_ranking:
            total_width += self.RANKING_WIDTH + 40  # 40px padding

        # Add space for title if included
        title_height = 60 if title else 0
        total_height = collage_height + title_height

        # Create the base image
        img = Image.new("RGB", (total_width, total_height), color=self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Load font for text - prefer monospace fonts
        title_font = None
        ranking_font = None

        # Try different monospace fonts
        font_paths = [
            "/System/Library/Fonts/Monaco.ttf",  # macOS Monaco
            "/System/Library/Fonts/Menlo.ttc",  # macOS Menlo
            "/System/Library/Fonts/Courier.ttc",  # macOS Courier
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
            "C:\\Windows\\Fonts\\consola.ttf",  # Windows Consolas
            "C:\\Windows\\Fonts\\cour.ttf",  # Windows Courier
        ]

        for font_path in font_paths:
            try:
                title_font = ImageFont.truetype(font_path, 32)
                ranking_font = ImageFont.truetype(font_path, self.RANKING_FONT_SIZE)
                logger.info(f"Using monospace font: {font_path}")
                break
            except:
                continue

        # Fallback to default if no monospace font found
        if not title_font:
            try:
                title_font = ImageFont.load_default()
                ranking_font = ImageFont.load_default()
                logger.warning("Using default font - no monospace font found")
            except:
                pass

        # Draw title if provided
        y_offset = 0
        if title:
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            # Center title across full image width (not just collage width)
            title_x = (total_width - title_width) // 2
            draw.text((title_x, 15), title, fill=self.TEXT_COLOR, font=title_font)
            y_offset = title_height

        # Place albums in grid
        logger.info(
            f"Generating collage with {album_count} albums in {cols}x{rows} grid"
        )

        for idx, album in enumerate(albums):
            # Calculate position in grid
            row = idx // cols
            col = idx % cols

            x = col * (self.TILE_SIZE + self.SPACING)
            y = row * (self.TILE_SIZE + self.SPACING) + y_offset

            # Load album artwork
            album_img = await self.load_album_artwork(album, db)

            # Paste album onto collage
            img.paste(album_img, (x, y))

        # Add ranking list if requested
        if include_ranking:
            ranking_x = collage_width + 40

            # Track current Y position for text
            current_text_y = y_offset  # Start flush with first row

            # Process albums row by row
            for row_idx in range(rows):
                # Get albums in this row
                row_start_idx = row_idx * cols
                row_end_idx = min(row_start_idx + cols, len(albums))

                if row_start_idx >= len(albums):
                    break  # No more albums

                # Calculate line height based on font
                line_height = (
                    self.RANKING_FONT_SIZE + 4
                )  # Add small spacing between lines

                # Draw each album in this row
                for idx in range(row_start_idx, row_end_idx):
                    album = albums[idx]
                    rank = idx + 1

                    # Get artist name (handle both string and Artist object)
                    artist_name = (
                        album.artist.name
                        if hasattr(album.artist, "name")
                        else str(album.artist)
                    )
                    # Truncate long names for better readability
                    if len(artist_name) > 20:
                        artist_name = artist_name[:20] + "..."

                    # Get album name
                    album_name = album.name if album.name else "Unknown Album"
                    if len(album_name) > 25:
                        album_name = album_name[:25] + "..."

                    if include_scores and album.rating_score is not None:
                        # Format with padding for alignment
                        text = f"{rank:2d}. {artist_name} - {album_name}"
                        score_text = f" ({album.rating_score})"

                        # Draw main text in white
                        draw.text(
                            (ranking_x, current_text_y),
                            text,
                            fill=self.TEXT_COLOR,
                            font=ranking_font,
                        )

                        # Draw score in a slightly dimmed color for better hierarchy
                        text_bbox = draw.textbbox(
                            (ranking_x, current_text_y), text, font=ranking_font
                        )
                        score_x = text_bbox[2] + 2
                        draw.text(
                            (score_x, current_text_y),
                            score_text,
                            fill=(200, 200, 200),
                            font=ranking_font,
                        )
                    else:
                        text = f"{rank:2d}. {artist_name} - {album_name}"
                        draw.text(
                            (ranking_x, current_text_y),
                            text,
                            fill=self.TEXT_COLOR,
                            font=ranking_font,
                        )

                    # Move to next line position
                    current_text_y += line_height

                # After finishing a row, add extra spacing to align with next row of albums
                # Calculate where the next row of albums starts
                next_row_y = (row_idx + 1) * (self.TILE_SIZE + self.SPACING) + y_offset

                # If our text hasn't reached the next row position, jump to it
                if row_idx < rows - 1 and current_text_y < next_row_y:
                    current_text_y = next_row_y

        # Save to bytes
        output = BytesIO()
        img.save(output, format="PNG", optimize=True, quality=95)
        output.seek(0)

        logger.info(f"Successfully generated collage: {total_width}x{total_height}px")
        return output.getvalue()

    async def generate_year_collage(
        self,
        year: int,
        db: Session,
        include_ranking: bool = True,
        include_scores: bool = True,
        include_title: bool = True,
        max_albums: Optional[int] = None,
    ) -> bytes:
        """
        Generate a collage for a specific year

        Args:
            year: Year to generate collage for
            db: Database session
            include_ranking: Whether to include ranking list
            include_scores: Whether to include scores in ranking
            include_title: Whether to include title at the top
            max_albums: Maximum number of albums to include

        Returns:
            Bytes of the generated image
        """
        # Query albums for the year, sorted by rating
        albums = (
            db.query(Album)
            .filter(Album.release_year == year, Album.is_rated == True)
            .order_by(Album.rating_score.desc())
            .all()
        )

        if not albums:
            raise ValueError(f"No rated albums found for year {year}")

        # Generate title only if requested
        title = f"{year} Year End" if include_title else None

        return await self.generate_collage(
            albums,
            db,
            include_ranking=include_ranking,
            include_scores=include_scores,
            max_albums=max_albums,
            title=title,
        )


# Singleton instance
_collage_service_instance = None


def get_collage_service() -> CollageService:
    """Get or create the singleton CollageService instance"""
    global _collage_service_instance
    if _collage_service_instance is None:
        _collage_service_instance = CollageService()
        logger.info("CollageService initialized")
    return _collage_service_instance
