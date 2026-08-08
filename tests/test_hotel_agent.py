import pytest
from src.agents.hotel_agent import HotelAgent
from src.models.hotel import HotelSearch

@pytest.mark.asyncio
async def test_hotel_agent_valid_search(sample_hotel_search, llm_client_mock):
    """Test hotel agent with valid search"""
    from src.validators.hotel_validator import HotelValidator
    
    agent = HotelAgent(llm_client_mock, HotelValidator())
    
    # Test
    recommendations = await agent.process(sample_hotel_search)
    
    # Assertions
    assert len(recommendations) > 0
    assert all(0 <= rec.match_score <= 1 for rec in recommendations)
    assert recommendations[0].match_score >= recommendations[-1].match_score

@pytest.mark.asyncio
async def test_hotel_agent_invalid_budget(sample_hotel_search, llm_client_mock):
    """Test hotel agent rejects invalid budget"""
    from src.validators.hotel_validator import HotelValidator
    
    agent = HotelAgent(llm_client_mock, HotelValidator())
    sample_hotel_search.budget_min = 1000000  # Unrealistic
    
    # Test
    with pytest.raises(ValueError):
        await agent.process(sample_hotel_search)
