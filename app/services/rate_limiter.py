"""
Rate limiter for external API calls
Ensures compliance with API rate limits
"""

import asyncio
import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API calls
    """
    
    def __init__(self, calls_per_second: float = 1.0, burst_size: Optional[int] = None):
        """
        Initialize rate limiter
        
        Args:
            calls_per_second: Maximum calls per second
            burst_size: Maximum burst size (defaults to calls_per_second)
        """
        self.calls_per_second = calls_per_second
        self.interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.burst_size = burst_size or max(1, int(calls_per_second))
        
        self._tokens = self.burst_size
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
        
        logger.debug(f"RateLimiter initialized: {calls_per_second} calls/sec, burst size: {self.burst_size}")
    
    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens from the bucket, waiting if necessary
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited in seconds
        """
        start_time = time.monotonic()
        
        async with self._lock:
            while tokens > self._tokens:
                # Calculate how many tokens we've accumulated since last update
                now = time.monotonic()
                elapsed = now - self._last_update
                new_tokens = elapsed * self.calls_per_second
                
                self._tokens = min(self.burst_size, self._tokens + new_tokens)
                self._last_update = now
                
                if tokens > self._tokens:
                    # Still not enough tokens, wait for more
                    wait_time = (tokens - self._tokens) / self.calls_per_second
                    logger.debug(f"Rate limit: waiting {wait_time:.2f}s for {tokens} tokens")
                    await asyncio.sleep(wait_time)
            
            # We have enough tokens, consume them
            self._tokens -= tokens
            
        wait_time = time.monotonic() - start_time
        if wait_time > 0.01:  # Only log if we actually waited
            logger.debug(f"Rate limiter waited {wait_time:.2f}s")
        
        return wait_time
    
    def reset(self):
        """Reset the rate limiter to full capacity"""
        self._tokens = self.burst_size
        self._last_update = time.monotonic()


class DomainRateLimiter:
    """
    Rate limiter that manages different limits per domain
    """
    
    # Default rate limits per domain
    DOMAIN_LIMITS = {
        'coverartarchive.org': 1.0,  # 1 request per second
        'archive.org': 1.0,           # Cover Art Archive mirror
        'musicbrainz.org': 1.0,       # MusicBrainz API
        'default': 10.0               # Default for other domains
    }
    
    def __init__(self):
        """Initialize domain-based rate limiter"""
        self._limiters: Dict[str, RateLimiter] = {}
        self._last_request: Dict[str, float] = defaultdict(float)
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
    
    def _get_limiter(self, domain: str) -> RateLimiter:
        """Get or create rate limiter for domain"""
        if domain not in self._limiters:
            # Check if we have a specific limit for this domain
            for key, limit in self.DOMAIN_LIMITS.items():
                if key in domain:
                    rate = limit
                    break
            else:
                rate = self.DOMAIN_LIMITS['default']
            
            self._limiters[domain] = RateLimiter(calls_per_second=rate)
            logger.info(f"Created rate limiter for {domain}: {rate} req/s")
        
        return self._limiters[domain]
    
    async def acquire(self, url: str) -> float:
        """
        Acquire permission to make a request to the given URL
        
        Args:
            url: Target URL
            
        Returns:
            Time waited in seconds
        """
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        
        # Record request time
        wait_time = await limiter.acquire()
        self._last_request[domain] = time.monotonic()
        
        return wait_time
    
    def get_stats(self) -> Dict:
        """Get rate limiting statistics"""
        stats = {}
        for domain, limiter in self._limiters.items():
            stats[domain] = {
                'rate': limiter.calls_per_second,
                'tokens_available': limiter._tokens,
                'last_request': self._last_request.get(domain, 0)
            }
        return stats


# Global instance
_domain_rate_limiter = None


def get_domain_rate_limiter() -> DomainRateLimiter:
    """Get or create global domain rate limiter"""
    global _domain_rate_limiter
    if _domain_rate_limiter is None:
        _domain_rate_limiter = DomainRateLimiter()
    return _domain_rate_limiter