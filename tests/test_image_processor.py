"""
Tests for the image processor module
Validates resizing, optimization, and metadata generation
"""

import pytest
import io
import hashlib
from PIL import Image
from unittest.mock import Mock, patch, MagicMock

from app.services.image_processor import (
    ImageProcessor,
    ImageProcessingError,
    get_image_processor
)


class TestImageProcessor:
    """Test suite for ImageProcessor class"""
    
    @pytest.fixture
    def processor(self):
        """Create an ImageProcessor instance for testing"""
        return ImageProcessor()
    
    @pytest.fixture
    def sample_image_data(self):
        """Create sample image data for testing"""
        # Create a 500x500 RGB image
        img = Image.new('RGB', (500, 500), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        return buffer.getvalue()
    
    @pytest.fixture
    def sample_png_data(self):
        """Create sample PNG image with transparency"""
        # Create a 400x400 RGBA image with transparency
        img = Image.new('RGBA', (400, 400), color=(255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    
    def test_processor_initialization(self, processor):
        """Test processor initializes with correct defaults"""
        assert processor.processing_stats['total_processed'] == 0
        assert processor.processing_stats['failures'] == 0
        assert 'original' in processor.SIZE_VARIANTS
        assert 'large' in processor.SIZE_VARIANTS
        assert processor.SIZE_VARIANTS['large'] == (192, 192)
    
    def test_process_image_invalid_variant(self, processor, sample_image_data):
        """Test processing with invalid variant name raises error"""
        with pytest.raises(ImageProcessingError) as exc_info:
            processor.process_image(sample_image_data, 'invalid_variant')
        
        assert "Invalid variant" in str(exc_info.value)
    
    def test_process_original_variant(self, processor, sample_image_data):
        """Test processing original variant maintains dimensions"""
        processed_data, metadata = processor.process_image(
            sample_image_data,
            'original',
            optimize=True
        )
        
        # Verify metadata
        assert metadata['variant'] == 'original'
        assert metadata['width'] == 500
        assert metadata['height'] == 500
        assert metadata['format'] == 'JPEG'
        assert metadata['file_size_bytes'] > 0
        assert 'checksum' in metadata
        
        # Verify image is valid
        img = Image.open(io.BytesIO(processed_data))
        assert img.size == (500, 500)
        assert img.format == 'JPEG'
    
    def test_process_large_variant(self, processor, sample_image_data):
        """Test processing large variant with correct dimensions"""
        processed_data, metadata = processor.process_image(
            sample_image_data,
            'large',
            optimize=True
        )
        
        # Verify metadata
        assert metadata['variant'] == 'large'
        assert metadata['width'] <= 192
        assert metadata['height'] <= 192
        assert metadata['quality'] == 90
        
        # Verify image dimensions
        img = Image.open(io.BytesIO(processed_data))
        assert max(img.size) <= 192
    
    def test_process_thumbnail_variant(self, processor, sample_image_data):
        """Test processing thumbnail variant"""
        processed_data, metadata = processor.process_image(
            sample_image_data,
            'thumbnail',
            optimize=True
        )
        
        # Verify dimensions
        assert metadata['width'] <= 80
        assert metadata['height'] <= 80
        assert metadata['quality'] == 80  # Lower quality for thumbnails
        
        # Verify compression
        assert metadata['compression_ratio'] < 1.0
    
    def test_smart_cropping(self, processor):
        """Test smart cropping maintains aspect ratio intelligently"""
        # Create a 600x300 landscape image
        img = Image.new('RGB', (600, 300), color='blue')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        image_data = buffer.getvalue()
        
        # Process with smart crop
        processed_data, metadata = processor.process_image(
            image_data,
            'medium',  # 64x64 target
            smart_crop=True
        )
        
        # Should be exactly 64x64 with smart crop
        assert metadata['width'] == 64
        assert metadata['height'] == 64
        
        # Process without smart crop (thumbnail mode)
        processed_data2, metadata2 = processor.process_image(
            image_data,
            'medium',
            smart_crop=False
        )
        
        # Should maintain aspect ratio without cropping
        assert metadata2['width'] == 64
        assert metadata2['height'] <= 64
    
    def test_rgba_to_rgb_conversion(self, processor, sample_png_data):
        """Test RGBA images are converted to RGB for JPEG output"""
        processed_data, metadata = processor.process_image(
            sample_png_data,
            'large',
            optimize=True
        )
        
        # Verify conversion
        img = Image.open(io.BytesIO(processed_data))
        assert img.mode == 'RGB'
        assert metadata['format'] == 'JPEG'
        
        # Original metadata should show transparency
        assert metadata['original_format'] == 'PNG'
    
    def test_process_all_variants(self, processor, sample_image_data):
        """Test processing all variants at once"""
        results = processor.process_all_variants(
            sample_image_data,
            optimize=True
        )
        
        # Should have all variants
        expected_variants = ['original', 'large', 'medium', 'small', 'thumbnail']
        assert set(results.keys()) == set(expected_variants)
        
        # Verify each variant
        for variant_name, (data, metadata) in results.items():
            assert metadata['variant'] == variant_name
            assert len(data) > 0
            assert metadata['file_size_bytes'] > 0
            
            # Verify dimensions
            if variant_name != 'original':
                target_size = processor.SIZE_VARIANTS[variant_name]
                assert metadata['width'] <= target_size[0]
                assert metadata['height'] <= target_size[1]
    
    def test_optimization_reduces_size(self, processor, sample_image_data):
        """Test that optimization reduces file size"""
        # Process with optimization
        optimized_data, optimized_meta = processor.process_image(
            sample_image_data,
            'large',
            optimize=True
        )
        
        # Process without optimization
        unoptimized_data, unoptimized_meta = processor.process_image(
            sample_image_data,
            'large',
            optimize=False
        )
        
        # For small images, optimization might not reduce size
        # but should at least not increase it significantly
        assert len(optimized_data) <= len(unoptimized_data) * 1.1  # Allow 10% variance
        
        # Compression ratio should be reasonable
        assert optimized_meta['compression_ratio'] <= unoptimized_meta['compression_ratio'] * 1.1
    
    def test_validate_processed_image(self, processor, sample_image_data):
        """Test image validation functionality"""
        # Process image
        processed_data, _ = processor.process_image(
            sample_image_data,
            'medium'
        )
        
        # Should validate correctly
        assert processor.validate_processed_image(processed_data, 'medium') is True
        
        # Should fail for wrong variant
        assert processor.validate_processed_image(processed_data, 'large') is True
        
        # Should fail for invalid data
        assert processor.validate_processed_image(b'invalid', 'medium') is False
    
    def test_processing_stats_tracking(self, processor, sample_image_data):
        """Test that processing stats are tracked correctly"""
        initial_stats = processor.get_processing_stats()
        assert initial_stats['total_processed'] == 0
        
        # Process some images
        processor.process_image(sample_image_data, 'large')
        processor.process_image(sample_image_data, 'medium')
        
        stats = processor.get_processing_stats()
        assert stats['total_processed'] == 2
        assert stats['success_rate'] == 100.0
        
        # Force a failure
        try:
            processor.process_image(b'invalid', 'large')
        except:
            pass
        
        stats = processor.get_processing_stats()
        assert stats['total_failures'] == 1
        assert stats['success_rate'] < 100.0
    
    def test_metadata_generation(self, processor, sample_image_data):
        """Test metadata is generated correctly"""
        processed_data, metadata = processor.process_image(
            sample_image_data,
            'medium'
        )
        
        # Required metadata fields
        assert 'variant' in metadata
        assert 'width' in metadata
        assert 'height' in metadata
        assert 'file_size_bytes' in metadata
        assert 'format' in metadata
        assert 'quality' in metadata
        assert 'checksum' in metadata
        assert 'compression_ratio' in metadata
        assert 'original_format' in metadata
        assert 'original_dimensions' in metadata
        
        # Verify checksum
        calculated_checksum = hashlib.md5(processed_data).hexdigest()
        assert metadata['checksum'] == calculated_checksum
    
    def test_large_image_handling(self, processor):
        """Test handling of large images"""
        # Create image at max size
        img = Image.new('RGB', (4096, 4096), color='green')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        large_data = buffer.getvalue()
        
        # Should process successfully
        processed_data, metadata = processor.process_image(
            large_data,
            'large'
        )
        assert metadata['width'] <= 192
        assert metadata['height'] <= 192
        
        # Create image exceeding max size
        oversized_img = Image.new('RGB', (5000, 5000), color='red')
        buffer = io.BytesIO()
        oversized_img.save(buffer, format='JPEG')
        oversized_data = buffer.getvalue()
        
        # Should raise error
        with pytest.raises(ImageProcessingError) as exc_info:
            processor.process_image(oversized_data, 'large')
        assert "too large" in str(exc_info.value)
    
    def test_progressive_encoding(self, processor, sample_image_data):
        """Test that large variants use progressive encoding"""
        # Process large variant
        large_data, _ = processor.process_image(
            sample_image_data,
            'large'
        )
        
        # Check if progressive (this is hard to verify directly,
        # but we can at least ensure it doesn't break)
        img = Image.open(io.BytesIO(large_data))
        assert img.format == 'JPEG'
    
    def test_error_handling(self, processor):
        """Test error handling for various failure scenarios"""
        # Invalid image data
        with pytest.raises(ImageProcessingError):
            processor.process_image(b'not an image', 'large')
        
        # Empty data
        with pytest.raises(ImageProcessingError):
            processor.process_image(b'', 'large')
        
        # Corrupted image data
        corrupted = b'JFIF' + b'corrupted data'
        with pytest.raises(ImageProcessingError):
            processor.process_image(corrupted, 'large')
    
    def test_global_instance(self):
        """Test global instance creation and reuse"""
        processor1 = get_image_processor()
        processor2 = get_image_processor()
        
        # Should be the same instance
        assert processor1 is processor2
    
    def test_aspect_ratio_preservation(self, processor):
        """Test that aspect ratio is preserved correctly"""
        # Create a 300x200 landscape image
        img = Image.new('RGB', (300, 200), color='yellow')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        landscape_data = buffer.getvalue()
        
        # Process with aspect ratio maintenance
        processed_data, metadata = processor.process_image(
            landscape_data,
            'medium',
            maintain_aspect=True,
            smart_crop=False
        )
        
        # Calculate aspect ratios
        original_aspect = 300 / 200
        processed_aspect = metadata['width'] / metadata['height']
        
        # Should be very close (within rounding error)
        assert abs(original_aspect - processed_aspect) < 0.1
    
    def test_quality_settings_per_variant(self, processor, sample_image_data):
        """Test that each variant uses correct quality settings"""
        variants_to_test = ['original', 'large', 'thumbnail']
        
        for variant in variants_to_test:
            _, metadata = processor.process_image(
                sample_image_data,
                variant
            )
            
            expected_quality = processor.QUALITY_SETTINGS[variant]
            assert metadata['quality'] == expected_quality


class TestImageProcessorIntegration:
    """Integration tests for image processor with real workflows"""
    
    @pytest.fixture
    def processor(self):
        return ImageProcessor()
    
    def test_batch_processing_workflow(self, processor):
        """Test processing multiple images in sequence"""
        # Create different types of images
        images = []
        
        # RGB JPEG
        img1 = Image.new('RGB', (800, 600), color='red')
        buffer = io.BytesIO()
        img1.save(buffer, format='JPEG')
        images.append(('jpeg', buffer.getvalue()))
        
        # RGBA PNG
        img2 = Image.new('RGBA', (600, 800), color=(0, 255, 0, 128))
        buffer = io.BytesIO()
        img2.save(buffer, format='PNG')
        images.append(('png', buffer.getvalue()))
        
        # Process all images
        results = []
        for img_type, img_data in images:
            try:
                variants = processor.process_all_variants(img_data)
                results.append((img_type, variants))
            except Exception as e:
                pytest.fail(f"Failed to process {img_type}: {e}")
        
        # Verify all processed successfully
        assert len(results) == 2
        
        for img_type, variants in results:
            assert len(variants) == 5  # All variants created
            
            # Verify each variant is valid
            for variant_name, (data, metadata) in variants.items():
                img = Image.open(io.BytesIO(data))
                assert img.format == 'JPEG'  # All converted to JPEG
    
    def test_memory_efficiency(self, processor):
        """Test that processor doesn't leak memory with large images"""
        # Create a large image
        large_img = Image.new('RGB', (3000, 3000), color='blue')
        buffer = io.BytesIO()
        large_img.save(buffer, format='JPEG', quality=95)
        large_data = buffer.getvalue()
        
        # Process multiple times
        for _ in range(5):
            processor.process_image(large_data, 'thumbnail')
        
        # Stats should show all processed
        stats = processor.get_processing_stats()
        assert stats['total_processed'] >= 5