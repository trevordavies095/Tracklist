"""
Resource monitoring service for tracking system resources
Helps identify and prevent resource leaks
"""

import os
import psutil
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import gc

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """
    Service for monitoring system resources and detecting potential leaks
    """
    
    def __init__(self):
        """Initialize the resource monitor"""
        self.process = psutil.Process(os.getpid())
        self.start_time = datetime.now(timezone.utc)
        self._last_check = datetime.now(timezone.utc)
        self._baseline_memory = None
        self._peak_memory = 0
        self._monitoring = False
        
    def get_memory_info(self) -> Dict[str, Any]:
        """
        Get current memory usage information
        
        Returns:
            Dict with memory statistics
        """
        try:
            mem_info = self.process.memory_info()
            mem_percent = self.process.memory_percent()
            
            # Track peak memory
            if mem_info.rss > self._peak_memory:
                self._peak_memory = mem_info.rss
            
            # Set baseline on first check
            if self._baseline_memory is None:
                self._baseline_memory = mem_info.rss
            
            return {
                "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
                "vms_mb": round(mem_info.vms / (1024 * 1024), 2),
                "percent": round(mem_percent, 2),
                "peak_mb": round(self._peak_memory / (1024 * 1024), 2),
                "baseline_mb": round(self._baseline_memory / (1024 * 1024), 2) if self._baseline_memory else 0,
                "growth_mb": round((mem_info.rss - self._baseline_memory) / (1024 * 1024), 2) if self._baseline_memory else 0
            }
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return {}
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get information about open connections
        
        Returns:
            Dict with connection statistics
        """
        try:
            connections = self.process.connections(kind='inet')
            
            # Count connections by status
            status_counts = {}
            for conn in connections:
                status = conn.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total": len(connections),
                "by_status": status_counts,
                "established": status_counts.get("ESTABLISHED", 0),
                "time_wait": status_counts.get("TIME_WAIT", 0),
                "close_wait": status_counts.get("CLOSE_WAIT", 0),
            }
        except Exception as e:
            logger.error(f"Error getting connection info: {e}")
            return {"total": 0, "by_status": {}}
    
    def get_file_descriptor_info(self) -> Dict[str, Any]:
        """
        Get information about open file descriptors
        
        Returns:
            Dict with file descriptor statistics
        """
        try:
            # This works on Unix-like systems
            num_fds = self.process.num_fds() if hasattr(self.process, 'num_fds') else None
            
            # Alternative for all platforms
            open_files = self.process.open_files()
            
            return {
                "open_files": len(open_files),
                "num_fds": num_fds,
                "files": [f.path for f in open_files[:10]]  # First 10 files as sample
            }
        except Exception as e:
            logger.error(f"Error getting file descriptor info: {e}")
            return {"open_files": 0, "num_fds": None}
    
    def get_thread_info(self) -> Dict[str, Any]:
        """
        Get information about threads
        
        Returns:
            Dict with thread statistics
        """
        try:
            num_threads = self.process.num_threads()
            return {
                "count": num_threads,
                "healthy": num_threads < 100  # Arbitrary threshold
            }
        except Exception as e:
            logger.error(f"Error getting thread info: {e}")
            return {"count": 0, "healthy": True}
    
    def get_database_pool_info(self) -> Dict[str, Any]:
        """
        Get information about database connection pool
        
        Returns:
            Dict with database pool statistics
        """
        try:
            from ..database import engine
            
            # SQLAlchemy pool statistics
            pool = engine.pool
            
            return {
                "size": pool.size() if hasattr(pool, 'size') else 0,
                "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else 0,
                "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else 0,
                "overflow": pool.overflow() if hasattr(pool, 'overflow') else 0,
                "total": pool.total() if hasattr(pool, 'total') else 0,
            }
        except Exception as e:
            logger.debug(f"Could not get database pool info: {e}")
            return {}
    
    async def get_full_report(self) -> Dict[str, Any]:
        """
        Get a complete resource usage report
        
        Returns:
            Dict with all resource metrics
        """
        now = datetime.now(timezone.utc)
        uptime = (now - self.start_time).total_seconds()
        
        # Force garbage collection before checking
        gc.collect()
        
        report = {
            "timestamp": now.isoformat(),
            "uptime_seconds": round(uptime, 2),
            "uptime_hours": round(uptime / 3600, 2),
            "memory": self.get_memory_info(),
            "connections": self.get_connection_info(),
            "file_descriptors": self.get_file_descriptor_info(),
            "threads": self.get_thread_info(),
            "database_pool": self.get_database_pool_info(),
            "python_objects": {
                "count": len(gc.get_objects()),
                "garbage": len(gc.garbage)
            }
        }
        
        # Check for potential leaks
        report["health_checks"] = self._check_resource_health(report)
        
        self._last_check = now
        return report
    
    def _check_resource_health(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check resource health and identify potential issues
        
        Args:
            report: Current resource report
            
        Returns:
            Dict with health check results
        """
        health = {
            "overall": "healthy",
            "warnings": [],
            "errors": []
        }
        
        # Check memory growth
        if report["memory"].get("growth_mb", 0) > 100:
            health["warnings"].append(f"Memory growth exceeds 100MB: {report['memory']['growth_mb']}MB")
            health["overall"] = "warning"
        
        if report["memory"].get("growth_mb", 0) > 500:
            health["errors"].append(f"Excessive memory growth: {report['memory']['growth_mb']}MB")
            health["overall"] = "critical"
        
        # Check connections
        total_connections = report["connections"].get("total", 0)
        if total_connections > 50:
            health["warnings"].append(f"High number of connections: {total_connections}")
            health["overall"] = "warning" if health["overall"] == "healthy" else health["overall"]
        
        if total_connections > 100:
            health["errors"].append(f"Excessive connections: {total_connections}")
            health["overall"] = "critical"
        
        # Check for CLOSE_WAIT connections (potential leak)
        close_wait = report["connections"].get("close_wait", 0)
        if close_wait > 10:
            health["warnings"].append(f"High CLOSE_WAIT connections: {close_wait}")
            health["overall"] = "warning" if health["overall"] == "healthy" else health["overall"]
        
        # Check file descriptors
        open_files = report["file_descriptors"].get("open_files", 0)
        if open_files > 100:
            health["warnings"].append(f"High number of open files: {open_files}")
            health["overall"] = "warning" if health["overall"] == "healthy" else health["overall"]
        
        if open_files > 500:
            health["errors"].append(f"Excessive open files: {open_files}")
            health["overall"] = "critical"
        
        # Check threads
        thread_count = report["threads"].get("count", 0)
        if thread_count > 50:
            health["warnings"].append(f"High thread count: {thread_count}")
            health["overall"] = "warning" if health["overall"] == "healthy" else health["overall"]
        
        # Check database pool
        db_pool = report.get("database_pool", {})
        if db_pool.get("checked_out", 0) > 10:
            health["warnings"].append(f"High database connections checked out: {db_pool['checked_out']}")
            health["overall"] = "warning" if health["overall"] == "healthy" else health["overall"]
        
        return health
    
    async def start_monitoring(self, interval_seconds: int = 300):
        """
        Start background monitoring task
        
        Args:
            interval_seconds: How often to log resource metrics (default: 5 minutes)
        """
        if self._monitoring:
            logger.warning("Resource monitoring already started")
            return
        
        self._monitoring = True
        logger.info(f"Starting resource monitoring with {interval_seconds}s interval")
        
        while self._monitoring:
            try:
                report = await self.get_full_report()
                health = report["health_checks"]
                
                if health["overall"] == "critical":
                    logger.error(f"Critical resource issues detected: {health['errors']}")
                elif health["overall"] == "warning":
                    logger.warning(f"Resource warnings: {health['warnings']}")
                else:
                    logger.info(
                        f"Resources healthy - Memory: {report['memory']['rss_mb']}MB, "
                        f"Connections: {report['connections']['total']}, "
                        f"Files: {report['file_descriptors']['open_files']}"
                    )
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(interval_seconds)
    
    def stop_monitoring(self):
        """Stop the background monitoring task"""
        self._monitoring = False
        logger.info("Resource monitoring stopped")


# Global instance
_resource_monitor = None


def get_resource_monitor() -> ResourceMonitor:
    """Get or create the global resource monitor instance"""
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = ResourceMonitor()
        logger.info("Resource monitor initialized")
    return _resource_monitor