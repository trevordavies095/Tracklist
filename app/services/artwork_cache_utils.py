"""
Artwork cache file system utilities
Handles directory initialization, path generation, and file management
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ArtworkCacheFileSystem:
    """Manages the artwork cache file system structure"""
    
    # Size variant specifications
    SIZE_SPECS = {
        'original': None,  # Keep original dimensions
        'large': (192, 192),
        'medium': (64, 64),
        'small': (48, 48),
        'thumbnail': (80, 80)
    }
    
    def __init__(self, base_path: str = "static/artwork_cache"):
        """
        Initialize the artwork cache file system manager
        
        Args:
            base_path: Base directory for artwork cache
        """
        self.base_path = Path(base_path)
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure all required directories exist with proper permissions"""
        try:
            # Create base directory
            self.base_path.mkdir(parents=True, exist_ok=True)
            
            # Create size-specific subdirectories
            for size_variant in self.SIZE_SPECS.keys():
                dir_path = self.base_path / size_variant
                dir_path.mkdir(exist_ok=True)
                
                # Set permissions (755 for directories)
                try:
                    os.chmod(dir_path, 0o755)
                except Exception as e:
                    logger.debug(f"Could not set permissions for {dir_path}: {e}")
            
            logger.info(f"Artwork cache directories initialized at {self.base_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize artwork cache directories: {e}")
            raise
    
    def generate_cache_key(self, album_id: int, musicbrainz_id: str) -> str:
        """
        Generate a unique cache key for an album
        
        Args:
            album_id: Database album ID
            musicbrainz_id: MusicBrainz release ID
            
        Returns:
            16-character cache key
        """
        # Create a unique string from album data
        # Match the format used in artwork_cache_service.py
        unique_string = f"{musicbrainz_id}_{album_id}"
        
        # Generate MD5 hash and take first 16 characters
        cache_key = hashlib.md5(unique_string.encode()).hexdigest()[:16]
        
        return cache_key
    
    def get_cache_path(self, cache_key: str, size_variant: str, extension: str = "jpg") -> Path:
        """
        Get the full file path for a cached image
        
        Args:
            cache_key: Unique cache key
            size_variant: Size variant (original, large, medium, small, thumbnail)
            extension: File extension (jpg, png, etc.)
            
        Returns:
            Full path to the cache file
        """
        if size_variant not in self.SIZE_SPECS:
            raise ValueError(f"Invalid size variant: {size_variant}")
        
        # Remove leading dot from extension if present
        if extension.startswith('.'):
            extension = extension[1:]
        
        filename = f"{cache_key}.{extension}"
        return self.base_path / size_variant / filename
    
    def get_web_path(self, cache_key: str, size_variant: str, extension: str = "jpg") -> str:
        """
        Get the web-accessible path for a cached image
        
        Args:
            cache_key: Unique cache key
            size_variant: Size variant
            extension: File extension
            
        Returns:
            Web path (e.g., /static/artwork_cache/medium/abc123.jpg)
        """
        cache_path = self.get_cache_path(cache_key, size_variant, extension)
        # Convert to web path
        return f"/{cache_path}"
    
    def exists(self, cache_key: str, size_variant: str, extension: str = "jpg") -> bool:
        """
        Check if a cached image exists
        
        Args:
            cache_key: Unique cache key
            size_variant: Size variant
            extension: File extension
            
        Returns:
            True if the file exists
        """
        cache_path = self.get_cache_path(cache_key, size_variant, extension)
        return cache_path.exists()
    
    def get_file_info(self, cache_key: str, size_variant: str, extension: str = "jpg") -> Optional[Dict]:
        """
        Get information about a cached file
        
        Args:
            cache_key: Unique cache key
            size_variant: Size variant
            extension: File extension
            
        Returns:
            Dictionary with file information or None if not found
        """
        cache_path = self.get_cache_path(cache_key, size_variant, extension)
        
        if not cache_path.exists():
            return None
        
        try:
            stat = cache_path.stat()
            return {
                "path": str(cache_path),
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime),
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
                "accessed_at": datetime.fromtimestamp(stat.st_atime)
            }
        except Exception as e:
            logger.error(f"Failed to get file info for {cache_path}: {e}")
            return None
    
    def delete_cache(self, cache_key: str, size_variant: Optional[str] = None) -> int:
        """
        Delete cached images
        
        Args:
            cache_key: Unique cache key
            size_variant: Specific size to delete, or None for all sizes
            
        Returns:
            Number of files deleted
        """
        deleted_count = 0
        
        variants_to_delete = [size_variant] if size_variant else self.SIZE_SPECS.keys()
        
        for variant in variants_to_delete:
            # Try common extensions
            for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                cache_path = self.get_cache_path(cache_key, variant, ext)
                if cache_path.exists():
                    try:
                        cache_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted cache file: {cache_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete {cache_path}: {e}")
        
        return deleted_count
    
    def get_cache_statistics(self) -> Dict:
        """
        Get statistics about the cache directory
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "total_files": 0,
            "total_size_mb": 0,
            "by_variant": {}
        }
        
        for size_variant in self.SIZE_SPECS.keys():
            variant_path = self.base_path / size_variant
            
            if not variant_path.exists():
                stats["by_variant"][size_variant] = {
                    "files": 0,
                    "size_mb": 0
                }
                continue
            
            files = list(variant_path.glob("*"))
            # Filter out .gitkeep files
            files = [f for f in files if f.name != '.gitkeep']
            
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            
            stats["by_variant"][size_variant] = {
                "files": len(files),
                "size_mb": round(total_size / (1024 * 1024), 2)
            }
            
            stats["total_files"] += len(files)
            stats["total_size_mb"] += stats["by_variant"][size_variant]["size_mb"]
        
        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        
        return stats
    
    def cleanup_orphaned_files(self, valid_cache_keys: set) -> int:
        """
        Remove cached files that don't match any valid cache keys
        
        Args:
            valid_cache_keys: Set of valid cache keys from database
            
        Returns:
            Number of files deleted
        """
        deleted_count = 0
        
        for size_variant in self.SIZE_SPECS.keys():
            variant_path = self.base_path / size_variant
            
            if not variant_path.exists():
                continue
            
            for file_path in variant_path.glob("*"):
                if file_path.name == '.gitkeep':
                    continue
                
                # Extract cache key from filename
                cache_key = file_path.stem  # Remove extension
                
                if cache_key not in valid_cache_keys:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted orphaned file: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete orphaned file {file_path}: {e}")
        
        return deleted_count
    
    def verify_structure(self) -> Tuple[bool, list]:
        """
        Verify the cache directory structure
        
        Returns:
            Tuple of (success, list of issues)
        """
        issues = []
        
        # Check base directory
        if not self.base_path.exists():
            issues.append(f"Base directory does not exist: {self.base_path}")
        elif not self.base_path.is_dir():
            issues.append(f"Base path is not a directory: {self.base_path}")
        
        # Check subdirectories
        for size_variant in self.SIZE_SPECS.keys():
            variant_path = self.base_path / size_variant
            
            if not variant_path.exists():
                issues.append(f"Missing directory: {variant_path}")
            elif not variant_path.is_dir():
                issues.append(f"Not a directory: {variant_path}")
            elif not os.access(variant_path, os.W_OK):
                issues.append(f"Directory not writable: {variant_path}")
        
        return len(issues) == 0, issues


# Global instance
_cache_fs = None


def get_cache_filesystem() -> ArtworkCacheFileSystem:
    """Get or create the global cache filesystem instance"""
    global _cache_fs
    if _cache_fs is None:
        _cache_fs = ArtworkCacheFileSystem()
    return _cache_fs


def init_artwork_cache_directories():
    """Initialize artwork cache directories (called on app startup)"""
    try:
        fs = get_cache_filesystem()
        success, issues = fs.verify_structure()
        
        if success:
            logger.info("Artwork cache directory structure verified successfully")
        else:
            logger.warning(f"Artwork cache directory issues found: {issues}")
            # Try to fix by recreating directories
            fs._ensure_directories()
        
        # Log statistics
        stats = fs.get_cache_statistics()
        logger.info(f"Artwork cache statistics: {stats['total_files']} files, {stats['total_size_mb']}MB")
        
    except Exception as e:
        logger.error(f"Failed to initialize artwork cache directories: {e}")
        # Don't fail the app startup, just log the error
        pass