"""LiteLLM client — supports arbitrary cloud and local providers via LiteLLM."""

from __future__ import annotations

import logging
from typing import Any

from app.llm.gemini import _parse_json

logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Multi-provider client using LiteLLM.

    Supports OpenAI, Anthropic, Groq, Mistral, Ollama, etc.
    Model format examples: 'groq/llama-3.3-70b-versatile', 'openai/gpt-4o-mini'
    """

    def __init__(
        self,
        model: str = "groq/llama-3.3-70b-versatile",
        api_key: str | None = None,
        critic_model: str | None = None,
        *,
        api_base: str | None = None,
    ) -> None:
        self.model = model
        self.critic_model = critic_model or model
        self.api_key = api_key
        self.api_base = api_base

    async def _call(self, model: str, prompt: str, temperature: float) -> str:
        import asyncio
        import litellm

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        delay = 1.5
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                resp = await litellm.acompletion(**kwargs)
                return (resp.choices[0].message.content or "").strip()
            except litellm.exceptions.RateLimitError as exc:
                last_exc = exc
                if attempt < 4:
                    logger.warning("LiteLLM 429 on %s (attempt %d); sleeping %.1fs", model, attempt + 1, delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise
            except Exception as exc:
                raise exc
        assert last_exc is not None
        raise last_exc

    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        return await self._call(self.model, prompt, temperature)

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict:
        text = await self._call(self.critic_model, prompt, temperature)
        return _parse_json(text)
