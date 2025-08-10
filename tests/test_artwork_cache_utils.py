"""
Unit tests for artwork cache filesystem utilities
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.artwork_cache_utils import (
    ArtworkCacheFileSystem,
    get_cache_filesystem,
    init_artwork_cache_directories
)


class TestArtworkCacheFileSystem:
    """Test the ArtworkCacheFileSystem class"""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def cache_fs(self, temp_cache_dir):
        """Create a cache filesystem instance with temp directory"""
        return ArtworkCacheFileSystem(base_path=temp_cache_dir)
    
    def test_directory_initialization(self, temp_cache_dir):
        """Test that directories are created on initialization"""
        cache_fs = ArtworkCacheFileSystem(base_path=temp_cache_dir)
        
        # Check that all size directories exist
        for size in ['original', 'large', 'medium', 'small', 'thumbnail']:
            dir_path = Path(temp_cache_dir) / size
            assert dir_path.exists()
            assert dir_path.is_dir()
    
    def test_generate_cache_key(self, cache_fs):
        """Test cache key generation"""
        key1 = cache_fs.generate_cache_key(1, "mb-123-456")
        key2 = cache_fs.generate_cache_key(1, "mb-123-456")
        key3 = cache_fs.generate_cache_key(2, "mb-123-456")
        
        # Same inputs should generate same key
        assert key1 == key2
        
        # Different inputs should generate different keys
        assert key1 != key3
        
        # Key should be 16 characters
        assert len(key1) == 16
    
    def test_get_cache_path(self, cache_fs, temp_cache_dir):
        """Test cache path generation"""
        cache_key = "test123"
        
        # Test different size variants
        path = cache_fs.get_cache_path(cache_key, "medium", "jpg")
        expected = Path(temp_cache_dir) / "medium" / "test123.jpg"
        assert path == expected
        
        # Test with different extension
        path = cache_fs.get_cache_path(cache_key, "large", "png")
        expected = Path(temp_cache_dir) / "large" / "test123.png"
        assert path == expected
        
        # Test with dot in extension
        path = cache_fs.get_cache_path(cache_key, "small", ".jpeg")
        expected = Path(temp_cache_dir) / "small" / "test123.jpeg"
        assert path == expected
    
    def test_get_cache_path_invalid_variant(self, cache_fs):
        """Test that invalid size variant raises error"""
        with pytest.raises(ValueError, match="Invalid size variant"):
            cache_fs.get_cache_path("test", "invalid_size", "jpg")
    
    def test_get_web_path(self, cache_fs, temp_cache_dir):
        """Test web path generation"""
        cache_key = "test123"
        web_path = cache_fs.get_web_path(cache_key, "medium", "jpg")
        
        # Should return a web-accessible path
        assert web_path.startswith("/")
        assert "medium/test123.jpg" in web_path
    
    def test_exists(self, cache_fs, temp_cache_dir):
        """Test file existence checking"""
        cache_key = "test123"
        
        # Should not exist initially
        assert not cache_fs.exists(cache_key, "medium", "jpg")
        
        # Create the file
        file_path = Path(temp_cache_dir) / "medium" / "test123.jpg"
        file_path.touch()
        
        # Should exist now
        assert cache_fs.exists(cache_key, "medium", "jpg")
    
    def test_get_file_info(self, cache_fs, temp_cache_dir):
        """Test getting file information"""
        cache_key = "test123"
        
        # Should return None for non-existent file
        info = cache_fs.get_file_info(cache_key, "medium", "jpg")
        assert info is None
        
        # Create a file with content
        file_path = Path(temp_cache_dir) / "medium" / "test123.jpg"
        file_path.write_bytes(b"test content")
        
        # Should return file info
        info = cache_fs.get_file_info(cache_key, "medium", "jpg")
        assert info is not None
        assert info["size_bytes"] == 12  # "test content" is 12 bytes
        assert "created_at" in info
        assert "modified_at" in info
        assert "accessed_at" in info
    
    def test_delete_cache(self, cache_fs, temp_cache_dir):
        """Test cache deletion"""
        cache_key = "test123"
        
        # Create files in multiple sizes
        for size in ["medium", "large"]:
            file_path = Path(temp_cache_dir) / size / f"{cache_key}.jpg"
            file_path.touch()
        
        # Delete specific size
        deleted = cache_fs.delete_cache(cache_key, "medium")
        assert deleted == 1
        assert not (Path(temp_cache_dir) / "medium" / f"{cache_key}.jpg").exists()
        assert (Path(temp_cache_dir) / "large" / f"{cache_key}.jpg").exists()
        
        # Delete all sizes
        deleted = cache_fs.delete_cache(cache_key)
        assert deleted == 1  # Only large remains
        assert not (Path(temp_cache_dir) / "large" / f"{cache_key}.jpg").exists()
    
    def test_get_cache_statistics(self, cache_fs, temp_cache_dir):
        """Test cache statistics generation"""
        # Create some test files
        for size in ["medium", "large"]:
            file_path = Path(temp_cache_dir) / size / "test.jpg"
            file_path.write_bytes(b"x" * 1024)  # 1KB file
        
        # Add .gitkeep files (should be ignored)
        for size in ["small", "thumbnail"]:
            gitkeep_path = Path(temp_cache_dir) / size / ".gitkeep"
            gitkeep_path.touch()
        
        stats = cache_fs.get_cache_statistics()
        
        assert stats["total_files"] == 2  # Only real files, not .gitkeep
        assert stats["by_variant"]["medium"]["files"] == 1
        assert stats["by_variant"]["large"]["files"] == 1
        assert stats["by_variant"]["small"]["files"] == 0  # .gitkeep ignored
    
    def test_cleanup_orphaned_files(self, cache_fs, temp_cache_dir):
        """Test cleanup of orphaned files"""
        # Create some files
        valid_key = "valid123"
        orphan_key = "orphan456"
        
        for key in [valid_key, orphan_key]:
            file_path = Path(temp_cache_dir) / "medium" / f"{key}.jpg"
            file_path.touch()
        
        # Create .gitkeep (should not be deleted)
        gitkeep_path = Path(temp_cache_dir) / "medium" / ".gitkeep"
        gitkeep_path.touch()
        
        # Clean up orphaned files
        valid_keys = {valid_key}
        deleted = cache_fs.cleanup_orphaned_files(valid_keys)
        
        assert deleted == 1
        assert (Path(temp_cache_dir) / "medium" / f"{valid_key}.jpg").exists()
        assert not (Path(temp_cache_dir) / "medium" / f"{orphan_key}.jpg").exists()
        assert gitkeep_path.exists()  # .gitkeep should remain
    
    def test_verify_structure(self, cache_fs, temp_cache_dir):
        """Test structure verification"""
        # Should pass initially
        success, issues = cache_fs.verify_structure()
        assert success
        assert len(issues) == 0
        
        # Remove a directory
        shutil.rmtree(Path(temp_cache_dir) / "medium")
        
        # Should fail now
        success, issues = cache_fs.verify_structure()
        assert not success
        assert len(issues) > 0
        assert any("Missing directory" in issue for issue in issues)


class TestGlobalFunctions:
    """Test global functions"""
    
    def test_get_cache_filesystem_singleton(self):
        """Test that get_cache_filesystem returns singleton"""
        fs1 = get_cache_filesystem()
        fs2 = get_cache_filesystem()
        assert fs1 is fs2
    
    @patch('app.services.artwork_cache_utils.logger')
    @patch('app.services.artwork_cache_utils.get_cache_filesystem')
    def test_init_artwork_cache_directories_success(self, mock_get_fs, mock_logger):
        """Test successful directory initialization"""
        mock_fs = MagicMock()
        mock_fs.verify_structure.return_value = (True, [])
        mock_fs.get_cache_statistics.return_value = {
            'total_files': 10,
            'total_size_mb': 5.5
        }
        mock_get_fs.return_value = mock_fs
        
        init_artwork_cache_directories()
        
        mock_fs.verify_structure.assert_called_once()
        mock_fs.get_cache_statistics.assert_called_once()
        mock_logger.info.assert_called()
    
    @patch('app.services.artwork_cache_utils.logger')
    @patch('app.services.artwork_cache_utils.get_cache_filesystem')
    def test_init_artwork_cache_directories_with_issues(self, mock_get_fs, mock_logger):
        """Test directory initialization with issues"""
        mock_fs = MagicMock()
        mock_fs.verify_structure.return_value = (False, ["Issue 1", "Issue 2"])
        mock_fs.get_cache_statistics.return_value = {
            'total_files': 0,
            'total_size_mb': 0
        }
        mock_get_fs.return_value = mock_fs
        
        init_artwork_cache_directories()
        
        mock_fs.verify_structure.assert_called_once()
        mock_fs._ensure_directories.assert_called_once()  # Should try to fix
        mock_logger.warning.assert_called()
    
    @patch('app.services.artwork_cache_utils.logger')
    @patch('app.services.artwork_cache_utils.get_cache_filesystem')
    def test_init_artwork_cache_directories_exception(self, mock_get_fs, mock_logger):
        """Test that initialization doesn't crash on exception"""
        mock_get_fs.side_effect = Exception("Test error")
        
        # Should not raise exception
        init_artwork_cache_directories()
        
        mock_logger.error.assert_called()