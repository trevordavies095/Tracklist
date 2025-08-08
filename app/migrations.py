"""
Database migration handler for automatic schema updates
Handles migration of existing databases when deploying new versions
"""

import logging
from typing import Optional, List
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


class MigrationHandler:
    """Handles automatic database migrations on startup"""
    
    def __init__(self, engine):
        self.engine = engine
        self.inspector = inspect(engine)
    
    def run_migrations(self):
        """Run all necessary migrations"""
        logger.info("Checking for necessary database migrations...")
        
        migrations_applied = []
        
        # Check and apply migrations for albums table
        if self.table_exists('albums'):
            if self.add_column_if_missing('albums', 'notes', 'TEXT'):
                migrations_applied.append("Added 'notes' column to albums table")
            
            if self.add_column_if_missing('albums', 'cover_art_local_path', 'TEXT'):
                migrations_applied.append("Added 'cover_art_local_path' column to albums table")
        
        if migrations_applied:
            logger.info(f"Applied {len(migrations_applied)} migrations:")
            for migration in migrations_applied:
                logger.info(f"  - {migration}")
        else:
            logger.info("No migrations needed - database schema is up to date")
        
        return migrations_applied
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database"""
        return self.inspector.has_table(table_name)
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table"""
        if not self.table_exists(table_name):
            return False
        
        columns = [col['name'] for col in self.inspector.get_columns(table_name)]
        return column_name in columns
    
    def add_column_if_missing(self, table_name: str, column_name: str, column_type: str) -> bool:
        """
        Add a column to a table if it doesn't exist
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to add
            column_type: SQL type of the column (e.g., 'TEXT', 'INTEGER')
            
        Returns:
            True if column was added, False if it already existed
        """
        if self.column_exists(table_name, column_name):
            return False
        
        try:
            with self.engine.connect() as conn:
                # Use ALTER TABLE to add the column
                sql = text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                conn.execute(sql)
                conn.commit()
                logger.info(f"Successfully added column '{column_name}' to table '{table_name}'")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add column '{column_name}' to table '{table_name}': {e}")
            raise
    
    def get_schema_version(self) -> Optional[str]:
        """
        Get the current schema version from alembic_version table if it exists
        
        Returns:
            Version string or None if alembic is not set up
        """
        if not self.table_exists('alembic_version'):
            return None
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = result.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.warning(f"Could not read alembic version: {e}")
            return None
    
    def ensure_alembic_version(self):
        """
        Ensure alembic_version table exists and is populated for future migrations
        This helps transition from manual migrations to alembic-based migrations
        """
        if not self.table_exists('alembic_version'):
            try:
                with self.engine.connect() as conn:
                    # Create alembic_version table
                    conn.execute(text("""
                        CREATE TABLE alembic_version (
                            version_num VARCHAR(32) NOT NULL,
                            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                        )
                    """))
                    
                    # Set to latest migration version
                    # This assumes all manual migrations have been applied
                    conn.execute(text("""
                        INSERT INTO alembic_version (version_num) 
                        VALUES ('371b310012dc')
                    """))
                    conn.commit()
                    logger.info("Created alembic_version table for future migrations")
            except Exception as e:
                # Table might already exist or other issue
                logger.debug(f"Could not create alembic_version table: {e}")


def run_migrations(engine):
    """
    Main migration runner - call this on application startup
    
    Args:
        engine: SQLAlchemy engine instance
    """
    handler = MigrationHandler(engine)
    migrations = handler.run_migrations()
    
    # Ensure alembic is set up for future migrations
    handler.ensure_alembic_version()
    
    return migrations