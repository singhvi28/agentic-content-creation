"""Cursor SDK LLM client — text-only agent runs via CURSOR_API_KEY."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import get_settings
from app.llm.gemini import _parse_json

logger = logging.getLogger(__name__)

_SYSTEM_PREAMBLE = (
    "You are a content-generation helper. Reply with ONLY the requested output. "
    "Do not explain yourself, do not use tools, and do not edit any files."
)


class CursorLLMClient:
    """One-shot Cursor agent runs with an empty tool allowlist (text only)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        critic_model: str | None = None,
        cwd: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.cursor_api_key
        self.model = model or settings.cursor_model
        self.critic_model = critic_model or settings.cursor_critic_model
        self.cwd = cwd or settings.cursor_cwd or str(Path.cwd())

    def _prompt_sync(self, prompt: str, *, model: str) -> str:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        if not self.api_key:
            raise RuntimeError("CURSOR_API_KEY is not set")

        wrapped = f"{_SYSTEM_PREAMBLE}\n\n{prompt}"
        result = Agent.prompt(
            wrapped,
            AgentOptions(
                api_key=self.api_key,
                model=model,
                tools=[],  # no built-in tools — text response only
                local=LocalAgentOptions(cwd=self.cwd),
            ),
        )
        if result.status == "error":
            raise RuntimeError(f"Cursor agent run failed (id={result.id})")
        if result.status == "cancelled":
            raise RuntimeError(f"Cursor agent run cancelled (id={result.id})")
        text = (result.result or "").strip()
        if not text:
            raise RuntimeError(f"Cursor agent returned empty result (id={result.id})")
        return text

    async def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        # temperature is unused by Cursor agents; kept for LLMClient protocol parity
        _ = temperature
        return await asyncio.to_thread(self._prompt_sync, prompt, model=self.model)

    async def generate_json(
        self, prompt: str, *, temperature: float = 0.2
    ) -> dict:
        _ = temperature
        text = await asyncio.to_thread(
            self._prompt_sync, prompt, model=self.critic_model
        )
        return _parse_json(text)
