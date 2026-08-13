"""LLM usage logging wrapper."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from app.db.models import LlmUsage
from app.db.session import AsyncSessionLocal
from app.llm.gemini import LLMClient

logger = logging.getLogger(__name__)

current_job_id: ContextVar[UUID | None] = ContextVar("current_job_id", default=None)


def estimate_tokens(prompt: str, completion: str) -> int:
    return max(1, (len(prompt) + len(completion) + 3) // 4)


class LoggingLLMClient:
    """Wraps any LLMClient and persists approximate token usage rows."""

    def __init__(
        self,
        inner: LLMClient,
        *,
        provider: str,
        model: str,
        critic_model: str | None = None,
    ) -> None:
        self.inner = inner
        self.provider = provider
        self.model = model
        self.critic_model = critic_model or model

    async def _record(
        self,
        *,
        operation: str,
        model: str,
        prompt: str,
        completion: str,
    ) -> None:
        job_id = current_job_id.get()
        row = LlmUsage(
            job_id=job_id,
            provider=self.provider,
            model=model,
            operation=operation,
            prompt_chars=len(prompt),
            completion_chars=len(completion),
            estimated_tokens=estimate_tokens(prompt, completion),
        )
        try:
            async with AsyncSessionLocal() as session:
                session.add(row)
                await session.commit()
        except Exception:
            logger.exception("Failed to record llm_usage")

    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        text = await self.inner.generate(prompt, temperature=temperature)
        await self._record(
            operation="generate",
            model=self.model,
            prompt=prompt,
            completion=text,
        )
        return text

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict[str, Any]:
        data = await self.inner.generate_json(prompt, temperature=temperature)
        # Approximate completion size from JSON string length
        completion = str(data)
        await self._record(
            operation="generate_json",
            model=self.critic_model,
            prompt=prompt,
            completion=completion,
        )
        return data
