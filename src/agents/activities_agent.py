"""
Activities Agent - Plans and books activities.
Uses Master Trip Register for schedule coordination.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List
import logging

from src.agents.base_agent import BaseAgent
from src.database.repository import ActivityRepository

logger = logging.getLogger(__name__)


class ActivitiesAgent(BaseAgent):
    """
    Activities Agent - Plans day activities.
    
    Workflow:
    1. Query Master Register for trip state
    2. Get available budget
    3. Check existing itinerary to avoid time conflicts
    4. Detect conflicts in schedule
    5. Search for activities
    6. Select activities based on schedule & interests
    7. Register each activity with Master Register
    8. Return complete activity plan
    """
    
    async def process(self, trip_id: str, city: str = None, **kwargs) -> Dict[str, Any]:
        """
        Process activity planning request.
        
        Args:
            trip_id: Trip ID
            city: City for activities
            **kwargs: Additional parameters
        
        Returns:
            Dict with activity plan and bookings
        """
        logger.info(f"🎫 ACTIVITIES AGENT: Planning activities for trip {trip_id}")
        
        # ==================== STEP 1: QUERY REGISTER ====================
        
        trip_state = self.get_trip_state(trip_id)
        if not trip_state:
            return {"success": False, "error": "Trip not found"}
        
        city = city or trip_state["destination"]
        logger.info(f"   City: {city}")
        logger.info(f"   Interests: {', '.join(trip_state.get('interests', []))}")
        
        # ==================== STEP 2: GET BUDGET ====================
        
        budget_info = self.get_budget_info(trip_id)
        # Allocate 30% of remaining budget for activities
        activities_budget = budget_info['remaining'] * 0.3
        logger.info(f"   Activity budget: ${activities_budget:.2f}")
        
        if activities_budget <= 0:
            logger.warning("   No budget for activities")
            return {
                "success": False,
                "error": "Insufficient budget for activities"
            }
        
        # ==================== STEP 3: CHECK EXISTING SCHEDULE ====================
        
        itinerary = self.get_itinerary(trip_id)
        logger.info(f"   Current itinerary: {len(itinerary)} items")
        
        for item in itinerary:
            logger.info(f"      {item.date}: {item.activity_name}")
        
        # ==================== STEP 4: DETECT CONFLICTS ====================
        
        conflicts = self.check_conflicts(trip_id)
        if conflicts:
            logger.warning(f"   ⚠️  {len(conflicts)} conflicts detected")
            for conflict in conflicts[:3]:  # Show first 3
                logger.warning(f"      {conflict.description}")
        
        # ==================== STEP 5: SEARCH ACTIVITIES ====================
        
        activity_repo = ActivityRepository(self.db)
        all_activities = activity_repo.get_by_city(city)
        logger.info(f"   Found {len(all_activities)} activities in {city}")
        
        # Filter by user interests
        user_interests = trip_state.get('interests', [])
        if user_interests:
            filtered = [a for a in all_activities if a.category in user_interests]
            logger.info(f"   Filtered to {len(filtered)} matching interests")
        else:
            filtered = all_activities
        
        # Filter by budget
        affordable = [a for a in filtered if a.cost <= activities_budget]
        logger.info(f"   Filtered to {len(affordable)} affordable activities")
        
        if not affordable:
            logger.error("   No affordable activities found")
            return {
                "success": False,
                "error": "No affordable activities found"
            }
        
        # ==================== STEP 6: SELECT ACTIVITIES ====================
        
        selected_activities = []
        current_budget = activities_budget
        
        # Create activity schedule
        activity_schedule = [
            {"day": 0, "time_start": "09:00", "time_end": "12:00", "slot": "morning"},
            {"day": 1, "time_start": "14:00", "time_end": "17:00", "slot": "afternoon"},
            {"day": 2, "time_start": "09:00", "time_end": "12:00", "slot": "morning"}
        ]
        
        # Rank activities by rating
        affordable.sort(key=lambda a: a.rating or 0, reverse=True)
        
        for i, activity in enumerate(affordable[:5]):  # Max 5 activities
            if current_budget < activity.cost:
                logger.info(f"   Budget exhausted, stopping")
                break
            
            if i >= len(activity_schedule):
                logger.info(f"   Schedule full, stopping")
                break
            
            schedule = activity_schedule[i]
            activity_date = date.fromisoformat(trip_state['check_in']) + timedelta(days=schedule['day'])
            
            logger.info(f"   Selecting: {activity.name}")
            logger.info(f"      Date: {activity_date}")
            logger.info(f"      Time: {schedule['time_start']}-{schedule['time_end']}")
            logger.info(f"      Cost: ${activity.cost}")
            
            selected_activities.append({
                "activity": activity,
                "date": activity_date,
                "time_start": schedule['time_start'],
                "time_end": schedule['time_end'],
                "slot": schedule['slot'],
                "cost": activity.cost
            })
            
            current_budget -= activity.cost
        
        # ==================== STEP 7: REGISTER BOOKINGS ====================
        
        registered_activities = []
        
        for activity_item in selected_activities:
            activity = activity_item['activity']
            
            success, message, booking_id = self.register_booking(
                trip_id=trip_id,
                booking_type="activity",
                resource_id=activity.id,
                resource_name=activity.name,
                cost=activity.cost,
                booking_date=activity_item['date'],
                booking_time_start=activity_item['time_start'],
                booking_time_end=activity_item['time_end'],
                duration_minutes=activity.duration_minutes
            )
            
            if success:
                registered_activities.append({
                    "name": activity.name,
                    "date": str(activity_item['date']),
                    "time": f"{activity_item['time_start']}-{activity_item['time_end']}",
                    "category": activity.category,
                    "cost": activity.cost,
                    "booking_id": booking_id,
                    "confirmation": message.split()[-1]
                })
            else:
                logger.error(f"   Failed to register {activity.name}: {message}")
        
        # ==================== STEP 8: RETURN RESULT ====================
        
        updated_budget = self.get_budget_info(trip_id)
        
        return {
            "success": True,
            "activities": registered_activities,
            "stats": {
                "total_activities": len(registered_activities),
                "total_cost": activities_budget - current_budget,
                "activities_budget": activities_budget
            },
            "budget": {
                "spent": updated_budget['spent'],
                "remaining": updated_budget['remaining'],
                "percentage": updated_budget['percentage_used']
            }
        }
