"""Restaurant recommendation agent with cuisine matching."""

import json
from typing import List, Optional
from src.agents.base_agent import BaseAgent
from src.models.restaurant import RestaurantSearch, RestaurantRecommendation, Restaurant
from src.core.llm_client import LLMClient
from src.validators.restaurant_validator import RestaurantValidator
from src.cache.manager import CacheManager

class RestaurantAgent(BaseAgent):
    """
    Restaurant recommendation agent.
    
    Features:
    - Cuisine preference matching
    - Dietary restriction handling
    - Price-to-quality optimization
    - Ambiance consideration
    - Distance optimization
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        validator: RestaurantValidator,
        cache: Optional[CacheManager] = None,
        restaurants_data_path: str = "data/restaurants.json"
    ):
        super().__init__("RestaurantAgent")
        self.llm = llm_client
        self.validator = validator
        self.cache = cache
        self.restaurants_db = self._load_database(restaurants_data_path)
    
    def _load_database(self, path: str) -> dict:
        """Load restaurants database."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Restaurants database not found at {path}")
            return {}
    
    async def process(
        self,
        request: RestaurantSearch
    ) -> List[RestaurantRecommendation]:
        """Process restaurant search request."""
        
        # STEP 1: Validate
        if not await self.validate(request):
            raise ValueError(f"Invalid restaurant search: {request}")
        
        # STEP 2: Cache check
        cache_key = self._make_cache_key(request)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
        
        # STEP 3: Filter by cuisine and dietary
        candidates = self._filter_restaurants(request)
        
        if not candidates:
            print(f"⚠️  No restaurants match criteria")
            return []
        
        # STEP 4: Score with Claude
        recommendations = await self._score_with_claude(request, candidates)
        
        # STEP 5: Cache
        if self.cache:
            await self.cache.set(cache_key, recommendations, ttl=3600)
        
        return recommendations
    
    async def validate(self, request: RestaurantSearch) -> bool:
        """Validate restaurant search."""
        return await self.validator.validate(request)
    
    def _make_cache_key(self, request: RestaurantSearch) -> str:
        """Create cache key."""
        cuisines_str = "_".join(sorted(request.cuisine_preferences))
        return f"restaurants:{request.city.lower()}:{request.date}:{request.meal_type}:{cuisines_str}"
    
    def _filter_restaurants(self, request: RestaurantSearch) -> List[Restaurant]:
        """Filter restaurants by criteria."""
        
        results = []
        restaurants_in_city = self.restaurants_db.get(request.city.lower(), [])
        
        for restaurant_data in restaurants_in_city:
            try:
                restaurant = Restaurant(**restaurant_data)
            except Exception as e:
                continue
            
            # Budget check
            if not (request.budget_min <= restaurant.price_level * 50 <= request.budget_max):
                continue
            
            # Cuisine check
            if request.cuisine_preferences:
                if not any(c in restaurant.cuisine_type for c in request.cuisine_preferences):
                    continue
            
            # Dietary restrictions
            if "vegetarian" in request.dietary_restrictions:
                if not restaurant.vegetarian_options:
                    continue
            if "vegan" in request.dietary_restrictions:
                if not restaurant.vegan_options:
                    continue
            
            results.append(restaurant)
        
        return results
    
    async def _score_with_claude(
        self,
        request: RestaurantSearch,
        candidates: List[Restaurant]
    ) -> List[RestaurantRecommendation]:
        """Score restaurants considering all preferences."""
        
        system_prompt = """You are a restaurant recommendation expert.

TASK: Score restaurants for meal experience.

SCORING (0-1):
- Cuisine match: Aligns with preferences
- Ambiance: Fits desired atmosphere
- Dietary compliance: Accommodates restrictions
- Price-value: Good value for money
- Quality: Rating and reviews
- Timing: Good for meal type

ANTI-BIAS:
✓ No anchoring on price/rating
✓ Consider all dietary needs
✓ Fair evaluation of all cuisines
✓ No hallucinated restaurants

RESPONSE FORMAT (JSON):
[{"id": "str", "score": float, "specialty": ["str"]}]"""
        
        restaurants_json = json.dumps(
            [r.dict() for r in candidates],
            indent=2
        )
        
        user_message = f"""City: {request.city}
Meal type: {request.meal_type}
Party size: {request.party_size}
Cuisine preferences: {request.cuisine_preferences}
Budget: ${request.budget_min}-${request.budget_max}
Dietary restrictions: {request.dietary_restrictions}
Ambiance: {request.ambiance or 'Any'}

Restaurants to evaluate:
{restaurants_json}

Score each for this specific meal type."""
        
        response = await self.llm.call(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format="json"
        )
        
        try:
            scores_data = json.loads(response)
        except json.JSONDecodeError:
            return []
        
        recommendations = []
        for i, restaurant in enumerate(candidates):
            if i < len(scores_data):
                score_data = scores_data[i]
                rec = RestaurantRecommendation(
                    restaurant=restaurant,
                    match_score=score_data.get("score", 0),
                    reasoning=f"Score: {score_data.get('score', 0)}",
                    suggested_time=self._suggest_time(request.meal_type),
                    specialty_recommendations=score_data.get("specialty", []),
                    booking_link=restaurant.booking_url
                )
                recommendations.append(rec)
        
        recommendations.sort(key=lambda x: x.match_score, reverse=True)
        return recommendations
    
    def _suggest_time(self, meal_type: str) -> str:
        """Suggest time based on meal type."""
        times = {
            "breakfast": "7:00-9:00 AM",
            "lunch": "12:00-2:00 PM",
            "dinner": "7:00-9:00 PM"
        }
        return times.get(meal_type, "18:00")
