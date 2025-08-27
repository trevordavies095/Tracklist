#!/usr/bin/env python3
"""
Test session expiry by manipulating the database directly.
This allows us to test expiry without waiting for real time to pass.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import requests
import time

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import UserSettings
from app.services.auth_service import get_auth_service

BASE_URL = "http://localhost:8000"

class Colors:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    WARNING = '\033[93m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_test(message):
    print(f"Testing: {message}")

def print_pass(message):
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_fail(message):
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def test_session_expiry():
    """Test that expired sessions are properly rejected"""
    
    print(f"\n{Colors.BOLD}SESSION EXPIRY TEST{Colors.ENDC}")
    print("="*50)
    
    # Connect to database
    db_path = os.getenv('DATABASE_URL', 'sqlite:///./data/tracklist.db')
    engine = create_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Check if auth is enabled
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if not settings or not settings.auth_enabled:
            print(f"{Colors.WARNING}Authentication is not enabled. Please enable it first.{Colors.ENDC}")
            return
        
        # Get current session token
        current_token = settings.session_token
        current_expiry = settings.session_expiry
        
        if not current_token:
            print(f"{Colors.WARNING}No active session found. Please login first.{Colors.ENDC}")
            return
        
        print(f"Current session token: {current_token[:20]}...")
        print(f"Current expiry: {current_expiry}")
        
        # Test 1: Valid session should work
        print_test("\n1. Testing valid session...")
        session = requests.Session()
        session.cookies.set('tracklist_session', current_token)
        
        resp = session.get(f"{BASE_URL}/api/v1/settings")
        if resp.status_code == 200:
            print_pass("Valid session accepted")
        else:
            print_fail(f"Valid session rejected! Status: {resp.status_code}")
        
        # Test 2: Expired session should be rejected
        print_test("\n2. Testing expired session...")
        
        # Set expiry to 1 hour ago
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        settings.session_expiry = expired_time
        db.commit()
        print(f"Set expiry to: {expired_time} (1 hour ago)")
        
        # Try to access protected endpoint
        resp = session.get(f"{BASE_URL}/api/v1/settings")
        if resp.status_code == 401 or resp.status_code == 303:
            print_pass("Expired session rejected correctly")
        else:
            print_fail(f"Expired session still accepted! Status: {resp.status_code}")
        
        # Test 3: Future-dated session should work
        print_test("\n3. Testing future-dated session...")
        
        # Set expiry to 1 hour from now
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        settings.session_expiry = future_time
        db.commit()
        print(f"Set expiry to: {future_time} (1 hour from now)")
        
        resp = session.get(f"{BASE_URL}/api/v1/settings")
        if resp.status_code == 200:
            print_pass("Future-dated session accepted")
        else:
            print_fail(f"Future-dated session rejected! Status: {resp.status_code}")
        
        # Test 4: Null/deleted session should be rejected
        print_test("\n4. Testing deleted session...")
        
        # Clear session from database
        settings.session_token = None
        settings.session_expiry = None
        db.commit()
        print("Cleared session from database")
        
        resp = session.get(f"{BASE_URL}/api/v1/settings")
        if resp.status_code == 401 or resp.status_code == 303:
            print_pass("Deleted session rejected correctly")
        else:
            print_fail(f"Deleted session still accepted! Status: {resp.status_code}")
        
        # Restore original session if it existed
        if current_token:
            print_test("\n5. Restoring original session...")
            settings.session_token = current_token
            settings.session_expiry = current_expiry
            db.commit()
            print_pass("Original session restored")
        
    finally:
        db.close()
    
    print(f"\n{Colors.BOLD}SESSION EXPIRY TEST COMPLETE{Colors.ENDC}")
    print("="*50)

def test_remember_me_duration():
    """Test that remember_me extends session duration"""
    
    print(f"\n{Colors.BOLD}REMEMBER ME DURATION TEST{Colors.ENDC}")
    print("="*50)
    
    # This would require actually logging in with remember_me
    # and checking the expiry time set in the database
    
    print("To test remember_me duration:")
    print("1. Login WITHOUT remember_me - check session_expiry is ~30 days")
    print("2. Login WITH remember_me - check session_expiry is ~90 days")
    print("\nManual verification required for this test.")

if __name__ == "__main__":
    test_session_expiry()
    test_remember_me_duration()