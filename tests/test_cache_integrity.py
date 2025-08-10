"""
Tests for cache integrity verification service
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from PIL import Image
import io

from app.services.cache_integrity_service import CacheIntegrityService, CacheIntegrityError
from app.services.artwork_cache_utils import ArtworkCacheFileSystem
from app.models import Album, ArtworkCache


class TestCacheIntegrityService:
    """Test cache integrity verification functionality"""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def cache_fs(self, temp_cache_dir):
        """Create cache filesystem"""
        return ArtworkCacheFileSystem(base_path=str(temp_cache_dir))
    
    @pytest.fixture
    def integrity_service(self, cache_fs):
        """Create integrity service"""
        return CacheIntegrityService(cache_fs=cache_fs)
    
    def create_test_image(self, path: Path, size=(100, 100)):
        """Create a test image file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', size, color='red')
        img.save(path, 'JPEG')
        return path
    
    def test_verify_missing_files(self, integrity_service, temp_cache_dir):
        """Test detection of missing files"""
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            # Setup mock database records
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # Create mock cache records pointing to non-existent files
            mock_records = [
                Mock(
                    id=1,
                    album_id=1,
                    size_variant='medium',
                    file_path=str(temp_cache_dir / 'medium' / 'missing1.jpg'),
                    file_size_bytes=1000
                ),
                Mock(
                    id=2,
                    album_id=2,
                    size_variant='large',
                    file_path=str(temp_cache_dir / 'large' / 'missing2.jpg'),
                    file_size_bytes=2000
                )
            ]
            
            # Setup query chain for different calls
            query_mock = Mock()
            query_mock.filter.return_value = query_mock
            query_mock.limit.return_value = query_mock
            query_mock.all.return_value = mock_records
            
            # Special handling for different query types
            def query_side_effect(model=None):
                if model is Album:
                    album_query = Mock()
                    album_query.filter.return_value = album_query
                    album_query.limit.return_value = album_query
                    album_query.all.return_value = []
                    return album_query
                elif model is None or model is ArtworkCache:
                    return query_mock
                else:
                    # For ArtworkCache.file_path
                    file_query = Mock()
                    file_query.filter.return_value = file_query
                    file_query.all.return_value = []
                    return file_query
            
            mock_db.query.side_effect = query_side_effect
            
            # Run verification
            result = integrity_service.verify_integrity(repair=False)
            
            # Check results
            assert result['summary']['total_records'] == 2
            assert result['summary']['valid_files'] == 0
            assert result['issues']['missing_files'] == 2
            assert result['integrity_score'] == 0  # All files missing
    
    def test_detect_orphaned_files(self, integrity_service, temp_cache_dir):
        """Test detection of orphaned files not in database"""
        # Create orphaned files
        orphan1 = self.create_test_image(temp_cache_dir / 'medium' / 'orphan1.jpg')
        orphan2 = self.create_test_image(temp_cache_dir / 'large' / 'orphan2.jpg')
        
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # No database records (all files are orphaned)
            mock_db.query().filter().all.return_value = []
            mock_db.query(ArtworkCache.file_path).filter().all.return_value = []
            mock_db.query(Album).filter().all.return_value = []
            mock_db.query(Album).filter().limit().all.return_value = []
            
            # Run verification
            result = integrity_service.verify_integrity(repair=False)
            
            # Check results
            assert result['issues']['orphaned_files'] == 2
    
    def test_verify_file_integrity(self, integrity_service, temp_cache_dir):
        """Test verification of file integrity"""
        # Create valid and corrupted files
        valid_file = self.create_test_image(temp_cache_dir / 'medium' / 'valid.jpg')
        
        # Create corrupted file
        corrupted_file = temp_cache_dir / 'medium' / 'corrupted.jpg'
        corrupted_file.parent.mkdir(parents=True, exist_ok=True)
        corrupted_file.write_text("not an image")
        
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # Mock records for both files
            mock_records = [
                Mock(
                    id=1,
                    album_id=1,
                    size_variant='medium',
                    file_path=str(valid_file),
                    file_size_bytes=valid_file.stat().st_size
                ),
                Mock(
                    id=2,
                    album_id=2,
                    size_variant='medium',
                    file_path=str(corrupted_file),
                    file_size_bytes=corrupted_file.stat().st_size
                )
            ]
            
            mock_db.query().filter().all.return_value = mock_records
            mock_db.query().filter().limit().all.return_value = mock_records
            mock_db.query(ArtworkCache.file_path).filter().all.return_value = [
                (str(valid_file),), (str(corrupted_file),)
            ]
            mock_db.query(Album).filter().all.return_value = []
            
            # Run verification
            result = integrity_service.verify_integrity(repair=False)
            
            # Check results - should detect corrupted file
            assert result['issues']['corrupted_files'] == 1
            assert result['summary']['valid_files'] >= 1
    
    def test_check_missing_variants(self, integrity_service):
        """Test detection of missing size variants"""
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # Mock album with cached artwork
            mock_album = Mock(id=1, name='Test Album', artwork_cached=True)
            mock_db.query(Album).filter().all.return_value = [mock_album]
            mock_db.query(Album).filter().limit().all.return_value = [mock_album]
            
            # Mock that only 'medium' and 'original' variants exist
            mock_db.query(ArtworkCache.size_variant).filter().all.return_value = [
                ('medium',), ('original',)
            ]
            
            # Mock empty file checks
            mock_db.query().filter().all.return_value = []
            mock_db.query(ArtworkCache.file_path).filter().all.return_value = []
            
            # Run verification
            result = integrity_service.verify_integrity(repair=False)
            
            # Check results - should detect missing variants
            assert result['issues']['missing_variants'] == 1
            missing = result['details']['missing_variants'][0] if 'details' in result else None
            if missing:
                assert 'thumbnail' in missing['missing']
                assert 'small' in missing['missing']
                assert 'large' in missing['missing']
                assert missing['has_original'] is True
                assert missing['can_rebuild'] is True
    
    def test_repair_missing_files(self, integrity_service):
        """Test repair of missing file records"""
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # Mock missing file record
            mock_record = Mock(id=1, album_id=1, file_path='/missing/file.jpg')
            mock_db.query().filter().first.return_value = mock_record
            mock_db.query().filter().all.return_value = [mock_record]
            mock_db.query(ArtworkCache.file_path).filter().all.return_value = []
            mock_db.query(Album).filter().all.return_value = []
            mock_db.query(Album).filter().first.return_value = Mock(id=1)
            mock_db.query(ArtworkCache).filter().count.return_value = 0
            
            # Set up missing file in results
            integrity_service.results['missing_files'] = [
                {'record_id': 1, 'album_id': 1, 'file_path': '/missing/file.jpg'}
            ]
            
            # Run repair
            result = integrity_service.verify_integrity(repair=True)
            
            # Verify record was deleted
            mock_db.delete.assert_called_once_with(mock_record)
            mock_db.commit.assert_called()
    
    def test_repair_orphaned_files(self, integrity_service, temp_cache_dir):
        """Test removal of orphaned files"""
        # Create orphaned file
        orphan = self.create_test_image(temp_cache_dir / 'medium' / 'orphan.jpg')
        
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # No database records
            mock_db.query().filter().all.return_value = []
            mock_db.query(ArtworkCache.file_path).filter().all.return_value = []
            mock_db.query(Album).filter().all.return_value = []
            
            # Run verification with repair
            result = integrity_service.verify_integrity(repair=True)
            
            # Check file was removed
            assert not orphan.exists()
            assert result['summary']['repairs_completed'] > 0
    
    def test_quick_check(self, integrity_service, temp_cache_dir):
        """Test quick integrity check"""
        # Create some test files
        file1 = self.create_test_image(temp_cache_dir / 'medium' / 'test1.jpg')
        file2 = self.create_test_image(temp_cache_dir / 'large' / 'test2.jpg')
        
        with patch('app.services.cache_integrity_service.SessionLocal') as mock_session:
            mock_db = Mock()
            mock_session.return_value.__enter__.return_value = mock_db
            
            # Mock total records
            mock_db.query(ArtworkCache).count.return_value = 100
            
            # Mock sample records - mix of valid and missing
            mock_db.query().filter().order_by().limit().all.return_value = [
                Mock(file_path=str(file1)),  # Exists
                Mock(file_path=str(file2)),  # Exists
                Mock(file_path='/missing/file1.jpg'),  # Missing
                Mock(file_path='/missing/file2.jpg'),  # Missing
            ]
            
            # Run quick check
            result = integrity_service.quick_check()
            
            # Check results
            assert result['type'] == 'quick_check'
            assert result['sample_size'] == 4
            assert result['sample_valid'] == 2
            assert result['sample_missing'] == 2
            assert result['estimated_integrity_score'] == 50.0
            assert result['estimated_missing'] == 50
    
    def test_generate_report(self, integrity_service):
        """Test report generation"""
        # Set up some test results
        integrity_service.results = {
            'start_time': datetime.now(timezone.utc),
            'end_time': datetime.now(timezone.utc),
            'total_records': 100,
            'valid_files': 95,
            'missing_files': [{'record_id': 1}],
            'corrupted_files': [{'record_id': 2}],
            'orphaned_files': [{'file_path': '/orphan.jpg'}],
            'size_mismatches': [],
            'missing_variants': [{'album_id': 1}],
            'repaired_files': [{'type': 'removed_orphaned_file'}],
            'failed_repairs': [],
            'errors': []
        }
        
        # Generate report
        report = integrity_service._generate_report(verbose=True)
        
        # Check report structure
        assert 'timestamp' in report
        assert 'integrity_score' in report
        assert report['integrity_score'] == 96.0  # (100 - 4 issues) / 100 * 100
        assert report['summary']['total_records'] == 100
        assert report['summary']['valid_files'] == 95
        assert report['summary']['issues_found'] == 4
        assert report['summary']['repairs_completed'] == 1
        
        # Check issues breakdown
        assert report['issues']['missing_files'] == 1
        assert report['issues']['corrupted_files'] == 1
        assert report['issues']['orphaned_files'] == 1
        assert report['issues']['missing_variants'] == 1
        
        # Check verbose details included
        assert 'details' in report
        assert len(report['details']['missing_files']) == 1