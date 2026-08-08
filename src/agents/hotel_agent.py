"""Hotel recommendation agent with bias mitigation."""

import json
from typing import List, Optional
from datetime import datetime
from src.agents.base_agent import BaseAgent
from src.models.hotel import HotelSearch, HotelRecommendation, Hotel
from src.core.llm_client import LLMClient
from src.validators.hotel_validator import HotelValidator
from src.cache.manager import CacheManager

class HotelAgent(BaseAgent):
    """
    Hotel recommendation agent.
    
    Features:
    - Bias mitigation (recency, loss-in-middle, hallucination)
    - Smart filtering (budget, amenities, availability)
    - Claude-based scoring and ranking
    - Cache integration
    - Real-time streaming
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        validator: HotelValidator,
        cache: Optional[CacheManager] = None,
        hotels_data_path: str = "data/hotels.json"
    ):
        super().__init__("HotelAgent")
        self.llm = llm_client
        self.validator = validator
        self.cache = cache
        self.hotels_db = self._load_database(hotels_data_path)
    
    def _load_database(self, path: str) -> dict:
        """Load hotels database from JSON."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Hotel database not found at {path}")
            return {}
    
    async def process(
        self,
        request: HotelSearch,
        stream: bool = False
    ) -> List[HotelRecommendation]:
        """
        Process hotel search request.
        
        Args:
            request: Hotel search criteria
            stream: If True, stream results as they're generated
        
        Returns:
            List of hotel recommendations sorted by match score
        
        Raises:
            ValueError: If request validation fails
        """
        
        # STEP 1: Validate request (anti-recency)
        if not await self.validate(request):
            raise ValueError(f"Invalid hotel search request: {request}")
        
        # STEP 2: Check cache
        cache_key = self._make_cache_key(request)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                print(f"✓ Cache HIT: {cache_key}")
                return cached
        
        # STEP 3: Filter candidates from database
        candidates = self._filter_hotels(request)
        
        if not candidates:
            print(f"⚠️  No hotels found for {request.city}")
            return []
        
        print(f"📋 Filtered candidates: {len(candidates)} hotels")
        
        # STEP 4: Score using Claude
        recommendations = await self._score_with_claude(request, candidates)
        
        # STEP 5: Cache results
        if self.cache:
            await self.cache.set(cache_key, recommendations, ttl=3600)
        
        return recommendations
    
    async def validate(self, request: HotelSearch) -> bool:
        """Validate hotel search request using validator."""
        return await self.validator.validate(request)
    
    def _make_cache_key(self, request: HotelSearch) -> str:
        """Create cache key from request."""
        return f"hotels:{request.city.lower()}:{request.check_in_date}"
    
    def _filter_hotels(self, request: HotelSearch) -> List[Hotel]:
        """
        Filter hotels by basic criteria.
        
        Filters:
        - City match
        - Budget range
        - Star rating minimum
        - Amenities availability
        - Availability status
        """
        
        results = []
        hotels_in_city = self.hotels_db.get(request.city.lower(), [])
        
        for hotel_data in hotels_in_city:
            try:
                hotel = Hotel(**hotel_data)
            except Exception as e:
                print(f"⚠️  Skipping invalid hotel: {e}")
                continue
            
            # Basic filters
            if not (request.budget_min <= hotel.price_per_night <= request.budget_max):
                continue
            
            if hotel.star_rating < request.star_rating_min:
                continue
            
            if not hotel.is_available:
                continue
            
            # Amenities check
            if request.required_amenities:
                if not all(a in hotel.amenities for a in request.required_amenities):
                    continue
            
            results.append(hotel)
        
        return results
    
    async def _score_with_claude(
        self,
        request: HotelSearch,
        candidates: List[Hotel]
    ) -> List[HotelRecommendation]:
        """
        Score and rank hotels using Claude.
        
        Bias Mitigation Strategy:
        - ANCHOR at START: Reinforce budget constraints
        - VERIFY in MIDDLE: Check all criteria
        - CONFIRM at END: Final verification checklist
        """
        
        system_prompt = """You are a hotel recommendation expert.

TASK: Score these hotels for the user and provide reasoning.

SCORING CRITERIA (0-1):
- Budget alignment: Matches specified price range
- Amenities match: Has required features
- Quality: Star rating reflects expectations
- Availability: Confirmed for dates
- Value: Price-to-quality ratio

ANTI-BIAS CHECKLIST:
✓ START: Verify budget constraints (no overspending)
✓ MIDDLE: Check ALL required amenities present
✓ END: Confirm hotel from provided list (no hallucinations)
✓ NO ANCHORING: Don't favor first hotel
✓ EQUAL CONSIDERATION: Evaluate all fairly

RESPONSE FORMAT (JSON):
[
  {
    "hotel_id": "str",
    "score": float (0-1),
    "reasoning": "str (2-3 sentences)",
    "recommendation": "bool"
  }
]"""
        
        # Format candidates for Claude
        hotels_json = json.dumps(
            [h.dict() for h in candidates],
            indent=2
        )
        
        # Build user message (ANCHOR at START)
        user_message = f"""BUDGET CONSTRAINT (START):
Min: ${request.budget_min}
Max: ${request.budget_max}
Dates: {request.check_in_date} to {request.check_out_date}
Nights: {request.num_nights}
Required amenities: {request.required_amenities or 'None'}

VERIFICATION CHECKLIST (MIDDLE):
☑ All amenities present?
☑ Price within range?
☑ Rating meets minimum {request.star_rating_min}?
☑ Available for dates?

HOTELS TO EVALUATE:
{hotels_json}

Score each hotel and provide match score 0-1.
Confirm all hotels are from the provided list.
Final check: {request.budget_min} <= price <= {request.budget_max}"""
        
        # Call Claude
        response = await self.llm.call(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format="json"
        )
        
        # Parse response
        try:
            scores_data = json.loads(response)
        except json.JSONDecodeError:
            print(f"⚠️  Failed to parse Claude response: {response}")
            return []
        
        # Build recommendations
        recommendations = []
        
        for i, hotel in enumerate(candidates):
            if i < len(scores_data):
                score_data = scores_data[i]
                
                rec = HotelRecommendation(
                    hotel=hotel,
                    match_score=score_data.get("score", 0),
                    reasoning=score_data.get("reasoning", ""),
                    booking_url=hotel.booking_url
                )
                recommendations.append(rec)
        
        # Sort by match score (highest first)
        recommendations.sort(key=lambda x: x.match_score, reverse=True)
        
        print(f"📊 Scored {len(recommendations)} hotels")
        
        return recommendations


# Example usage
async def example_hotel_search():
    """Example of using HotelAgent."""
    from src.models.hotel import HotelSearch
    from src.core.llm_client import LLMClient
    from src.validators.hotel_validator import HotelValidator
    
    # Initialize
    llm = LLMClient()
    validator = HotelValidator()
    agent = HotelAgent(llm, validator)
    
    # Search
    request = HotelSearch(
        city="Hanoi",
        check_in_date="2024-03-20",
        check_out_date="2024-03-23",
        num_nights=3,
        budget_min=3000,
        budget_max=8000,
        star_rating_min=4.0,
        required_amenities=["WiFi", "Gym", "Restaurant"]
    )
    
    # Get recommendations
    recommendations = await agent.process(request)
    
    # Display results
    for rec in recommendations[:3]:
        print(f"\n{rec.hotel.name}")
        print(f"  Score: {rec.match_score:.2f}")
        print(f"  ${rec.hotel.price_per_night}/night")
        print(f"  Rating: {rec.hotel.rating_score}⭐")
        print(f"  Why: {rec.reasoning}")
