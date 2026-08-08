"""Pytest fixtures and configuration."""

import pytest
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

# ============================================================================
# HOTEL FIXTURES
# ============================================================================

@pytest.fixture
def sample_hotel_search():
    """Sample hotel search request."""
    from src.models.hotel import HotelSearch
    return HotelSearch(
        city="Hanoi",
        check_in_date="2024-03-20",
        check_out_date="2024-03-23",
        num_nights=3,
        budget_min=3000,
        budget_max=8000,
        star_rating_min=4.0,
        required_amenities=["WiFi", "Gym"]
    )

@pytest.fixture
def sample_hotel_data():
    """Sample hotel data."""
    return {
        "id": "hanoi_001",
        "name": "Test Hotel",
        "city": "Hanoi",
        "star_rating": 4.5,
        "price_per_night": 5500,
        "currency": "VND",
        "amenities": ["WiFi", "Gym", "Restaurant"],
        "address": "Test St",
        "rating_score": 4.6,
        "rating_count": 100,
        "description": "Test hotel",
        "is_available": True,
        "booking_url": "https://example.com"
    }

# ============================================================================
# ACTIVITIES FIXTURES
# ============================================================================

@pytest.fixture
def sample_activity_search():
    """Sample activity search request."""
    from src.models.activities import ActivitySearch
    return ActivitySearch(
        city="Hanoi",
        date="2024-03-20",
        interests=["history", "culture", "food"],
        max_duration=480,
        budget_per_activity=100,
        num_activities=5,
        difficulty_level="moderate"
    )

@pytest.fixture
def sample_activity_data():
    """Sample activity data."""
    return {
        "id": "hanoi_act_001",
        "name": "Temple Tour",
        "city": "Hanoi",
        "category": "cultural",
        "duration_minutes": 60,
        "cost": 50000,
        "currency": "VND",
        "difficulty": "easy",
        "rating_score": 4.7,
        "description": "Visit ancient temples",
        "best_time": "morning",
        "requires_booking": False
    }

# ============================================================================
# RESTAURANT FIXTURES
# ============================================================================

@pytest.fixture
def sample_restaurant_search():
    """Sample restaurant search request."""
    from src.models.restaurant import RestaurantSearch
    return RestaurantSearch(
        city="Hanoi",
        date="2024-03-20",
        meal_type="dinner",
        cuisine_preferences=["vietnamese"],
        budget_min=50,
        budget_max=300,
        party_size=2,
        dietary_restrictions=[]
    )

@pytest.fixture
def sample_restaurant_data():
    """Sample restaurant data."""
    return {
        "id": "hanoi_rest_001",
        "name": "Test Restaurant",
        "city": "Hanoi",
        "cuisine_type": "vietnamese",
        "price_level": 2,
        "rating_score": 4.6,
        "rating_count": 100,
        "address": "Test St",
        "specialty_dishes": ["Pho", "Spring Rolls"],
        "vegetarian_options": True,
        "vegan_options": True,
        "description": "Test restaurant",
        "booking_url": "https://example.com"
    }

# ============================================================================
# MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    mock = AsyncMock()
    mock.call = AsyncMock(
        return_value=json.dumps([
            {"score": 0.9, "reasoning": "Great match"},
            {"score": 0.8, "reasoning": "Good option"}
        ])
    )
    mock.get_metrics = MagicMock(return_value={
        "total_calls": 1,
        "total_tokens": 1000,
        "total_cost": "$0.50"
    })
    return mock

@pytest.fixture
def mock_cache():
    """Mock cache."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    return mock
