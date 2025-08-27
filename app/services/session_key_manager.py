"""
Session key management for persistent JWT signing across restarts.
Ensures sessions survive application/container restarts.
"""

import os
import secrets
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionKeyManager:
    """Manages the SESSION_SECRET_KEY with automatic persistence."""
    
    KEY_FILE_PATH = "data/.session_key"
    _instance_key = None
    
    @classmethod
    def get_or_create_key(cls) -> str:
        """
        Get the session secret key with the following priority:
        1. From environment variable SESSION_SECRET_KEY
        2. From persistent file (for Docker/production)
        3. Generate new and save to file
        
        This ensures sessions survive restarts even without explicit configuration.
        """
        if cls._instance_key:
            return cls._instance_key
        
        # Priority 1: Environment variable
        env_key = os.getenv("SESSION_SECRET_KEY")
        if env_key:
            logger.info("Using SESSION_SECRET_KEY from environment variable")
            cls._instance_key = env_key
            return env_key
        
        # Priority 2: Persistent file (create data dir if needed)
        key_file = Path(cls.KEY_FILE_PATH)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        
        if key_file.exists():
            try:
                with open(key_file, 'r') as f:
                    stored_key = f.read().strip()
                if stored_key:
                    logger.info(f"Using persisted SESSION_SECRET_KEY from {cls.KEY_FILE_PATH}")
                    cls._instance_key = stored_key
                    return stored_key
            except Exception as e:
                logger.error(f"Error reading session key file: {e}")
        
        # Priority 3: Generate new key and persist it
        new_key = secrets.token_hex(32)
        try:
            with open(key_file, 'w') as f:
                f.write(new_key)
            # Make file readable only by owner
            os.chmod(key_file, 0o600)
            logger.warning(f"Generated new SESSION_SECRET_KEY and saved to {cls.KEY_FILE_PATH}")
            logger.warning("This is normal on first run, but sessions from previous instances will be invalidated.")
        except Exception as e:
            logger.error(f"Failed to save session key to file: {e}")
            logger.warning("Sessions will not survive restarts without SESSION_SECRET_KEY in environment!")
        
        cls._instance_key = new_key
        return new_key
    
    @classmethod
    def rotate_key(cls, backup: bool = True) -> str:
        """
        Rotate the session key (invalidates all existing sessions).
        
        Args:
            backup: If True, backs up the old key before rotating
            
        Returns:
            The new session key
        """
        key_file = Path(cls.KEY_FILE_PATH)
        
        # Backup old key if requested
        if backup and key_file.exists():
            backup_file = key_file.with_suffix('.backup')
            try:
                with open(key_file, 'r') as f:
                    old_key = f.read()
                with open(backup_file, 'w') as f:
                    f.write(old_key)
                os.chmod(backup_file, 0o600)
                logger.info(f"Backed up old key to {backup_file}")
            except Exception as e:
                logger.error(f"Failed to backup old key: {e}")
        
        # Generate and save new key
        new_key = secrets.token_hex(32)
        try:
            with open(key_file, 'w') as f:
                f.write(new_key)
            os.chmod(key_file, 0o600)
            logger.warning("SESSION_SECRET_KEY rotated - all existing sessions are now invalid")
        except Exception as e:
            logger.error(f"Failed to save new session key: {e}")
            raise
        
        cls._instance_key = new_key
        return new_key