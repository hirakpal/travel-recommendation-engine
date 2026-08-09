"""LangGraph routing workflow for travel recommendations."""

import logging
from datetime import date, datetime
from typing import Any, Dict, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.activities_agent import ActivitiesAgent
from src.agents.hotel_agent import HotelAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.core.intent_parser import IntentParser
from src.core.runtime_diagnostics import record_event
from src.database.trip_register_repository import TripRegisterRepository

logger = logging.getLogger(__name__)

RouteName = Literal[
    "trip_planning",
    "hotel_search",
    "activity_search",
    "restaurant_search",
]


class TravelGraphState(TypedDict, total=False):
    user_request: str
    user_id: str
    intent: Dict[str, Any]
    check_in_date: date
    check_out_date: date
    number_of_nights: int
    route: RouteName
    trip_id: str
    trip: Any
    hotel_result: Dict[str, Any]
    activities_result: Dict[str, Any]
    restaurant_result: Dict[str, Any]
    itinerary: list
    conflicts: list
    budget: Dict[str, Any]
    result: Dict[str, Any]
    error: str


class LangGraphTravelRouter:
    """Route travel requests through specialist agent nodes."""

    def __init__(self, db, llm_client):
        self.db = db
        self.llm_client = llm_client
        self.register = TripRegisterRepository(db)
        self.intent_parser = IntentParser(llm_client)
        self.hotel_agent = HotelAgent(db, llm_client)
        self.activities_agent = ActivitiesAgent(db, llm_client)
        self.restaurant_agent = RestaurantAgent(db, llm_client)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(TravelGraphState)

        builder.add_node("parse_intent", self._parse_intent)
        builder.add_node("create_trip", self._create_trip)
        builder.add_node("hotel", self._run_hotel)
        builder.add_node("activities", self._run_activities)
        builder.add_node("restaurants", self._run_restaurants)
        builder.add_node("finalize", self._finalize)

        builder.add_edge(START, "parse_intent")

        builder.add_conditional_edges(
            "parse_intent",
            self._route_after_intent,
            {
                "trip_planning": "create_trip",
                "hotel_search": "create_trip",
                "activity_search": "create_trip",
                "restaurant_search": "create_trip",
            },
        )

        builder.add_conditional_edges(
            "create_trip",
            self._route_after_trip,
            {
                "trip_planning": "hotel",
                "hotel_search": "hotel",
                "activity_search": "activities",
                "restaurant_search": "restaurants",
            },
        )

        builder.add_conditional_edges(
            "hotel",
            self._route_after_hotel,
            {
                "trip_planning": "activities",
                "hotel_search": "finalize",
            },
        )

        builder.add_conditional_edges(
            "activities",
            self._route_after_activities,
            {
                "trip_planning": "restaurants",
                "activity_search": "finalize",
            },
        )
        builder.add_edge("restaurants", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    async def ainvoke(
        self,
        user_request: str,
        user_id: str = "streamlit-user",
    ) -> Dict[str, Any]:
        """Execute the routed graph and return the UI result format."""

        logger.info("LANGGRAPH_INVOKE_START")
        record_event(
            "LangGraph",
            "workflow_started",
            mode="orchestration",
            input_data={"user_request": user_request, "user_id": user_id},
        )

        try:
            state = await self.graph.ainvoke(
                {
                    "user_request": user_request,
                    "user_id": user_id,
                }
            )
            logger.info("LANGGRAPH_INVOKE_SUCCESS")
            record_event(
                "LangGraph",
                "workflow_completed",
                mode="orchestration",
                status="success",
                input_data=user_request,
                output_data=state.get("result"),
                trip_id=state.get("trip_id"),
            )
            return state.get(
                "result",
                {
                    "success": False,
                    "error": "Graph completed without a result.",
                },
            )
        except Exception as exc:
            logger.exception("LANGGRAPH_INVOKE_FAILED")
            record_event(
                "LangGraph",
                "workflow_failed",
                mode="orchestration",
                status="error",
                input_data=user_request,
                output_data=f"{type(exc).__name__}: {exc}",
            )
            return {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def _parse_intent(
        self,
        state: TravelGraphState,
    ) -> Dict[str, Any]:
        parsed = await self.intent_parser.parse(state["user_request"])
        entities = parsed.entities or {}

        destination = (
            entities.get("destination")
            or entities.get("city")
            or entities.get("location")
            or ""
        )

        aliases = {
            "veitnam": "Vietnam",
            "viet nam": "Vietnam",
        }
        destination = aliases.get(
            str(destination).strip().lower(),
            str(destination).strip(),
        )

        try:
            budget = float(entities.get("budget") or 0)
        except (TypeError, ValueError):
            budget = 0.0

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

        intent = {
            "destination": destination,
            "check_in_date": self._to_date(
                entities.get("check_in_date")
                or entities.get("check_in")
            ),
            "check_out_date": self._to_date(
                entities.get("check_out_date")
                or entities.get("check_out")
            ),
            "budget": budget,
            "currency": "USD",
            "interests": interests,
            "dietary": dietary,
            "intent_type": self._route_name(parsed.type),
        }

        check_in = intent["check_in_date"]
        check_out = intent["check_out_date"]
        number_of_nights = (check_out - check_in).days
        logger.info(
            "LANGGRAPH_DATE_CONTEXT arrival=%s return=%s nights=%s",
            check_in,
            check_out,
            number_of_nights,
        )

        logger.info("LANGGRAPH_INTENT_PARSED route=%s", intent["intent_type"])
        record_event(
            "Intent Router",
            "intent_parsed",
            mode="llm",
            status="success",
            input_data=state["user_request"],
            output_data=intent,
        )
        return {
            "intent": intent,
            "route": intent["intent_type"],
            "check_in_date": check_in,
            "check_out_date": check_out,
            "number_of_nights": number_of_nights,
        }

    def _route_after_intent(
        self,
        state: TravelGraphState,
    ) -> RouteName:
        return state.get("route", "trip_planning")

    async def _create_trip(
        self,
        state: TravelGraphState,
    ) -> Dict[str, Any]:
        intent = state["intent"]
        trip = self.register.create_trip(
            user_id=state.get("user_id", "streamlit-user"),
            destination=intent["destination"],
            check_in_date=intent["check_in_date"],
            check_out_date=intent["check_out_date"],
            budget_total=intent["budget"],
            currency=intent["currency"],
            interests=intent["interests"],
            dietary_restrictions=intent["dietary"],
        )
        logger.info("LANGGRAPH_TRIP_CREATED trip_id=%s", trip.id)
        record_event(
            "Master Trip Register",
            "trip_created",
            mode="database",
            status="success",
            input_data=intent,
            output_data={"trip_id": trip.id, "nights": trip.num_nights},
            trip_id=trip.id,
        )
        return {"trip_id": trip.id, "trip": trip}

    def _route_after_trip(self, state: TravelGraphState) -> RouteName:
        return state.get("route", "trip_planning")

    async def _run_hotel(self, state: TravelGraphState) -> Dict[str, Any]:
        logger.info(
            "LANGGRAPH_HOTEL_CONTEXT check_in=%s check_out=%s nights=%s",
            state["check_in_date"],
            state["check_out_date"],
            state["number_of_nights"],
        )
        result = await self.hotel_agent.process(
            trip_id=state["trip_id"],
            city=state["intent"]["destination"],
        )
        logger.info("LANGGRAPH_HOTEL_COMPLETE")
        record_event(
            "Hotel Agent",
            "recommendations_completed",
            mode="agent",
            status="success",
            input_data={"trip_id": state["trip_id"], "city": state["intent"]["destination"]},
            output_data=result,
            trip_id=state["trip_id"],
        )
        return {"hotel_result": result}

    def _route_after_hotel(self, state: TravelGraphState) -> RouteName:
        return state.get("route", "trip_planning")

    async def _run_activities(
        self,
        state: TravelGraphState,
    ) -> Dict[str, Any]:
        logger.info(
            "LANGGRAPH_ACTIVITIES_CONTEXT check_in=%s check_out=%s nights=%s",
            state["check_in_date"],
            state["check_out_date"],
            state["number_of_nights"],
        )
        result = await self.activities_agent.process(
            trip_id=state["trip_id"],
            city=state["intent"]["destination"],
        )
        logger.info("LANGGRAPH_ACTIVITIES_COMPLETE")
        record_event(
            "Activities Agent",
            "recommendations_completed",
            mode="agent",
            status="success",
            input_data={"trip_id": state["trip_id"], "city": state["intent"]["destination"]},
            output_data=result,
            trip_id=state["trip_id"],
        )
        return {"activities_result": result}

    async def _run_restaurants(
        self,
        state: TravelGraphState,
    ) -> Dict[str, Any]:
        result = await self.restaurant_agent.process(
            trip_id=state["trip_id"],
            city=state["intent"]["destination"],
        )
        logger.info("LANGGRAPH_RESTAURANTS_COMPLETE")
        record_event(
            "Restaurant Agent",
            "recommendations_completed",
            mode="agent",
            status="success",
            input_data={"trip_id": state["trip_id"], "city": state["intent"]["destination"]},
            output_data=result,
            trip_id=state["trip_id"],
        )
        return {"restaurant_result": result}

    def _route_after_activities(
        self,
        state: TravelGraphState,
    ) -> RouteName:
        return state.get("route", "trip_planning")

    async def _finalize(
        self,
        state: TravelGraphState,
    ) -> Dict[str, Any]:
        trip_id = state["trip_id"]
        trip = state["trip"]
        hotel = state.get("hotel_result", {}).get("hotel")
        activities = state.get("activities_result", {}).get(
            "activities", []
        )
        meals = state.get("restaurant_result", {}).get("meals", [])

        conflicts = self.register.get_conflicts(
            trip_id,
            resolved=False,
        )
        itinerary = self.register.build_itinerary(trip_id)
        budget = self.register.get_budget_summary(trip_id)

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
                "hotel": hotel,
                "activities": activities,
                "meals": meals,
            },
            "itinerary": itinerary,
            "budget": budget,
            "conflicts": conflicts,
            "stats": {
                "total_activities": len(activities),
                "total_meals": len(meals),
                "total_cost": budget.get("spent", 0),
                "budget_remaining": budget.get("remaining", 0),
                "conflicts": len(conflicts),
            },
            "message": (
                "Trip planned successfully for "
                f"{trip.destination}."
            ),
        }
        record_event(
            "LangGraph",
            "recommendation_result_assembled",
            mode="orchestration",
            status="success",
            output_data={
                "hotel": bool(hotel),
                "activities": len(activities),
                "meals": len(meals),
                "conflicts": len(conflicts),
            },
            trip_id=trip_id,
        )
        return {"result": result}

    @staticmethod
    def _route_name(intent_type: Any) -> RouteName:
        value = getattr(intent_type, "value", str(intent_type))
        if value in {
            "hotel_search",
            "activity_search",
            "restaurant_search",
            "trip_planning",
        }:
            return value
        return "trip_planning"

    @staticmethod
    def _to_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not value:
            raise ValueError("A valid date is required.")
        return date.fromisoformat(str(value)[:10])
