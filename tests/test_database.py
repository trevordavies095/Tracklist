import pytest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import create_tables, init_db, get_db
from app.models import Base, UserSettings


class TestDatabase:
    def test_create_tables(self):
        """Test database table creation"""
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp()
        database_url = f"sqlite:///{db_path}"
        
        try:
            engine = create_engine(database_url, connect_args={"check_same_thread": False})
            
            # Override the engine in the database module temporarily
            import app.database
            original_engine = app.database.engine
            app.database.engine = engine
            
            # Test table creation
            create_tables()
            
            # Verify tables exist by checking metadata
            Base.metadata.bind = engine
            from sqlalchemy import inspect
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            expected_tables = ['artists', 'albums', 'tracks', 'user_settings']
            for table in expected_tables:
                assert table in tables
            
            # Restore original engine
            app.database.engine = original_engine
            
        finally:
            os.close(db_fd)
            os.unlink(db_path)

    def test_init_db(self):
        """Test database initialization with default data"""
        # Create temporary database
        db_fd, db_path = tempfile.mkstemp()
        database_url = f"sqlite:///{db_path}"
        
        try:
            engine = create_engine(database_url, connect_args={"check_same_thread": False})
            TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            
            # Override the database module components temporarily
            import app.database
            original_engine = app.database.engine
            original_session = app.database.SessionLocal
            
            app.database.engine = engine
            app.database.SessionLocal = TestingSessionLocal
            
            # Create tables and initialize
            create_tables()
            init_db()
            
            # Verify default settings were created
            session = TestingSessionLocal()
            try:
                settings = session.query(UserSettings).filter(UserSettings.user_id == 1).first()
                assert settings is not None
                assert settings.album_bonus == 0.25
                assert settings.theme == 'light'
            finally:
                session.close()
            
            # Test that init_db doesn't create duplicate settings
            init_db()
            session = TestingSessionLocal()
            try:
                settings_count = session.query(UserSettings).filter(UserSettings.user_id == 1).count()
                assert settings_count == 1
            finally:
                session.close()
            
            # Restore original components
            app.database.engine = original_engine
            app.database.SessionLocal = original_session
            
        finally:
            os.close(db_fd)
            os.unlink(db_path)

    def test_get_db_dependency(self):
        """Test the get_db dependency function"""
        db_generator = get_db()
        db_session = next(db_generator)
        
        # Should be a valid session
        assert db_session is not None
        assert hasattr(db_session, 'query')
        assert hasattr(db_session, 'add')
        assert hasattr(db_session, 'commit')
        
        # Clean up
        try:
            next(db_generator)
        except StopIteration:
            pass  # Expected behavior