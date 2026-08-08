"""
Supervisor Agent - Coordinates the travel recommendation agents.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from src.agents.activities_agent import ActivitiesAgent
from src.agents.hotel_agent import HotelAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.core.intent_parser import IntentParser
from src.database.trip_register_repository import TripRegisterRepository

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Coordinate intent parsing, trip creation, and specialized agents."""

    def __init__(self, db: Session, llm_client=None):
        self.db = db
        self.llm_client = llm_client
        self.register = TripRegisterRepository(db)

        self.hotel_agent = HotelAgent(db, llm_client)
        self.activities_agent = ActivitiesAgent(db, llm_client)
        self.restaurant_agent = RestaurantAgent(db, llm_client)

        self.intent_parser = IntentParser(llm_client)

    async def plan_trip(
        self,
        user_request: str,
        user_id: str = "streamlit-user",
    ) -> Dict[str, Any]:
        """Plan a complete trip."""

        logger.info("=" * 70)
        logger.info("SUPERVISOR: Starting trip planning")
        logger.info("=" * 70)
        logger.info("User request: %s", user_request)

        intent = await self._parse_intent(user_request)

        destination = intent["destination"]
        check_in_date = intent["check_in_date"]
        check_out_date = intent["check_out_date"]
        budget = intent["budget"]

        if not destination:
            return {
                "success": False,
                "error": "Destination could not be extracted from the request.",
            }

        if not check_in_date or not check_out_date:
            return {
                "success": False,
                "error": "Check-in and check-out dates are required.",
            }

        if budget <= 0:
            return {
                "success": False,
                "error": "A valid budget is required.",
            }

        logger.info("Destination: %s", destination)
        logger.info("Check-in: %s", check_in_date)
        logger.info("Check-out: %s", check_out_date)
        logger.info("Budget: $%s", budget)

        trip = self.register.create_trip(
            user_id=user_id,
            destination=destination,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            budget_total=budget,
            currency=intent.get("currency", "USD"),
            interests=intent.get("interests", []),
            dietary_restrictions=intent.get("dietary", []),
        )

        trip_id = trip.id

        logger.info("Trip created: %s", trip_id)

        hotel_result = await self.hotel_agent.process(
            trip_id=trip_id,
            city=destination,
        )

        if not hotel_result.get("success"):
            return {
                "success": False,
                "error": (
                    "Hotel booking failed: "
                    f"{hotel_result.get('error', 'Unknown error')}"
                ),
                "trip_id": trip_id,
            }

        activities_result = await self.activities_agent.process(
            trip_id=trip_id,
            city=destination,
        )

        if not activities_result.get("success"):
            activities_result = {
                "activities": [],
                "stats": {
                    "total_activities": 0,
                    "total_cost": 0,
                },
            }

        restaurant_result = await self.restaurant_agent.process(
            trip_id=trip_id,
            city=destination,
        )

        if not restaurant_result.get("success"):
            restaurant_result = {
                "meals": [],
                "stats": {
                    "total_meals": 0,
                    "total_cost": 0,
                },
            }

        conflicts = self.register.get_conflicts(
            trip_id,
            resolved=False,
        )

        itinerary = self.register.build_itinerary(trip_id)
        final_budget = self.register.get_budget_summary(trip_id)
        audit_logs = self.register.get_audit_logs(
            trip_id,
            limit=10,
        )

        activities = activities_result.get("activities", [])
        meals = restaurant_result.get("meals", [])

        return {
            "success": True,
            "trip_id": trip_id,
            "trip": {
                "destination": trip.destination,
                "check_in": str(trip.check_in_date),
                "check_out": str(trip.check_out_date),
                "nights": trip.num_nights,
            },
            "bookings": {
                "hotel": hotel_result.get("hotel"),
                "activities": activities,
                "meals": meals,
            },
            "itinerary": itinerary,
            "stats": {
                "total_activities": len(activities),
                "total_meals": len(meals),
                "total_cost": final_budget.get("spent", 0),
                "budget_remaining": final_budget.get("remaining", 0),
                "conflicts": len(conflicts),
                "audit_logs": len(audit_logs),
            },
            "budget": final_budget,
            "conflicts": conflicts,
            "message": (
                "Trip planned successfully with "
                f"{len(activities)} activities and "
                f"{len(meals)} meals."
            ),
        }

    async def _parse_intent(
        self,
        user_request: str,
    ) -> Dict[str, Any]:
        """Convert the Pydantic Intent object into a dictionary."""

        parsed_intent = await self.intent_parser.parse(user_request)
        entities = parsed_intent.entities or {}

        interests = (
            entities.get("interests")
            or entities.get("preferences")
            or []
        )

        dietary = (
            entities.get("dietary")
            or entities.get("dietary_restrictions")
            or []
        )

        if isinstance(interests, str):
            interests = [interests]

        if isinstance(dietary, str):
            dietary = [dietary]

        try:
            budget = float(entities.get("budget") or 0)
        except (TypeError, ValueError):
            budget = 0.0

        return {
            "destination": (
                entities.get("destination")
                or entities.get("city")
                or entities.get("location")
                or ""
            ),
            "check_in_date": (
                entities.get("check_in_date")
                or entities.get("check_in")
                or ""
            ),
            "check_out_date": (
                entities.get("check_out_date")
                or entities.get("check_out")
                or ""
            ),
            "budget": budget,
            "currency": "USD",
            "interests": interests,
            "dietary": dietary,
            "confidence": parsed_intent.confidence,
            "requires_clarification": (
                parsed_intent.requires_clarification
            ),
        }
