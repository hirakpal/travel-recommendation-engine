"""
Restaurant Agent - Plans and books meals.
Uses Master Trip Register for dietary & schedule coordination.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List
import logging

from src.agents.base_agent import BaseAgent
from src.database.repository import RestaurantRepository

logger = logging.getLogger(__name__)


class RestaurantAgent(BaseAgent):
    """
    Restaurant Agent - Plans meals.
    
    Workflow:
    1. Query Master Register for trip state & dietary restrictions
    2. Get available budget
    3. Check existing meal bookings
    4. Search for restaurants matching dietary needs
    5. Plan meals for trip duration
    6. Register each meal with Master Register
    7. Return meal plan with confirmations
    """
    
    async def process(self, trip_id: str, city: str = None, **kwargs) -> Dict[str, Any]:
        """
        Process meal planning request.
        
        Args:
            trip_id: Trip ID
            city: City for restaurants
            **kwargs: Additional parameters
        
        Returns:
            Dict with meal plan and bookings
        """
        logger.info(f"🍜 RESTAURANT AGENT: Planning meals for trip {trip_id}")
        
        # ==================== STEP 1: QUERY REGISTER ====================
        
        trip_state = self.get_trip_state(trip_id)
        if not trip_state:
            return {"success": False, "error": "Trip not found"}
        
        city = city or trip_state["destination"]
        logger.info(f"   City: {city}")
        logger.info(f"   Duration: {trip_state['nights']} nights")
        
        # ==================== STEP 2: GET DIETARY RESTRICTIONS ====================
        
        dietary_restrictions = trip_state.get('dietary', [])
        logger.info(f"   Dietary restrictions: {', '.join(dietary_restrictions) if dietary_restrictions else 'None'}")
        
        # ==================== STEP 3: GET BUDGET ====================
        
        budget_info = self.get_budget_info(trip_id)
        # Allocate 20% of remaining budget for meals
        meals_budget = budget_info['remaining'] * 0.2
        logger.info(f"   Meals budget: ${meals_budget:.2f}")
        
        # Per-meal budget (3 meals per day)
        num_meals = trip_state['nights'] * 3
        budget_per_meal = meals_budget / num_meals if num_meals > 0 else 0
        logger.info(f"   Budget per meal: ${budget_per_meal:.2f} ({num_meals} meals)")
        
        if meals_budget <= 0 or budget_per_meal <= 0:
            logger.warning("   No budget for meals")
            return {
                "success": False,
                "error": "Insufficient budget for meals"
            }
        
        # ==================== STEP 4: CHECK EXISTING MEALS ====================
        
        existing_meals = self.get_existing_bookings(trip_id, booking_type="restaurant")
        logger.info(f"   Existing meal bookings: {len(existing_meals)}")
        
        # ==================== STEP 5: SEARCH RESTAURANTS ====================
        
        restaurant_repo = RestaurantRepository(self.db)
        all_restaurants = restaurant_repo.get_by_city(city)
        logger.info(f"   Found {len(all_restaurants)} restaurants")
        
        # Filter by dietary needs
        suitable_restaurants = []
        for restaurant in all_restaurants:
            if not dietary_restrictions:
                # No restrictions, all OK
                suitable_restaurants.append(restaurant)
            else:
                # Check if restaurant has dietary options
                restaurant_options = restaurant.dietary_options or []
                if any(diet in restaurant_options for diet in dietary_restrictions):
                    suitable_restaurants.append(restaurant)
        
        logger.info(f"   Suitable restaurants: {len(suitable_restaurants)}")
        
        if not suitable_restaurants:
            logger.warning("   No restaurants match dietary requirements")
            suitable_restaurants = all_restaurants  # Fallback
        
        # Filter by budget
        affordable = [r for r in suitable_restaurants if (r.average_cost or 0) <= budget_per_meal]
        logger.info(f"   Affordable restaurants: {len(affordable)}")
        
        if not affordable:
            logger.error("   No affordable restaurants")
            return {
                "success": False,
                "error": "No affordable restaurants found"
            }
        
        # ==================== STEP 6: PLAN MEALS ====================
        
        check_in_date = date.fromisoformat(trip_state['check_in'])
        meal_types = ["breakfast", "lunch", "dinner"]
        meal_times = {
            "breakfast": ("07:00", "08:30"),
            "lunch": ("12:00", "13:30"),
            "dinner": ("18:00", "19:30")
        }
        
        meal_plan = []
        
        for day in range(trip_state['nights']):
            meal_date = check_in_date + timedelta(days=day)
            
            for meal_type in meal_types:
                # Rotate through restaurants
                restaurant = affordable[len(meal_plan) % len(affordable)]
                start_time, end_time = meal_times[meal_type]
                
                logger.info(f"   Planning: {meal_date} {meal_type}")
                logger.info(f"      Restaurant: {restaurant.name}")
                logger.info(f"      Cuisine: {restaurant.cuisine}")
                logger.info(f"      Cost: ${restaurant.average_cost}")
                
                meal_plan.append({
                    "restaurant": restaurant,
                    "date": meal_date,
                    "meal_type": meal_type,
                    "time_start": start_time,
                    "time_end": end_time,
                    "cost": restaurant.average_cost
                })
        
        logger.info(f"   Planned {len(meal_plan)} meals")
        
        # ==================== STEP 7: REGISTER MEALS ====================
        
        registered_meals = []
        
        for meal in meal_plan:
            restaurant = meal['restaurant']
            
            success, message, booking_id = self.register_booking(
                trip_id=trip_id,
                booking_type="restaurant",
                resource_id=restaurant.id,
                resource_name=restaurant.name,
                cost=restaurant.average_cost,
                booking_date=meal['date'],
                booking_time_start=meal['time_start'],
                booking_time_end=meal['time_end'],
                duration_minutes=90
            )
            
            if success:
                registered_meals.append({
                    "restaurant": restaurant.name,
                    "date": str(meal['date']),
                    "meal_type": meal['meal_type'],
                    "time": f"{meal['time_start']}-{meal['time_end']}",
                    "cuisine": restaurant.cuisine,
                    "cost": restaurant.average_cost,
                    "booking_id": booking_id,
                    "confirmation": message.split()[-1]
                })
            else:
                logger.warning(f"   Failed to book meal: {message}")
        
        # ==================== STEP 8: RETURN RESULT ====================
        
        updated_budget = self.get_budget_info(trip_id)
        
        return {
            "success": True,
            "meals": registered_meals,
            "stats": {
                "total_meals": len(registered_meals),
                "total_cost": meals_budget if len(registered_meals) > 0 else 0,
                "meals_budget": meals_budget,
                "restaurants_used": len(set(m['restaurant'] for m in registered_meals))
            },
            "budget": {
                "spent": updated_budget['spent'],
                "remaining": updated_budget['remaining'],
                "percentage": updated_budget['percentage_used']
            }
        }
