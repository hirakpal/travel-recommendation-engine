"""Comprehensive error recovery strategies."""

import asyncio
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class ExponentialBackoff:
    """Exponential backoff retry strategy."""
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        max_retries: int = 5
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.max_retries = max_retries
    
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with exponential backoff."""
        
        delay = self.initial_delay
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * self.multiplier, self.max_delay)
                else:
                    logger.error(f"All {self.max_retries} attempts failed")
        
        raise last_exception

class ErrorRecoveryManager:
    """Manages error recovery across system."""
    
    def __init__(self):
        self.backoff = ExponentialBackoff()
    
    async def safe_call(
        self,
        func: Callable,
        fallback: Optional[Any] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Call function with error recovery.
        
        Falls back to default value on failure.
        """
        
        try:
            return await self.backoff.execute(func, *args, **kwargs)
        
        except Exception as e:
            logger.error(f"Error recovery failed: {e}")
            if fallback is not None:
                return fallback
            raise
