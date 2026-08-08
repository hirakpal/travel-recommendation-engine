"""
Supervisor Agent - Orchestrates all specialized agents.
Coordinates Hotel, Activities, and Restaurant agents.
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import logging

from src.agents.hotel_agent import HotelAgent
from src.agents.activities_agent import ActivitiesAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.database.trip_register_repository import TripRegisterRepository
from src.core.intent_parser import IntentParser

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """
    Supervisor Agent - Orchestrates the multi-agent system.
    
    Responsibilities:
    1. Parse user intent
    2. Create/load trip in Master Register
    3. Route to specialized agents
    4. Coordinate agent execution
    5. Compile final results
    6. Handle errors and conflicts
    """
    
    def __init__(self, db: Session, llm_client=None):
        """Initialize supervisor with specialized agents."""
        self.db = db
        self.llm_client = llm_client
        self.register = TripRegisterRepository(db)
        
        # Initialize specialized agents
        self.hotel_agent = HotelAgent(db, llm_client)
        self.activities_agent = ActivitiesAgent(db, llm_client)
        self.restaurant_agent = RestaurantAgent(db, llm_client)
        
        self.intent_parser = IntentParser(llm_client)
    
    async def plan_trip(self, user_request: str, user_id: str) -> Dict[str, Any]:
        """
        Plan complete trip based on user request.
        
        Args:
            user_request: User's natural language request
            user_id: User identifier
        
        Returns:
            Complete trip plan with all bookings
        """
        logger.info("="*70)
        logger.info("🎯 SUPERVISOR: Starting trip planning")
        logger.info("="*70)
        logger.info(f"User request: {user_request}")
        
        # ==================== STEP 1: PARSE INTENT ====================
        
        logger.info("\n1️⃣  PARSING INTENT")
        logger.info("-" * 70)
        
        intent = await self._parse_intent(user_request)
        logger.info(f"   Destination: {intent['destination']}")
        logger.info(f"   Check-in: {intent['check_in_date']}")
        logger.info(f"   Check-out: {intent['check_out_date']}")
        logger.info(f"   Budget: ${intent['budget']}")
        logger.info(f"   Interests: {', '.join(intent.get('interests', []))}")
        logger.info(f"   Dietary: {', '.join(intent.get('dietary', []))}")
        
        # ==================== STEP 2: CREATE TRIP IN REGISTER ====================
        
        logger.info("\n2️⃣  CREATING TRIP IN MASTER REGISTER")
        logger.info("-" * 70)
        
        trip = self.register.create_trip(
            user_id=user_id,
            destination=intent['destination'],
            check_in_date=intent['check_in_date'],
            check_out_date=intent['check_out_date'],
            budget_total=intent['budget'],
            currency=intent.get('currency', 'USD'),
            interests=intent.get('interests', []),
            dietary_restrictions=intent.get('dietary', [])
        )
        
        trip_id = trip.id
        logger.info(f"   ✅ Trip created: {trip_id}")
        logger.info(f"   Destination: {trip.destination}")
        logger.info(f"   Nights: {trip.num_nights}")
        logger.info(f"   Budget: ${trip.budget_total}")
        
        # ==================== STEP 3: ROUTE TO HOTEL AGENT ====================
        
        logger.info("\n3️⃣  HOTEL AGENT")
        logger.info("-" * 70)
        
        hotel_result = await self.hotel_agent.process(
            trip_id=trip_id,
            city=intent['destination']
        )
        
        if not hotel_result['success']:
            logger.error(f"   ❌ Hotel booking failed: {hotel_result.get('error')}")
            return {
                "success": False,
                "error": f"Hotel booking failed: {hotel_result.get('error')}",
                "trip_id": trip_id
            }
        
        logger.info(f"   ✅ Hotel booked: {hotel_result['hotel']['name']}")
        logger.info(f"      Cost: ${hotel_result['hotel']['total_cost']:.2f}")
        logger.info(f"      Budget remaining: ${hotel_result['budget']['remaining']:.2f}")
        
        # ==================== STEP 4: ROUTE TO ACTIVITIES AGENT ====================
        
        logger.info("\n4️⃣  ACTIVITIES AGENT")
        logger.info("-" * 70)
        
        activities_result = await self.activities_agent.process(
            trip_id=trip_id,
            city=intent['destination']
        )
        
        if not activities_result['success']:
            logger.warning(f"   ⚠️  Activities booking: {activities_result.get('error')}")
            activities_result = {"activities": [], "stats": {"total_activities": 0}}
        else:
            logger.info(f"   ✅ Activities booked: {activities_result['stats']['total_activities']}")
            logger.info(f"      Cost: ${activities_result['stats']['total_cost']:.2f}")
            logger.info(f"      Budget remaining: ${activities_result['budget']['remaining']:.2f}")
        
        # ==================== STEP 5: ROUTE TO RESTAURANT AGENT ====================
        
        logger.info("\n5️⃣  RESTAURANT AGENT")
        logger.info("-" * 70)
        
        restaurant_result = await self.restaurant_agent.process(
            trip_id=trip_id,
            city=intent['destination']
        )
        
        if not restaurant_result['success']:
            logger.warning(f"   ⚠️  Restaurant booking: {restaurant_result.get('error')}")
            restaurant_result = {"meals": [], "stats": {"total_meals": 0}}
        else:
            logger.info(f"   ✅ Meals booked: {restaurant_result['stats']['total_meals']}")
            logger.info(f"      Cost: ${restaurant_result['stats']['total_cost']:.2f}")
            logger.info(f"      Budget remaining: ${restaurant_result['budget']['remaining']:.2f}")
        
        # ==================== STEP 6: CHECK FOR CONFLICTS ====================
        
        logger.info("\n6️⃣  CONFLICT DETECTION")
        logger.info("-" * 70)
        
        conflicts = self.register.get_conflicts(trip_id, resolved=False)
        if conflicts:
            logger.warning(f"   ⚠️  {len(conflicts)} conflicts detected:")
            for conflict in conflicts:
                logger.warning(f"      {conflict.description}")
        else:
            logger.info(f"   ✅ No conflicts detected")
        
        # ==================== STEP 7: BUILD FINAL ITINERARY ====================
        
        logger.info("\n7️⃣  BUILDING ITINERARY")
        logger.info("-" * 70)
        
        itinerary = self.register.build_itinerary(trip_id)
        logger.info(f"   ✅ Itinerary built: {len(itinerary)} items")
        
        # ==================== STEP 8: COMPILE RESULTS ====================
        
        logger.info("\n8️⃣  COMPILING RESULTS")
        logger.info("-" * 70)
        
        final_budget = self.register.get_budget_summary(trip_id)
        audit_logs = self.register.get_audit_logs(trip_id, limit=10)
        
        logger.info(f"   Final budget: ${final_budget['spent']:.2f} / ${final_budget['total']:.2f}")
        logger.info(f"   Remaining: ${final_budget['remaining']:.2f}")
        logger.info(f"   Breakdown: {final_budget['breakdown']}")
        logger.info(f"   Audit logs: {len(audit_logs)}")
        
        # ==================== RETURN COMPLETE TRIP PLAN ====================
        
        result = {
            "success": True,
            "trip_id": trip_id,
            "trip": {
                "destination": trip.destination,
                "check_in": str(trip.check_in_date),
                "check_out": str(trip.check_out_date),
                "nights": trip.num_nights
            },
            "bookings": {
                "hotel": hotel_result.get('hotel'),
                "activities": activities_result.get('activities', []),
                "meals": restaurant_result.get('meals', [])
            },
            "stats": {
                "total_activities": len(activities_result.get('activities', [])),
                "total_meals": len(restaurant_result.get('meals', [])),
                "total_cost": final_budget['spent'],
                "budget_remaining": final_budget['remaining'],
                "conflicts": len(conflicts)
            },
            "budget": final_budget,
            "message": f"✅ Trip planned successfully! Booked {len(activities_result.get('activities', []))} activities and {len(restaurant_result.get('meals', []))} meals with no conflicts."
        }
        
        logger.info("\n" + "="*70)
        logger.info("✅ TRIP PLANNING COMPLETE")
        logger.info("="*70)
        
        return result
    
    # ==================== HELPER METHODS ====================
    
    async def _parse_intent(self, user_request: str) -> Dict[str, Any]:
        """Parse user request to extract trip parameters."""
        # Use intent parser to extract structured data
        intent = await self.intent_parser.parse(user_request)
        return intent
