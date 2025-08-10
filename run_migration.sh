#!/bin/bash

# Artwork Cache Migration Runner
# This script runs the artwork cache migration in the background

echo "======================================"
echo "Artwork Cache Migration"
echo "======================================"

# Check for command line arguments
if [ "$1" == "--help" ]; then
    echo "Usage: ./run_migration.sh [options]"
    echo "Options:"
    echo "  --reset    Reset progress and start fresh"
    echo "  --status   Check migration status"
    echo "  --help     Show this help message"
    exit 0
fi

if [ "$1" == "--status" ]; then
    if [ -f "logs/artwork_migration_progress.json" ]; then
        echo "Migration Status:"
        python -c "
import json
with open('logs/artwork_migration_progress.json', 'r') as f:
    p = json.load(f)
    print(f\"Progress: {p['processed']}/{p['total']} albums processed\")
    print(f\"Failed: {len(p.get('failed_album_ids', {}))} albums\")
    if p['processed'] < p['total']:
        print(f\"Remaining: {p['total'] - p['processed']} albums\")
        print('Status: In progress (run script to continue)')
    else:
        print('Status: Complete!')
"
    else
        echo "No migration in progress"
    fi
    
    if [ -f "logs/artwork_migration_report.json" ]; then
        echo ""
        echo "Last migration report:"
        python -c "
import json
from datetime import datetime
with open('logs/artwork_migration_report.json', 'r') as f:
    r = json.load(f)
    if r.get('completed_at'):
        print(f\"Completed at: {r['completed_at']}\")
    print(f\"Albums cached: {r.get('cached', 0)}\")
    print(f\"Failed: {r.get('failed', 0)}\")
    print(f\"Total size: {r.get('bytes_cached', 0) / (1024*1024):.2f} MB\")
    print(f\"Processing time: {r.get('processing_time_seconds', 0) / 60:.1f} minutes\")
"
    fi
    exit 0
fi

if [ "$1" == "--reset" ]; then
    echo "Resetting migration progress..."
    rm -f logs/artwork_migration_progress.json
    echo "Progress reset. Migration will start from beginning."
fi

# Check Python availability
if ! command -v python &> /dev/null; then
    echo "Error: Python is not installed or not in PATH"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if migration is already complete
if [ -f "logs/artwork_migration_progress.json" ]; then
    python -c "
import json
with open('logs/artwork_migration_progress.json', 'r') as f:
    p = json.load(f)
    if p['processed'] >= p['total']:
        print('Migration already complete!')
        print(f\"All {p['total']} albums have been processed.\")
        print('Use --reset to start over.')
        exit(1)
"
    if [ $? -eq 1 ]; then
        exit 0
    fi
    echo "Resuming migration from previous progress..."
else
    echo "Starting new migration..."
fi

# Run the migration
echo ""
echo "Running migration (this may take a while)..."
echo "Check logs/artwork_migration.log for detailed progress"
echo ""

# Run in background with nohup
nohup python migrate_artwork_cache.py > logs/migration_output.log 2>&1 &
MIGRATION_PID=$!

echo "Migration started in background (PID: $MIGRATION_PID)"
echo ""
echo "Commands:"
echo "  ./run_migration.sh --status   Check progress"
echo "  tail -f logs/artwork_migration.log   Watch detailed logs"
echo "  kill $MIGRATION_PID   Stop migration"
echo ""
echo "The migration will continue even if you close this terminal."