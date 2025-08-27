"""
Authentication service for secure password handling and session management.
All password operations are server-side only - passwords are NEVER sent to the client.
"""

import os
import bcrypt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from ..models import UserSettings
from .session_key_manager import SessionKeyManager

logger = logging.getLogger(__name__)


class AuthService:
    """
    Authentication service handling password management and sessions.
    
    SECURITY PRINCIPLES:
    - Passwords (hashed or plain) are NEVER sent to the client
    - All password operations happen server-side only
    - Session tokens use HttpOnly cookies (not accessible via JavaScript)
    - Generic error messages to prevent user enumeration
    """
    
    # JWT configuration
    _SECRET_KEY = None
    ALGORITHM = "HS256"
    DEFAULT_EXPIRY_DAYS = int(os.getenv("SESSION_EXPIRY_DAYS", "30"))
    REMEMBER_ME_DAYS = int(os.getenv("REMEMBER_ME_DAYS", "90"))
    
    @classmethod
    def get_secret_key(cls):
        """Get or generate the secret key for JWT signing."""
        if cls._SECRET_KEY is None:
            # Use SessionKeyManager for automatic persistence
            cls._SECRET_KEY = SessionKeyManager.get_or_create_key()
        return cls._SECRET_KEY
    
    @property
    def SECRET_KEY(self):
        """Property to get secret key."""
        return self.get_secret_key()
    
    @classmethod
    def is_auth_enabled(cls, db: Session) -> bool:
        """
        Check if authentication is enabled.
        Can be overridden by DISABLE_AUTH environment variable for development.
        """
        # Development override
        if os.getenv("DISABLE_AUTH", "false").lower() == "true":
            return False
            
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        return settings.auth_enabled if settings else False
    
    @classmethod
    def needs_setup(cls, db: Session) -> bool:
        """Check if authentication is enabled but not set up."""
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if not settings:
            return False
            
        return settings.auth_enabled and not settings.password_hash
    
    @classmethod
    def get_auth_status(cls, db: Session) -> Dict[str, Any]:
        """
        Get authentication status WITHOUT any password data.
        This is safe to send to the client.
        """
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        
        if not settings:
            return {
                "auth_enabled": False,
                "is_setup_complete": False,
                "has_password": False,
                "requires_setup": False
            }
        
        return {
            "auth_enabled": settings.auth_enabled,
            "is_setup_complete": settings.is_setup_complete,
            "is_password_configured": bool(settings.password_hash),  # Just a boolean flag, not the password itself
            "requires_setup": settings.auth_enabled and not settings.password_hash
            # NEVER include password_hash, session_token, etc.
        }
    
    @classmethod
    def verify_password(cls, db: Session, password: str) -> bool:
        """
        Server-side only password verification.
        Returns False for any failure to prevent timing attacks.
        """
        try:
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings or not settings.password_hash:
                # Still perform bcrypt operation to prevent timing attacks
                bcrypt.checkpw(b"dummy", b"$2b$12$dummy.hash.to.prevent.timing.attacks")
                return False
            
            return bcrypt.checkpw(
                password.encode('utf-8'), 
                settings.password_hash.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    @classmethod
    def set_password(cls, db: Session, new_password: str) -> bool:
        """
        Server-side only password setting.
        Hashes password with bcrypt (12 rounds).
        """
        try:
            # Hash password with bcrypt
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(new_password.encode('utf-8'), salt)
            
            # Update settings
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                settings = UserSettings(user_id=1)
                db.add(settings)
            
            settings.password_hash = hashed.decode('utf-8')
            settings.is_setup_complete = True
            
            # Invalidate existing session on password change
            settings.session_token = None
            settings.session_expiry = None
            
            db.commit()
            logger.info("Password updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Password setting error: {e}")
            db.rollback()
            return False
    
    @classmethod
    def enable_auth(cls, db: Session, initial_password: str) -> bool:
        """Enable authentication and set initial password."""
        try:
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                settings = UserSettings(user_id=1)
                db.add(settings)
            
            # Enable auth
            settings.auth_enabled = True
            
            # Set password
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(initial_password.encode('utf-8'), salt)
            settings.password_hash = hashed.decode('utf-8')
            settings.is_setup_complete = True
            
            db.commit()
            logger.info("Authentication enabled successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error enabling authentication: {e}")
            db.rollback()
            return False
    
    @classmethod
    def disable_auth(cls, db: Session, current_password: str) -> bool:
        """Disable authentication (requires current password)."""
        try:
            # Verify current password first
            if not cls.verify_password(db, current_password):
                return False
            
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                return False
            
            # Disable auth and clear password
            settings.auth_enabled = False
            settings.password_hash = None
            settings.session_token = None
            settings.session_expiry = None
            settings.is_setup_complete = False
            
            db.commit()
            logger.info("Authentication disabled successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error disabling authentication: {e}")
            db.rollback()
            return False
    
    @classmethod
    def create_session(cls, db: Session, remember_me: bool = False) -> Optional[str]:
        """
        Create a new session token (JWT).
        Returns token string to be set as HttpOnly cookie.
        """
        try:
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                logger.error("No user settings found when creating session")
                return None
            
            # Determine expiry
            expiry_days = cls.REMEMBER_ME_DAYS if remember_me else cls.DEFAULT_EXPIRY_DAYS
            logger.info(f"Creating session with remember_me={remember_me}, expiry_days={expiry_days}")
            logger.debug(f"REMEMBER_ME_DAYS={cls.REMEMBER_ME_DAYS}, DEFAULT_EXPIRY_DAYS={cls.DEFAULT_EXPIRY_DAYS}")
            
            expiry = datetime.now(timezone.utc) + timedelta(days=expiry_days)
            
            # Create JWT token
            payload = {
                "user_id": settings.user_id,
                "exp": expiry,
                "iat": datetime.now(timezone.utc),
                "remember_me": remember_me
            }
            
            logger.debug(f"JWT payload: exp={expiry}, remember_me={remember_me}")
            
            token = jwt.encode(payload, cls.get_secret_key(), algorithm=cls.ALGORITHM)
            
            # Store token and expiry in database
            # SQLite stores datetimes as text, so we ensure UTC but store without timezone info
            # to avoid SQLite compatibility issues
            settings.session_token = token
            # Store as naive datetime (SQLite doesn't handle timezones well)
            # But we know it's always UTC
            settings.session_expiry = expiry.replace(tzinfo=None) if expiry.tzinfo else expiry
            settings.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            
            logger.info(f"Session created successfully - Token: {token[:20]}..., Expiry: {settings.session_expiry}")
            
            return token
            
        except Exception as e:
            logger.error(f"Session creation error: {e}")
            return None
    
    @classmethod
    def validate_session(cls, db: Session, token: str) -> bool:
        """
        Validate a session token.
        Checks both JWT validity and database session.
        """
        if not token:
            logger.debug("No token provided for validation")
            return False
            
        try:
            # First check if token exists in database before attempting JWT decode
            # This avoids JWT expiry exceptions for known invalid tokens
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if not settings:
                logger.debug("No user settings found in database")
                return False
            
            if settings.session_token != token:
                logger.debug("Token mismatch - database token differs from provided token")
                logger.debug(f"DB token: {settings.session_token[:20] if settings.session_token else 'None'}...")
                return False
            
            # Try to decode JWT - this will raise an exception if expired
            logger.debug(f"Attempting to decode JWT token: {token[:20]}...")
            
            try:
                # First try normal decode (will fail if expired)
                # Add leeway to handle small clock skew issues (5 minutes)
                payload = jwt.decode(token, cls.get_secret_key(), algorithms=[cls.ALGORITHM], 
                                   options={"leeway": 300})  # 5 minutes leeway for clock skew
            except jwt.ExpiredSignatureError:
                # Token is expired according to JWT - but let's check if we should extend it
                logger.warning("JWT token expired according to signature")
                
                # Decode without verification to inspect the payload
                payload = jwt.decode(token, cls.get_secret_key(), algorithms=[cls.ALGORITHM], 
                                    options={"verify_exp": False})
                
                jwt_exp = payload.get('exp')
                remember_me = payload.get('remember_me', False)
                
                if jwt_exp:
                    jwt_exp_dt = datetime.fromtimestamp(jwt_exp, tz=timezone.utc)
                    logger.debug(f"Expired JWT expiry: {jwt_exp_dt}")
                    logger.debug(f"Remember me flag: {remember_me}")
                
                # Check database expiry as fallback
                if settings.session_expiry:
                    db_expiry = settings.session_expiry
                    if db_expiry.tzinfo is None:
                        db_expiry = db_expiry.replace(tzinfo=timezone.utc)
                    
                    if db_expiry > datetime.now(timezone.utc):
                        logger.warning("JWT expired but database session still valid - possible clock/timezone issue")
                        # Database says session is still valid, but JWT is expired
                        # This suggests a timezone or clock sync issue
                        # For safety, we'll still reject the session
                
                return False
            
            # Log JWT payload details
            jwt_exp = payload.get('exp')
            if jwt_exp:
                jwt_exp_dt = datetime.fromtimestamp(jwt_exp, tz=timezone.utc)
                logger.debug(f"JWT expiry from token: {jwt_exp_dt}")
                logger.debug(f"Current UTC time: {datetime.now(timezone.utc)}")
                logger.debug(f"JWT is_expired: {jwt_exp_dt < datetime.now(timezone.utc)}")
                logger.debug(f"Remember me flag in JWT: {payload.get('remember_me', False)}")
            
            # Check expiry
            if settings.session_expiry:
                # Make sure we're comparing timezone-aware datetimes
                expiry = settings.session_expiry
                if expiry.tzinfo is None:
                    # Make expiry timezone-aware if it isn't already
                    logger.debug(f"Converting naive datetime to UTC: {expiry}")
                    expiry = expiry.replace(tzinfo=timezone.utc)
                
                logger.debug(f"DB session expiry: {expiry}")
                logger.debug(f"Current UTC time: {datetime.now(timezone.utc)}")
                logger.debug(f"DB session is_expired: {expiry < datetime.now(timezone.utc)}")
                
                if expiry < datetime.now(timezone.utc):
                    logger.info(f"Session expired - DB expiry {expiry} < current time {datetime.now(timezone.utc)}")
                    return False
            else:
                logger.debug("No session expiry set in database")
            
            logger.debug("Session validation successful")
            return True
            
        except JWTError as e:
            logger.warning(f"JWT validation error: {e}")
            logger.debug(f"Token that failed: {token[:20]}...")
            return False
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False
    
    @classmethod
    def invalidate_session(cls, db: Session) -> bool:
        """Invalidate the current session."""
        try:
            settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
            if settings:
                settings.session_token = None
                settings.session_expiry = None
                db.commit()
            return True
        except Exception as e:
            logger.error(f"Session invalidation error: {e}")
            return False
    
    @classmethod
    def invalidate_all_sessions(cls, db: Session) -> bool:
        """Invalidate all sessions (used after password change)."""
        return cls.invalidate_session(db)  # Single user system


# Singleton instance
_auth_service = AuthService()


def get_auth_service() -> AuthService:
    """Get the authentication service instance."""
    return _auth_service