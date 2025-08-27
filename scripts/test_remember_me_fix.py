#!/usr/bin/env python3
"""
Test the remember me functionality to ensure it properly sets 90-day expiry.
"""

import os
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
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
    print(f"\n{Colors.BOLD}Testing: {message}{Colors.ENDC}")

def print_pass(message):
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_fail(message):
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def print_info(message):
    print(f"{Colors.WARNING}ℹ {message}{Colors.ENDC}")

def test_remember_me():
    """Test remember me functionality"""
    
    print(f"\n{Colors.BOLD}REMEMBER ME FUNCTIONALITY TEST{Colors.ENDC}")
    print("=" * 50)
    
    # Connect to database
    db_path = os.getenv('DATABASE_URL', 'sqlite:///./data/tracklist.db')
    engine = create_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    auth_service = get_auth_service()
    
    try:
        # Check if auth is enabled
        settings = db.query(UserSettings).filter(UserSettings.user_id == 1).first()
        if not settings or not settings.auth_enabled:
            print_fail("Authentication is not enabled. Please enable it first.")
            return
        
        if not settings.password_hash:
            print_fail("No password set. Please complete setup first.")
            return
        
        session = requests.Session()
        
        # Test 1: Login WITHOUT remember_me
        print_test("Login WITHOUT remember_me (should be 30 days)")
        
        # Clear any existing session
        settings.session_token = None
        settings.session_expiry = None
        db.commit()
        
        # Note: We can't actually test the login without knowing the password
        # So we'll simulate by creating a session directly
        token = auth_service.create_session(db, remember_me=False)
        if token:
            # Check the expiry in database
            db.refresh(settings)
            if settings.session_expiry:
                expiry = settings.session_expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                days_diff = (expiry - now).days
                
                print_info(f"Session expires: {expiry}")
                print_info(f"Days until expiry: {days_diff}")
                
                if 29 <= days_diff <= 31:  # Allow some tolerance
                    print_pass(f"Default session is ~30 days ({days_diff} days)")
                else:
                    print_fail(f"Expected ~30 days, got {days_diff} days")
        
        # Test 2: Login WITH remember_me
        print_test("Login WITH remember_me (should be 90 days)")
        
        # Clear session again
        settings.session_token = None
        settings.session_expiry = None
        db.commit()
        
        # Create session with remember_me
        token = auth_service.create_session(db, remember_me=True)
        if token:
            # Check the expiry in database
            db.refresh(settings)
            if settings.session_expiry:
                expiry = settings.session_expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                days_diff = (expiry - now).days
                
                print_info(f"Session expires: {expiry}")
                print_info(f"Days until expiry: {days_diff}")
                
                if 89 <= days_diff <= 91:  # Allow some tolerance
                    print_pass(f"Remember me session is ~90 days ({days_diff} days)")
                else:
                    print_fail(f"Expected ~90 days, got {days_diff} days")
        
        # Test 3: Check environment variables
        print_test("Environment variable configuration")
        
        print_info(f"DEFAULT_EXPIRY_DAYS: {auth_service.DEFAULT_EXPIRY_DAYS}")
        print_info(f"REMEMBER_ME_DAYS: {auth_service.REMEMBER_ME_DAYS}")
        
        if auth_service.REMEMBER_ME_DAYS == 90:
            print_pass("REMEMBER_ME_DAYS is correctly set to 90")
        else:
            print_fail(f"REMEMBER_ME_DAYS is {auth_service.REMEMBER_ME_DAYS}, expected 90")
        
        if auth_service.DEFAULT_EXPIRY_DAYS == 30:
            print_pass("DEFAULT_EXPIRY_DAYS is correctly set to 30")
        else:
            print_fail(f"DEFAULT_EXPIRY_DAYS is {auth_service.DEFAULT_EXPIRY_DAYS}, expected 30")
        
    finally:
        db.close()
    
    print(f"\n{Colors.BOLD}TEST COMPLETE{Colors.ENDC}")
    print("=" * 50)
    print("\nTo fully test the remember me functionality:")
    print("1. Log out if currently logged in")
    print("2. Log in WITHOUT checking 'Remember me'")
    print("3. Run scripts/fix_session_expiry.py to check expiry (should be ~30 days)")
    print("4. Log out and log in again WITH 'Remember me' checked")
    print("5. Run scripts/fix_session_expiry.py to check expiry (should be ~90 days)")

if __name__ == "__main__":
    test_remember_me()