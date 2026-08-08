"""Hotel agent tests."""

import pytest
from src.agents.hotel_agent import HotelAgent
from src.models.hotel import HotelSearch, Hotel
from src.validators.hotel_validator import HotelValidator

class TestHotelAgent:
    """Hotel agent test suite."""
    
    @pytest.mark.asyncio
    async def test_valid_search(self, mock_llm_client, mock_cache, sample_hotel_search):
        """Test hotel search with valid request."""
        agent = HotelAgent(mock_llm_client, HotelValidator(), mock_cache)
        
        # Process
        result = await agent.process(sample_hotel_search)
        
        # Verify
        assert isinstance(result, list)
    
    @pytest.mark.asyncio
    async def test_invalid_budget(self, mock_llm_client, sample_hotel_search):
        """Test rejection of invalid budget."""
        sample_hotel_search.budget_min = 1000000
        agent = HotelAgent(mock_llm_client, HotelValidator())
        
        # Should raise
        with pytest.raises(ValueError):
            await agent.process(sample_hotel_search)
    
    @pytest.mark.asyncio
    async def test_invalid_dates(self, mock_llm_client, sample_hotel_search):
        """Test rejection of invalid dates."""
        sample_hotel_search.check_in_date = "2024-03-23"
        sample_hotel_search.check_out_date = "2024-03-20"
        agent = HotelAgent(mock_llm_client, HotelValidator())
        
        with pytest.raises(ValueError):
            await agent.process(sample_hotel_search)
    
    def test_cache_key_generation(self, sample_hotel_search):
        """Test cache key generation."""
        agent = HotelAgent(None, HotelValidator())
        key = agent._make_cache_key(sample_hotel_search)
        
        assert "hotels:" in key
        assert "hanoi" in key.lower()
        assert "2024-03-20" in key
    
    @pytest.mark.asyncio
    async def test_hotel_filtering(self, mock_llm_client, sample_hotel_search):
        """Test hotel filtering logic."""
        agent = HotelAgent(mock_llm_client, HotelValidator())
        
        # Mock database
        agent.hotels_db = {
            "hanoi": [
                {
                    "id": "h1",
                    "name": "Expensive",
                    "city": "Hanoi",
                    "star_rating": 4.5,
                    "price_per_night": 10000,  # Too expensive
                    "currency": "VND",
                    "amenities": ["WiFi"],
                    "address": "St",
                    "rating_score": 4.5,
                    "rating_count": 100,
                    "description": "Test",
                    "is_available": True
                },
                {
                    "id": "h2",
                    "name": "Good",
                    "city": "Hanoi",
                    "star_rating": 4.5,
                    "price_per_night": 5500,  # Within budget
                    "currency": "VND",
                    "amenities": ["WiFi", "Gym"],
                    "address": "St",
                    "rating_score": 4.5,
                    "rating_count": 100,
                    "description": "Test",
                    "is_available": True
                }
            ]
        }
        
        # Filter
        filtered = agent._filter_hotels(sample_hotel_search)
        
        # Should only get the good one
        assert len(filtered) == 1
        assert filtered[0].id == "h2"
