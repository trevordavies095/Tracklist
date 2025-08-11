"""
Scheduled tasks management for periodic maintenance
Handles daily cache cleanup and other scheduled operations
"""

import asyncio
import logging
from datetime import datetime, time, timezone, timedelta
from typing import Dict, Any, Optional, Callable
import json
from pathlib import Path

from .background_tasks import get_background_manager
from .cache_cleanup_service import get_cleanup_service, CleanupConfig

logger = logging.getLogger(__name__)


class ScheduledTaskManager:
    """
    Manages scheduled tasks like daily cache cleanup
    """

    def __init__(self):
        """Initialize the scheduled task manager"""
        self.background_manager = get_background_manager()
        self.tasks = {}
        self.running = False
        self._scheduler_task = None
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load scheduled tasks configuration from environment variables"""
        import os

        # Default configuration with environment variable overrides
        default_config = {
            "cache_cleanup": {
                "enabled": os.getenv("CACHE_CLEANUP_ENABLED", "true").lower() == "true",
                "schedule": os.getenv("CACHE_CLEANUP_SCHEDULE", "daily"),
                "time": os.getenv("CACHE_CLEANUP_TIME", "03:00"),  # 3 AM
                "retention_days": int(os.getenv("CACHE_RETENTION_DAYS", "365")),
                "max_cache_size_mb": int(os.getenv("CACHE_MAX_SIZE_MB", "5000")),  # 5 GB
                "dry_run": os.getenv("CACHE_CLEANUP_DRY_RUN", "false").lower() == "true"
            },
            "memory_cache_clear": {
                "enabled": os.getenv("MEMORY_CACHE_CLEAR_ENABLED", "true").lower() == "true",
                "schedule": os.getenv("MEMORY_CACHE_CLEAR_SCHEDULE", "weekly"),
                "day": os.getenv("MEMORY_CACHE_CLEAR_DAY", "sunday"),
                "time": os.getenv("MEMORY_CACHE_CLEAR_TIME", "04:00")
            },
            "reports": {
                "enabled": os.getenv("REPORTS_ENABLED", "true").lower() == "true",
                "schedule": os.getenv("REPORTS_SCHEDULE", "weekly"),
                "day": os.getenv("REPORTS_DAY", "monday"),
                "time": os.getenv("REPORTS_TIME", "09:00")
            },
            "integrity_check": {
                "enabled": os.getenv("INTEGRITY_CHECK_ENABLED", "true").lower() == "true",
                "schedule": os.getenv("INTEGRITY_CHECK_SCHEDULE", "weekly"),
                "day": os.getenv("INTEGRITY_CHECK_DAY", "sunday"),
                "time": os.getenv("INTEGRITY_CHECK_TIME", "02:00"),  # 2 AM
                "auto_repair": os.getenv("INTEGRITY_AUTO_REPAIR", "true").lower() == "true",
                "quick_check_daily": os.getenv("INTEGRITY_QUICK_CHECK", "true").lower() == "true"
            }
        }

        # Optional: Load from config file if exists (overrides env vars)
        config_file = Path("config/scheduled_tasks.json")
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults
                    for key in default_config:
                        if key in loaded_config:
                            default_config[key].update(loaded_config[key])
                    logger.info("Loaded scheduled tasks config from file")
            except Exception as e:
                logger.warning(f"Could not load config file, using environment variables: {e}")

        return default_config

    async def start(self):
        """Start the scheduled task manager"""
        if self.running:
            logger.warning("Scheduled task manager already running")
            return

        self.running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())
        logger.info("Scheduled task manager started")

    async def stop(self):
        """Stop the scheduled task manager"""
        self.running = False
        if self._scheduler_task:
            await self._scheduler_task
        logger.info("Scheduled task manager stopped")

    async def _run_scheduler(self):
        """Main scheduler loop"""
        logger.info("Starting scheduler loop")

        while self.running:
            try:
                now = datetime.now(timezone.utc)

                # Check each scheduled task
                if self.config["cache_cleanup"]["enabled"]:
                    await self._check_and_run_task(
                        "cache_cleanup",
                        self._should_run_cache_cleanup,
                        self._run_cache_cleanup
                    )

                if self.config["memory_cache_clear"]["enabled"]:
                    await self._check_and_run_task(
                        "memory_cache_clear",
                        self._should_run_memory_clear,
                        self._run_memory_clear
                    )

                if self.config["reports"]["enabled"]:
                    await self._check_and_run_task(
                        "reports",
                        self._should_run_reports,
                        self._run_reports
                    )

                if self.config["integrity_check"]["enabled"]:
                    # Full integrity check (weekly)
                    await self._check_and_run_task(
                        "integrity_check",
                        self._should_run_integrity_check,
                        self._run_integrity_check
                    )

                    # Quick check (daily)
                    if self.config["integrity_check"]["quick_check_daily"]:
                        await self._check_and_run_task(
                            "integrity_quick_check",
                            self._should_run_quick_check,
                            self._run_quick_check
                        )

                # Sleep until next minute
                await asyncio.sleep(60 - now.second)

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)

    async def _check_and_run_task(
        self,
        task_name: str,
        should_run: Callable,
        run_func: Callable
    ):
        """Check if a task should run and execute it"""
        if task_name not in self.tasks:
            self.tasks[task_name] = {
                'last_run': None,
                'running': False
            }

        task_info = self.tasks[task_name]

        # Don't run if already running
        if task_info['running']:
            return

        # Check if should run
        if should_run():
            # Check if already ran today
            if task_info['last_run']:
                if task_info['last_run'].date() == datetime.now(timezone.utc).date():
                    return

            # Run the task
            logger.info(f"Running scheduled task: {task_name}")
            task_info['running'] = True

            try:
                # Add to background queue
                task_id = self.background_manager.add_task(
                    func=run_func,
                    name=f"scheduled_{task_name}",
                    priority=7  # Low priority for scheduled tasks
                )

                task_info['last_run'] = datetime.now(timezone.utc)
                task_info['task_id'] = task_id

                logger.info(f"Scheduled task {task_name} queued: {task_id}")

            finally:
                task_info['running'] = False

    def _should_run_cache_cleanup(self) -> bool:
        """Check if cache cleanup should run"""
        config = self.config["cache_cleanup"]
        schedule_time = datetime.strptime(config["time"], "%H:%M").time()
        now = datetime.now(timezone.utc)

        # Check if it's the right time
        if config["schedule"] == "daily":
            return (
                now.hour == schedule_time.hour and
                now.minute == schedule_time.minute
            )

        return False

    def _should_run_memory_clear(self) -> bool:
        """Check if memory cache clear should run"""
        config = self.config["memory_cache_clear"]
        schedule_time = datetime.strptime(config["time"], "%H:%M").time()
        now = datetime.now(timezone.utc)

        # Check if it's the right day and time
        if config["schedule"] == "weekly":
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2,
                'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_map.get(config["day"].lower(), 6)

            return (
                now.weekday() == target_day and
                now.hour == schedule_time.hour and
                now.minute == schedule_time.minute
            )

        return False

    def _should_run_reports(self) -> bool:
        """Check if reports should run"""
        config = self.config["reports"]
        schedule_time = datetime.strptime(config["time"], "%H:%M").time()
        now = datetime.now(timezone.utc)

        # Check if it's the right day and time
        if config["schedule"] == "weekly":
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2,
                'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_map.get(config["day"].lower(), 0)

            return (
                now.weekday() == target_day and
                now.hour == schedule_time.hour and
                now.minute == schedule_time.minute
            )

        return False

    def _should_run_integrity_check(self) -> bool:
        """Check if full integrity check should run"""
        config = self.config["integrity_check"]
        schedule_time = datetime.strptime(config["time"], "%H:%M").time()
        now = datetime.now(timezone.utc)

        # Check if it's the right day and time (weekly)
        if config["schedule"] == "weekly":
            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2,
                'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_map.get(config["day"].lower(), 6)

            return (
                now.weekday() == target_day and
                now.hour == schedule_time.hour and
                now.minute == schedule_time.minute
            )

        return False

    def _should_run_quick_check(self) -> bool:
        """Check if quick integrity check should run (daily)"""
        config = self.config["integrity_check"]
        # Run quick check at 1 AM daily
        now = datetime.now(timezone.utc)
        return now.hour == 1 and now.minute == 0

    async def _run_cache_cleanup(self) -> Dict[str, Any]:
        """Run cache cleanup task"""
        config = self.config["cache_cleanup"]

        cleanup_config = CleanupConfig(
            default_retention_days=config["retention_days"],
            max_cache_size_mb=config.get("max_cache_size_mb"),
            dry_run=config.get("dry_run", False)
        )

        cleanup_service = get_cleanup_service(cleanup_config)
        result = cleanup_service.cleanup()

        # Save result to scheduled task log
        self._save_task_result("cache_cleanup", result)

        return result

    async def _run_memory_clear(self) -> Dict[str, Any]:
        """Clear memory caches"""
        from .artwork_memory_cache import get_artwork_memory_cache

        memory_cache = get_artwork_memory_cache()
        stats_before = memory_cache.get_stats()

        memory_cache.clear()

        result = {
            'cleared_at': datetime.now(timezone.utc).isoformat(),
            'entries_cleared': stats_before['capacity']['current_entries'],
            'memory_freed_mb': stats_before['memory']['mb_total']
        }

        self._save_task_result("memory_cache_clear", result)

        logger.info(f"Cleared memory cache: {result['entries_cleared']} entries, {result['memory_freed_mb']:.2f} MB")

        return result

    async def _run_reports(self) -> Dict[str, Any]:
        """Generate weekly reports"""
        reports = {}

        # Cache cleanup status
        cleanup_service = get_cleanup_service()
        reports['cache_status'] = cleanup_service.get_cleanup_status()

        # Memory cache stats
        from .artwork_memory_cache import get_artwork_memory_cache
        memory_cache = get_artwork_memory_cache()
        reports['memory_cache'] = memory_cache.get_stats()

        # Background tasks stats
        reports['background_tasks'] = self.background_manager.get_status()

        # Save report
        self._save_task_result("weekly_report", reports)

        logger.info("Generated weekly reports")

        return reports

    async def _run_integrity_check(self) -> Dict[str, Any]:
        """Run full integrity check"""
        from .cache_integrity_service import get_integrity_service

        config = self.config["integrity_check"]
        integrity_service = get_integrity_service()

        # Run verification with optional repair
        result = integrity_service.verify_integrity(
            repair=config.get("auto_repair", True),
            verbose=True
        )

        # Save result
        self._save_task_result("integrity_check", result)

        logger.info(
            f"Integrity check completed: score={result['integrity_score']}%, "
            f"issues={result['summary']['issues_found']}, "
            f"repairs={result['summary']['repairs_completed']}"
        )

        return result

    async def _run_quick_check(self) -> Dict[str, Any]:
        """Run quick integrity check (sample-based)"""
        from .cache_integrity_service import get_integrity_service

        integrity_service = get_integrity_service()
        result = integrity_service.quick_check()

        # Save result
        self._save_task_result("integrity_quick_check", result)

        logger.info(
            f"Quick integrity check: estimated score={result['estimated_integrity_score']}%"
        )

        # If integrity is below threshold, trigger full check
        if result['estimated_integrity_score'] < 90:
            logger.warning(
                f"Integrity score below threshold ({result['estimated_integrity_score']}%), "
                "consider running full check"
            )

        return result

    def _save_task_result(self, task_name: str, result: Dict[str, Any]):
        """Save task result to file"""
        results_dir = Path("logs/scheduled_tasks")
        results_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = results_dir / f"{task_name}_{timestamp}.json"

        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)

        logger.debug(f"Task result saved to {result_file}")

    def get_status(self) -> Dict[str, Any]:
        """Get scheduled tasks status"""
        return {
            'running': self.running,
            'config': self.config,
            'tasks': {
                name: {
                    'last_run': info['last_run'].isoformat() if info['last_run'] else None,
                    'running': info['running']
                }
                for name, info in self.tasks.items()
            }
        }

    async def trigger_cleanup_now(self, dry_run: bool = False) -> Dict[str, Any]:
        """Manually trigger cache cleanup"""
        logger.info(f"Manually triggering cache cleanup (dry_run={dry_run})")

        config = self.config["cache_cleanup"].copy()
        config["dry_run"] = dry_run

        cleanup_config = CleanupConfig(
            default_retention_days=config["retention_days"],
            max_cache_size_mb=config.get("max_cache_size_mb"),
            dry_run=dry_run
        )

        cleanup_service = get_cleanup_service(cleanup_config)
        result = cleanup_service.cleanup()

        return result


# Global instance
_scheduled_task_manager = None


def get_scheduled_task_manager() -> ScheduledTaskManager:
    """Get the global scheduled task manager instance"""
    global _scheduled_task_manager
    if _scheduled_task_manager is None:
        _scheduled_task_manager = ScheduledTaskManager()
    return _scheduled_task_manager


async def start_scheduled_tasks():
    """Start scheduled tasks"""
    manager = get_scheduled_task_manager()
    await manager.start()


async def stop_scheduled_tasks():
    """Stop scheduled tasks"""
    manager = get_scheduled_task_manager()
    await manager.stop()
