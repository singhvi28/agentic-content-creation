"""Arq worker: runs the content pipeline asynchronously."""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlparse

from arq.connections import RedisSettings

from app.config import get_settings
from app.db.models import JobStatus
from app.db.session import AsyncSessionLocal
from app.llm.cursor import CursorLLMClient
from app.llm.gemini import FakeLLMClient, GeminiClient
from app.orchestrator.pipeline import run_pipeline
from app.services.events import hub

logger = logging.getLogger(__name__)


def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
        password=parsed.password,
    )


def build_llm():
    settings = get_settings()
    provider = (settings.llm_provider or "auto").lower().strip()

    if settings.use_fake_llm or provider == "fake":
        logger.warning("Using FakeLLMClient (no external LLM calls)")
        return FakeLLMClient()

    if provider == "cursor" or (provider == "auto" and settings.cursor_api_key):
        logger.info("Using CursorLLMClient model=%s", settings.cursor_model)
        return CursorLLMClient()

    if provider == "gemini" or (provider == "auto" and settings.gemini_api_key):
        logger.info("Using GeminiClient model=%s", settings.gemini_model)
        return GeminiClient()

    raise RuntimeError(
        "No LLM configured. Set CURSOR_API_KEY or GEMINI_API_KEY, "
        "or USE_FAKE_LLM=true / LLM_PROVIDER=fake."
    )


async def run_content_job(ctx: dict, job_id: str) -> None:
    """Arq task entrypoint."""
    jid = uuid.UUID(job_id)
    llm = build_llm()

    async def on_status(
        job_uuid: uuid.UUID, status: JobStatus, payload: dict | None = None
    ) -> None:
        event = {"job_id": str(job_uuid), "status": status.value}
        if payload:
            event["payload"] = payload
        await hub.publish(job_uuid, event)

    async with AsyncSessionLocal() as session:
        try:
            await run_pipeline(session, jid, llm, on_status=on_status)
        except Exception:
            logger.exception("Job %s failed", job_id)
            # pipeline already marks failed; swallow so Arq doesn't retry forever


async def on_startup(ctx: dict) -> None:
    logger.info("Arq worker started")


async def on_shutdown(ctx: dict) -> None:
    logger.info("Arq worker stopped")


class WorkerSettings:
    functions = [run_content_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings_from_url(get_settings().redis_url)
    max_jobs = 2  # Cursor agent runs are heavier than Gemini calls
    job_timeout = 3600  # campaigns run multiple LLM passes sequentially
