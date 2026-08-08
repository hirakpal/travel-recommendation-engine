"""
Hotel Agent - Books hotel accommodations.
Uses Master Trip Register for state management.
"""

from datetime import datetime, date
from typing import Dict, Any, List
from sqlalchemy.orm import Session
import logging

from src.agents.base_agent import BaseAgent
from src.database.repository import HotelRepository

logger = logging.getLogger(__name__)


class HotelAgent(BaseAgent):
    """
    Hotel Agent - Searches and books hotels.
    
    Workflow:
    1. Query Master Register for trip state
    2. Get available budget
    3. Check existing bookings
    4. Search for hotels within budget
    5. Select best option
    6. Register booking with Master Register
    7. Return confirmation
    """
    
    async def process(self, trip_id: str, city: str = None, **kwargs) -> Dict[str, Any]:
        """
        Process hotel booking request.
        
        Args:
            trip_id: Trip ID
            city: City to search (if None, use trip destination)
            **kwargs: Additional parameters
        
        Returns:
            Dict with booking status and details
        """
        logger.info(f"🏨 HOTEL AGENT: Processing hotel booking request for trip {trip_id}")
        
        # ==================== STEP 1: QUERY REGISTER ====================
        
        trip_state = self.get_trip_state(trip_id)
        if not trip_state:
            return {
                "success": False,
                "error": "Trip not found"
            }
        
        city = city or trip_state["destination"]
        logger.info(f"   City: {city}")
        logger.info(f"   Check-in: {trip_state['check_in']}")
        logger.info(f"   Check-out: {trip_state['check_out']}")
        logger.info(f"   Nights: {trip_state['nights']}")
        
        # ==================== STEP 2: CHECK BUDGET ====================
        
        budget_info = self.get_budget_info(trip_id)
        available_budget = budget_info['remaining']
        logger.info(f"   Available budget: ${available_budget:.2f}")
        
        if available_budget <= 0:
            logger.warning("   No budget remaining for hotel")
            return {
                "success": False,
                "error": "Insufficient budget for hotel"
            }
        
        # Budget allocation: 50% of total trip budget for hotel
        hotel_budget = min(available_budget, trip_state["budget"] * 0.5)
        max_per_night = hotel_budget / trip_state["nights"]
        logger.info(f"   Hotel budget: ${hotel_budget:.2f}")
        logger.info(f"   Max per night: ${max_per_night:.2f}")
        
        # ==================== STEP 3: CHECK EXISTING BOOKINGS ====================
        
        existing_hotels = self.get_existing_bookings(trip_id, booking_type="hotel")
        if existing_hotels:
            logger.info(f"   ℹ️  Hotel already booked: {existing_hotels[0].resource_name}")
            return {
                "success": True,
                "message": "Hotel already booked",
                "booking": {
                    "name": existing_hotels[0].resource_name,
                    "cost": existing_hotels[0].cost,
                    "confirmation": existing_hotels[0].confirmation_number
                }
            }
        
        # ==================== STEP 4: SEARCH HOTELS ====================
        
        hotel_repo = HotelRepository(self.db)
        candidates = hotel_repo.get_by_city_and_budget(city, 0, max_per_night)
        
        logger.info(f"   Found {len(candidates)} hotels within budget")
        
        if not candidates:
            logger.error(f"   No hotels found in {city} within ${max_per_night:.2f}/night")
            return {
                "success": False,
                "error": f"No hotels found in {city} within budget"
            }
        
        # ==================== STEP 5: SELECT BEST OPTION ====================
        
        # Rank by rating
        candidates.sort(key=lambda h: (h.rating or 0, -h.price_per_night), reverse=True)
        best_hotel = candidates[0]
        
        logger.info(f"   Selected hotel: {best_hotel.name}")
        logger.info(f"      Rating: {best_hotel.rating}/5")
        logger.info(f"      Price: ${best_hotel.price_per_night}/night")
        logger.info(f"      Amenities: {', '.join(best_hotel.amenities) if best_hotel.amenities else 'N/A'}")
        
        # Calculate total cost
        total_cost = best_hotel.price_per_night * trip_state["nights"]
        logger.info(f"      Total: ${total_cost:.2f} ({trip_state['nights']} nights)")
        
        # ==================== STEP 6: REGISTER BOOKING ====================
        
        success, message, booking_id = self.register_booking(
            trip_id=trip_id,
            booking_type="hotel",
            resource_id=best_hotel.id,
            resource_name=best_hotel.name,
            cost=total_cost,
            check_in_date=date.fromisoformat(trip_state['check_in']),
            check_out_date=date.fromisoformat(trip_state['check_out'])
        )
        
        if not success:
            return {
                "success": False,
                "error": message
            }
        
        # ==================== STEP 7: RETURN RESULT ====================
        
        updated_budget = self.get_budget_info(trip_id)
        
        return {
            "success": True,
            "hotel": {
                "name": best_hotel.name,
                "city": best_hotel.city,
                "rating": best_hotel.rating,
                "price_per_night": best_hotel.price_per_night,
                "total_cost": total_cost,
                "amenities": best_hotel.amenities,
                "address": best_hotel.address,
                "phone": best_hotel.phone,
                "website": best_hotel.website
            },
            "booking": {
                "id": booking_id,
                "confirmation_number": message.split()[-1],
                "status": "confirmed"
            },
            "budget": {
                "spent": updated_budget['spent'],
                "remaining": updated_budget['remaining'],
                "percentage": updated_budget['percentage_used']
            }
        }
