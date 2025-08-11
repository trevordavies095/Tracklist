from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
from pathlib import Path
from .models import Base
import logging

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL with proper path handling"""
    # Check for custom database path
    db_path_env = os.getenv("TRACKLIST_DB_PATH")
    database_url = os.getenv("DATABASE_URL")

    if db_path_env:
        # User specified custom database path
        db_path = Path(db_path_env).resolve()

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to database URL format
        database_url = f"sqlite:///{db_path}"
        logger.info(f"Using custom database path: {db_path}")

    elif database_url:
        # Use provided DATABASE_URL
        if database_url.startswith("sqlite:///"):
            # Extract path from SQLite URL and ensure directory exists
            db_file_path = database_url.replace("sqlite:///", "")
            if not db_file_path.startswith("/"):
                # Relative path
                db_path = Path(db_file_path).resolve()
            else:
                # Absolute path
                db_path = Path(db_file_path)

            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using database path from DATABASE_URL: {db_path}")
    else:
        # Default fallback
        default_path = Path("./data/tracklist.db").resolve()
        default_path.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{default_path}"
        logger.info(f"Using default database path: {default_path}")

    return database_url


# Database configuration
DATABASE_URL = get_database_url()

# Create engine with proper SQLite configuration
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
    echo=False  # Set to True for SQL query logging
)

# Enable foreign key constraints for SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        logger.debug("SQLite foreign key constraints enabled")

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

    # First create all tables
    create_tables()

    # Note: Database migrations are handled by Alembic in entrypoint.sh

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

        logger.info(f"Database initialized successfully at: {DATABASE_URL}")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_db_info():
    """Get information about the current database"""
    if DATABASE_URL.startswith("sqlite:///"):
        db_file_path = DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_file_path)

        return {
            "type": "SQLite",
            "path": str(db_path.resolve()),
            "exists": db_path.exists(),
            "size": db_path.stat().st_size if db_path.exists() else 0,
            "readable": os.access(db_path.parent, os.R_OK) if db_path.parent.exists() else True,
            "writable": os.access(db_path.parent, os.W_OK) if db_path.parent.exists() else True
        }
    else:
        return {
            "type": "Other",
            "url": DATABASE_URL,
            "path": None
        }
