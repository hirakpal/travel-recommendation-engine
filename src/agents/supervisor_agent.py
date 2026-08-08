"""
Supervisor agent for intent routing and conversation management.

Routes user requests to appropriate specialist agents.
Manages conversation context and multi-turn interactions.
"""

import json
from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

from src.core.llm_client import LLMClient
from src.core.intent_parser import Intent, IntentType

class ConversationRole(str, Enum):
    """Roles in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ConversationMessage(BaseModel):
    """Single message in conversation."""
    role: ConversationRole
    content: str
    timestamp: datetime
    intent: Optional[IntentType] = None
    entities: Optional[dict] = None

class TripContext(BaseModel):
    """Context for current trip planning."""
    destination: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    budget: Optional[float] = None
    interests: List[str] = []
    dietary_restrictions: List[str] = []
    party_size: int = 1
    status: str = "planning"  # planning, booked, completed

class ConversationContext(BaseModel):
    """Conversation state and context."""
    session_id: str
    user_id: Optional[str] = None
    created_at: datetime
    messages: List[ConversationMessage] = []
    trip: TripContext = TripContext()
    last_intent: Optional[IntentType] = None
    agents_used: List[str] = []
    
    def add_message(
        self,
        role: ConversationRole,
        content: str,
        intent: Optional[IntentType] = None,
        entities: Optional[dict] = None
    ):
        """Add message to conversation."""
        msg = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            intent=intent,
            entities=entities
        )
        self.messages.append(msg)

class SupervisorAgent:
    """
    Supervisor agent for multi-agent orchestration.
    
    Responsibilities:
    - Parse user intent
    - Route to appropriate agent
    - Maintain conversation context
    - Handle multi-turn interactions
    - Escalate to human when needed
    """
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.conversations = {}  # session_id -> ConversationContext
    
    async def process_input(
        self,
        session_id: str,
        user_input: str,
        user_id: Optional[str] = None
    ) -> tuple[str, Optional[str], ConversationContext]:
        """
        Process user input and route to appropriate agent.
        
        Args:
            session_id: Unique conversation ID
            user_input: Natural language input from user
            user_id: Optional user identifier
        
        Returns:
            (response, agent_used, updated_context)
        """
        
        # Get or create conversation context
        context = self._get_or_create_context(session_id, user_id)
        
        # Add user message
        context.add_message(ConversationRole.USER, user_input)
        
        # Parse intent
        intent_result = await self._parse_intent(user_input, context)
        
        # Route to appropriate handler
        if intent_result.type == IntentType.HOTEL_SEARCH:
            response, agent = await self._handle_hotel_search(user_input, intent_result, context)
        
        elif intent_result.type == IntentType.ACTIVITY_SEARCH:
            response, agent = await self._handle_activity_search(user_input, intent_result, context)
        
        elif intent_result.type == IntentType.RESTAURANT_SEARCH:
            response, agent = await self._handle_restaurant_search(user_input, intent_result, context)
        
        elif intent_result.type == IntentType.TRIP_PLANNING:
            response, agent = await self._handle_trip_planning(user_input, intent_result, context)
        
        elif intent_result.type == IntentType.UNKNOWN:
            response, agent = await self._handle_clarification(user_input, context)
        
        else:
            response, agent = await self._handle_out_of_domain(user_input, context)
        
        # Update context
        context.add_message(
            ConversationRole.ASSISTANT,
            response,
            intent=intent_result.type,
            entities=intent_result.entities
        )
        context.last_intent = intent_result.type
        if agent:
            context.agents_used.append(agent)
        
        # Save conversation
        self.conversations[session_id] = context
        
        return response, agent, context
    
    async def _parse_intent(
        self,
        user_input: str,
        context: ConversationContext
    ) -> Intent:
        """Parse user intent from input."""
        
        prompt = f"""
        Analyze this user input and extract intent.
        
        Previous intents: {[str(m.intent) for m in context.messages[-5:] if m.role == ConversationRole.USER]}
        Current destination: {context.trip.destination}
        Current budget: {context.trip.budget}
        
        User input: "{user_input}"
        
        Classify as one of:
        - hotel_search: Looking for hotels
        - activity_search: Looking for activities/tours
        - restaurant_search: Looking for dining
        - trip_planning: Planning entire trip
        - modification: Changing existing booking
        - inquiry: General question
        - unknown: Unclear intent
        
        Extract entities:
        - city/destination
        - dates (check-in, check-out)
        - budget
        - interests
        - dietary restrictions
        
        Return JSON:
        {{
            "intent": "intent_type",
            "confidence": 0.0-1.0,
            "entities": {{"key": "value"}},
            "reasoning": "brief explanation"
        }}
        """
        
        response = await self.llm.call(
            system_prompt="You are an intent classifier for travel planning.",
            user_message=prompt,
            response_format="json"
        )
        
        try:
            data = json.loads(response)
            
            # Update context with extracted entities
            entities = data.get("entities", {})
            if "city" in entities:
                context.trip.destination = entities["city"]
            if "budget" in entities:
                try:
                    context.trip.budget = float(entities["budget"])
                except:
                    pass
            if "check_in" in entities:
                context.trip.check_in = entities["check_in"]
            if "check_out" in entities:
                context.trip.check_out = entities["check_out"]
            if "interests" in entities:
                context.trip.interests = entities.get("interests", [])
            if "dietary" in entities:
                context.trip.dietary_restrictions = entities.get("dietary", [])
            
            # Map to IntentType
            intent_str = data.get("intent", "unknown").upper()
            intent_type = IntentType(intent_str.lower()) if intent_str.lower() in [i.value for i in IntentType] else IntentType.UNKNOWN
            
            return Intent(
                type=intent_type,
                confidence=data.get("confidence", 0),
                entities=entities,
                requires_clarification=data.get("confidence", 1) < 0.6
            )
        
        except Exception as e:
            print(f"Intent parsing error: {e}")
            return Intent(
                type=IntentType.UNKNOWN,
                confidence=0,
                entities={},
                requires_clarification=True
            )
    
    async def _handle_hotel_search(
        self,
        user_input: str,
        intent: Intent,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle hotel search request."""
        
        if not context.trip.destination:
            return "I'd like to help you find a hotel. Which city are you visiting?", None
        
        if not context.trip.check_in:
            return "What are your check-in and check-out dates?", None
        
        # Would call HotelAgent here
        response = f"""
        I'll search for hotels in {context.trip.destination}.
        
        Search criteria:
        - Check-in: {context.trip.check_in}
        - Check-out: {context.trip.check_out}
        - Budget: ${context.trip.budget if context.trip.budget else 'flexible'}
        
        (Hotel Agent would process this search)
        """
        
        return response, "HotelAgent"
    
    async def _handle_activity_search(
        self,
        user_input: str,
        intent: Intent,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle activity search request."""
        
        if not context.trip.destination:
            return "Which city would you like to explore?", None
        
        if not context.trip.interests:
            return "What interests you? (e.g., history, culture, food, nature, adventure)", None
        
        response = f"""
        I'll find activities in {context.trip.destination} matching your interests: {', '.join(context.trip.interests)}.
        
        (Activities Agent would process this search)
        """
        
        return response, "ActivitiesAgent"
    
    async def _handle_restaurant_search(
        self,
        user_input: str,
        intent: Intent,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle restaurant search request."""
        
        if not context.trip.destination:
            return "Which city are you dining in?", None
        
        # Extract meal type from input
        meal_type = "dinner"
        if "breakfast" in user_input.lower():
            meal_type = "breakfast"
        elif "lunch" in user_input.lower():
            meal_type = "lunch"
        
        response = f"""
        I'll find restaurants in {context.trip.destination} for {meal_type}.
        
        Dietary restrictions: {', '.join(context.trip.dietary_restrictions) if context.trip.dietary_restrictions else 'None'}
        
        (Restaurant Agent would process this search)
        """
        
        return response, "RestaurantAgent"
    
    async def _handle_trip_planning(
        self,
        user_input: str,
        intent: Intent,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle complete trip planning."""
        
        # Gather required information
        missing = []
        if not context.trip.destination:
            missing.append("destination")
        if not context.trip.check_in:
            missing.append("check-in date")
        if not context.trip.check_out:
            missing.append("check-out date")
        if not context.trip.interests:
            missing.append("interests")
        
        if missing:
            return f"To plan your trip, I need: {', '.join(missing)}", None
        
        response = f"""
        Great! I'll plan your {context.trip.destination} trip:
        
        Trip Details:
        - Destination: {context.trip.destination}
        - Duration: {context.trip.check_in} to {context.trip.check_out}
        - Interests: {', '.join(context.trip.interests)}
        - Budget: ${context.trip.budget if context.trip.budget else 'flexible'}
        - Party size: {context.trip.party_size}
        
        I'll coordinate hotels, activities, and restaurants for you.
        (Orchestrator would run all agents)
        """
        
        return response, "Orchestrator"
    
    async def _handle_clarification(
        self,
        user_input: str,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle unclear input."""
        
        prompt = f"""
        The user input is unclear. Ask for clarification.
        
        Recent conversation:
        {self._format_conversation(context.messages[-5:])}
        
        User input: "{user_input}"
        
        Ask a clarifying question to understand what they want.
        """
        
        response = await self.llm.call(
            system_prompt="You help clarify travel planning requests.",
            user_message=prompt,
            response_format="text"
        )
        
        return response, None
    
    async def _handle_out_of_domain(
        self,
        user_input: str,
        context: ConversationContext
    ) -> tuple[str, str]:
        """Handle out-of-domain requests."""
        
        return """
        I'm specialized in travel planning - helping you find hotels, activities, and restaurants.
        
        How can I help with your travel plans?
        """, None
    
    def _get_or_create_context(
        self,
        session_id: str,
        user_id: Optional[str] = None
    ) -> ConversationContext:
        """Get existing context or create new."""
        
        if session_id not in self.conversations:
            self.conversations[session_id] = ConversationContext(
                session_id=session_id,
                user_id=user_id,
                created_at=datetime.now()
            )
        
        return self.conversations[session_id]
    
    def _format_conversation(self, messages: List[ConversationMessage]) -> str:
        """Format conversation history."""
        
        result = []
        for msg in messages:
            role = msg.role.value.upper()
            result.append(f"{role}: {msg.content[:100]}")
        
        return "\n".join(result)
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation context."""
        return self.conversations.get(session_id)
    
    def clear_context(self, session_id: str):
        """Clear conversation context."""
        if session_id in self.conversations:
            del self.conversations[session_id]
