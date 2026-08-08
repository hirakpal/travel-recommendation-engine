"""
Base agent with Master Trip Register integration.
"""

from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from src.database.trip_register_repository import TripRegisterRepository


class BaseAgent(ABC):
    """Base agent with register support."""
    
    def __init__(self, db: Session):
        self.db = db
        self.register = TripRegisterRepository(db)
    
    @abstractmethod
    async def recommend(self, trip_id: str, **kwargs):
        """Make recommendation using register."""
        pass
    
    # ==================== HELPER METHODS ====================
    
    def get_trip_state(self, trip_id: str):
        """Get current trip state from register."""
        return self.register.get_trip(trip_id)
    
    def get_budget_info(self, trip_id: str):
        """Get budget info from register."""
        return self.register.get_budget_summary(trip_id)
    
    def check_budget(self, trip_id: str, amount: float) -> bool:
        """Check if can afford booking."""
        return self.register.can_afford(trip_id, amount)
    
    def get_existing_bookings(self, trip_id: str, booking_type: str = None):
        """Get existing bookings."""
        return self.register.get_trip_bookings(trip_id, booking_type=booking_type)
    
    def get_itinerary(self, trip_id: str):
        """Get current itinerary."""
        return self.register.get_itinerary(trip_id)
    
    def check_conflicts(self, trip_id: str):
        """Check for conflicts."""
        return self.register.get_conflicts(trip_id, resolved=False)
    
    def add_booking(
        self,
        trip_id: str,
        booking_type: str,
        resource_id: str,
        resource_name: str,
        cost: float,
        **kwargs
    ):
        """Add booking to register."""
        return self.register.add_booking(
            trip_id=trip_id,
            booking_type=booking_type,
            resource_id=resource_id,
            resource_name=resource_name,
            cost=cost,
            agent_name=self.__class__.__name__,
            **kwargs
        )
