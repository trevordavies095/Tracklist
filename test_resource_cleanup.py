#!/usr/bin/env python3
"""
Test script to verify resource cleanup implementation
Tests that HTTP clients, database sessions, and file handles are properly closed
"""

import asyncio
import time
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_http_client_cleanup():
    """Test that HTTP clients are properly closed"""
    logger.info("Testing HTTP client cleanup...")
    
    from app.services.artwork_cache_service import get_artwork_cache_service
    from app.services.cover_art_service import get_cover_art_service
    from app.musicbrainz_client import MusicBrainzClient
    from app.services.resource_monitor import ResourceMonitor
    
    monitor = ResourceMonitor()
    
    # Get initial state
    initial_report = await monitor.get_full_report()
    initial_connections = initial_report['connections']['total']
    logger.info(f"Initial connections: {initial_connections}")
    
    # Create services
    artwork_service = get_artwork_cache_service()
    cover_art_service = get_cover_art_service()
    
    # Use MusicBrainz client
    async with MusicBrainzClient() as mb_client:
        # This should create an HTTP connection
        pass
    
    # Check connections after creation
    after_create = await monitor.get_full_report()
    after_connections = after_create['connections']['total']
    logger.info(f"Connections after creating services: {after_connections}")
    
    # Close services
    await artwork_service.close()
    await cover_art_service.close()
    
    # Give some time for connections to close
    await asyncio.sleep(1)
    
    # Check connections after cleanup
    final_report = await monitor.get_full_report()
    final_connections = final_report['connections']['total']
    logger.info(f"Connections after cleanup: {final_connections}")
    
    # Verify no connection leak
    if final_connections > initial_connections:
        logger.warning(f"Potential connection leak: {final_connections - initial_connections} connections not closed")
        return False
    else:
        logger.info("✓ HTTP client cleanup successful")
        return True

async def test_database_session_cleanup():
    """Test that database sessions are properly closed"""
    logger.info("Testing database session cleanup...")
    
    from app.database import SessionLocal, get_db
    from app.models import Album
    from app.services.resource_monitor import ResourceMonitor
    
    monitor = ResourceMonitor()
    
    # Get initial state
    initial_report = await monitor.get_full_report()
    initial_pool = initial_report.get('database_pool', {})
    logger.info(f"Initial DB pool: {initial_pool}")
    
    # Create and use sessions
    sessions = []
    for i in range(5):
        session = SessionLocal()
        try:
            # Do a simple query
            count = session.query(Album).count()
            logger.debug(f"Session {i}: Album count = {count}")
        finally:
            session.close()
    
    # Check pool after sessions
    after_report = await monitor.get_full_report()
    after_pool = after_report.get('database_pool', {})
    logger.info(f"DB pool after sessions: {after_pool}")
    
    # Verify no session leak
    checked_out = after_pool.get('checked_out', 0)
    if checked_out > 0:
        logger.warning(f"Potential session leak: {checked_out} sessions still checked out")
        return False
    else:
        logger.info("✓ Database session cleanup successful")
        return True

async def test_memory_stability():
    """Test that memory usage is stable"""
    logger.info("Testing memory stability...")
    
    from app.services.resource_monitor import ResourceMonitor
    from app.services.artwork_cache_service import get_artwork_cache_service
    
    monitor = ResourceMonitor()
    
    # Get baseline
    baseline_report = await monitor.get_full_report()
    baseline_memory = baseline_report['memory']['rss_mb']
    logger.info(f"Baseline memory: {baseline_memory}MB")
    
    # Create and destroy services multiple times
    for i in range(10):
        service = get_artwork_cache_service()
        if hasattr(service, 'close'):
            await service.close()
        
        # Force garbage collection
        import gc
        gc.collect()
        
        if i % 3 == 0:
            current_report = await monitor.get_full_report()
            current_memory = current_report['memory']['rss_mb']
            growth = current_memory - baseline_memory
            logger.debug(f"Iteration {i}: Memory = {current_memory}MB (growth: {growth}MB)")
    
    # Final check
    await asyncio.sleep(1)
    gc.collect()
    
    final_report = await monitor.get_full_report()
    final_memory = final_report['memory']['rss_mb']
    total_growth = final_memory - baseline_memory
    
    logger.info(f"Final memory: {final_memory}MB (growth: {total_growth}MB)")
    
    # Allow some growth but flag excessive growth
    if total_growth > 10:
        logger.warning(f"Excessive memory growth: {total_growth}MB")
        return False
    else:
        logger.info("✓ Memory usage stable")
        return True

async def test_resource_monitoring():
    """Test the resource monitoring service itself"""
    logger.info("Testing resource monitoring service...")
    
    from app.services.resource_monitor import ResourceMonitor
    
    monitor = ResourceMonitor()
    
    # Get full report
    report = await monitor.get_full_report()
    
    # Verify report structure
    required_keys = ['timestamp', 'memory', 'connections', 'file_descriptors', 'threads', 'health_checks']
    missing_keys = [k for k in required_keys if k not in report]
    
    if missing_keys:
        logger.error(f"Missing keys in report: {missing_keys}")
        return False
    
    # Check health checks
    health = report['health_checks']
    logger.info(f"Health status: {health['overall']}")
    
    if health['warnings']:
        logger.warning(f"Health warnings: {health['warnings']}")
    
    if health['errors']:
        logger.error(f"Health errors: {health['errors']}")
        return False
    
    logger.info("✓ Resource monitoring working correctly")
    return True

async def main():
    """Run all resource cleanup tests"""
    logger.info("=" * 60)
    logger.info("Starting Resource Cleanup Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Resource Monitoring", test_resource_monitoring),
        ("HTTP Client Cleanup", test_http_client_cleanup),
        ("Database Session Cleanup", test_database_session_cleanup),
        ("Memory Stability", test_memory_stability),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\nRunning: {test_name}")
        logger.info("-" * 40)
        try:
            result = await test_func()
            results[test_name] = "PASSED" if result else "FAILED"
        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            results[test_name] = "ERROR"
        
        # Give time between tests
        await asyncio.sleep(1)
    
    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    all_passed = True
    for test_name, status in results.items():
        symbol = "✓" if status == "PASSED" else "✗"
        logger.info(f"{symbol} {test_name}: {status}")
        if status != "PASSED":
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All tests passed! Resource cleanup is working correctly.")
        return 0
    else:
        logger.error("\n❌ Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)