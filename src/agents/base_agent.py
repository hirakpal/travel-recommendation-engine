"""
Base Agent - Abstract base class for all specialized agents.
All agents inherit from BaseAgent and use Master Trip Register.
"""

from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from src.database.trip_register_repository import TripRegisterRepository
from src.core.prompts import get_agent_prompt
import logging

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base agent with Master Trip Register integration.
    
    All specialized agents (Hotel, Activities, Restaurant) inherit from this.
    """
    
    def __init__(self, db: Session, llm_client=None):
        """
        Initialize agent.
        
        Args:
            db: Database session
            llm_client: LLM client (Claude or OpenAI)
        """
        self.db = db
        self.llm_client = llm_client
        self.register = TripRegisterRepository(db)
        self.agent_name = self.__class__.__name__
    
    @abstractmethod
    async def process(self, trip_id: str, **kwargs) -> Dict[str, Any]:
        """
        Process agent request.
        
        Implemented by subclasses:
        - HotelAgent: Book hotel
        - ActivitiesAgent: Plan activities
        - RestaurantAgent: Book restaurants
        """
        pass
    
    # ==================== SHARED METHODS ====================
    
    def get_trip_state(self, trip_id: str) -> Optional[Dict[str, Any]]:
        """Get complete trip state from register."""
        trip = self.register.get_trip(trip_id)
        if not trip:
            logger.error(f"Trip {trip_id} not found")
            return None
        
        logger.info(f"Trip loaded: {trip.destination}, {trip.num_nights} nights")
        return {
            "id": trip.id,
            "destination": trip.destination,
            "check_in": str(trip.check_in_date),
            "check_out": str(trip.check_out_date),
            "nights": trip.num_nights,
            "budget": trip.budget_total,
            "currency": trip.currency,
            "interests": trip.interests,
            "dietary": trip.dietary_restrictions,
            "status": trip.status
        }
    
    def get_budget_info(self, trip_id: str) -> Dict[str, float]:
        """Get budget info from register."""
        budget = self.register.get_budget_summary(trip_id)
        logger.info(f"Budget: ${budget['spent']:.2f} spent, ${budget['remaining']:.2f} remaining")
        return budget
    
    def can_afford(self, trip_id: str, amount: float) -> bool:
        """Check if trip can afford booking."""
        return self.register.can_afford(trip_id, amount)
    
    def get_remaining_budget(self, trip_id: str) -> float:
        """Get remaining budget."""
        return self.register.get_remaining_budget(trip_id)
    
    def get_existing_bookings(self, trip_id: str, booking_type: str = None) -> List:
        """Get existing bookings of type."""
        bookings = self.register.get_trip_bookings(trip_id, booking_type=booking_type)
        logger.info(f"Found {len(bookings)} existing bookings")
        return bookings
    
    def get_itinerary(self, trip_id: str) -> List:
        """Get current itinerary."""
        itinerary = self.register.get_itinerary(trip_id)
        logger.info(f"Current itinerary has {len(itinerary)} items")
        return itinerary
    
    def check_conflicts(self, trip_id: str) -> List:
        """Check for conflicts."""
        conflicts = self.register.get_conflicts(trip_id, resolved=False)
        if conflicts:
            logger.warning(f"Found {len(conflicts)} conflicts")
        return conflicts
    
    def register_booking(
        self,
        trip_id: str,
        booking_type: str,
        resource_id: str,
        resource_name: str,
        cost: float,
        **kwargs
    ) -> tuple[bool, str, Optional[str]]:
        """Register booking with Master Trip Register."""
        logger.info(f"Registering {booking_type} booking: {resource_name} (${cost})")
        
        success, message, booking_id = self.register.add_booking(
            trip_id=trip_id,
            booking_type=booking_type,
            resource_id=resource_id,
            resource_name=resource_name,
            cost=cost,
            agent_name=self.agent_name,
            **kwargs
        )
        
        if success:
            logger.info(f"✅ Booking registered: {message}")
        else:
            logger.error(f"❌ Booking failed: {message}")
        
        return success, message, booking_id
    
    def log_decision(self, trip_id: str, decision: str, reason: str = ""):
        """Log agent decision."""
        logger.info(f"[{self.agent_name}] Decision: {decision}")
        if reason:
            logger.info(f"[{self.agent_name}] Reason: {reason}")
    
    # ==================== LLM INTEGRATION ====================
    
    async def get_llm_recommendation(
        self,
        prompt: str,
        context: Dict[str, Any]
    ) -> str:
        """Get recommendation from LLM."""
        if not self.llm_client:
            logger.warning("No LLM client available")
            return None
        
        full_prompt = f"{prompt}\n\nContext: {context}"
        response = await self.llm_client.call(
            system_prompt="You are a travel recommendation assistant.",
            user_message=full_prompt,
        )
        return response
