"""Health checks and system monitoring."""

from datetime import datetime
from dataclasses import dataclass
from typing import Optional

@dataclass
class HealthStatus:
    """System health status."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    checks: dict
    message: str = ""

class HealthChecker:
    """Health checks for system components."""
    
    def __init__(self):
        self.last_check = None
        self.status_history = []
    
    async def check_llm_client(self, llm_client) -> bool:
        """Check if LLM client is responsive."""
        try:
            # Quick API call
            await llm_client.call(
                system_prompt="Test",
                user_message="ping",
                max_tokens=10
            )
            return True
        except Exception as e:
            print(f"LLM check failed: {e}")
            return False
    
    async def check_database(self, db_connection) -> bool:
        """Check if database is responsive."""
        try:
            # Quick query
            await db_connection.execute("SELECT 1")
            return True
        except Exception as e:
            print(f"Database check failed: {e}")
            return False
    
    async def check_cache(self, cache) -> bool:
        """Check if cache is responsive."""
        try:
            # Quick set/get
            await cache.set("health_check", "ok", ttl=60)
            result = await cache.get("health_check")
            return result is not None
        except Exception as e:
            print(f"Cache check failed: {e}")
            return False
    
    async def full_check(self, components: dict) -> HealthStatus:
        """Run full health check."""
        
        checks = {}
        all_healthy = True
        
        for name, checker in components.items():
            try:
                result = await checker()
                checks[name] = "healthy" if result else "unhealthy"
                if not result:
                    all_healthy = False
            except Exception as e:
                checks[name] = f"error: {e}"
                all_healthy = False
        
        status = "healthy" if all_healthy else "degraded"
        
        health = HealthStatus(
            status=status,
            timestamp=datetime.now(),
            checks=checks
        )
        
        self.status_history.append(health)
        self.last_check = health
        
        return health
