from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date

class Location(BaseModel):
    """Geographic location"""
    city: str
    country: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class Budget(BaseModel):
    """Budget constraints"""
    min_amount: float
    max_amount: float
    currency: str = "USD"

class DateRange(BaseModel):
    """Date range for trip"""
    start_date: date
    end_date: date
    num_nights: Optional[int] = None

class TravelPreferences(BaseModel):
    """User travel preferences"""
    style: str  # "luxury", "budget", "mid-range"
    pace: str  # "fast", "moderate", "slow"
    interests: list[str]  # ["history", "nature", "food"]
    dietary_restrictions: Optional[list[str]] = None
    accessibility_needs: Optional[list[str]] = None
