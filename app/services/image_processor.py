"""
Image processing module for artwork variants
Handles resizing, cropping, optimization, and format conversion
"""

import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from io import BytesIO
from PIL import Image, ImageOps, ImageFilter
import hashlib

logger = logging.getLogger(__name__)


class ImageProcessingError(Exception):
    """Exception raised during image processing operations"""
    pass


class ImageProcessor:
    """
    Advanced image processor for creating optimized artwork variants
    Supports smart cropping, optimization, and multiple output formats
    """
    
    # Size variant specifications with aspect ratios
    SIZE_VARIANTS = {
        'original': None,
        'large': (192, 192),
        'medium': (64, 64),
        'small': (48, 48),
        'thumbnail': (80, 80)
    }
    
    # Quality settings per variant (for optimization)
    QUALITY_SETTINGS = {
        'original': 95,
        'large': 90,
        'medium': 85,
        'small': 85,
        'thumbnail': 80
    }
    
    # Supported input formats
    SUPPORTED_FORMATS = {'JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF'}
    
    # Maximum dimensions for safety
    MAX_DIMENSION = 4096
    
    # Default output format
    DEFAULT_OUTPUT_FORMAT = 'JPEG'
    
    def __init__(self):
        """Initialize the image processor"""
        self.processing_stats = {
            'total_processed': 0,
            'total_bytes_saved': 0,
            'failures': 0
        }
    
    def process_image(
        self,
        image_data: bytes,
        variant: str,
        optimize: bool = True,
        maintain_aspect: bool = True,
        smart_crop: bool = True
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Process an image to create a specific size variant
        
        Args:
            image_data: Raw image data
            variant: Size variant name
            optimize: Whether to optimize for web
            maintain_aspect: Whether to maintain aspect ratio
            smart_crop: Whether to use smart cropping
            
        Returns:
            Tuple of (processed_image_data, metadata)
            
        Raises:
            ImageProcessingError: If processing fails
        """
        if variant not in self.SIZE_VARIANTS:
            raise ImageProcessingError(f"Invalid variant: {variant}")
        
        try:
            # Open and validate image
            img = self._open_and_validate(image_data)
            
            # Get original metadata
            original_metadata = self._extract_metadata(img, len(image_data))
            
            # Process based on variant
            if variant == 'original':
                # For original, just optimize without resizing
                processed_img = self._optimize_original(img, optimize)
            else:
                # Resize and optimize for specific variant
                target_size = self.SIZE_VARIANTS[variant]
                processed_img = self._resize_image(
                    img, 
                    target_size, 
                    maintain_aspect, 
                    smart_crop
                )
            
            # Convert to RGB if needed (for JPEG output)
            if processed_img.mode in ('RGBA', 'LA', 'P'):
                processed_img = self._convert_to_rgb(processed_img)
            
            # Save to bytes with optimization
            output_data = self._save_optimized(
                processed_img, 
                variant, 
                optimize
            )
            
            # Generate metadata for processed image
            metadata = self._generate_metadata(
                processed_img, 
                output_data, 
                variant, 
                original_metadata
            )
            
            # Update stats
            self.processing_stats['total_processed'] += 1
            bytes_saved = len(image_data) - len(output_data)
            if bytes_saved > 0:
                self.processing_stats['total_bytes_saved'] += bytes_saved
            
            logger.debug(f"Processed {variant} variant: {metadata}")
            return output_data, metadata
            
        except Exception as e:
            self.processing_stats['failures'] += 1
            logger.error(f"Image processing failed for {variant}: {e}")
            raise ImageProcessingError(f"Failed to process {variant}: {str(e)}")
    
    def process_all_variants(
        self,
        image_data: bytes,
        optimize: bool = True
    ) -> Dict[str, Tuple[bytes, Dict[str, Any]]]:
        """
        Process an image into all defined variants
        
        Args:
            image_data: Raw image data
            optimize: Whether to optimize for web
            
        Returns:
            Dictionary mapping variant names to (data, metadata) tuples
        """
        results = {}
        errors = []
        
        for variant in self.SIZE_VARIANTS.keys():
            try:
                processed_data, metadata = self.process_image(
                    image_data, 
                    variant, 
                    optimize
                )
                results[variant] = (processed_data, metadata)
                logger.info(f"Successfully processed {variant} variant")
            except Exception as e:
                errors.append((variant, str(e)))
                logger.error(f"Failed to process {variant}: {e}")
        
        if errors and not results:
            raise ImageProcessingError(f"All variants failed: {errors}")
        
        if errors:
            logger.warning(f"Some variants failed: {errors}")
        
        return results
    
    def _open_and_validate(self, image_data: bytes) -> Image.Image:
        """
        Open and validate an image from bytes
        
        Args:
            image_data: Raw image data
            
        Returns:
            PIL Image object
            
        Raises:
            ImageProcessingError: If image is invalid
        """
        try:
            img = Image.open(BytesIO(image_data))
            
            # Validate format
            if img.format not in self.SUPPORTED_FORMATS:
                raise ImageProcessingError(
                    f"Unsupported format: {img.format}. "
                    f"Supported: {self.SUPPORTED_FORMATS}"
                )
            
            # Validate dimensions
            if max(img.size) > self.MAX_DIMENSION:
                raise ImageProcessingError(
                    f"Image too large: {img.size}. "
                    f"Max dimension: {self.MAX_DIMENSION}"
                )
            
            # Load image data (required for some operations)
            img.load()
            
            return img
            
        except Exception as e:
            if isinstance(e, ImageProcessingError):
                raise
            raise ImageProcessingError(f"Failed to open image: {e}")
    
    def _resize_image(
        self,
        img: Image.Image,
        target_size: Tuple[int, int],
        maintain_aspect: bool = True,
        smart_crop: bool = True
    ) -> Image.Image:
        """
        Resize an image with smart cropping options
        
        Args:
            img: PIL Image object
            target_size: Target dimensions (width, height)
            maintain_aspect: Whether to maintain aspect ratio
            smart_crop: Whether to use smart cropping
            
        Returns:
            Resized PIL Image
        """
        if not maintain_aspect:
            # Simple resize without maintaining aspect ratio
            return img.resize(target_size, Image.Resampling.LANCZOS)
        
        if smart_crop:
            # Use ImageOps.fit for smart cropping (center crop by default)
            return ImageOps.fit(
                img,
                target_size,
                Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)  # Center crop
            )
        else:
            # Use thumbnail to maintain aspect ratio without cropping
            img_copy = img.copy()
            img_copy.thumbnail(target_size, Image.Resampling.LANCZOS)
            return img_copy
    
    def _optimize_original(
        self,
        img: Image.Image,
        optimize: bool = True
    ) -> Image.Image:
        """
        Optimize the original image without resizing
        
        Args:
            img: PIL Image object
            optimize: Whether to apply optimization
            
        Returns:
            Optimized PIL Image
        """
        if not optimize:
            return img
        
        # Apply slight sharpening if image is large
        if min(img.size) > 500:
            img = img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=50))
        
        # Auto-enhance could be added here if needed
        # from PIL import ImageEnhance
        # enhancer = ImageEnhance.Contrast(img)
        # img = enhancer.enhance(1.1)
        
        return img
    
    def _convert_to_rgb(self, img: Image.Image) -> Image.Image:
        """
        Convert image to RGB mode for JPEG compatibility
        
        Args:
            img: PIL Image object
            
        Returns:
            RGB PIL Image
        """
        if img.mode == 'RGBA':
            # Create white background
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            # Paste image using alpha channel as mask
            rgb_img.paste(img, mask=img.split()[3])
            return rgb_img
        elif img.mode == 'LA':
            # Convert grayscale with alpha to RGB
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[1])
            return rgb_img
        elif img.mode == 'P':
            # Convert palette mode to RGB
            return img.convert('RGB')
        else:
            # Already RGB or grayscale without alpha
            return img.convert('RGB')
    
    def _save_optimized(
        self,
        img: Image.Image,
        variant: str,
        optimize: bool = True
    ) -> bytes:
        """
        Save image to bytes with optimization
        
        Args:
            img: PIL Image object
            variant: Size variant name
            optimize: Whether to apply optimization
            
        Returns:
            Optimized image data as bytes
        """
        output = BytesIO()
        
        # Get quality setting for variant
        quality = self.QUALITY_SETTINGS.get(variant, 85)
        
        # Save with optimization
        save_kwargs = {
            'format': self.DEFAULT_OUTPUT_FORMAT,
            'quality': quality,
            'optimize': optimize
        }
        
        # Add progressive encoding for larger images
        if variant in ['original', 'large']:
            save_kwargs['progressive'] = True
        
        # Add specific optimizations for JPEG
        if self.DEFAULT_OUTPUT_FORMAT == 'JPEG':
            save_kwargs['subsampling'] = 2  # 4:2:0 subsampling
            
        img.save(output, **save_kwargs)
        
        return output.getvalue()
    
    def _extract_metadata(
        self,
        img: Image.Image,
        data_size: int
    ) -> Dict[str, Any]:
        """
        Extract metadata from original image
        
        Args:
            img: PIL Image object
            data_size: Size of image data in bytes
            
        Returns:
            Dictionary of metadata
        """
        return {
            'format': img.format,
            'mode': img.mode,
            'width': img.width,
            'height': img.height,
            'aspect_ratio': round(img.width / img.height, 2) if img.height > 0 else 1,
            'file_size_bytes': data_size,
            'has_transparency': img.mode in ('RGBA', 'LA', 'P'),
            'info': dict(img.info) if hasattr(img, 'info') else {}
        }
    
    def _generate_metadata(
        self,
        img: Image.Image,
        output_data: bytes,
        variant: str,
        original_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate metadata for processed image
        
        Args:
            img: Processed PIL Image
            output_data: Processed image data
            variant: Size variant name
            original_metadata: Metadata from original image
            
        Returns:
            Dictionary of metadata
        """
        # Calculate checksum
        checksum = hashlib.md5(output_data).hexdigest()
        
        metadata = {
            'variant': variant,
            'width': img.width,
            'height': img.height,
            'file_size_bytes': len(output_data),
            'format': self.DEFAULT_OUTPUT_FORMAT,
            'quality': self.QUALITY_SETTINGS.get(variant, 85),
            'checksum': checksum,
            'compression_ratio': round(
                len(output_data) / original_metadata['file_size_bytes'], 3
            ) if original_metadata['file_size_bytes'] > 0 else 1,
            'original_format': original_metadata['format'],
            'original_dimensions': (
                original_metadata['width'], 
                original_metadata['height']
            )
        }
        
        return metadata
    
    def validate_processed_image(
        self,
        image_data: bytes,
        expected_variant: str
    ) -> bool:
        """
        Validate a processed image meets requirements
        
        Args:
            image_data: Processed image data
            expected_variant: Expected size variant
            
        Returns:
            True if valid, False otherwise
        """
        try:
            img = Image.open(BytesIO(image_data))
            
            if expected_variant == 'original':
                # Original should just be valid
                return img.format in self.SUPPORTED_FORMATS
            
            expected_size = self.SIZE_VARIANTS.get(expected_variant)
            if not expected_size:
                return False
            
            # Check dimensions are within expected bounds
            # Allow some tolerance for aspect ratio maintenance
            width_ok = img.width <= expected_size[0]
            height_ok = img.height <= expected_size[1]
            
            return width_ok and height_ok
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            'total_processed': self.processing_stats['total_processed'],
            'total_failures': self.processing_stats['failures'],
            'success_rate': round(
                (self.processing_stats['total_processed'] - 
                 self.processing_stats['failures']) / 
                self.processing_stats['total_processed'] * 100, 2
            ) if self.processing_stats['total_processed'] > 0 else 0,
            'total_bytes_saved': self.processing_stats['total_bytes_saved'],
            'mb_saved': round(
                self.processing_stats['total_bytes_saved'] / (1024 * 1024), 2
            )
        }


# Global instance
_image_processor = None


def get_image_processor() -> ImageProcessor:
    """Get or create the global image processor instance"""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor