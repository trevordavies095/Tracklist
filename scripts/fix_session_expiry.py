#!/usr/bin/env python3
"""
Fix session expiry issues by recalculating expiry times.
This script can be run to fix existing sessions that may have incorrect expiry times.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import UserSettings
from app.services.auth_service import get_auth_service
from jose import jwt

def fix_session_expiry():
    """Fix existing session expiry times"""
    
    # Connect to database
    db_path = os.getenv('DATABASE_URL', 'sqlite:///./data/tracklist.db')
    engine = create_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    auth_service = get_auth_service()
    
    try:
        # Get current settings
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if not settings:
            print("No user settings found")
            return
        
        if not settings.session_token:
            print("No active session found")
            return
        
        print(f"Current session token: {settings.session_token[:20]}...")
        print(f"Current session expiry: {settings.session_expiry}")
        
        # Try to decode the JWT token to check its expiry
        try:
            # Decode without verification to inspect payload
            payload = jwt.decode(
                settings.session_token,
                auth_service.get_secret_key(),
                algorithms=[auth_service.ALGORITHM],
                options={"verify_exp": False, "verify_signature": False}
            )
            
            jwt_exp = payload.get('exp')
            remember_me = payload.get('remember_me', False)
            iat = payload.get('iat')
            
            if jwt_exp:
                jwt_exp_dt = datetime.fromtimestamp(jwt_exp, tz=timezone.utc)
                print(f"\nJWT Token Info:")
                print(f"  - Expiry: {jwt_exp_dt}")
                print(f"  - Remember Me: {remember_me}")
                
                if iat:
                    iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc)
                    print(f"  - Issued At: {iat_dt}")
                    
                    # Calculate how long the session was meant to last
                    duration = jwt_exp_dt - iat_dt
                    days = duration.days
                    print(f"  - Duration: {days} days")
                    
                    # Check if it matches expected values
                    expected_days = auth_service.REMEMBER_ME_DAYS if remember_me else auth_service.DEFAULT_EXPIRY_DAYS
                    print(f"  - Expected: {expected_days} days (remember_me={remember_me})")
                    
                    if days != expected_days:
                        print(f"\n⚠️  MISMATCH: Token duration is {days} days but should be {expected_days} days")
                
                # Check if database expiry matches JWT expiry
                if settings.session_expiry:
                    db_expiry = settings.session_expiry
                    # Assume it's UTC even if naive
                    if db_expiry.tzinfo is None:
                        db_expiry = db_expiry.replace(tzinfo=timezone.utc)
                    
                    print(f"\nDatabase session expiry: {db_expiry}")
                    
                    # Compare with JWT expiry
                    diff = abs((jwt_exp_dt - db_expiry).total_seconds())
                    if diff > 60:  # More than 1 minute difference
                        print(f"⚠️  MISMATCH: Database and JWT expiry differ by {diff:.0f} seconds")
                        
                        # Fix by updating database to match JWT
                        print("\nFixing database expiry to match JWT...")
                        settings.session_expiry = jwt_exp_dt.replace(tzinfo=None)  # Store as naive for SQLite
                        db.commit()
                        print("✅ Database expiry updated")
                    else:
                        print("✅ Database and JWT expiry match")
                
                # Check if session is expired
                now = datetime.now(timezone.utc)
                if jwt_exp_dt < now:
                    print(f"\n❌ Session is EXPIRED (expired {(now - jwt_exp_dt).total_seconds() / 3600:.1f} hours ago)")
                else:
                    remaining = jwt_exp_dt - now
                    print(f"\n✅ Session is VALID (expires in {remaining.days} days, {remaining.seconds // 3600} hours)")
                    
        except Exception as e:
            print(f"Error decoding JWT: {e}")
        
    finally:
        db.close()

if __name__ == "__main__":
    fix_session_expiry()