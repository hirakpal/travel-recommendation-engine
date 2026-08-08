"""Cache manager (Redis wrapper)."""

import json
from typing import Optional, Any

class CacheManager:
    """Simple in-memory cache (use Redis in production)."""
    
    def __init__(self):
        self.store = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        return self.store.get(key)
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        self.store[key] = {
            "value": value,
            "ttl": ttl
        }
    
    async def delete(self, key: str):
        """Delete from cache."""
        if key in self.store:
            del self.store[key]
    
    async def clear_all(self):
        """Clear all cache."""
        self.store.clear()
