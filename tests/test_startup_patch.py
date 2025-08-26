"""
Patch startup events for testing.
This prevents background tasks from running during tests.
"""

import os
from unittest.mock import patch, AsyncMock

# Set testing environment variables
os.environ["TESTING"] = "true"
os.environ["DISABLE_BACKGROUND_TASKS"] = "true"
os.environ["DISABLE_SCHEDULED_TASKS"] = "true"
os.environ["AUTO_MIGRATE_ARTWORK"] = "false"

# Patch startup functions
def disable_startup_tasks():
    """Disable background tasks during testing."""
    import app.main as main_module
    
    # Replace startup event with no-op
    async def mock_startup():
        pass
    
    # Monkey patch the startup event
    if hasattr(main_module, 'startup_event'):
        main_module.startup_event = mock_startup
    
    # Patch background task imports
    with patch('app.services.background_tasks.start_background_tasks', new=AsyncMock()):
        with patch('app.services.scheduled_tasks.start_scheduled_tasks', new=AsyncMock()):
            pass

# Apply patches when imported
disable_startup_tasks()