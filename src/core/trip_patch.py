"""Validated partial updates for an existing Master Trip Register record."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TripPatch(BaseModel):
    """Only fields explicitly supplied by the user are changed."""

    model_config = ConfigDict(extra="forbid")

    destination: Optional[str] = None
    check_in_date: Optional[date] = None
    check_out_date: Optional[date] = None
    budget_total: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    travelers: Optional[int] = Field(default=None, ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    interests: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    accessibility_needs: Optional[List[str]] = None
    transport_preferences: Optional[List[str]] = None
    accommodation_preferences: Optional[List[str]] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_patch(self) -> "TripPatch":
        if (
            self.check_in_date is not None
            and self.check_out_date is not None
            and self.check_out_date <= self.check_in_date
        ):
            raise ValueError("check_out_date must be after check_in_date")
        if self.adults is not None and self.travelers is not None:
            if self.adults > self.travelers:
                raise ValueError("adults cannot exceed travelers")
        if self.currency:
            self.currency = self.currency.upper().strip()
        return self

    def changed_fields(self) -> Dict[str, Any]:
        """Return only fields explicitly provided by the caller."""

        return self.model_dump(exclude_unset=True)

    @classmethod
    def from_mapping(cls, values: Dict[str, Any]) -> "TripPatch":
        """Validate an extracted intent/update mapping."""

        return cls.model_validate(values)
