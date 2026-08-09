"""Session-only state for hotel recommendations and split-stay selection."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class HotelRecommendation(BaseModel):
    """A hotel option shown to the user; it is not a booking."""

    hotel_id: str
    name: str
    city: Optional[str] = None
    price_per_night: Optional[float] = None
    currency: str = "USD"
    score: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)


class HotelStaySegment(BaseModel):
    """One contiguous hotel stay within the overall trip."""

    sequence: int = Field(ge=1)
    check_in_date: date
    check_out_date: date
    selected_hotel_id: Optional[str] = None
    selected_hotel_name: Optional[str] = None

    @property
    def number_of_nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    @model_validator(mode="after")
    def validate_dates(self) -> "HotelStaySegment":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("Hotel check-out must be after check-in")
        return self


class HotelRecommendationSession(BaseModel):
    """Temporary Hotel Agent working memory held outside the register."""

    trip_id: str
    trip_check_in_date: date
    trip_check_out_date: date
    accommodation_preferences: List[str] = Field(default_factory=list)
    recommendations: List[HotelRecommendation] = Field(default_factory=list)
    segments: List[HotelStaySegment] = Field(default_factory=list)
    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=5, ge=1, le=5)
    single_hotel_for_trip: Optional[bool] = None

    @model_validator(mode="after")
    def validate_trip_dates(self) -> "HotelRecommendationSession":
        if self.trip_check_out_date <= self.trip_check_in_date:
            raise ValueError("Trip check-out must be after check-in")
        self.validate_segments()
        return self

    @property
    def trip_nights(self) -> int:
        return (
            self.trip_check_out_date - self.trip_check_in_date
        ).days

    @property
    def selected_hotel_ids(self) -> List[str]:
        return [
            segment.selected_hotel_id
            for segment in self.segments
            if segment.selected_hotel_id
        ]

    def set_recommendations(
        self,
        recommendations: List[HotelRecommendation],
    ) -> "HotelRecommendationSession":
        self.recommendations = recommendations
        self.page_index = 0
        return self

    def current_page(self) -> List[HotelRecommendation]:
        """Return at most five recommendations for the current page."""

        start = self.page_index * self.page_size
        return self.recommendations[start : start + self.page_size]

    @property
    def has_more_pages(self) -> bool:
        return (
            (self.page_index + 1) * self.page_size
            < len(self.recommendations)
        )

    def show_more(self) -> "HotelRecommendationSession":
        if self.has_more_pages:
            self.page_index += 1
        return self

    def reset_pagination(self) -> "HotelRecommendationSession":
        self.page_index = 0
        return self

    def configure_single_hotel(self, hotel_id: str) -> "HotelRecommendationSession":
        """Use one selected hotel for the complete trip."""

        hotel = self._get_recommendation(hotel_id)
        self.single_hotel_for_trip = True
        self.segments = [
            HotelStaySegment(
                sequence=1,
                check_in_date=self.trip_check_in_date,
                check_out_date=self.trip_check_out_date,
                selected_hotel_id=hotel.hotel_id,
                selected_hotel_name=hotel.name,
            )
        ]
        return self

    def configure_split_stay(
        self,
        first_hotel_id: str,
        first_hotel_check_out: date,
    ) -> "HotelRecommendationSession":
        """Create two contiguous segments with no gaps or overlaps."""

        if first_hotel_check_out <= self.trip_check_in_date:
            raise ValueError(
                "The first hotel must end after the overall trip check-in."
            )
        if first_hotel_check_out >= self.trip_check_out_date:
            raise ValueError(
                "The first hotel must end before the overall trip check-out."
            )

        first_hotel = self._get_recommendation(first_hotel_id)
        second_check_in = first_hotel_check_out
        second_hotel = None
        if len(self.segments) > 1 and self.segments[1].selected_hotel_id:
            second_hotel = self._get_recommendation(
                self.segments[1].selected_hotel_id
            )

        self.single_hotel_for_trip = False
        self.segments = [
            HotelStaySegment(
                sequence=1,
                check_in_date=self.trip_check_in_date,
                check_out_date=first_hotel_check_out,
                selected_hotel_id=first_hotel.hotel_id,
                selected_hotel_name=first_hotel.name,
            ),
            HotelStaySegment(
                sequence=2,
                check_in_date=second_check_in,
                check_out_date=self.trip_check_out_date,
                selected_hotel_id=second_hotel.hotel_id if second_hotel else None,
                selected_hotel_name=second_hotel.name if second_hotel else None,
            ),
        ]
        self.validate_segments()
        return self

    def select_hotel(
        self,
        segment_sequence: int,
        hotel_id: str,
    ) -> "HotelRecommendationSession":
        hotel = self._get_recommendation(hotel_id)
        for segment in self.segments:
            if segment.sequence == segment_sequence:
                segment.selected_hotel_id = hotel.hotel_id
                segment.selected_hotel_name = hotel.name
                break
        else:
            raise ValueError(f"Unknown hotel segment: {segment_sequence}")
        return self

    def remove_hotel(self, segment_sequence: int) -> "HotelRecommendationSession":
        for segment in self.segments:
            if segment.sequence == segment_sequence:
                segment.selected_hotel_id = None
                segment.selected_hotel_name = None
                return self
        raise ValueError(f"Unknown hotel segment: {segment_sequence}")

    def validate_segments(self) -> None:
        """Ensure segments exactly cover the trip with no gaps or overlaps."""

        if not self.segments:
            return

        ordered = sorted(self.segments, key=lambda item: item.sequence)
        if ordered[0].check_in_date != self.trip_check_in_date:
            raise ValueError("First hotel segment must start on trip check-in")
        if ordered[-1].check_out_date != self.trip_check_out_date:
            raise ValueError("Last hotel segment must end on trip check-out")

        for previous, current in zip(ordered, ordered[1:]):
            if current.check_in_date != previous.check_out_date:
                raise ValueError(
                    "Hotel segments must be contiguous; the next check-in "
                    "must equal the previous check-out."
                )

        if sum(item.number_of_nights for item in ordered) != self.trip_nights:
            raise ValueError("Hotel segment nights must equal total trip nights")

    def as_working_memory(self) -> Dict[str, Any]:
        """Return session-safe JSON data; nothing is persisted."""

        return self.model_dump(mode="json")

    def _get_recommendation(self, hotel_id: str) -> HotelRecommendation:
        for recommendation in self.recommendations:
            if recommendation.hotel_id == hotel_id:
                return recommendation
        raise ValueError(f"Hotel recommendation not found: {hotel_id}")
