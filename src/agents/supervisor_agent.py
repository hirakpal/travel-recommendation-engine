import logging
from datetime import date, datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from src.agents.activities_agent import ActivitiesAgent
from src.agents.hotel_agent import HotelAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.core.intent_parser import IntentParser
from src.database.trip_register_repository import TripRegisterRepository

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Coordinate travel planning for any destination."""

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

    @staticmethod
    def _to_date(value: Any) -> date:
        """Convert a date string into a Python date object."""

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if not value:
            raise ValueError("A valid date is required.")

        return date.fromisoformat(str(value)[:10])

    async def plan_trip(
        self,
        user_request: str,
        user_id: str = "streamlit-user",
    ) -> Dict[str, Any]:
        """Plan a complete trip."""

        logger.info("SUPERVISOR_PLAN_TRIP_START")
        logger.info("User request: %s", user_request)

        try:
            intent = await self._parse_intent(user_request)

            logger.info(
                "NORMALIZED_INTENT_TYPE=%s",
                type(intent).__name__,
            )
            logger.info("NORMALIZED_INTENT=%s", intent)

            destination = intent["destination"]
            check_in_date = intent["check_in_date"]
            check_out_date = intent["check_out_date"]
            budget = intent["budget"]

            if not destination:
                return {
                    "success": False,
                    "error": "Destination could not be detected.",
                }

            if not check_in_date or not check_out_date:
                return {
                    "success": False,
                    "error": "Check-in and check-out dates are required.",
                }

            if budget <= 0:
                return {
                    "success": False,
                    "error": "Budget must be greater than zero.",
                }

            logger.info("CREATE_TRIP_START")

            trip = self.register.create_trip(
                user_id=user_id,
                destination=destination,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                budget_total=budget,
                currency=intent.get("currency", "USD"),
                interests=intent.get("interests", []),
                dietary_restrictions=intent.get(
                    "dietary",
                    [],
                ),
            )

            trip_id = trip.id

            logger.info(
                "CREATE_TRIP_SUCCESS trip_id=%s",
                trip_id,
            )

            logger.info("HOTEL_AGENT_START")

            hotel_result = await self.hotel_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "HOTEL_AGENT_RESULT=%s",
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

            logger.info("ACTIVITIES_AGENT_START")

            activities_result = await self.activities_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "ACTIVITIES_AGENT_RESULT=%s",
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

            logger.info("RESTAURANT_AGENT_START")

            restaurant_result = await self.restaurant_agent.process(
                trip_id=trip_id,
                city=destination,
            )

            logger.info(
                "RESTAURANT_AGENT_RESULT=%s",
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

            logger.info("CONFLICT_CHECK_START")

            conflicts = self.register.get_conflicts(
                trip_id,
                resolved=False,
            )

            logger.info(
                "CONFLICT_CHECK_SUCCESS count=%s",
                len(conflicts),
            )

            logger.info("ITINERARY_BUILD_START")

            itinerary = self.register.build_itinerary(trip_id)

            logger.info(
                "ITINERARY_BUILD_SUCCESS count=%s",
                len(itinerary),
            )

            logger.info("BUDGET_SUMMARY_START")

            budget_summary = self.register.get_budget_summary(trip_id)

            logger.info(
                "BUDGET_SUMMARY_SUCCESS=%s",
                budget_summary,
            )

            activities = activities_result.get(
                "activities",
                [],
            )

            meals = restaurant_result.get(
                "meals",
                [],
            )

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
                    "Trip planned successfully for "
                    f"{destination}."
                ),
            }

            logger.info("SUPERVISOR_PLAN_TRIP_SUCCESS")

            return result

        except Exception as exc:
            logger.exception("SUPERVISOR_PLAN_TRIP_FAILED")

            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _parse_intent(
        self,
        user_request: str,
    ) -> Dict[str, Any]:
        """Parse and normalize the Intent model."""

        parsed_intent = await self.intent_parser.parse(user_request)

        logger.info(
            "RAW_INTENT_TYPE=%s",
            type(parsed_intent).__name__,
        )

        entities = parsed_intent.entities or {}

        destination = (
            entities.get("destination")
            or entities.get("city")
            or entities.get("location")
            or ""
        )

        destination_aliases = {
            "veitnam": "Vietnam",
            "viet nam": "Vietnam",
        }

        destination = destination_aliases.get(
            str(destination).strip().lower(),
            str(destination).strip(),
        )

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

        check_in_value = (
            entities.get("check_in_date")
            or entities.get("check_in")
            or ""
        )

        check_out_value = (
            entities.get("check_out_date")
            or entities.get("check_out")
            or ""
        )

        check_in_date = self._to_date(check_in_value)
        check_out_date = self._to_date(check_out_value)

        normalized_intent = {
            "destination": destination,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "budget": budget,
            "currency": "USD",
            "interests": interests,
            "dietary": dietary,
            "confidence": parsed_intent.confidence,
            "requires_clarification": (
                parsed_intent.requires_clarification
            ),
        }

        logger.info(
            "NORMALIZED_INTENT_TYPE=%s",
            type(normalized_intent).__name__,
        )
        logger.info(
            "NORMALIZED_INTENT=%s",
            normalized_intent,
        )

        return normalized_intent
