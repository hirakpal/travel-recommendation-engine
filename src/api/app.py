"""FastAPI application setup."""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from src.core.llm_client import LLMClient
from src.validators.hotel_validator import HotelValidator
from src.validators.activities_validator import ActivitiesValidator
from src.validators.restaurant_validator import RestaurantValidator
from src.agents.hotel_agent import HotelAgent
from src.agents.activities_agent import ActivitiesAgent
from src.agents.restaurant_agent import RestaurantAgent
from src.cache.manager import CacheManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global agent instances
agents = {}
cache = None
llm_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    
    global agents, cache, llm_client
    
    # Startup
    logger.info("🚀 Starting Travel Recommendation Engine")
    
    # Initialize cache
    try:
        cache = CacheManager()
        logger.info("✓ Cache initialized")
    except Exception as e:
        logger.warning(f"⚠️  Cache failed: {e}")
        cache = None
    
    # Initialize LLM client
    try:
        llm_client = LLMClient()
        logger.info("✓ LLM client initialized")
    except Exception as e:
        logger.error(f"✗ LLM client failed: {e}")
        raise
    
    # Initialize agents
    try:
        agents = {
            "hotel": HotelAgent(
                llm_client,
                HotelValidator(),
                cache
            ),
            "activities": ActivitiesAgent(
                llm_client,
                ActivitiesValidator(),
                cache
            ),
            "restaurant": RestaurantAgent(
                llm_client,
                RestaurantValidator(),
                cache
            )
        }
        logger.info("✓ All agents initialized")
    except Exception as e:
        logger.error(f"✗ Agent initialization failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Travel Recommendation Engine")

# Create FastAPI app
app = FastAPI(
    title="Travel Recommendation Engine",
    description="Multi-agent AI travel recommendations",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint."""
    return {
        "service": "Travel Recommendation Engine",
        "status": "running",
        "version": "0.1.0"
    }

@app.get("/health", tags=["Health"])
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "agents": list(agents.keys()) if agents else [],
        "cache": "enabled" if cache else "disabled"
    }

@app.get("/metrics", tags=["Metrics"])
async def metrics():
    """Get system metrics."""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not available")
    
    return llm_client.get_metrics()

# ============================================================================
# HOTEL ENDPOINTS
# ============================================================================

from src.models.hotel import HotelSearch, HotelRecommendation

@app.post("/api/v1/hotels/search", response_model=list[HotelRecommendation], tags=["Hotels"])
async def search_hotels(request: HotelSearch):
    """
    Search for hotels.
    
    Example:
```json
    {
      "city": "Hanoi",
      "check_in_date": "2024-03-20",
      "check_out_date": "2024-03-23",
      "num_nights": 3,
      "budget_min": 3000,
      "budget_max": 8000,
      "star_rating_min": 4.0
    }
```
    """
    
    if "hotel" not in agents:
        raise HTTPException(status_code=503, detail="Hotel agent not available")
    
    try:
        recommendations = await agents["hotel"].process(request)
        return recommendations
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Hotel search error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ============================================================================
# ACTIVITIES ENDPOINTS
# ============================================================================

from src.models.activities import ActivitySearch, ActivityRecommendation

@app.post("/api/v1/activities/search", response_model=list[ActivityRecommendation], tags=["Activities"])
async def search_activities(request: ActivitySearch):
    """
    Search for activities.
    
    Example:
```json
    {
      "city": "Hanoi",
      "date": "2024-03-20",
      "interests": ["history", "culture", "food"],
      "max_duration": 480,
      "budget_per_activity": 100,
      "num_activities": 5,
      "difficulty_level": "moderate"
    }
```
    """
    
    if "activities" not in agents:
        raise HTTPException(status_code=503, detail="Activities agent not available")
    
    try:
        recommendations = await agents["activities"].process(request)
        return recommendations
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Activities search error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ============================================================================
# RESTAURANT ENDPOINTS
# ============================================================================

from src.models.restaurant import RestaurantSearch, RestaurantRecommendation

@app.post("/api/v1/restaurants/search", response_model=list[RestaurantRecommendation], tags=["Restaurants"])
async def search_restaurants(request: RestaurantSearch):
    """
    Search for restaurants.
    
    Example:
```json
    {
      "city": "Hanoi",
      "date": "2024-03-20",
      "meal_type": "dinner",
      "cuisine_preferences": ["vietnamese", "fusion"],
      "budget_min": 50,
      "budget_max": 300,
      "party_size": 2,
      "dietary_restrictions": []
    }
```
    """
    
    if "restaurant" not in agents:
        raise HTTPException(status_code=503, detail="Restaurant agent not available")
    
    try:
        recommendations = await agents["restaurant"].process(request)
        return recommendations
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Restaurant search error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# ============================================================================
# MULTI-AGENT ENDPOINTS
# ============================================================================

from pydantic import BaseModel

class TripPlanRequest(BaseModel):
    """Trip planning request."""
    city: str
    check_in_date: str
    check_out_date: str
    num_nights: int
    budget_total: float
    interests: list[str]
    dietary_restrictions: list[str] = []

class TripPlan(BaseModel):
    """Complete trip plan."""
    city: str
    duration: str
    hotels: list = []
    activities: list = []
    restaurants: list = []
    summary: str

@app.post("/api/v1/trips/plan", response_model=TripPlan, tags=["Trips"])
async def plan_trip(request: TripPlanRequest):
    """
    Plan complete trip with hotels, activities, and restaurants.
    
    Coordinates all three agents for a complete trip plan.
    """
    
    try:
        # Calculate per-night budget
        nightly_budget = request.budget_total / request.num_nights
        
        # Hotel search
        hotel_search = HotelSearch(
            city=request.city,
            check_in_date=request.check_in_date,
            check_out_date=request.check_out_date,
            num_nights=request.num_nights,
            budget_min=nightly_budget * 0.7,
            budget_max=nightly_budget * 1.3,
            star_rating_min=3.5
        )
        hotels = await agents["hotel"].process(hotel_search)
        
        # Activities search
        activity_search = ActivitySearch(
            city=request.city,
            date=request.check_in_date,
            interests=request.interests,
            max_duration=480,  # 8 hours per day
            budget_per_activity=50,
            num_activities=3,
            difficulty_level="moderate"
        )
        activities = await agents["activities"].process(activity_search)
        
        # Restaurant search
        restaurant_search = RestaurantSearch(
            city=request.city,
            date=request.check_in_date,
            meal_type="dinner",
            cuisine_preferences=["local"],
            budget_min=30,
            budget_max=150,
            party_size=1,
            dietary_restrictions=request.dietary_restrictions
        )
        restaurants = await agents["restaurant"].process(restaurant_search)
        
        # Generate summary
        summary = f"""
        {request.num_nights}-night trip to {request.city}
        
        Stay: {hotels[0].hotel.name if hotels else 'TBD'} (${hotels[0].hotel.price_per_night}/night)
        
        Activities: {', '.join([a.activity.name for a in activities[:3]])}
        
        Dining: {', '.join([r.restaurant.name for r in restaurants[:2]])}
        """
        
        return TripPlan(
            city=request.city,
            duration=f"{request.num_nights} nights",
            hotels=[h.dict() for h in hotels[:3]],
            activities=[a.dict() for a in activities[:3]],
            restaurants=[r.dict() for r in restaurants[:2]],
            summary=summary.strip()
        )
    
    except Exception as e:
        logger.error(f"Trip planning error: {e}")
        raise HTTPException(status_code=500, detail="Trip planning failed")

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@app.post("/admin/cache/clear", tags=["Admin"])
async def clear_cache():
    """Clear all cache."""
    if not cache:
        raise HTTPException(status_code=503, detail="Cache not available")
    
    try:
        await cache.clear_all()
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/metrics/reset", tags=["Admin"])
async def reset_metrics():
    """Reset LLM metrics."""
    if not llm_client:
        raise HTTPException(status_code=503, detail="LLM client not available")
    
    llm_client.reset_metrics()
    return {"status": "reset"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )
