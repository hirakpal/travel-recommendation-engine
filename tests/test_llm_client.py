"""LLM client tests."""

import pytest
import os
from unittest.mock import patch, MagicMock
from src.core.llm_client import LLMClient

class TestLLMClient:
    """LLM client tests."""
    
    def test_initialization(self):
        """Test LLM client initialization."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()
            assert client.api_key == "test-key"
            assert client.model == "claude-opus-4-6"
    
    def test_missing_api_key(self):
        """Test error when API key missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                LLMClient()
    
    def test_cache_key_calculation(self):
        """Test cache key generation."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()
            client.total_calls = 5
            client.total_tokens = 1000
            
            metrics = client.get_metrics()
            assert metrics["total_calls"] == 5
            assert metrics["total_tokens"] == 1000
