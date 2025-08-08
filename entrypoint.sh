#!/bin/bash
set -e

echo "Starting Tracklist application..."

# Run database migrations
echo "Running database migrations..."

# First check if alembic_version table exists and has invalid revision
if [ -f "./data/tracklist.db" ]; then
    # Check if alembic_version table exists
    HAS_ALEMBIC_TABLE=$(sqlite3 ./data/tracklist.db "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version';" 2>/dev/null || echo "")
    
    if [ ! -z "$HAS_ALEMBIC_TABLE" ]; then
        # Get current revision from database
        CURRENT_REV=$(sqlite3 ./data/tracklist.db "SELECT version_num FROM alembic_version;" 2>/dev/null || echo "")
        
        # Check if the revision exists in our migrations
        if [ ! -z "$CURRENT_REV" ] && [ ! -f "./alembic/versions/${CURRENT_REV}_*.py" ]; then
            echo "Warning: Database has unknown migration revision: $CURRENT_REV"
            echo "Clearing invalid revision and stamping with current migration..."
            sqlite3 ./data/tracklist.db "DELETE FROM alembic_version;"
        fi
    fi
fi

# Run migrations (this will create tables if they don't exist)
alembic upgrade head

# Start the application
echo "Starting Uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000