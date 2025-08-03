from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
from pathlib import Path
from .models import Base
import logging

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tracklist.db")

# Create database directory if it doesn't exist
db_path = Path("./tracklist.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

# Create engine with proper SQLite configuration
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
    echo=False  # Set to True for SQL query logging
)

# Create sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database with default data"""
    from .models import UserSettings
    
    db = SessionLocal()
    try:
        # Create default user settings if they don't exist
        existing_settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if not existing_settings:
            default_settings = UserSettings(
                user_id=1,
                album_bonus=0.33,
                theme='light'
            )
            db.add(default_settings)
            db.commit()
            logger.info("Default user settings created")
        else:
            logger.info("Default user settings already exist")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()