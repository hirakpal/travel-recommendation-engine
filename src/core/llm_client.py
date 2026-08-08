"""
OpenAI LLM client with streaming, retries, error handling, and metrics.
"""

import asyncio
import logging
import os
from typing import AsyncGenerator, Optional

import openai
from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI client used by the travel recommendation application."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        self.client = OpenAI(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=0,
        )

        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=0,
        )

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
        use_cache: bool = False,
    ) -> str:
        """
        Send a request to OpenAI.

        Args:
            system_prompt: System instructions.
            user_message: User request.
            response_format: "text" or "json".
            stream: Whether to stream the response.
            temperature: Response creativity.
            max_tokens: Maximum output tokens.
            use_cache: Retained for compatibility; OpenAI prompt caching
                is not manually controlled here.
        """
        if stream:
            return await self._call_with_streaming(
                system_prompt=system_prompt,
                user_message=user_message,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return await self._call_standard(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _build_request_kwargs(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        request_kwargs = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format.lower() == "json":
            request_kwargs["response_format"] = {
                "type": "json_object"
            }

        return request_kwargs

    async def _call_standard(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Make a standard non-streaming request with retry logic."""

        request_kwargs = self._build_request_kwargs(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "OpenAI request attempt %s/%s",
                    attempt + 1,
                    self.max_retries,
                )

                response = self.client.chat.completions.create(
                    **request_kwargs
                )

                text = response.choices[0].message.content or ""

                self._update_metrics(response)

                logger.info("OpenAI request successful")
                return text

            except openai.RateLimitError as error:
                wait_time = 2**attempt
                logger.warning(
                    "OpenAI rate limit reached. Retrying in %s seconds.",
                    wait_time,
                )

                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        "OpenAI rate limit exceeded after retries"
                    ) from error

                await asyncio.sleep(wait_time)

            except openai.APIError as error:
                logger.error("OpenAI API error: %s", error)

                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"OpenAI request failed after "
                        f"{self.max_retries} attempts: {error}"
                    ) from error

                await asyncio.sleep(2**attempt)

            except Exception as error:
                logger.exception("Unexpected OpenAI error")

                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"Unexpected OpenAI error: {error}"
                    ) from error

                await asyncio.sleep(2**attempt)

        raise RuntimeError("OpenAI request failed")

    async def _call_with_streaming(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "text",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Make a streaming request using the synchronous OpenAI client."""

        request_kwargs = self._build_request_kwargs(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        full_response = ""

        try:
            stream = self.client.chat.completions.create(
                **request_kwargs,
                stream=True,
            )

            for chunk in stream:
                if not chunk.choices:
                    continue

                text = chunk.choices[0].delta.content or ""
                full_response += text
                print(text, end="", flush=True)

            print()
            self.total_calls += 1

            logger.info(
                "OpenAI streaming request successful (%s characters)",
                len(full_response),
            )

            return full_response

        except Exception as error:
            logger.exception("OpenAI streaming request failed")
            raise RuntimeError(
                f"OpenAI streaming request failed: {error}"
            ) from error

    async def call_streaming(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncGenerator[str, None]:
        """Yield response text chunks from an asynchronous OpenAI stream."""

        request_kwargs = self._build_request_kwargs(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format="text",
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            stream = await self.async_client.chat.completions.create(
                **request_kwargs,
                stream=True,
            )

            self.total_calls += 1

            async for chunk in stream:
                if not chunk.choices:
                    continue

                text = chunk.choices[0].delta.content or ""

                if text:
                    yield text

        except Exception as error:
            logger.exception("Async OpenAI streaming request failed")
            raise RuntimeError(
                f"Async OpenAI streaming request failed: {error}"
            ) from error

    def _update_metrics(self, response) -> None:
        """Update token usage and approximate cost metrics."""

        self.total_calls += 1

        if not response.usage:
            return

        input_tokens = response.usage.prompt_tokens or 0
        output_tokens = response.usage.completion_tokens or 0
        total_tokens = response.usage.total_tokens or 0

        self.total_tokens += total_tokens

        # Approximate GPT-4o-mini pricing.
        input_cost = input_tokens * 0.00015 / 1000
        output_cost = output_tokens * 0.0006 / 1000

        self.total_cost += input_cost + output_cost

        logger.debug(
            "Tokens: %s (input: %s, output: %s), cost: $%.6f",
            total_tokens,
            input_tokens,
            output_tokens,
            input_cost + output_cost,
        )

    def get_metrics(self) -> dict:
        """Return client usage metrics."""

        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost": f"${self.total_cost:.4f}",
            "cache_hits": self.cache_hits,
            "cache_hit_rate": (
                f"{(self.cache_hits / self.total_calls * 100):.1f}%"
                if self.total_calls > 0
                else "0%"
            ),
            "avg_tokens_per_call": (
                self.total_tokens // self.total_calls
                if self.total_calls > 0
                else 0
            ),
        }

    def reset_metrics(self) -> None:
        """Reset usage metrics."""

        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.cache_hits = 0
