"""
Claude LLM Client with streaming, caching, and error handling.

Features:
- Token streaming for real-time responses
- Prompt caching for cost savings
- Automatic retry with exponential backoff
- Rate limiting integration
- Error recovery
"""

import os
import json
import asyncio
from typing import Optional, AsyncGenerator
from datetime import datetime
import anthropic
from anthropic import Anthropic, AsyncAnthropic
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Claude LLM Client with production-ready features.
    
    Usage:
        client = LLMClient()
        response = await client.call(
            system_prompt="You are helpful",
            user_message="What is AI?",
            stream=True
        )
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4-6",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize LLM Client.
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model to use (default: claude-opus-4-6)
            timeout: Request timeout in seconds
            max_retries: Max retry attempts
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Initialize clients
        self.client = Anthropic(api_key=self.api_key, timeout=timeout)
        self.async_client = AsyncAnthropic(api_key=self.api_key, timeout=timeout)
        
        # Metrics
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.cache_hits = 0
    
    async def call(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = True
    ) -> str:
        """
        Call Claude API.
        
        Args:
            system_prompt: System instructions for Claude
            user_message: User query
            response_format: "text" or "json"
            stream: If True, stream response token-by-token
            temperature: Creativity level (0-1)
            max_tokens: Maximum response length
            use_cache: Enable prompt caching for cost savings
        
        Returns:
            Claude's response
        
        Raises:
            RuntimeError: If all retries failed
        """
        
        if stream:
            return await self._call_with_streaming(
                system_prompt=system_prompt,
                user_message=user_message,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )
        else:
            return await self._call_standard(
                system_prompt=system_prompt,
                user_message=user_message,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )
    
    async def _call_standard(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = True
    ) -> str:
        """Standard API call with retry logic."""
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"LLM Call (attempt {attempt + 1}/{self.max_retries})")
                
                # Build request
                messages = [{"role": "user", "content": user_message}]
                
                # System prompt with cache control
                system = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"} if use_cache else None
                    }
                ]
                
                # Remove None cache_control
                system = [s for s in system if s["cache_control"] is not None]
                
                # Make request
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system if system else system_prompt,
                    messages=messages,
                    temperature=temperature
                )
                
                # Extract response
                text = response.content[0].text
                
                # Track metrics
                self._update_metrics(response, use_cache)
                
                logger.info(f"✓ LLM call successful")
                return text
            
            except anthropic.RateLimitError as e:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
                continue
            
            except anthropic.APIError as e:
                logger.error(f"API Error: {e}")
                if attempt == self.max_retries - 1:
                    raise RuntimeError(f"LLM call failed after {self.max_retries} attempts: {e}")
                await asyncio.sleep(2 ** attempt)
                continue
        
        raise RuntimeError("LLM call failed: max retries exceeded")
    
    async def _call_with_streaming(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        use_cache: bool = True
    ) -> str:
        """Streaming API call with async iteration."""
        
        messages = [{"role": "user", "content": user_message}]
        
        system = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"} if use_cache else None
            }
        ]
        system = [s for s in system if s["cache_control"] is not None]
        
        full_response = ""
        
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system if system else system_prompt,
                messages=messages,
                temperature=temperature
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    # Note: In real streaming, yield would be used in AsyncGenerator
                    print(text, end="", flush=True)
            
            print()  # Newline after streaming
            logger.info(f"✓ Streaming call successful ({len(full_response)} chars)")
            return full_response
        
        except Exception as e:
            logger.error(f"Streaming call error: {e}")
            raise
    
    async def call_streaming(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[str, None]:
        """
        Streaming response as AsyncGenerator.
        
        Yields tokens as they arrive from Claude.
        
        Usage:
            async for token in client.call_streaming(...):
                print(token, end="", flush=True)
        """
        
        messages = [{"role": "user", "content": user_message}]
        
        try:
            with self.async_client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                temperature=temperature
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise
    
    def _update_metrics(self, response, used_cache: bool = False):
        """Update usage metrics."""
        self.total_calls += 1
        
        # Count tokens
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        total_tokens = input_tokens + output_tokens
        
        self.total_tokens += total_tokens
        
        # Estimate cost (Opus pricing)
        # Input: $0.015/1K tokens, Output: $0.045/1K tokens
        # With cache: Input hits are 80% cheaper
        input_cost = input_tokens * (0.003 if used_cache else 0.015) / 1000
        output_cost = output_tokens * 0.045 / 1000
        cost = input_cost + output_cost
        
        self.total_cost += cost
        
        # Log metrics
        logger.debug(
            f"Tokens: {total_tokens} (in: {input_tokens}, out: {output_tokens}) | "
            f"Cost: ${cost:.4f} | Total cost: ${self.total_cost:.2f}"
        )
        
        if used_cache:
            self.cache_hits += 1
    
    def get_metrics(self) -> dict:
        """Get performance metrics."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost": f"${self.total_cost:.2f}",
            "cache_hits": self.cache_hits,
            "cache_hit_rate": f"{(self.cache_hits / self.total_calls * 100):.1f}%" if self.total_calls > 0 else "0%",
            "avg_tokens_per_call": self.total_tokens // self.total_calls if self.total_calls > 0 else 0
        }
    
    def reset_metrics(self):
        """Reset metrics counters."""
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.cache_hits = 0
