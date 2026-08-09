"""Structured draft collected by the Ask Anita conversational assistant."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TripDraft(BaseModel):
    """A trip draft that is safe to update before user confirmation."""

    destination: Optional[str] = None
    check_in_date: Optional[date] = None
    check_out_date: Optional[date] = None
    number_of_nights: Optional[int] = None
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

    # Temporary conversational state; not persisted as trip data.
    pending_date_field: Optional[str] = None
    pending_date_day: Optional[int] = None
    pending_date_month: Optional[int] = None
    date_confirmation_required: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_missing_counts(cls, values: Any) -> Any:
        """Treat LLM placeholder zeros as missing values."""

        if not isinstance(values, dict):
            return values

        normalized = dict(values)
        for field_name in ("travelers", "adults"):
            if normalized.get(field_name) == 0:
                normalized[field_name] = None

        return normalized

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

        # Derived data is always calculated in Python from the two dates.
        if self.check_in_date is not None and self.check_out_date is not None:
            self.number_of_nights = (
                self.check_out_date - self.check_in_date
            ).days
        else:
            self.number_of_nights = None

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
        return (
            not self.missing_required_fields()
            and not self.date_confirmation_required
        )

    @property
    def duration_days(self) -> Optional[int]:
        if self.check_in_date is None or self.check_out_date is None:
            return None
        return (self.check_out_date - self.check_in_date).days

    def merge(self, updates: Dict[str, Any]) -> "TripDraft":
        """Return a validated draft with non-empty updates applied."""

        current = self.model_dump()

        for key, value in updates.items():
            if key not in current:
                continue

            # Conversational state must be allowed to clear itself.  In
            # particular, after Anita receives the missing year for a date,
            # pending_date_field/day/month are intentionally set to None.
            if key in {
                "pending_date_field",
                "pending_date_day",
                "pending_date_month",
            }:
                current[key] = value
                continue

            if value is None or value == "":
                continue
            if key in {"travelers", "adults"} and value == 0:
                continue
            current[key] = value

        return TripDraft.model_validate(current)
