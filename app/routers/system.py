"""
System monitoring and health check endpoints
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..services.resource_monitor import get_resource_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/resources")
async def get_resource_metrics() -> Dict[str, Any]:
    """
    Get current resource usage metrics

    Provides detailed information about:
    - Memory usage and growth
    - Network connections
    - Open file descriptors
    - Thread count
    - Database connection pool

    This endpoint helps identify resource leaks and monitor application health.
    """
    try:
        monitor = get_resource_monitor()
        report = await monitor.get_full_report()

        logger.debug(
            f"Resource report generated: {report['health_checks']['overall']} health"
        )

        return {"status": "success", "data": report}

    except Exception as e:
        logger.error(f"Failed to get resource metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to retrieve resource metrics", "message": str(e)},
        )


@router.get("/health/detailed")
async def get_detailed_health() -> Dict[str, Any]:
    """
    Get detailed health check including resource status

    Enhanced health check that includes:
    - Basic health status
    - Resource usage summary
    - Health warnings and errors
    - Database connectivity
    """
    try:
        from ..database import get_db_info

        # Get resource report
        monitor = get_resource_monitor()
        report = await monitor.get_full_report()

        # Get database info
        db_info = get_db_info()

        # Build health response
        health_status = {
            "status": "healthy",
            "service": "tracklist",
            "checks": {
                "database": {
                    "status": "connected" if db_info.get("exists") else "disconnected",
                    "type": db_info.get("type", "unknown"),
                },
                "resources": {
                    "status": report["health_checks"]["overall"],
                    "memory_mb": report["memory"]["rss_mb"],
                    "connections": report["connections"]["total"],
                    "warnings": report["health_checks"]["warnings"],
                    "errors": report["health_checks"]["errors"],
                },
            },
            "metrics": {
                "uptime_hours": report["uptime_hours"],
                "memory_growth_mb": report["memory"]["growth_mb"],
                "peak_memory_mb": report["memory"]["peak_mb"],
                "open_files": report["file_descriptors"]["open_files"],
                "threads": report["threads"]["count"],
            },
        }

        # Adjust overall status based on resource health
        if report["health_checks"]["overall"] == "critical":
            health_status["status"] = "unhealthy"
        elif report["health_checks"]["overall"] == "warning":
            health_status["status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Failed to get detailed health: {e}")
        return {"status": "unhealthy", "service": "tracklist", "error": str(e)}


@router.post("/gc")
async def trigger_garbage_collection() -> Dict[str, Any]:
    """
    Manually trigger garbage collection

    Forces Python garbage collector to run and clean up unused objects.
    Returns statistics about the collection.
    """
    try:
        import gc

        # Get stats before
        before_objects = len(gc.get_objects())

        # Run garbage collection
        collected = gc.collect()

        # Get stats after
        after_objects = len(gc.get_objects())

        logger.info(f"Garbage collection completed: {collected} objects collected")

        return {
            "status": "success",
            "collected": collected,
            "objects_before": before_objects,
            "objects_after": after_objects,
            "objects_freed": before_objects - after_objects,
        }

    except Exception as e:
        logger.error(f"Failed to run garbage collection: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to run garbage collection", "message": str(e)},
        )
