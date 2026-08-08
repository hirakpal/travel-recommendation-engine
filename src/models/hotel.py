from pydantic import BaseModel
from typing import Optional

class Hotel(BaseModel):
    """Hotel recommendation"""
    id: str
    name: str
    city: str
    star_rating: float  # 1-5
    price_per_night: float
    currency: str = "USD"
    amenities: list[str]
    address: str
    rating_score: float
    rating_count: int
    description: str
    is_available: bool = True
    booking_url: Optional[str] = None

class HotelSearch(BaseModel):
    """Hotel search request"""
    city: str
    check_in_date: str
    check_out_date: str
    num_nights: int
    budget_min: float
    budget_max: float
    star_rating_min: float = 3.0
    required_amenities: list[str] = []

class HotelRecommendation(BaseModel):
    """Hotel recommendation response"""
    hotel: Hotel
    match_score: float  # 0-1
    reasoning: str
    booking_url: Optional[str] = None
