import pytest
import json
from datetime import date, timedelta

@pytest.fixture
def sample_hotel_search():
    """Sample hotel search"""
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
def sample_activity_search():
    """Sample activity search"""
    from src.models.activities import ActivitySearch
    return ActivitySearch(
        city="Hanoi",
        date="2024-03-20",
        interests=["history", "culture", "food"],
        max_duration=480,
        budget_per_activity=100,
        num_activities=5
    )

@pytest.fixture
def llm_client_mock(mocker):
    """Mock LLM client"""
    mock = mocker.AsyncMock()
    mock.call = mocker.AsyncMock(return_value='{"score": 0.9, "reasoning": "Great match"}')
    return mock
