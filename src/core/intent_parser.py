"""
Parse user intent from natural language.
"""

import json
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


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
    """Parse natural-language travel requests using OpenAI."""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def parse(self, user_input: str) -> Intent:
        prompt = f"""
Parse this travel request into structured JSON.

User request:
"{user_input}"

Return exactly this structure:
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
- Use ISO dates: YYYY-MM-DD.
- Return budget as a number.
- Return interests and dietary as arrays.
- Use an empty string when a value is unavailable.
"""

        response = await self.llm.call(
            system_prompt="You are a travel intent parser. Return valid JSON only.",
            user_message=prompt,
            response_format="json",
        )

        if isinstance(response, str):
            data = json.loads(response)
        else:
            data = response

        intent_value = data.get("intent", "unknown")

        try:
            intent_type = IntentType(intent_value)
        except ValueError:
            intent_type = IntentType.UNKNOWN

        return Intent(
            type=intent_type,
            confidence=float(data.get("confidence", 0.0)),
            entities=data.get("entities", {}),
            requires_clarification=bool(
                data.get("requires_clarification", False)
            ),
        )
