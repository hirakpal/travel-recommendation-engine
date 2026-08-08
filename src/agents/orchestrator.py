"""
Multi-agent orchestrator for coordinating agents.

Runs multiple agents in parallel/sequence and combines results.
"""

import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.agents.hotel_agent import HotelAgent
from src.agents.activities_agent import ActivitiesAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.models.hotel import HotelSearch, HotelRecommendation
from src.models.activities import ActivitySearch, ActivityRecommendation
from src.models.restaurant import RestaurantSearch, RestaurantRecommendation

@dataclass
class TripPlan:
    """Complete trip plan."""
    destination: str
    duration: str
    hotels: List[HotelRecommendation]
    activities: List[ActivityRecommendation]
    restaurants: List[RestaurantRecommendation]
    itinerary: List[Dict[str, Any]]
    summary: str

class MultiAgentOrchestrator:
    """
    Orchestrator for running multiple agents.
    
    Coordinates:
    - Hotel search
    - Activities planning
    - Restaurant recommendations
    - Itinerary generation
    """
    
    def __init__(
        self,
        hotel_agent: HotelAgent,
        activities_agent: ActivitiesAgent,
        restaurant_agent: RestaurantAgent
    ):
        self.hotel = hotel_agent
        self.activities = activities_agent
        self.restaurant = restaurant_agent
    
    async def plan_trip(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        budget: float,
        interests: List[str],
        dietary_restrictions: Optional[List[str]] = None,
        num_nights: Optional[int] = None
    ) -> TripPlan:
        """
        Plan complete trip with all recommendations.
        
        Runs agents in parallel and combines results.
        """
        
        if dietary_restrictions is None:
            dietary_restrictions = []
        
        # Calculate nights if not provided
        from datetime import datetime
        if not num_nights:
            check_in_date = datetime.fromisoformat(check_in)
            check_out_date = datetime.fromisoformat(check_out)
            num_nights = (check_out_date - check_in_date).days
        
        # Distribute budget
        nightly_budget = budget / num_nights if num_nights > 0 else budget
        
        # Create search requests
        hotel_search = HotelSearch(
            city=destination,
            check_in_date=check_in,
            check_out_date=check_out,
            num_nights=num_nights,
            budget_min=nightly_budget * 0.7,
            budget_max=nightly_budget * 1.3,
            star_rating_min=3.5
        )
        
        activities_search = ActivitySearch(
            city=destination,
            date=check_in,
            interests=interests,
            max_duration=480,  # 8 hours per day
            budget_per_activity=50,
            num_activities=3,
            difficulty_level="moderate"
        )
        
        restaurant_search = RestaurantSearch(
            city=destination,
            date=check_in,
            meal_type="dinner",
            cuisine_preferences=["local"],
            budget_min=30,
            budget_max=150,
            party_size=1,
            dietary_restrictions=dietary_restrictions
        )
        
        # Run agents in parallel
        print(f"🔄 Planning trip to {destination}...")
        
        hotel_task = self.hotel.process(hotel_search)
        activities_task = self.activities.process(activities_search)
        restaurant_task = self.restaurant.process(restaurant_search)
        
        # Wait for all
        hotels, activities, restaurants = await asyncio.gather(
            hotel_task,
            activities_task,
            restaurant_task,
            return_exceptions=True
        )
        
        # Handle errors
        if isinstance(hotels, Exception):
            print(f"⚠️  Hotel search failed: {hotels}")
            hotels = []
        if isinstance(activities, Exception):
            print(f"⚠️  Activities search failed: {activities}")
            activities = []
        if isinstance(restaurants, Exception):
            print(f"⚠️  Restaurant search failed: {restaurants}")
            restaurants = []
        
        # Generate itinerary
        itinerary = self._generate_itinerary(
            check_in,
            num_nights,
            activities,
            restaurants,
            hotels
        )
        
        # Generate summary
        summary = self._generate_summary(
            destination,
            num_nights,
            hotels,
            activities,
            restaurants
        )
        
        return TripPlan(
            destination=destination,
            duration=f"{num_nights} nights",
            hotels=hotels[:3] if hotels else [],
            activities=activities[:5] if activities else [],
            restaurants=restaurants[:3] if restaurants else [],
            itinerary=itinerary,
            summary=summary
        )
    
    def _generate_itinerary(
        self,
        check_in: str,
        num_nights: int,
        activities: List[ActivityRecommendation],
        restaurants: List[RestaurantRecommendation],
        hotels: List[HotelRecommendation]
    ) -> List[Dict[str, Any]]:
        """Generate day-by-day itinerary."""
        
        from datetime import datetime, timedelta
        
        start_date = datetime.fromisoformat(check_in)
        itinerary = []
        
        for day in range(num_nights):
            current_date = start_date + timedelta(days=day)
            
            day_plan = {
                "day": day + 1,
                "date": current_date.strftime("%Y-%m-%d"),
                "morning": None,
                "afternoon": None,
                "evening": {
                    "dinner": restaurants[day % len(restaurants)] if restaurants else None
                },
                "hotel": hotels[0] if hotels else None
            }
            
            # Distribute activities
            if activities:
                activity_idx = (day * 2) % len(activities)
                day_plan["morning"] = activities[activity_idx]
                if activity_idx + 1 < len(activities):
                    day_plan["afternoon"] = activities[activity_idx + 1]
            
            itinerary.append(day_plan)
        
        return itinerary
    
    def _generate_summary(
        self,
        destination: str,
        num_nights: int,
        hotels: List[HotelRecommendation],
        activities: List[ActivityRecommendation],
        restaurants: List[RestaurantRecommendation]
    ) -> str:
        """Generate trip summary."""
        
        hotel_name = hotels[0].hotel.name if hotels else "TBD"
        hotel_price = hotels[0].hotel.price_per_night if hotels else "TBD"
        
        activity_names = [a.activity.name for a in activities[:3]]
        restaurant_names = [r.restaurant.name for r in restaurants[:2]]
        
        summary = f"""
        **{destination} Trip Summary**
        
        Duration: {num_nights} nights
        
        **Accommodation:**
        {hotel_name} (${hotel_price}/night)
        
        **Activities:**
        {chr(10).join([f"- {a}" for a in activity_names])}
        
        **Dining:**
        {chr(10).join([f"- {r}" for r in restaurant_names])}
        
        Your trip is all planned! 🎉
        """
        
        return summary.strip()
