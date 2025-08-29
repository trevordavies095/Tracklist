"""
Rate limiting middleware to prevent abuse
Uses in-memory storage with sliding window algorithm
"""

import time
import logging
from typing import Dict, Tuple, Optional
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter using sliding window algorithm
    """
    
    def __init__(self, requests: int, window_seconds: int):
        """
        Initialize rate limiter
        
        Args:
            requests: Number of requests allowed
            window_seconds: Time window in seconds
        """
        self.max_requests = requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
        self._cleanup_interval = 300  # Cleanup old entries every 5 minutes
        self._last_cleanup = time.time()
    
    def is_allowed(self, identifier: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed
        
        Args:
            identifier: Client identifier (IP address)
            
        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        now = time.time()
        
        # Periodic cleanup
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries()
            self._last_cleanup = now
        
        # Get request history for this identifier
        request_times = self.requests[identifier]
        
        # Remove old requests outside the window
        cutoff_time = now - self.window_seconds
        while request_times and request_times[0] < cutoff_time:
            request_times.popleft()
        
        # Check if limit exceeded
        if len(request_times) >= self.max_requests:
            # Calculate when the oldest request will expire
            oldest_request = request_times[0]
            retry_after = int(oldest_request + self.window_seconds - now) + 1
            return False, retry_after
        
        # Add current request
        request_times.append(now)
        return True, None
    
    def _cleanup_old_entries(self):
        """Remove entries with no recent requests"""
        now = time.time()
        cutoff_time = now - self.window_seconds
        
        # Find and remove inactive identifiers
        inactive = []
        for identifier, request_times in self.requests.items():
            # Remove old requests
            while request_times and request_times[0] < cutoff_time:
                request_times.popleft()
            
            # Mark for removal if no recent requests
            if not request_times:
                inactive.append(identifier)
        
        # Remove inactive entries
        for identifier in inactive:
            del self.requests[identifier]
        
        if inactive:
            logger.debug(f"Cleaned up {len(inactive)} inactive rate limit entries")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting
    """
    
    # Default rate limits per endpoint pattern
    DEFAULT_LIMITS = {
        "/api/v1/search": (30, 60),           # 30 requests per minute
        "/api/v1/albums": (10, 60),           # 10 album creations per minute
        "/api/v1/tracks/*/rating": (100, 60), # 100 rating updates per minute
        "/api/v1/system": (60, 60),           # 60 system requests per minute
        "default": (1000, 3600),              # 1000 requests per hour globally
    }
    
    def __init__(self, app, limits: Optional[Dict[str, Tuple[int, int]]] = None):
        """
        Initialize rate limit middleware
        
        Args:
            app: FastAPI application
            limits: Optional custom limits dict {path_pattern: (requests, seconds)}
        """
        super().__init__(app)
        self.limits = limits or self.DEFAULT_LIMITS
        self.limiters = {}
        
        # Create rate limiters for each endpoint pattern
        for pattern, (requests, seconds) in self.limits.items():
            self.limiters[pattern] = RateLimiter(requests, seconds)
        
        logger.info("Rate limiting middleware initialized")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request with rate limiting
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response or raises HTTPException if rate limited
        """
        # Skip rate limiting for static files and health checks
        if request.url.path.startswith("/static") or request.url.path == "/health":
            return await call_next(request)
        
        # Get client identifier (IP address)
        client_ip = self._get_client_ip(request)
        
        # Find matching rate limiter
        limiter = self._get_limiter_for_path(request.url.path)
        
        # Check rate limit
        allowed, retry_after = limiter.is_allowed(client_ip)
        
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for {client_ip} on {request.url.path}"
            )
            
            # Return 429 Too Many Requests response directly
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please try again in {retry_after} seconds.",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )
        
        # Continue with request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = limiter.max_requests - len(limiter.requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time() + limiter.window_seconds)
        )
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address from request
        
        Args:
            request: Incoming request
            
        Returns:
            Client IP address
        """
        # Check for forwarded IP (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if request.client:
            return request.client.host
        
        # Default if no IP found
        return "unknown"
    
    def _get_limiter_for_path(self, path: str) -> RateLimiter:
        """
        Get the appropriate rate limiter for a path
        
        Args:
            path: Request path
            
        Returns:
            RateLimiter instance
        """
        # Check for exact match first
        if path in self.limiters:
            return self.limiters[path]
        
        # Check for pattern match
        for pattern, limiter in self.limiters.items():
            if pattern == "default":
                continue
            
            # Simple wildcard matching
            if "*" in pattern:
                pattern_parts = pattern.split("*")
                if len(pattern_parts) == 2:
                    # Check if path starts with first part and ends with second part
                    if path.startswith(pattern_parts[0]) and path.endswith(pattern_parts[1]):
                        return limiter
            
            # Check if path starts with pattern
            if path.startswith(pattern):
                return limiter
        
        # Fall back to default limiter
        return self.limiters.get("default", self.limiters[list(self.limiters.keys())[0]])


def get_rate_limiter(
    requests: int = 60,
    window_seconds: int = 60
) -> RateLimiter:
    """
    Factory function to create a rate limiter
    
    Args:
        requests: Number of requests allowed
        window_seconds: Time window in seconds
        
    Returns:
        RateLimiter instance
    """
    return RateLimiter(requests, window_seconds)