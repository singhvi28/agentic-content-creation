"""Gemini LLM client. Swappable for tests via mock."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str: ...

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict: ...


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        critic_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.critic_model = critic_model or settings.gemini_critic_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def _call(self, model: str, prompt: str, temperature: float) -> str:
        from google.genai import errors as genai_errors

        client = self._get_client()
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"temperature": temperature},
                )
                return (getattr(response, "text", None) or "").strip()
            except genai_errors.ClientError as exc:
                last_exc = exc
                if getattr(exc, "status_code", None) == 429 and attempt < 3:
                    logger.warning(
                        "Gemini 429 on %s (attempt %s); sleeping %.1fs",
                        model,
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        return await self._call(self.model, prompt, temperature)

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict:
        text = await self._call(self.critic_model, prompt, temperature)
        return _parse_json(text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


class FakeLLMClient:
    """Deterministic stub for tests — never hits the network."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        self.calls.append(("generate", prompt[:80]))
        lower = prompt.lower()
        if "multi-platform campaign" in lower or "shared message plan" in lower:
            return (
                "1. Hook: ship faster with confidence\n"
                "2. Key points: CI gates, feedback loops, ownership\n"
                "3. Shared CTA: try one change this week\n"
                "4. Proof: fewer regressions, faster PRs"
            )
        if "numbered outline" in lower or (
            "content strategist" in lower and "no draft yet" in lower
        ):
            return "1. Hook\n2. Context\n3. Key points\n4. CTA"
        if "revising a draft" in lower or "editor feedback" in lower:
            return "Revised content: polished version addressing the feedback."
        if "adapting a shared campaign plan" in lower:
            return (
                "Campaign asset draft adapted from the shared plan. "
                "Clear hook and consistent CTA."
            )
        if "a/b hook variant" in lower or "invent a clearly different opening hook" in lower:
            m = re.search(r"variant\s+(\d+)\s+of\s+(\d+)", lower)
            idx = int(m.group(1)) if m else 1
            return (
                f"Hook variant {idx}: Distinct opening for A/B test. "
                "Draft content based on the brief. Clear, useful, and complete."
            )
        return "Draft content based on the brief. Clear, useful, and complete."

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict:
        self.calls.append(("generate_json", prompt[:80]))
        lower = prompt.lower()
        if "brand consistency editor" in lower or "multi-platform content pack" in lower:
            return {
                "consistency": 8,
                "hook_alignment": 8,
                "cta_alignment": 8,
                "notes": "Hook and CTA are aligned across surfaces; tighten Medium intro.",
            }
        return {
            "coherence": 8,
            "on_topic": 8,
            "notes": "Tighten the intro and strengthen the call to action.",
        }
