from pydantic import BaseModel
from typing import Optional

class Activity(BaseModel):
    """Activity recommendation"""
    id: str
    name: str
    city: str
    category: str  # "adventure", "cultural", "food", etc.
    duration_minutes: int
    cost: float
    currency: str = "USD"
    difficulty: str  # "easy", "moderate", "hard"
    rating_score: float
    description: str
    best_time: str  # "morning", "afternoon", "evening"
    requires_booking: bool = False

class ActivitySearch(BaseModel):
    """Activity search request"""
    city: str
    date: str
    interests: list[str]
    max_duration: int = 480  # minutes
    budget_per_activity: float
    num_activities: int = 5
    difficulty_level: str = "moderate"

class ActivityRecommendation(BaseModel):
    """Activity recommendation response"""
    activity: Activity
    match_score: float  # 0-1
    reasoning: str
    time_slot: str  # "morning", "afternoon", "evening"
    booking_info: Optional[dict] = None
