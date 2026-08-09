"""Deterministic Supervisor -> Hotel Agent handoff validation.

This module does not create bookings or update the database.  It only checks
whether the Hotel Agent has enough validated trip context to begin its
recommendation workflow.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HotelHandoff(BaseModel):
    """Validated context passed from Supervisor to Hotel Agent."""

    model_config = ConfigDict(extra="ignore")

    trip_id: Optional[str] = None
    destination: Optional[str] = None
    check_in_date: Optional[date] = None
    check_out_date: Optional[date] = None
    number_of_nights: Optional[int] = Field(default=None, ge=1)
    travelers: Optional[int] = Field(default=None, ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    budget: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None

    # Collected by Hotel Agent after the core handoff is complete.
    accommodation_preferences: Optional[List[str]] = None

    MISSING_FIELD_QUESTIONS: ClassVar[Dict[str, str]] = {
        "trip_id": "I need the trip ID before I can continue with hotel recommendations.",
        "destination": "Which destination should I search for hotels in?",
        "check_in_date": "What is your hotel check-in date?",
        "check_out_date": "What is your hotel check-out date?",
        "number_of_nights": "How many nights will you stay?",
        "travelers": "How many travelers will need accommodation?",
        "adults": "How many of the travelers are adults?",
        "budget": "What is your accommodation budget?",
        "currency": "Which currency should I use for the accommodation budget?",
        "accommodation_preferences": (
            "Which hotel tier do you prefer: Budget / Backpacker, Mid-Range, "
            "or Luxury / 5-Star? You may select one or more."
        ),
    }

    ACCOMMODATION_OPTIONS: ClassVar[List[str]] = [
        "Budget / Backpacker",
        "Mid-Range",
        "Luxury / 5-Star",
    ]

    @model_validator(mode="after")
    def validate_relationships(self) -> "HotelHandoff":
        """Validate values that are available without guessing missing data."""

        if self.check_in_date and self.check_out_date:
            if self.check_out_date <= self.check_in_date:
                raise ValueError(
                    "check_out_date must be after check_in_date"
                )

            calculated_nights = (
                self.check_out_date - self.check_in_date
            ).days
            if self.number_of_nights is None:
                self.number_of_nights = calculated_nights
            elif self.number_of_nights != calculated_nights:
                raise ValueError(
                    "number_of_nights does not match the supplied dates"
                )

        if self.travelers is not None and self.adults is not None:
            if self.adults > self.travelers:
                raise ValueError("adults cannot exceed travelers")

        if self.currency:
            self.currency = self.currency.upper().strip()

        if self.accommodation_preferences is not None:
            self.accommodation_preferences = [
                value.strip()
                for value in self.accommodation_preferences
                if value and value.strip()
            ]

        return self

    @classmethod
    def from_trip_draft(
        cls,
        draft: Any,
        trip_id: Optional[str] = None,
    ) -> "HotelHandoff":
        """Build a handoff from a TripDraft without database access."""

        return cls(
            trip_id=trip_id,
            destination=getattr(draft, "destination", None),
            check_in_date=getattr(draft, "check_in_date", None),
            check_out_date=getattr(draft, "check_out_date", None),
            number_of_nights=getattr(draft, "number_of_nights", None),
            travelers=getattr(draft, "travelers", None),
            adults=getattr(draft, "adults", None),
            budget=getattr(draft, "budget", None),
            currency=getattr(draft, "currency", None),
            accommodation_preferences=getattr(
                draft,
                "accommodation_preferences",
                None,
            ),
        )

    def missing_fields(
        self,
        *,
        include_accommodation_preferences: bool = False,
    ) -> List[str]:
        """Return only fields absent from the handoff.

        Accommodation preferences are excluded from the initial gate because
        the Hotel Agent asks the user for them after the core handoff passes.
        Pass ``include_accommodation_preferences=True`` for the final gate.
        """

        required = [
            "trip_id",
            "destination",
            "check_in_date",
            "check_out_date",
            "number_of_nights",
            "travelers",
            "adults",
            "budget",
            "currency",
        ]
        if include_accommodation_preferences:
            required.append("accommodation_preferences")

        missing: List[str] = []
        for field_name in required:
            value = getattr(self, field_name)
            if value is None or value == "" or value == []:
                missing.append(field_name)
        return missing

    def missing_questions(
        self,
        *,
        include_accommodation_preferences: bool = False,
    ) -> List[str]:
        """Return questions corresponding only to currently missing fields."""

        return [
            self.MISSING_FIELD_QUESTIONS[field]
            for field in self.missing_fields(
                include_accommodation_preferences=(
                    include_accommodation_preferences
                )
            )
        ]

    @property
    def ready_for_hotel_agent(self) -> bool:
        """Whether core trip context is ready for Hotel Agent."""

        return not self.missing_fields()

    @property
    def ready_for_recommendations(self) -> bool:
        """Whether core context and accommodation preferences are ready."""

        return not self.missing_fields(
            include_accommodation_preferences=True
        )

    def as_agent_input(self) -> Dict[str, Any]:
        """Return a safe, JSON-serializable payload for Hotel Agent."""

        return self.model_dump(mode="json", exclude_none=True)
