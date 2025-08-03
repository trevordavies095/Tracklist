import pytest
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import Base


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database"""
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp()
    database_url = f"sqlite:///{db_path}"
    
    # Create engine and session
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    yield TestingSessionLocal, engine
    
    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope="function")
def db_session(test_db):
    """Get a database session for testing"""
    TestingSessionLocal, engine = test_db
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with test database"""
    TestingSessionLocal, engine = test_db
    
    # Import the FastAPI app instance
    from app.main import app as fastapi_app
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    fastapi_app.dependency_overrides[get_db] = override_get_db
    
    # Initialize database tables for testing
    from app.database import create_tables, init_db
    import app.database
    original_engine = app.database.engine
    original_session = app.database.SessionLocal
    
    app.database.engine = engine
    app.database.SessionLocal = TestingSessionLocal
    
    try:
        create_tables()
        init_db()
        
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        app.database.engine = original_engine
        app.database.SessionLocal = original_session
        fastapi_app.dependency_overrides.clear()