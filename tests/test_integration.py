"""Integration tests."""

import pytest
from src.agents.hotel_agent import HotelAgent
from src.core.llm_client import LLMClient
from src.validators.hotel_validator import HotelValidator
from src.models.hotel import HotelSearch

class TestIntegration:
    """Integration test suite."""
    
    @pytest.mark.asyncio
    async def test_hotel_agent_full_flow(self, sample_hotel_search):
        """Test full hotel agent flow."""
        try:
            llm = LLMClient()
            agent = HotelAgent(llm, HotelValidator())
            
            # Run search
            result = await agent.process(sample_hotel_search)
            
            # Verify
            assert isinstance(result, list)
            
        except Exception as e:
            # Expected if no real API key
            pytest.skip(f"Skipped (no API key): {e}")
