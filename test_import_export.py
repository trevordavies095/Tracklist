#!/usr/bin/env python3
"""
Test script for import/export functionality
Run with: python test_import_export.py
"""

import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_export():
    """Test database export"""
    print("Testing Export...")
    response = requests.get(f"{BASE_URL}/api/v1/settings/export")
    
    if response.status_code == 200:
        data = response.json()
        
        # Verify structure
        assert "export_metadata" in data, "Missing export_metadata"
        assert "settings" in data, "Missing settings"
        assert "artists" in data, "Missing artists"
        assert "albums" in data, "Missing albums"
        assert "tracks" in data, "Missing tracks"
        
        # Save for import test
        filename = f"test_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Export successful! Saved to {filename}")
        print(f"   - Artists: {len(data['artists'])}")
        print(f"   - Albums: {len(data['albums'])}")
        print(f"   - Tracks: {len(data['tracks'])}")
        return filename
    else:
        print(f"❌ Export failed: {response.status_code}")
        print(response.text)
        return None

def test_import(filename):
    """Test database import"""
    print(f"\nTesting Import with {filename}...")
    
    with open(filename, 'rb') as f:
        files = {'file': (filename, f, 'application/json')}
        response = requests.post(f"{BASE_URL}/api/v1/settings/import", files=files)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Import successful!")
        print(f"   - Success: {data['success']}")
        print(f"   - Message: {data['message']}")
        if data.get('statistics'):
            print(f"   - Statistics: {data['statistics']}")
        return True
    else:
        print(f"❌ Import failed: {response.status_code}")
        print(response.text)
        return False

def test_invalid_import():
    """Test import with invalid files"""
    print("\nTesting Import Validation...")
    
    # Test 1: Invalid JSON structure
    invalid_data = {"invalid": "structure"}
    with open("test_invalid.json", 'w') as f:
        json.dump(invalid_data, f)
    
    with open("test_invalid.json", 'rb') as f:
        files = {'file': ('test_invalid.json', f, 'application/json')}
        response = requests.post(f"{BASE_URL}/api/v1/settings/import", files=files)
    
    if response.status_code == 400:
        print("✅ Correctly rejected invalid structure")
    else:
        print(f"❌ Should have rejected invalid file: {response.status_code}")
    
    # Test 2: Non-JSON file
    with open("test.txt", 'w') as f:
        f.write("This is not JSON")
    
    with open("test.txt", 'rb') as f:
        files = {'file': ('test.txt', f, 'text/plain')}
        response = requests.post(f"{BASE_URL}/api/v1/settings/import", files=files)
    
    if response.status_code == 400:
        print("✅ Correctly rejected non-JSON file")
    else:
        print(f"❌ Should have rejected text file: {response.status_code}")

def main():
    """Run all tests"""
    print("=" * 50)
    print("Testing Import/Export Functionality")
    print("=" * 50)
    
    # Test export
    backup_file = test_export()
    
    if backup_file:
        # Test import with valid file
        test_import(backup_file)
    
    # Test validation
    test_invalid_import()
    
    print("\n" + "=" * 50)
    print("Testing Complete!")
    print("=" * 50)

if __name__ == "__main__":
    main()