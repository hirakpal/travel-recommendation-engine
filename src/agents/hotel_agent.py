from src.agents.base_agent import BaseAgent
from src.models.hotel import HotelSearch, HotelRecommendation, Hotel
from src.core.llm_client import LLMClient
from src.validators.hotel_validator import HotelValidator
from typing import List
import json

class HotelAgent(BaseAgent):
    """Hotel recommendation agent"""
    
    def __init__(self, llm_client: LLMClient, validator: HotelValidator):
        super().__init__("HotelAgent")
        self.llm = llm_client
        self.validator = validator
        self.hotels_database = self._load_hotels()
    
    def _load_hotels(self) -> dict:
        """Load hotels from database"""
        with open("data/hotels.json") as f:
            return json.load(f)
    
    async def process(self, request: HotelSearch) -> List[HotelRecommendation]:
        """Find best hotels for request"""
        
        # Validate request
        if not await self.validate(request):
            raise ValueError("Invalid hotel search request")
        
        # Get candidates from database
        candidates = self._filter_hotels(request)
        
        # Score using Claude
        recommendations = await self._score_and_rank(request, candidates)
        
        return recommendations
    
    async def validate(self, request: HotelSearch) -> bool:
        """Validate hotel search request"""
        return self.validator.validate(request)
    
    def _filter_hotels(self, request: HotelSearch) -> List[Hotel]:
        """Filter hotels by basic criteria"""
        results = []
        
        for hotel_data in self.hotels_database.get(request.city.lower(), []):
            hotel = Hotel(**hotel_data)
            
            # Basic filters
            if not (request.budget_min <= hotel.price_per_night <= request.budget_max):
                continue
            if hotel.star_rating < request.star_rating_min:
                continue
            if not hotel.is_available:
                continue
            
            results.append(hotel)
        
        return results
    
    async def _score_and_rank(self, request: HotelSearch, candidates: List[Hotel]) -> List[HotelRecommendation]:
        """Score hotels using Claude and rank"""
        
        system_prompt = """You are a hotel recommendation expert.
        
        TASK: Rank these hotels for the user and provide match scores.
        - Consider budget, amenities, location, ratings
        - Provide reasoning for each recommendation
        - Return JSON array with scores 0-1
        
        IMPORTANT - Bias Mitigation:
        ✓ Verify budget within acceptable range (START, MIDDLE, END check)
        ✓ Check all amenities are present
        ✓ Don't anchor on first hotel
        ✓ Only recommend from provided list (no hallucinations)
        """
        
        hotels_info = json.dumps([h.dict() for h in candidates], indent=2)
        user_request = f"""
        Check-in: {request.check_in_date}
        Check-out: {request.check_out_date}
        Budget: ${request.budget_min}-${request.budget_max}
        Minimum stars: {request.star_rating_min}
        Required amenities: {request.required_amenities}
        
        Available hotels:
        {hotels_info}
        """
        
        # Call Claude for scoring
        response = await self.llm.call(
            system_prompt=system_prompt,
            user_message=user_request,
            response_format="json"
        )
        
        # Parse and return recommendations
        scores = json.loads(response)
        recommendations = []
        
        for hotel, score_data in zip(candidates, scores):
            rec = HotelRecommendation(
                hotel=hotel,
                match_score=score_data["score"],
                reasoning=score_data["reasoning"],
                booking_url=hotel.booking_url
            )
            recommendations.append(rec)
        
        # Sort by match score
        return sorted(recommendations, key=lambda x: x.match_score, reverse=True)
