from pydantic import BaseModel
from typing import Optional

class Restaurant(BaseModel):
    """Restaurant recommendation"""
    id: str
    name: str
    city: str
    cuisine_type: str
    price_level: int  # 1-5 ($ to $$$$$)
    rating_score: float
    rating_count: int
    address: str
    distance_from_hotel_km: Optional[float] = None
    specialty_dishes: list[str]
    vegetarian_options: bool
    vegan_options: bool
    description: str
    booking_url: Optional[str] = None

class RestaurantSearch(BaseModel):
    """Restaurant search request"""
    city: str
    date: str
    meal_type: str  # "breakfast", "lunch", "dinner"
    cuisine_preferences: list[str]
    budget_min: float
    budget_max: float
    party_size: int
    dietary_restrictions: list[str] = []
    ambiance: Optional[str] = None

class RestaurantRecommendation(BaseModel):
    """Restaurant recommendation response"""
    restaurant: Restaurant
    match_score: float  # 0-1
    reasoning: str
    suggested_time: str
    specialty_recommendations: list[str]
    booking_link: Optional[str] = None
