"""Conversation and trip context management."""

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class UserPreferences(BaseModel):
    """User preferences."""
    budget_conscious: bool = False
    luxury_preference: bool = False
    adventure_seeker: bool = False
    cultural_interest: bool = True
    food_enthusiast: bool = True

class SessionState(BaseModel):
    """Complete session state."""
    session_id: str
    user_id: Optional[str]
    created_at: datetime
    last_activity: datetime
    
    # Trip context
    destination: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    budget: Optional[float] = None
    interests: list[str] = []
    party_size: int = 1
    dietary_restrictions: list[str] = []
    
    # User preferences
    preferences: UserPreferences = UserPreferences()
    
    # Conversation metadata
    message_count: int = 0
    agents_consulted: list[str] = []
    
    # Bookings
    booked_hotel: Optional[Dict[str, Any]] = None
    booked_activities: list[Dict[str, Any]] = []
    booked_restaurants: list[Dict[str, Any]] = []
