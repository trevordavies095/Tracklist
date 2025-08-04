#!/usr/bin/env python3
"""
Test script to verify cover art service is working
"""

import asyncio
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from services.cover_art_service import get_cover_art_service


async def test_cover_art():
    """Test the cover art service with some known albums"""
    
    # Test albums with known cover art
    test_albums = [
        ("e8f70201-8899-3f0c-9e07-5d6495bc8046", "OK Computer - Radiohead"),
        ("fed37cfc-2a6d-4569-9ac0-501a7c7598eb", "Blonde - Frank Ocean"),
        ("1d9e8ed6-3893-4d3b-aa7d-6cd79609e386", "To Pimp a Butterfly - Kendrick Lamar")
    ]
    
    cover_art_service = get_cover_art_service()
    
    print("🎨 Testing Cover Art Archive API...")
    print("=" * 50)
    
    for mbid, album_name in test_albums:
        print(f"\n🔍 Testing: {album_name}")
        print(f"   MusicBrainz ID: {mbid}")
        
        try:
            cover_art_url = await cover_art_service.get_cover_art_url(mbid)
            
            if cover_art_url:
                print(f"   ✅ Found cover art: {cover_art_url}")
            else:
                print(f"   ❌ No cover art found")
                
        except Exception as e:
            print(f"   💥 Error: {e}")
    
    # Clean up
    await cover_art_service.close()
    
    print("\n" + "=" * 50)
    print("🎉 Cover art test complete!")


if __name__ == "__main__":
    asyncio.run(test_cover_art())