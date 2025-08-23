"""
User-specific rate limiter for application features
Prevents abuse of resource-intensive operations
"""

import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)


class UserRateLimiter:
    """
    Simple in-memory rate limiter for user operations
    Uses a sliding window approach for rate limiting
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 3600,
        identifier: str = "operation",
    ):
        """
        Initialize user rate limiter

        Args:
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds (default 1 hour)
            identifier: Name of the operation being limited
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.identifier = identifier

        # Store request timestamps per user/session
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

        logger.debug(
            f"UserRateLimiter initialized for {identifier}: "
            f"{max_requests} requests per {window_seconds} seconds"
        )

    def _clean_old_requests(self, user_id: str) -> None:
        """Remove requests outside the current window"""
        now = time.time()
        cutoff = now - self.window_seconds

        # Keep only requests within the window
        self._requests[user_id] = [
            timestamp for timestamp in self._requests[user_id] if timestamp > cutoff
        ]

    def check_rate_limit(self, user_id: str) -> tuple[bool, Optional[Dict]]:
        """
        Check if user has exceeded rate limit

        Args:
            user_id: Unique identifier for the user/session

        Returns:
            Tuple of (allowed, info_dict)
            - allowed: True if request is allowed
            - info_dict: Information about rate limit status
        """
        with self._lock:
            # Clean old requests
            self._clean_old_requests(user_id)

            request_count = len(self._requests[user_id])

            if request_count >= self.max_requests:
                # Calculate when the oldest request will expire
                oldest_request = min(self._requests[user_id])
                reset_time = oldest_request + self.window_seconds
                wait_seconds = max(0, reset_time - time.time())

                return False, {
                    "requests_made": request_count,
                    "max_requests": self.max_requests,
                    "window_seconds": self.window_seconds,
                    "reset_in_seconds": int(wait_seconds),
                    "reset_at": datetime.fromtimestamp(reset_time).isoformat(),
                }

            # Request is allowed
            remaining = self.max_requests - request_count

            return True, {
                "requests_made": request_count,
                "requests_remaining": remaining,
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
            }

    def record_request(self, user_id: str) -> None:
        """
        Record a request from the user

        Args:
            user_id: Unique identifier for the user/session
        """
        with self._lock:
            self._requests[user_id].append(time.time())
            logger.debug(f"Recorded {self.identifier} request for user {user_id}")

    def reset_user(self, user_id: str) -> None:
        """
        Reset rate limit for a specific user

        Args:
            user_id: Unique identifier for the user/session
        """
        with self._lock:
            if user_id in self._requests:
                del self._requests[user_id]
                logger.debug(f"Reset {self.identifier} rate limit for user {user_id}")

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self._lock:
            total_users = len(self._requests)
            total_requests = sum(len(reqs) for reqs in self._requests.values())

            return {
                "identifier": self.identifier,
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "active_users": total_users,
                "total_requests": total_requests,
            }


class ArtworkRefreshLimiter:
    """
    Specialized rate limiter for artwork refresh operations
    """

    # Conservative limits to prevent abuse
    # Allow 5 refreshes per hour per session
    MAX_REFRESHES_PER_HOUR = 5

    # Allow 20 refreshes per day per session
    MAX_REFRESHES_PER_DAY = 20

    def __init__(self):
        """Initialize artwork refresh rate limiters"""
        self.hourly_limiter = UserRateLimiter(
            max_requests=self.MAX_REFRESHES_PER_HOUR,
            window_seconds=3600,  # 1 hour
            identifier="artwork_refresh_hourly",
        )

        self.daily_limiter = UserRateLimiter(
            max_requests=self.MAX_REFRESHES_PER_DAY,
            window_seconds=86400,  # 24 hours
            identifier="artwork_refresh_daily",
        )

        logger.info(
            f"ArtworkRefreshLimiter initialized: "
            f"{self.MAX_REFRESHES_PER_HOUR}/hour, {self.MAX_REFRESHES_PER_DAY}/day"
        )

    def check_limit(self, session_id: str) -> tuple[bool, Optional[Dict]]:
        """
        Check if artwork refresh is allowed

        Args:
            session_id: Session identifier

        Returns:
            Tuple of (allowed, limit_info)
        """
        # Check hourly limit first
        hourly_allowed, hourly_info = self.hourly_limiter.check_rate_limit(session_id)
        if not hourly_allowed:
            return False, {
                "limit_type": "hourly",
                "message": f"Hourly refresh limit exceeded ({self.MAX_REFRESHES_PER_HOUR} per hour)",
                **hourly_info,
            }

        # Check daily limit
        daily_allowed, daily_info = self.daily_limiter.check_rate_limit(session_id)
        if not daily_allowed:
            return False, {
                "limit_type": "daily",
                "message": f"Daily refresh limit exceeded ({self.MAX_REFRESHES_PER_DAY} per day)",
                **daily_info,
            }

        # Both limits OK
        return True, {"allowed": True, "hourly": hourly_info, "daily": daily_info}

    def record_refresh(self, session_id: str) -> None:
        """Record an artwork refresh"""
        self.hourly_limiter.record_request(session_id)
        self.daily_limiter.record_request(session_id)

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            "hourly": self.hourly_limiter.get_stats(),
            "daily": self.daily_limiter.get_stats(),
        }


# Global instance
_artwork_refresh_limiter = None


def get_artwork_refresh_limiter() -> ArtworkRefreshLimiter:
    """Get or create global artwork refresh rate limiter"""
    global _artwork_refresh_limiter
    if _artwork_refresh_limiter is None:
        _artwork_refresh_limiter = ArtworkRefreshLimiter()
    return _artwork_refresh_limiter
