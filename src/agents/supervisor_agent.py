"""
Supervisor Agent - Coordinates all travel recommendation agents.
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
    """Coordinate intent parsing and travel recommendation agents."""

    def __init__(self, db: Session, llm_client=None):
        logger.info("SUPERVISOR_INIT_START")

        self.db = db
        self.llm_client = llm_client
        self.register = TripRegisterRepository(db)

        self.hotel_agent = HotelAgent(db, llm_client)
        self.activities_agent = ActivitiesAgent(db, llm_client)
        self.restaurant_agent = RestaurantAgent(db, llm_client)
        self.intent_parser = IntentParser(llm_client)

        logger.info("SUPERVISOR_INIT_SUCCESS")

    async def plan_trip(
        self,
        user_request: str,
        user_id: str = "streamlit-user",
    ) -> Dict[str, Any]:
        """Plan a complete trip with transaction logging."""

        logger.info("=" * 70)
        logger.info("SUPERVISOR_PLAN_TRIP_START")
        logger.info("User ID: %s", user_id)
        logger.info("User request: %s", user_request)
        logger.info("=" * 70)

        try:
            logger.info("STEP_1_INTENT_PARSE_START")

            intent = await self._parse_intent(user_request)

            logger.info("STEP_1_INTENT_PARSE_SUCCESS")
            logger.info("Normalized intent type: %s", type(intent).__name__)
            logger.info("Normalized intent: %s", intent)

            destination = intent["destination"]
            check_in_date = intent["check_in_date"]
            check_out_date = intent["check_out_date"]
            budget = intent["budget"]

            if not destination:
                raise ValueError(
                    "Destination could not be detected."
                )

            if not check_in_date or not check_out_date:
                raise ValueError(
                    "Check-in and check-out dates are required."
                )

            if budget <= 0:
                raise ValueError(
                    "Budget must be greater than zero."
                )

            logger.info("STEP_2_CREATE_TRIP_START")

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

            logger.info(
                "STEP_2_CREATE_TRIP_SUCCESS trip_id=%s",
                trip_id,
            )

            logger.info("STEP_3_HOTEL_AGENT_START")

            hotel_result = await self.hotel_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "STEP_3_HOTEL_AGENT_RESULT=%s",
                hotel_result,
            )

            if not hotel_result.get("success"):
                return {
                    "success": False,
                    "trip_id": trip_id,
                    "error": (
                        "Hotel booking failed: "
                        f"{hotel_result.get('error', 'Unknown error')}"
                    ),
                }

            logger.info("STEP_4_ACTIVITIES_AGENT_START")

            activities_result = await self.activities_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "STEP_4_ACTIVITIES_AGENT_RESULT=%s",
                activities_result,
            )

            if not activities_result.get("success"):
                activities_result = {
                    "activities": [],
                    "stats": {
                        "total_activities": 0,
                        "total_cost": 0,
                    },
                }

            logger.info("STEP_5_RESTAURANT_AGENT_START")

            restaurant_result = await self.restaurant_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "STEP_5_RESTAURANT_AGENT_RESULT=%s",
                restaurant_result,
            )

            if not restaurant_result.get("success"):
                restaurant_result = {
                    "meals": [],
                    "stats": {
                        "total_meals": 0,
                        "total_cost": 0,
                    },
                }

            logger.info("STEP_6_CONFLICT_CHECK_START")

            conflicts = self.register.get_conflicts(
                trip_id,
                resolved=False,
            )

            logger.info(
                "STEP_6_CONFLICT_CHECK_SUCCESS count=%s",
                len(conflicts),
            )

            logger.info("STEP_7_BUILD_ITINERARY_START")

            itinerary = self.register.build_itinerary(trip_id)

            logger.info(
                "STEP_7_BUILD_ITINERARY_SUCCESS count=%s",
                len(itinerary),
            )

            logger.info("STEP_8_BUDGET_SUMMARY_START")

            budget_summary = self.register.get_budget_summary(trip_id)

            logger.info(
                "STEP_8_BUDGET_SUMMARY_SUCCESS=%s",
                budget_summary,
            )

            activities = activities_result.get("activities", [])
            meals = restaurant_result.get("meals", [])

            result = {
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
                "budget": budget_summary,
                "conflicts": conflicts,
                "stats": {
                    "total_activities": len(activities),
                    "total_meals": len(meals),
                    "total_cost": budget_summary.get(
                        "spent",
                        0,
                    ),
                    "budget_remaining": budget_summary.get(
                        "remaining",
                        0,
                    ),
                    "conflicts": len(conflicts),
                },
                "message": (
                    "Trip planned successfully with "
                    f"{len(activities)} activities and "
                    f"{len(meals)} meals."
                ),
            }

            logger.info("SUPERVISOR_PLAN_TRIP_SUCCESS")
            logger.info("Trip ID: %s", trip_id)

            return result

        except Exception as exc:
            logger.exception("SUPERVISOR_PLAN_TRIP_FAILED")
            logger.error("Exception type: %s", type(exc).__name__)
            logger.error("Exception message: %s", str(exc))

            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _parse_intent(
        self,
        user_request: str,
    ) -> Dict[str, Any]:
        """
        Convert the Pydantic Intent object into a dictionary.

        This prevents:
        TypeError: 'Intent' object is not subscriptable
        """

        logger.info("SUPERVISOR_PARSE_INTENT_START")

        parsed_intent = await self.intent_parser.parse(user_request)

        logger.info(
            "RAW_INTENT_TYPE=%s",
            type(parsed_intent).__name__,
        )
        logger.info("RAW_INTENT=%r", parsed_intent)

        entities = parsed_intent.entities or {}

        logger.info(
            "RAW_ENTITIES_TYPE=%s",
            type(entities).__name__,
        )
        logger.info("RAW_ENTITIES=%s", entities)

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

        normalized_intent = {
            "destination": (
                entities.get("destination")
                or entities.get("city")
                or entities.get("location")
                or ""
            ),
            "
