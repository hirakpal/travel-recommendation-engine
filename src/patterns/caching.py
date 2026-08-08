"""Prompt caching for cost optimization."""

import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta

class PromptCache:
    """
    Caching strategy for prompts.
    
    Cost savings:
    - Input tokens with cache: $0.003/1K (vs $0.015 without)
    - Savings: 80% on cached input tokens
    """
    
    def __init__(self, ttl_hours: int = 24):
        self.store = {}
        self.ttl = timedelta(hours=ttl_hours)
    
    def _make_key(self, system_prompt: str, user_message: str) -> str:
        """Generate cache key from prompts."""
        combined = f"{system_prompt}|{user_message}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    async def get(
        self,
        system_prompt: str,
        user_message: str
    ) -> Optional[str]:
        """Get cached response."""
        key = self._make_key(system_prompt, user_message)
        
        if key in self.store:
            entry = self.store[key]
            if datetime.now() < entry["expires"]:
                entry["hits"] += 1
                return entry["response"]
            else:
                del self.store[key]
        
        return None
    
    async def set(
        self,
        system_prompt: str,
        user_message: str,
        response: str
    ):
        """Cache response."""
        key = self._make_key(system_prompt, user_message)
        
        self.store[key] = {
            "response": response,
            "expires": datetime.now() + self.ttl,
            "hits": 0,
            "created": datetime.now()
        }
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_hits = sum(e["hits"] for e in self.store.values())
        total_entries = len(self.store)
        
        return {
            "total_entries": total_entries,
            "total_hits": total_hits,
            "hit_rate": total_hits / (total_hits + 1) if total_entries > 0 else 0,
            "estimated_savings": f"${total_hits * 0.012:.2f}"  # ~$0.012 per hit
        }
