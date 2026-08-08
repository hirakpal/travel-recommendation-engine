"""Streaming responses for real-time token delivery."""

from typing import AsyncGenerator
import asyncio

class StreamingManager:
    """Manages streamed responses."""
    
    def __init__(self, buffer_size: int = 10):
        self.buffer_size = buffer_size
        self.first_token_time = None
    
    async def stream_response(
        self,
        llm_call: callable
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens as they arrive from LLM.
        
        Tracks first-token time for latency metrics.
        """
        
        import time
        start_time = time.time()
        first_token = True
        
        async for token in llm_call():
            if first_token:
                self.first_token_time = time.time() - start_time
                first_token = False
            
            yield token
    
    def get_first_token_latency(self) -> float:
        """Get time to first token in seconds."""
        return self.first_token_time or 0
