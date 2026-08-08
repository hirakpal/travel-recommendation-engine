"""
Parse user intent from natural language.

Extracts:
- Intent type (hotel_search, activity_search, etc.)
- Entities (city, dates, budget)
- Confidence score
"""

from typing import Optional
from pydantic import BaseModel
from enum import Enum

class IntentType(str, Enum):
    """Types of user intents."""
    HOTEL_SEARCH = "hotel_search"
    ACTIVITY_SEARCH = "activity_search"
    RESTAURANT_SEARCH = "restaurant_search"
    TRIP_PLANNING = "trip_planning"
    UNKNOWN = "unknown"

class Entity(BaseModel):
    """Extracted entity."""
    type: str  # city, date, budget, etc.
    value: str
    confidence: float

class Intent(BaseModel):
    """Parsed user intent."""
    type: IntentType
    confidence: float  # 0-1
    entities: dict  # {entity_type: value}
    requires_clarification: bool

class IntentParser:
    """Parse natural language to structured intent."""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def parse(self, user_input: str) -> Intent:
        """Parse user input to intent."""
        
        prompt = f"""
        Parse this travel request to structured intent.
        
        User input: "{user_input}"
        
        Extract:
        1. Intent type: hotel_search, activity_search, restaurant_search, trip_planning
        2. City/destination
        3. Dates
        4. Budget
        5. Preferences
        
        Return JSON:
        {{
            "intent": "intent_type",
            "confidence": 0.0-1.0,
            "entities": {{
                "city": "extracted city",
                "dates": "date range",
                "budget": "budget amount",
                "preferences": ["list", "of", "preferences"]
            }},
            "requires_clarification": true/false
        }}
        """
        
        response = await self.llm.call(
            system_prompt="You parse travel requests.",
            user_message=prompt,
            response_format="json"
        )
        
        import json
        data = json.loads(response)
        
        return Intent(
            type=IntentType(data.get("intent", "unknown")),
            confidence=data.get("confidence", 0),
            entities=data.get("entities", {}),
            requires_clarification=data.get("requires_clarification", False)
        )
