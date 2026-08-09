"""Conversational intake service for the Ask Anita assistant."""

import json
import logging
import re
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

            updated_draft = draft.merge(updates)
            reply = extraction.reply.strip()

            if updated_draft.is_complete:
                if not reply:
                    reply = self.next_question(updated_draft)
            else:
                next_question = self.next_question(updated_draft)
                if reply:
                    reply = f"{reply}\n\n{next_question}"
                else:
                    reply = next_question

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
    def next_question(draft: TripDraft) -> str:
        """Return the next question for the first missing required field."""

        questions = {
            "destination": "Where would you like to travel?",
            "check_in_date": "What is your check-in date?",
            "check_out_date": "What is your check-out date?",
            "budget": "What budget should I plan within, and which currency?",
            "travelers": "How many travelers will be going?",
            "adults": "How many of the travelers are adults?",
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
