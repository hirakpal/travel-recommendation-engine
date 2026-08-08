"""Trip models used by the travel recommendation engine."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.models.activities import ActivityRecommendation
from src.models.base import Budget, DateRange, Location, TravelPreferences
from src.models.hotel import HotelRecommendation
from src.models.restaurant import RestaurantRecommendation


class TripStatus(str, Enum):
    """Lifecycle state of a trip recommendation."""

    DRAFT = "draft"
    PLANNING = "planning"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Trip(BaseModel):
    """A complete trip request and its generated recommendations."""

    id: Optional[str] = None
    destination: Location
    date_range: DateRange
    budget: Budget
    preferences: TravelPreferences
    travelers: int = Field(default=1, ge=1)
    status: TripStatus = TripStatus.DRAFT

    hotel_recommendations: list[HotelRecommendation] = Field(
        default_factory=list
    )
    activity_recommendations: list[ActivityRecommendation] = Field(
        default_factory=list
    )
    restaurant_recommendations: list[RestaurantRecommendation] = Field(
        default_factory=list
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

