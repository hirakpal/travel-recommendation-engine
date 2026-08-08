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
    def __init__(self, llm_client):
        self.llm = llm_client

    async def parse(self, user_input: str) -> Intent:
        logger.info("INTENT_PARSE_START")
        logger.info("User input: %s", user_input)

        prompt = f"""
Parse this travel request into valid JSON.

User request:
{user_input}

Return this structure:
{{
  "intent": "trip_planning",
  "confidence": 0.95,
  "entities": {{
    "destination": "the destination from the request",
    "check_in_date": "YYYY-MM-DD",
    "check_out_date": "YYYY-MM-DD",
    "budget": 0,
    "interests": [],
    "dietary": []
  }},
  "requires_clarification": false
}}

Rules:
- Support any country, city, or destination.
- Preserve the destination from the user request.
- Correct obvious spelling mistakes in destination names.
- Dates must use YYYY-MM-DD.
- Budget must be a number.
- interests and dietary must be arrays.
- Return JSON only.
"""

        try:
            response = await self.llm.call(
                system_prompt=(
                    "You are a global travel intent parser. "
                    "Return valid JSON only."
                ),
                user_message=prompt,
                response_format="json",
            )

            data = (
                json.loads(response)
                if isinstance(response, str)
                else response
            )

            intent_value = data.get("intent", "unknown")

            try:
                intent_type = IntentType(intent_value)
            except ValueError:
                intent_type = IntentType.UNKNOWN

            result = Intent(
                type=intent_type,
                confidence=float(data.get("confidence", 0)),
                entities=data.get("entities", {}),
                requires_clarification=bool(
                    data.get("requires_clarification", False)
                ),
            )

            logger.info("INTENT_PARSE_SUCCESS")
            logger.info("Intent type: %s", type(result).__name__)
            logger.info("Entities: %s", result.entities)

            return result

        except Exception:
            logger.exception("INTENT_PARSE_FAILED")
            raise
