"""Token bucket rate limiting."""

from typing import Optional
from datetime import datetime, timedelta
import asyncio

class TokenBucket:
    """
    Token bucket for rate limiting.
    
    Tiered limits:
    - Hotel: 30 requests/minute
    - Restaurant: 120 requests/minute
    - Activities: 60 requests/minute
    """
    
    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        refill_interval: float = 60.0
    ):
        """
        Initialize token bucket.
        
        Args:
            capacity: Max tokens
            refill_rate: Tokens to add per interval
            refill_interval: Seconds between refills
        """
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.refill_interval = refill_interval
        self.last_refill = datetime.now()
    
    async def consume(self, tokens: int = 1) -> bool:
        """
        Consume tokens. Return True if allowed.
        
        False if rate limited.
        """
        await self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    async def _refill(self):
        """Refill tokens based on time elapsed."""
        now = datetime.now()
        elapsed = (now - self.last_refill).total_seconds()
        
        refills = elapsed // self.refill_interval
        if refills > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + (refills * self.refill_rate)
            )
            self.last_refill = now
    
    async def wait_available(self, tokens: int = 1) -> None:
        """Wait until tokens available."""
        while not await self.consume(tokens):
            await asyncio.sleep(0.1)

class RateLimiter:
    """Rate limiter for different services."""
    
    def __init__(self):
        # 30 requests per minute
        self.hotel_bucket = TokenBucket(
            capacity=30,
            refill_rate=0.5,
            refill_interval=60.0
        )
        
        # 120 requests per minute
        self.restaurant_bucket = TokenBucket(
            capacity=120,
            refill_rate=2.0,
            refill_interval=60.0
        )
        
        # 60 requests per minute
        self.activities_bucket = TokenBucket(
            capacity=60,
            refill_rate=1.0,
            refill_interval=60.0
        )
    
    async def check_hotel(self) -> bool:
        """Check if hotel request allowed."""
        return await self.hotel_bucket.consume()
    
    async def check_restaurant(self) -> bool:
        """Check if restaurant request allowed."""
        return await self.restaurant_bucket.consume()
    
    async def check_activities(self) -> bool:
        """Check if activities request allowed."""
        return await self.activities_bucket.consume()
