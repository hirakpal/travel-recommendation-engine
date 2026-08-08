"""
Parse travel requests into structured intent.
"""

import json
import logging
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    HOTEL_SEARCH = "hotel_search"
    ACTIVITY_SEARCH = "activity_search"
    RESTAURANT_SEARCH = "restaurant_search"
    TRIP_PLANNING = "trip_planning"
    UNKNOWN = "unknown"


class Entity(BaseModel):
    type: str
    value: str
    confidence: float = 1.0


class Intent(BaseModel):
    type: IntentType
    confidence: float = 0.0
    entities: Dict[str, Any] = Field(default_factory=dict)
    requires_clarification: bool = False


class IntentParser:
    """Parse travel requests using the configured LLM client."""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def parse(self, user_input: str) -> Intent:
        logger.info("INTENT_PARSE_START")
        logger.info("User input: %s", user_input)

        prompt = f"""
Parse this travel request into JSON.

User request:
{user_input}

Return exactly:
{{
  "intent": "trip_planning",
  "confidence": 0.95,
  "entities": {{
    "destination": "Vietnam",
    "check_in_date": "2026-08-08",
    "check_out_date": "2026-08-16",
    "budget": 2000,
    "interests": ["Culture", "Food", "Nature"],
    "dietary": []
  }},
  "requires_clarification": false
}}

Rules:
- Dates must use YYYY-MM-DD format.
- Budget must be a number.
- interests and dietary must be arrays.
- Return valid JSON only.
"""

        try:
            response = await self.llm.call(
                system_prompt=(
                    "You are a travel intent parser. "
                    "Return valid JSON only."
                ),
                user_message=prompt,
                response_format="json",
            )

            logger.info(
                "LLM_RESPONSE_TYPE=%s",
                type(response).__name__,
            )

            data = (
                json.loads(response)
                if isinstance(response, str)
                else response
            )

            logger.info("LLM_PARSED_DATA=%s", data)

            intent_value = data.get("intent", "unknown")

            try:
                intent_type = IntentType(intent_value)
            except ValueError:
                intent_type = IntentType.UNKNOWN

            parsed_intent = Intent(
                type=intent_type,
                confidence=float(data.get("confidence", 0)),
                entities=data.get("entities", {}),
                requires_clarification=bool(
                    data.get("requires_clarification", False)
                ),
            )

            logger.info(
                "INTENT_PARSE_SUCCESS type=%s entities=%s",
                type(parsed_intent).__name__,
                parsed_intent.entities,
            )

            return parsed_intent

        except Exception:
            logger.exception("INTENT_PARSE_FAILED")
            raise
