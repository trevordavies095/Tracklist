#!/usr/bin/env python3
"""
Basic validation script for Phase 1 implementation
Tests core functionality without external dependencies
"""

import sys
import os
import tempfile
from pathlib import Path

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_models():
    """Test that models can be imported and created"""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models import Base, Artist, Album, Track, UserSettings
        
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp()
        database_url = f"sqlite:///{db_path}"
        
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Test basic model creation
        session = SessionLocal()
        
        # Test Artist
        artist = Artist(name="Test Artist", musicbrainz_id="test-id")
        session.add(artist)
        session.commit()
        
        # Test Album
        album = Album(
            artist_id=artist.id, 
            name="Test Album", 
            musicbrainz_id="test-album-id"
        )
        session.add(album)
        session.commit()
        
        # Test Track
        track = Track(
            album_id=album.id,
            track_number=1,
            name="Test Track"
        )
        session.add(track)
        session.commit()
        
        # Test UserSettings
        settings = UserSettings(user_id=1, album_bonus=0.25)
        session.add(settings)
        session.commit()
        
        # Verify relationships
        assert album.artist.name == "Test Artist"
        assert track.album.name == "Test Album"
        
        session.close()
        os.close(db_fd)
        os.unlink(db_path)
        
        print("✓ Models test passed")
        return True
        
    except Exception as e:
        print(f"✗ Models test failed: {e}")
        return False

def test_database():
    """Test database functionality"""
    try:
        from app.database import create_tables, init_db
        from app.models import Base, UserSettings
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp()
        database_url = f"sqlite:///{db_path}"
        
        # Override database configuration temporarily
        import app.database
        original_engine = app.database.engine
        original_session = app.database.SessionLocal
        
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        app.database.engine = engine
        app.database.SessionLocal = SessionLocal
        
        # Test table creation
        create_tables()
        
        # Test initialization
        init_db()
        
        # Verify default settings
        session = SessionLocal()
        settings = session.query(UserSettings).filter(UserSettings.user_id == 1).first()
        assert settings is not None
        assert settings.album_bonus == 0.25
        session.close()
        
        # Restore original configuration
        app.database.engine = original_engine
        app.database.SessionLocal = original_session
        
        os.close(db_fd)
        os.unlink(db_path)
        
        print("✓ Database test passed")
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_exceptions():
    """Test custom exceptions"""
    try:
        from app.exceptions import (
            TracklistException, NotFoundError, 
            ValidationError, ConflictError
        )
        
        # Test TracklistException
        exc = TracklistException("Test error", {"code": 123})
        assert exc.message == "Test error"
        assert exc.details["code"] == 123
        
        # Test HTTP exceptions
        not_found = NotFoundError("Album", "123")
        assert not_found.status_code == 404
        
        validation = ValidationError("Invalid", "field")
        assert validation.status_code == 400
        
        conflict = ConflictError("Conflict")
        assert conflict.status_code == 409
        
        print("✓ Exceptions test passed")
        return True
        
    except Exception as e:
        print(f"✗ Exceptions test failed: {e}")
        return False

def test_logging():
    """Test logging configuration"""
    try:
        from app.logging_config import setup_logging
        import logging
        
        # Test basic setup
        config = setup_logging(level="DEBUG")
        assert config["level"] == "DEBUG"
        
        # Test with file
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "test.log")
            config = setup_logging(level="INFO", log_file=log_file)
            
            # Test logging
            logger = logging.getLogger("test_logger")
            logger.info("Test message")
            
            # Verify file exists and has content
            assert Path(log_file).exists()
            with open(log_file, 'r') as f:
                content = f.read()
                assert "Test message" in content
        
        print("✓ Logging test passed")
        return True
        
    except Exception as e:
        print(f"✗ Logging test failed: {e}")
        return False

def test_app_structure():
    """Test application structure and imports"""
    try:
        # Test main app imports
        from app.main import app
        from app import models, database, exceptions, logging_config
        
        # Test FastAPI app configuration
        assert app.title == "Tracklist"
        assert app.version == "1.0.0"
        
        print("✓ App structure test passed")
        return True
        
    except Exception as e:
        print(f"✗ App structure test failed: {e}")
        return False

def main():
    """Run all Phase 1 validation tests"""
    print("Running Phase 1 validation tests...\n")
    
    tests = [
        test_app_structure,
        test_exceptions,
        test_logging,
        test_models,
        test_database,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Phase 1 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Phase 1 implementation validated successfully!")
        return True
    else:
        print("❌ Some Phase 1 tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)