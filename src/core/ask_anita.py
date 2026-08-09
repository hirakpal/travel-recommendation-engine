"""Conversational intake service for the Ask Anita assistant."""

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Tuple

from pydantic import BaseModel, Field, ValidationError

from src.core.trip_draft import TripDraft
from src.core.runtime_diagnostics import record_event
from src.core.preference_taxonomy import normalize_preference_values

logger = logging.getLogger(__name__)
logger.info("ANITA_SOURCE_VERSION=DATE_CONFIRMATION_V5")


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
        "pending_date_range_start_day",
        "pending_date_range_start_month",
        "pending_date_range_end_day",
        "pending_date_range_end_month",
        "date_confirmation_required",
        "pending_preference_field",
        "preferences_collected",
    }

    def __init__(self, llm_client):
        self.llm = llm_client

    async def _extract_with_repair(
        self,
        prompt: str,
    ) -> AnitaExtraction:
        """Parse LLM output and request one schema repair when necessary."""

        system_prompt = (
            "You are Anita, a friendly travel-planning intake assistant. "
            "Extract trip details only. Never book, purchase, or claim "
            "that anything is confirmed. Return valid JSON only."
        )
        response = await self.llm.call(
            system_prompt=system_prompt,
            user_message=prompt,
            response_format="json",
        )

        for attempt in range(2):
            try:
                data = (
                    json.loads(response)
                    if isinstance(response, str)
                    else response
                )
                extraction = AnitaExtraction.model_validate(data)
                record_event(
                    "Intent Parser",
                    "extraction_validated",
                    mode="llm",
                    status="success",
                    output_data=extraction,
                    details={"attempt": attempt + 1},
                )
                return extraction
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                if attempt == 1:
                    record_event(
                        "Intent Parser",
                        "extraction_validation_failed",
                        mode="llm",
                        status="error",
                        output_data=str(exc),
                        details={"attempts": 2},
                    )
                    raise ValueError(
                        "The intent parser returned invalid structured data."
                    ) from exc

                record_event(
                    "Intent Parser",
                    "extraction_repair_requested",
                    mode="llm",
                    status="retry",
                    output_data=str(exc),
                    details={"attempt": attempt + 1},
                )
                response = await self.llm.call(
                    system_prompt=system_prompt,
                    user_message=(
                        "Repair your previous response. Return JSON matching "
                        "this exact shape: {\"updates\": {}, \"reply\": "
                        "\"\"}. Do not add unknown top-level fields. "
                        f"Validation error: {exc}\nPrevious response: "
                        f"{str(response)[:3000]}"
                    ),
                    response_format="json",
                )

    async def chat(
        self,
        draft: TripDraft,
        user_message: str,
    ) -> Tuple[TripDraft, str]:
        """Apply one user message and return the updated draft and reply."""

        logger.info("ANITA_MESSAGE_START")
        logger.info("ANITA_SOURCE_VERSION=DATE_CONFIRMATION_V5")
        logger.info("User message: %s", user_message)
        record_event(
            "Ask Anita",
            "user_message_received",
            mode="conversation",
            input_data=user_message,
            output_data=draft,
            details={"missing_before": draft.missing_required_fields()},
        )

        normalized_message = user_message.strip().lower()

        # Once mandatory fields are complete, the next user message belongs
        # to the first optional agent-input question unless one is already
        # pending.
        if (
            not draft.missing_required_fields()
            and not draft.preferences_collected
            and draft.pending_preference_field is None
        ):
            draft = self._prepare_preference_state(draft)

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

        # A partial date is deliberately held until the user supplies a
        # year. Validate that year before extraction so an old year cannot
        # fall through to the LLM and overwrite the pending date state.
        if draft.pending_date_field:
            year_match = re.fullmatch(
                r"(?:year\s*)?(\d{4})",
                normalized_message,
            )
            if year_match and int(year_match.group(1)) < date.today().year:
                return draft, (
                    f"That year is in the past. Please provide "
                    f"{date.today().year} or a future year for the "
                    f"{draft.pending_date_field.replace('_', ' ')}."
                )

        if draft.pending_preference_field:
            updated_draft = self._apply_preference_answer(
                draft,
                user_message,
            )
            if updated_draft is not None:
                logger.info(
                    "ANITA_PREFERENCE_CAPTURED field=%s values=%s",
                    draft.pending_preference_field,
                    getattr(updated_draft, draft.pending_preference_field),
                )
                record_event(
                    "Ask Anita",
                    "preference_captured",
                    mode="deterministic",
                    input_data=user_message,
                    output_data=updated_draft,
                    details={
                        "field": draft.pending_preference_field,
                        "missing_after": updated_draft.missing_required_fields(),
                    },
                )
                return updated_draft, self.next_question(updated_draft)

        # A duration does not identify calendar dates. Never let the LLM
        # invent an arrival year or return date from "5 nights".
        if self._contains_duration_without_dates(user_message):
            if draft.check_in_date is None:
                return draft, (
                    "I can plan that duration, but I still need the "
                    "arrival/check-in date and return/check-out date. "
                    "Please provide both dates, including month and year."
                )
            if draft.check_out_date is None:
                return draft, (
                    "I noted the duration, but I still need your "
                    "return/check-out date. Please provide the calendar "
                    "date, including month and year."
                )

        # Dates have priority over counts. In particular, when Anita asks
        # for the missing year, "2026" must complete the pending date and
        # must never become a traveler count.
        try:
            date_updates = self._extract_deterministic_fields(
                draft,
                user_message,
            )
        except ValueError:
            return draft, (
                "That is not a valid calendar date. Please provide a "
                "real day and month, for example: 20 August 2026."
            )

        date_keys = {
            "check_in_date",
            "check_out_date",
            "pending_date_field",
            "pending_date_day",
            "pending_date_month",
        }
        if date_updates and date_keys.intersection(date_updates):
            logger.info("ANITA_DATE_DETERMINISTIC_PATH")
            updated_draft, reply = self._apply_local_updates(
                draft, date_updates
            )
            record_event(
                "Ask Anita",
                "date_fields_updated",
                mode="deterministic",
                input_data=user_message,
                output_data=updated_draft,
                details={"updates": date_updates, "reply": reply},
            )
            return updated_draft, reply

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
            record_event(
                "Ask Anita",
                "traveler_counts_updated",
                mode="deterministic",
                input_data=user_message,
                output_data=updated_draft,
                details={"updates": count_updates, "reply": reply},
            )
            logger.info("ANITA_COUNT_FIX_VERSION=2")
            logger.info(
                "ANITA_MESSAGE_SUCCESS complete=%s missing=%s",
                updated_draft.is_complete,
                updated_draft.missing_required_fields(),
            )
            return updated_draft, reply

        try:
            deterministic_updates = self._extract_deterministic_fields(
                draft,
                user_message,
            )
        except ValueError:
            return draft, (
                "That is not a valid calendar date. Please provide a "
                "real day and month, for example: 23 August."
            )

        if (
            deterministic_updates
            and self._is_deterministic_only(user_message)
        ):
            logger.info("ANITA_DETERMINISTIC_PATH")
            updated_draft, reply = self._apply_local_updates(
                draft,
                deterministic_updates,
            )
            record_event(
                "Ask Anita",
                "fields_updated",
                mode="deterministic",
                input_data=user_message,
                output_data=updated_draft,
                details={"updates": deterministic_updates, "reply": reply},
            )
            return updated_draft, reply

        prompt = self._build_prompt(draft, user_message)

        try:
            record_event(
                "Ask Anita",
                "llm_extraction_start",
                mode="llm",
                input_data=user_message,
                details={"missing_before": draft.missing_required_fields()},
            )
            extraction = await self._extract_with_repair(prompt)
            updates = {
                key: value
                for key, value in extraction.updates.items()
                if key in self.ALLOWED_FIELDS
            }
            for field_name in (
                "dietary_restrictions",
                "accessibility_needs",
                "transport_preferences",
                "accommodation_preferences",
            ):
                if field_name in updates:
                    updates[field_name] = normalize_preference_values(
                        field_name,
                        updates[field_name],
                    )

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
            record_event(
                "Ask Anita",
                "llm_extraction_complete",
                mode="llm",
                status="success",
                input_data=user_message,
                output_data=updated_draft,
                details={
                    "llm_updates": extraction.updates,
                    "reply": reply,
                    "missing_after": updated_draft.missing_required_fields(),
                },
            )

            return updated_draft, reply

        except Exception:
            logger.exception("ANITA_MESSAGE_FAILED")
            record_event(
                "Ask Anita",
                "message_failed",
                mode="conversation",
                status="error",
                input_data=user_message,
            )
            raise

    @staticmethod
    def _build_state_reply(
        draft: TripDraft,
        updates: Dict[str, Any],
    ) -> str:
        """Build a truthful response from validated draft state."""

        acknowledgements = []

        if draft.pending_date_field == "date_range":
            return (
                "I understood the date range from "
                f"{draft.pending_date_range_start_day}/"
                f"{draft.pending_date_range_start_month} to "
                f"{draft.pending_date_range_end_day}/"
                f"{draft.pending_date_range_end_month}. Which year should "
                "I use for both dates? Please reply with a four-digit year, "
                "for example: 2026."
            )

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

            # A four-digit value in the year range is a date year, not a
            # traveler count. If no date is pending, let the LLM ask for
            # clarification rather than corrupting the draft.
            if 1900 <= number <= 2100:
                return result

            if draft.travelers is None:
                result["travelers"] = number
                result.pop("adults", None)
            elif draft.adults is None:
                result["adults"] = number

        return result

    def _apply_local_updates(
        self,
        draft: TripDraft,
        updates: Dict[str, Any],
    ) -> Tuple[TripDraft, str]:
        """Validate deterministic updates without an LLM call."""

        try:
            candidate = draft.merge(updates)
        except ValueError:
            return draft, (
                "That is not a valid value. Please provide a corrected "
                "date, budget, or traveler count."
            )

        current_year = date.today().year
        for field_name in ("check_in_date", "check_out_date"):
            value = getattr(candidate, field_name)
            if value and value.year < current_year:
                return draft, (
                    f"The year must be {current_year} or later. "
                    "Please provide the date again."
                )

        duration = candidate.duration_days
        date_changed = bool(
            {"check_in_date", "check_out_date"}.intersection(updates)
        )

        if date_changed and duration is not None and duration > 20:
            return draft, (
                "We do not support trips longer than 20 days. "
                "Please adjust the dates or reply 'exit' to stop."
            )

        if date_changed and duration is not None and duration > 10:
            updates = dict(updates)
            updates["date_confirmation_required"] = True
            candidate = draft.merge(updates)

        return candidate, self._build_state_reply(candidate, updates)

    @staticmethod
    def _is_deterministic_only(user_message: str) -> bool:
        """Identify messages that do not require an LLM."""

        text = user_message.strip().lower()
        patterns = [
            r"\d+",
            r"\d+\s*(?:adults?|travellers?|travelers?|people)",
            r"\d{1,3}\s*[,/]\s*\d{1,3}(?:\s*[,/]\s*\d{1,3})?",
            r"\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+(?:\s+\d{4})?",
            r"(?:\d[\d,]*(?:\.\d+)?)\s*"
            r"(?:inr|usd|eur|gbp|aud|cad|sgd|jpy|\$|€|£)",
            r"(?:year\s*)?\d{4}",
            r"(?:trip|travel|visit|go)\s+to\s+[a-z][a-z .'-]+",
        ]
        return any(re.fullmatch(pattern, text) for pattern in patterns)

    @staticmethod
    def _contains_duration_without_dates(user_message: str) -> bool:
        """Detect duration-only messages such as '5 nights'."""

        text = user_message.strip().lower()
        has_duration = bool(
            re.search(r"\b\d+\s*(?:night|nights|day|days)\b", text)
        )
        has_calendar_date = bool(
            re.search(
                r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
                r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
                r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
                r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
                r"dec(?:ember)?)\b",
                text,
            )
        )
        return has_duration and not has_calendar_date

    @staticmethod
    def _preference_questions() -> Dict[str, str]:
        return {
            "interests": (
                "What are your interests for this trip? For example: "
                "culture, food, history, nature, shopping, or adventure. "
                "Reply 'none' if you have no preference."
            ),
            "dietary_restrictions": (
                "Do you have any dietary restrictions? For example: "
                "vegetarian, vegan, halal, kosher, or gluten-free. "
                "Reply 'none' if not applicable."
            ),
            "accessibility_needs": (
                "Do you have any accessibility needs I should consider, "
                "such as wheelchair access or limited walking? Reply "
                "'none' if not applicable."
            ),
            "transport_preferences": (
                "How would you prefer to get around? For example: walking, "
                "public transport, taxi, rental car, or private transfer. "
                "Reply 'none' if you have no preference."
            ),
            "accommodation_preferences": (
                "Which hotel tier do you prefer: Budget / Backpacker, "
                "Mid-Range, or Luxury / 5-Star? You may select one or more. "
                "Reply 'none' if you have no preference."
            ),
        }

    @classmethod
    def _next_preference_field(
        cls,
        draft: TripDraft,
    ) -> str | None:
        if draft.missing_required_fields():
            return None

        fields = tuple(cls._preference_questions())
        if draft.pending_preference_field in fields:
            return draft.pending_preference_field

        for field_name in fields:
            value = getattr(draft, field_name)
            if not value:
                return field_name

        return None

    @classmethod
    def _prepare_preference_state(cls, draft: TripDraft) -> TripDraft:
        """Set the next optional question after mandatory data is complete."""

        if draft.missing_required_fields():
            return draft

        next_field = cls._next_preference_field(draft)
        if next_field is None:
            return draft.merge(
                {
                    "pending_preference_field": None,
                    "preferences_collected": True,
                }
            )

        if draft.pending_preference_field == next_field:
            return draft

        return draft.merge({"pending_preference_field": next_field})

    @classmethod
    def _apply_preference_answer(
        cls,
        draft: TripDraft,
        user_message: str,
    ) -> TripDraft | None:
        field_name = draft.pending_preference_field
        if field_name not in cls._preference_questions():
            return None

        text = user_message.strip()
        if text.lower() in {"no", "none", "n/a", "na", "skip", "not applicable"}:
            values = []
        else:
            values = normalize_preference_values(field_name, text)

        current = draft.merge({field_name: values})
        fields = tuple(cls._preference_questions())
        index = fields.index(field_name)
        if index == len(fields) - 1:
            return current.merge(
                {
                    "pending_preference_field": None,
                    "preferences_collected": True,
                }
            )

        return current.merge(
            {"pending_preference_field": fields[index + 1]}
        )

    @staticmethod
    def _extract_deterministic_fields(
        draft: TripDraft,
        user_message: str,
    ) -> Dict[str, Any]:
        """Extract fields where guessing would be unsafe."""

        text = user_message.strip()
        lower_text = text.lower()
        updates: Dict[str, Any] = {}

        destination_match = re.fullmatch(
            r"(?:trip|travel|visit|go)\s+to\s+(.+)",
            text,
            flags=re.IGNORECASE,
        )
        if destination_match:
            updates["destination"] = destination_match.group(1).strip()

        if draft.pending_date_field == "date_range":
            year_match = re.fullmatch(
                r"(?:year\s*)?(\d{4})",
                lower_text,
            )
            if year_match:
                year = int(year_match.group(1))
                if year < date.today().year:
                    return {
                        "pending_date_field": "date_range",
                        "pending_date_range_start_day": draft.pending_date_range_start_day,
                        "pending_date_range_start_month": draft.pending_date_range_start_month,
                        "pending_date_range_end_day": draft.pending_date_range_end_day,
                        "pending_date_range_end_month": draft.pending_date_range_end_month,
                    }
                try:
                    start = date(
                        year,
                        draft.pending_date_range_start_month,
                        draft.pending_date_range_start_day,
                    )
                    end = date(
                        year,
                        draft.pending_date_range_end_month,
                        draft.pending_date_range_end_day,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "That is not a valid date range."
                    ) from exc
                return {
                    "check_in_date": start,
                    "check_out_date": end,
                    "pending_date_field": None,
                    "pending_date_range_start_day": None,
                    "pending_date_range_start_month": None,
                    "pending_date_range_end_day": None,
                    "pending_date_range_end_month": None,
                }

        if draft.pending_date_field:
            year_match = re.fullmatch(
                r"(?:year\s*)?(\d{4})",
                lower_text,
            )
            if year_match:
                year = int(year_match.group(1))
                if year < date.today().year:
                    return {
                        "pending_date_field": draft.pending_date_field,
                        "pending_date_day": draft.pending_date_day,
                        "pending_date_month": draft.pending_date_month,
                    }
                try:
                    parsed = date(
                        year,
                        draft.pending_date_month,
                        draft.pending_date_day,
                    )
                except ValueError:
                    raise ValueError(
                        "That is not a valid calendar date. "
                        "Please provide a valid year."
                    )
                updates[draft.pending_date_field] = parsed
                updates["pending_date_field"] = None
                updates["pending_date_day"] = None
                updates["pending_date_month"] = None
                logger.info(
                    "ANITA_DATE_YEAR_ACCEPTED field=%s date=%s",
                    draft.pending_date_field,
                    parsed.isoformat(),
                )
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

        # Normalize common human date formats before matching. This handles
        # ordinal suffixes and non-standard whitespace consistently.
        date_text = re.sub(r"\s+", " ", lower_text).strip()
        date_text = re.sub(
            r"\b(\d{1,2})(?:st|nd|rd|th)\b",
            r"\1",
            date_text,
        )

        range_match = re.fullmatch(
            r"(?:(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
            r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})"
            r"(?:\s+(\d{4}))?\s*(?:-|–|to)\s*"
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
            r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})"
            r"(?:\s+(\d{4}))?",
            date_text,
            flags=re.IGNORECASE,
        )
        if not range_match:
            range_match = re.fullmatch(
                r"(\d{1,2})\s+(jan(?:uary)?|feb(?:ruary)?|"
                r"mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
                r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
                r"nov(?:ember)?|dec(?:ember)?)\s+(\d{4})?\s*"
                r"(?:-|–|to)\s*(\d{1,2})\s+"
                r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
                r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
                r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
                r"dec(?:ember)?)\s+(\d{4})?",
                date_text,
                flags=re.IGNORECASE,
            )

        if range_match:
            values = range_match.groups()
            if values[0].isdigit():
                start_day, start_month, start_year = values[0], values[1], values[2]
                end_day, end_month, end_year = values[3], values[4], values[5]
            else:
                start_month, start_day, start_year = values[0], values[1], values[2]
                end_month, end_day, end_year = values[3], values[4], values[5]

            start_month_number = datetime.strptime(
                start_month[:3].title(), "%b"
            ).month
            end_month_number = datetime.strptime(
                end_month[:3].title(), "%b"
            ).month

            if start_year and end_year:
                updates["check_in_date"] = AskAnita._parse_user_date(
                    start_day, start_month, start_year
                )
                updates["check_out_date"] = AskAnita._parse_user_date(
                    end_day, end_month, end_year
                )
                return updates

            updates.update(
                {
                    "pending_date_field": "date_range",
                    "pending_date_range_start_day": int(start_day),
                    "pending_date_range_start_month": start_month_number,
                    "pending_date_range_end_day": int(end_day),
                    "pending_date_range_end_month": end_month_number,
                    "pending_date_day": None,
                    "pending_date_month": None,
                }
            )
            return updates

        date_matches = re.findall(
            r"\b(\d{1,2})\s+"
            r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
            r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
            r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"(?:\s+(\d{4}))?\b",
            date_text,
            flags=re.IGNORECASE,
        )
        logger.info(
            "ANITA_DATE_SCAN input=%r normalized=%r matches=%s",
            lower_text,
            date_text,
            date_matches,
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

        # A complete date supplied while Anita is waiting for a missing year
        # supersedes the partial-date state. Without clearing these fields,
        # the next unrelated message (for example, the budget) can trigger
        # the old "which year?" question again.
        if parsed_dates and draft.pending_date_field:
            updates["pending_date_field"] = None
            updates["pending_date_day"] = None
            updates["pending_date_month"] = None

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

        preference_field = draft.pending_preference_field
        if preference_field is None and not draft.preferences_collected:
            preference_field = AskAnita._next_preference_field(draft)
        if preference_field:
            return AskAnita._preference_questions()[preference_field]

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
- Map arrival/check-in to check_in_date and return/departure to
  check_out_date.
- If either calendar date is missing, ask for it, including month and year.
- If the user provides only a duration such as "5 nights", do not invent
  dates; ask for the arrival and return calendar dates.
- Dates must use YYYY-MM-DD.
- Budget must be numeric.
- Support any destination worldwide.
- Do not book or confirm hotels, activities, restaurants, transport, or payments.
- Return JSON only.
"""
