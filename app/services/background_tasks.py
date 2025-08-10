"""
Background task management for non-blocking operations
Handles artwork caching and other async tasks
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from collections import deque
import traceback

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """
    Manages background tasks for the application
    Uses asyncio to run tasks without blocking the main application
    """
    
    def __init__(self, max_concurrent_tasks: int = 3):
        """
        Initialize the background task manager
        
        Args:
            max_concurrent_tasks: Maximum number of concurrent background tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self._task_queue = deque()
        self._running_tasks = {}
        self._completed_tasks = deque(maxlen=100)  # Keep last 100 completed tasks
        self._failed_tasks = deque(maxlen=50)  # Keep last 50 failed tasks
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._task_counter = 0
        self._shutdown = False
        
        # Start the task processor
        self._processor_task = None
        
    async def start(self):
        """Start the background task processor"""
        if not self._processor_task:
            self._processor_task = asyncio.create_task(self._process_tasks())
            logger.info("Background task manager started")
    
    async def stop(self):
        """Stop the background task processor"""
        self._shutdown = True
        if self._processor_task:
            await self._processor_task
            logger.info("Background task manager stopped")
    
    async def _process_tasks(self):
        """Process tasks from the queue"""
        while not self._shutdown:
            try:
                # Check if we have tasks to process
                if self._task_queue and len(self._running_tasks) < self.max_concurrent_tasks:
                    task_info = self._task_queue.popleft()
                    
                    # Create and start the task
                    task = asyncio.create_task(self._run_task(task_info))
                    self._running_tasks[task_info['id']] = {
                        'task': task,
                        'info': task_info,
                        'started_at': datetime.now(timezone.utc)
                    }
                    
                # Clean up completed tasks
                completed = []
                for task_id, task_data in self._running_tasks.items():
                    if task_data['task'].done():
                        completed.append(task_id)
                
                for task_id in completed:
                    del self._running_tasks[task_id]
                
                # Sleep briefly to avoid busy waiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in task processor: {e}")
                await asyncio.sleep(1)
    
    async def _run_task(self, task_info: Dict[str, Any]):
        """Run a single task with error handling"""
        async with self._semaphore:
            try:
                logger.info(f"Starting task {task_info['id']}: {task_info['name']}")
                
                # Execute the task function
                func = task_info['func']
                args = task_info.get('args', ())
                kwargs = task_info.get('kwargs', {})
                
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    # Run sync functions in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, func, *args, **kwargs)
                
                # Record success
                self._completed_tasks.append({
                    'id': task_info['id'],
                    'name': task_info['name'],
                    'completed_at': datetime.now(timezone.utc),
                    'result': result
                })
                
                logger.info(f"Task {task_info['id']} completed successfully")
                
                # Call success callback if provided
                if 'on_success' in task_info:
                    await self._call_callback(task_info['on_success'], result)
                
                return result
                
            except Exception as e:
                # Record failure
                error_msg = str(e)
                error_trace = traceback.format_exc()
                
                self._failed_tasks.append({
                    'id': task_info['id'],
                    'name': task_info['name'],
                    'failed_at': datetime.now(timezone.utc),
                    'error': error_msg,
                    'traceback': error_trace
                })
                
                logger.error(f"Task {task_info['id']} failed: {error_msg}")
                
                # Call error callback if provided
                if 'on_error' in task_info:
                    await self._call_callback(task_info['on_error'], e)
                
                # Re-raise if critical
                if task_info.get('critical', False):
                    raise
    
    async def _call_callback(self, callback: Callable, arg: Any):
        """Call a callback function safely"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(arg)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, callback, arg)
        except Exception as e:
            logger.error(f"Error in callback: {e}")
    
    def add_task(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        name: Optional[str] = None,
        priority: int = 5,
        critical: bool = False,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ) -> str:
        """
        Add a task to the background queue
        
        Args:
            func: Function to execute
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            name: Human-readable task name
            priority: Task priority (1=highest, 10=lowest)
            critical: If True, errors will be re-raised
            on_success: Callback on successful completion
            on_error: Callback on error
            
        Returns:
            Task ID
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}_{datetime.now(timezone.utc).timestamp()}"
        
        task_info = {
            'id': task_id,
            'name': name or func.__name__,
            'func': func,
            'args': args,
            'kwargs': kwargs or {},
            'priority': priority,
            'critical': critical,
            'on_success': on_success,
            'on_error': on_error,
            'queued_at': datetime.now(timezone.utc)
        }
        
        # Add to queue based on priority
        if priority <= 3:
            self._task_queue.appendleft(task_info)
        else:
            self._task_queue.append(task_info)
        
        logger.debug(f"Task {task_id} queued: {task_info['name']}")
        return task_id
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the task manager"""
        return {
            'queued': len(self._task_queue),
            'running': len(self._running_tasks),
            'completed': len(self._completed_tasks),
            'failed': len(self._failed_tasks),
            'max_concurrent': self.max_concurrent_tasks,
            'shutdown': self._shutdown,
            'running_tasks': [
                {
                    'id': task_id,
                    'name': data['info']['name'],
                    'started_at': data['started_at'].isoformat()
                }
                for task_id, data in self._running_tasks.items()
            ]
        }
    
    def get_task_history(self, limit: int = 20) -> Dict[str, Any]:
        """Get recent task history"""
        return {
            'completed': list(self._completed_tasks)[-limit:],
            'failed': list(self._failed_tasks)[-limit:]
        }


# Global instance
_background_manager = None


def get_background_manager() -> BackgroundTaskManager:
    """Get the global background task manager instance"""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager


async def start_background_tasks():
    """Start the background task system"""
    manager = get_background_manager()
    await manager.start()


async def stop_background_tasks():
    """Stop the background task system"""
    manager = get_background_manager()
    await manager.stop()