"""Conversational intake service for the Ask Anita assistant."""

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Tuple

from pydantic import BaseModel, Field

from src.core.trip_draft import TripDraft

logger = logging.getLogger(__name__)


class AnitaExtraction(BaseModel):
    """Strict structured output expected from the LLM."""

    updates: Dict[str, Any] = Field(default_factory=dict)
    reply: str = ""


class AskAnita:
    """Collect and validate trip information through conversation."""

    ALLOWED_FIELDS = {
        "destination",
        "check_in_date",
        "check_out_date",
        "budget",
        "currency",
        "travelers",
        "adults",
        "interests",
        "dietary_restrictions",
        "accessibility_needs",
        "transport_preferences",
        "accommodation_preferences",
        "notes",
        "pending_date_field",
        "pending_date_day",
        "pending_date_month",
        "date_confirmation_required",
    }

    def __init__(self, llm_client):
        self.llm = llm_client

    async def chat(
        self,
        draft: TripDraft,
        user_message: str,
    ) -> Tuple[TripDraft, str]:
        """Apply one user message and return the updated draft and reply."""

        logger.info("ANITA_MESSAGE_START")
        logger.info("User message: %s", user_message)

        normalized_message = user_message.strip().lower()

        if draft.date_confirmation_required:
            if normalized_message in {
                "yes",
                "y",
                "confirm",
                "confirmed",
                "looks good",
            }:
                updated_draft = draft.merge(
                    {"date_confirmation_required": False}
                )
                return updated_draft, self.next_question(updated_draft)

            if normalized_message in {
                "exit",
                "cancel",
                "quit",
            }:
                return draft, (
                    "Understood. I will not continue with these dates. "
                    "You can start a new conversation when ready."
                )

            if normalized_message in {"no", "n", "change", "revise"}:
                updated_draft = draft.merge(
                    {
                        "check_in_date": None,
                        "check_out_date": None,
                        "date_confirmation_required": False,
                    }
                )
                return updated_draft, (
                    "Please provide a new check-in and check-out date."
                )

            return draft, (
                "Your trip is longer than 10 days. Please reply "
                "'yes' to confirm these dates, 'no' to change them, "
                "or 'exit' to stop."
            )

        # Count answers are deterministic and must not be delegated to the
        # LLM, because a bare number is otherwise ambiguous.
        count_updates = self._apply_count_answer(
            draft,
            user_message,
            {},
        )
        if count_updates:
            updated_draft = draft.merge(count_updates)
            reply = self.next_question(updated_draft)
            logger.info("ANITA_COUNT_FIX_VERSION=2")
            logger.info(
                "ANITA_MESSAGE_SUCCESS complete=%s missing=%s",
                updated_draft.is_complete,
                updated_draft.missing_required_fields(),
            )
            return updated_draft, reply

        prompt = self._build_prompt(draft, user_message)

        try:
            response = await self.llm.call(
                system_prompt=(
                    "You are Anita, a friendly travel-planning intake "
                    "assistant. Extract trip details only. Never book, "
                    "purchase, or claim that anything is confirmed."
                ),
                user_message=prompt,
                response_format="json",
            )

            data = (
                json.loads(response)
                if isinstance(response, str)
                else response
            )

            extraction = AnitaExtraction.model_validate(data)
            updates = {
                key: value
                for key, value in extraction.updates.items()
                if key in self.ALLOWED_FIELDS
            }

            updates = self._apply_count_answer(
                draft,
                user_message,
                updates,
            )

            try:
                deterministic_updates = (
                    self._extract_deterministic_fields(
                        draft,
                        user_message,
                    )
                )
            except ValueError:
                return draft, (
                    "That is not a valid calendar date. Please provide "
                    "a real day and month, for example: 23 August."
                )
            updates.update(deterministic_updates)

            try:
                candidate = draft.merge(updates)
            except ValueError as exc:
                return draft, (
                    f"I could not use that date: {exc} "
                    "Please provide a valid date."
                )

            if candidate.check_in_date and candidate.check_in_date.year < date.today().year:
                return draft, (
                    "The date year cannot be before the current year "
                    f"({date.today().year}). Please provide a current "
                    "or future year."
                )

            if candidate.check_out_date and candidate.check_out_date.year < date.today().year:
                return draft, (
                    "The date year cannot be before the current year "
                    f"({date.today().year}). Please provide a current "
                    "or future year."
                )

            duration = candidate.duration_days
            date_changed = bool(
                {
                    "check_in_date",
                    "check_out_date",
                }.intersection(updates)
            )

            if date_changed and duration is not None and duration > 20:
                return draft, (
                    "We do not support trips longer than 20 days. "
                    "Please adjust the dates or reply 'exit' to stop."
                )

            if date_changed and duration is not None and duration > 10:
                updates["date_confirmation_required"] = True
                candidate = draft.merge(updates)

            updated_draft = candidate
            
            # Follow-up text is generated from validated state, not from
            # free-form LLM text that may invent a year such as 2023.
            reply = self._build_state_reply(
                updated_draft,
                deterministic_updates,
            )

            logger.info(
                "ANITA_MESSAGE_SUCCESS complete=%s missing=%s",
                updated_draft.is_complete,
                updated_draft.missing_required_fields(),
            )

            return updated_draft, reply

        except Exception:
            logger.exception("ANITA_MESSAGE_FAILED")
            raise

    @staticmethod
    def _build_state_reply(
        draft: TripDraft,
        updates: Dict[str, Any],
    ) -> str:
        """Build a truthful response from validated draft state."""

        acknowledgements = []

        if draft.pending_date_field:
            month_name = date(
                2000,
                draft.pending_date_month,
                draft.pending_date_day,
            ).strftime("%B")
            return (
                f"I understood {month_name} "
                f"{draft.pending_date_day}. Which year should I use? "
                "Please reply with a four-digit year, for example: 2026."
            )

        if draft.date_confirmation_required:
            return (
                f"Your trip is {draft.duration_days} days long. "
                "Please confirm both dates by replying 'yes', reply "
                "'no' to change them, or 'exit' to stop."
            )

        if "check_in_date" in updates:
            acknowledgements.append(
                f"Check-in set to {draft.check_in_date}."
            )

        if "check_out_date" in updates:
            acknowledgements.append(
                f"Check-out set to {draft.check_out_date}."
            )

        if "budget" in updates:
            acknowledgements.append(
                f"Budget set to {draft.budget:,.2f} "
                f"{draft.currency}."
            )

        if draft.is_complete:
            return (
                " ".join(acknowledgements)
                + "\n\nAll required details are collected. "
                "Please review and confirm them."
            )

        next_question = AskAnita.next_question(draft)
        if acknowledgements:
            return " ".join(acknowledgements) + "\n\n" + next_question

        return next_question

    @staticmethod
    def _apply_count_answer(
        draft: TripDraft,
        user_message: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve numeric traveler answers deterministically."""

        text = user_message.strip().lower()
        result = dict(updates)

        adult_match = re.search(r"\b(\d+)\s*adults?\b", text)
        traveler_match = re.search(
            r"\b(\d+)\s*(?:travellers?|travelers?|people)\b",
            text,
        )

        if adult_match:
            result["adults"] = int(adult_match.group(1))
            return result

        if traveler_match:
            result["travelers"] = int(traveler_match.group(1))
            result.pop("adults", None)
            return result

        if re.fullmatch(r"\d+", text):
            number = int(text)

            if draft.travelers is None:
                result["travelers"] = number
                result.pop("adults", None)
            elif draft.adults is None:
                result["adults"] = number

        return result

    @staticmethod
    def _extract_deterministic_fields(
        draft: TripDraft,
        user_message: str,
    ) -> Dict[str, Any]:
        """Extract fields where guessing would be unsafe."""

        text = user_message.strip()
        lower_text = text.lower()
        updates: Dict[str, Any] = {}

        if draft.pending_date_field:
            year_match = re.fullmatch(
                r"(?:year\s*)?(\d{4})",
                lower_text,
            )
            if year_match:
                year = int(year_match.group(1))
                try:
                    parsed = date(
                        year,
                        draft.pending_date_month,
                        draft.pending_date_day,
                    )
                except ValueError:
                    return draft, (
                        "That is not a valid calendar date. "
                        "Please provide a valid year."
                    )
                updates[draft.pending_date_field] = parsed
                updates["pending_date_field"] = None
                updates["pending_date_day"] = None
                updates["pending_date_month"] = None
                return updates

        currency_match = re.search(
            r"(?:inr|usd|eur|gbp|aud|cad|sgd|jpy|\$|€|£)",
            lower_text,
        )

        amount_match = re.search(
            r"(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*"
            r"(?:inr|usd|eur|gbp|aud|cad|sgd|jpy|\$|€|£)?",
            lower_text,
        )

        if currency_match and amount_match:
            currency_token = currency_match.group(0)
            currency_map = {
                "$": "USD",
                "€": "EUR",
                "£": "GBP",
            }
            updates["currency"] = currency_map.get(
                currency_token.upper(),
                currency_token.upper(),
            )
            updates["budget"] = float(
                amount_match.group(1).replace(",", "")
            )

        date_matches = re.findall(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
            r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
            r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"(?:\s+(\d{4}))?\b",
            lower_text,
        )

        parsed_dates = []
        incomplete_date = None
        for day, month, year in date_matches:
            if not year:
                incomplete_date = (int(day), month)
            else:
                parsed_dates.append(
                    AskAnita._parse_user_date(day, month, year)
                )

        if incomplete_date:
            day, month = incomplete_date
            field = (
                "check_in_date"
                if draft.check_in_date is None
                else "check_out_date"
            )
            updates["pending_date_field"] = field
            updates["pending_date_day"] = day
            updates["pending_date_month"] = datetime.strptime(
                month[:3].title(),
                "%b",
            ).month
            updates.pop("check_in_date", None)
            updates.pop("check_out_date", None)
            return updates

        if len(parsed_dates) >= 2:
            updates["check_in_date"] = parsed_dates[0]
            updates["check_out_date"] = parsed_dates[1]
        elif len(parsed_dates) == 1:
            if draft.check_in_date is None:
                updates["check_in_date"] = parsed_dates[0]
            elif draft.check_out_date is None:
                updates["check_out_date"] = parsed_dates[0]

        age_values = re.fullmatch(
            r"\s*(\d{1,3})\s*[,/]\s*(\d{1,3})"
            r"(?:\s*[,/]\s*(\d{1,3}))?\s*",
            text,
        )

        if age_values and draft.travelers is None:
            ages = [
                int(value)
                for value in age_values.groups()
                if value is not None
            ]
            if len(ages) >= 2:
                updates["travelers"] = len(ages)
                updates["adults"] = sum(age >= 18 for age in ages)

        return updates

    @staticmethod
    def _parse_user_date(
        day: str,
        month: str,
        year: str,
    ) -> date:
        """Parse a user date and use the current year when omitted."""

        parsed_year = int(year) if year else date.today().year
        month_value = month[:3].title()
        parsed = datetime.strptime(
            f"{day} {month_value} {parsed_year}",
            "%d %b %Y",
        ).date()

        if not year and parsed < date.today():
            parsed = parsed.replace(year=parsed.year + 1)

        return parsed

    @staticmethod
    def next_question(draft: TripDraft) -> str:
        """Return the next question for the first missing required field."""

        questions = {
            "destination": "Where would you like to travel?",
            "check_in_date": "What is your check-in date?",
            "check_out_date": "What is your check-out date?",
            "budget": "What budget should I plan within, and which currency?",
            "travelers": (
                "How many people will travel? Reply with a number, "
                "for example: '3 travelers'."
            ),
            "adults": (
                "How many of those travelers are adults? Reply with "
                "a number, for example: '2 adults'."
            ),
        }

        missing = draft.missing_required_fields()
        if missing:
            return questions[missing[0]]

        return (
            "I have all the required details. Please review the trip "
            "summary and confirm before I continue."
        )

    @staticmethod
    def _build_prompt(
        draft: TripDraft,
        user_message: str,
    ) -> str:
        current = draft.model_dump(mode="json")

        return f"""
Current trip draft:
{json.dumps(current, indent=2)}

User message:
{user_message}

Extract only information explicitly provided or clearly implied by the
user. Do not invent values. Return JSON in this exact shape:
{{
  "updates": {{
    "destination": "",
    "check_in_date": "YYYY-MM-DD",
    "check_out_date": "YYYY-MM-DD",
    "budget": null,
    "currency": "USD",
    "travelers": null,
    "adults": null,
    "interests": [],
    "dietary_restrictions": [],
    "accessibility_needs": [],
    "transport_preferences": [],
    "accommodation_preferences": [],
    "notes": ""
  }},
  "reply": "A short helpful response or the next question"
}}

Rules:
- Preserve any previously collected information.
- Dates must use YYYY-MM-DD.
- Budget must be numeric.
- Support any destination worldwide.
- Do not book or confirm hotels, activities, restaurants, transport, or payments.
- Return JSON only.
"""
