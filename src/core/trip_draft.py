"""Structured draft collected by the Ask Anita conversational assistant."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TripDraft(BaseModel):
    """A trip draft that is safe to update before user confirmation."""

    destination: Optional[str] = None
    check_in_date: Optional[date] = None
    check_out_date: Optional[date] = None
    budget: Optional[float] = Field(default=None, gt=0)
    currency: str = "USD"

    travelers: Optional[int] = Field(default=None, ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    interests: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
    accessibility_needs: List[str] = Field(default_factory=list)
    transport_preferences: List[str] = Field(default_factory=list)
    accommodation_preferences: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_date_order(self) -> "TripDraft":
        if (
            self.check_in_date is not None
            and self.check_out_date is not None
            and self.check_out_date <= self.check_in_date
        ):
            raise ValueError(
                "Check-out date must be after check-in date."
            )

        if (
            self.travelers is not None
            and self.adults is not None
            and self.adults > self.travelers
        ):
            raise ValueError(
                "Number of adults cannot exceed number of travelers."
            )

        return self

    def missing_required_fields(self) -> List[str]:
        """Return mandatory fields that Anita still needs."""

        required = {
            "destination": self.destination,
            "check_in_date": self.check_in_date,
            "check_out_date": self.check_out_date,
            "budget": self.budget,
            "travelers": self.travelers,
            "adults": self.adults,
        }
        return [name for name, value in required.items() if not value]

    @property
    def is_complete(self) -> bool:
        return not self.missing_required_fields()

    def merge(self, updates: Dict[str, Any]) -> "TripDraft":
        """Return a validated draft with non-empty updates applied."""

        current = self.model_dump()

        for key, value in updates.items():
            if key not in current:
                continue
            if value is None or value == "":
                continue
            current[key] = value

        return TripDraft.model_validate(current)
