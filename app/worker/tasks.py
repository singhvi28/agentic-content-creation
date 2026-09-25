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
from app.llm.litellm_client import LiteLLMClient
from app.llm.logging_client import LoggingLLMClient, current_job_id
from app.orchestrator.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
        password=parsed.password,
    )


def build_llm(
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    llm_critic_model: str | None = None,
):
    settings = get_settings()
    provider = (settings.llm_provider or "auto").lower().strip()

    if settings.use_fake_llm or provider == "fake" or (llm_model and llm_model.strip().lower() == "fake"):
        logger.warning("Using FakeLLMClient (no external LLM calls)")
        inner = FakeLLMClient()
        return LoggingLLMClient(
            inner, provider="fake", model="fake", critic_model="fake"
        )

    # User-supplied client-side key or model takes precedence via LiteLLM
    if llm_api_key or llm_model:
        model = llm_model or settings.litellm_model or "groq/llama-3.3-70b-versatile"
        critic_model = llm_critic_model or model
        api_key = llm_api_key or settings.litellm_api_key or settings.groq_api_key
        logger.info("Using LiteLLMClient model=%s with client-supplied/LiteLLM config", model)
        inner = LiteLLMClient(
            model=model,
            api_key=api_key,
            critic_model=critic_model,
        )
        return LoggingLLMClient(
            inner,
            provider="litellm",
            model=model,
            critic_model=critic_model,
        )

    if provider == "groq" or (provider == "auto" and settings.groq_api_key):
        model = settings.litellm_model or "groq/llama-3.3-70b-versatile"
        logger.info("Using LiteLLMClient (Groq) model=%s", model)
        inner = LiteLLMClient(
            model=model,
            api_key=settings.groq_api_key,
            critic_model=model,
        )
        return LoggingLLMClient(
            inner,
            provider="groq",
            model=model,
            critic_model=model,
        )

    if provider == "cursor" or (provider == "auto" and settings.cursor_api_key):
        logger.info("Using CursorLLMClient model=%s", settings.cursor_model)
        inner = CursorLLMClient()
        return LoggingLLMClient(
            inner,
            provider="cursor",
            model=settings.cursor_model,
            critic_model=settings.cursor_critic_model,
        )

    if provider == "gemini" or (provider == "auto" and settings.gemini_api_key):
        logger.info("Using GeminiClient model=%s", settings.gemini_model)
        inner = GeminiClient()
        return LoggingLLMClient(
            inner,
            provider="gemini",
            model=settings.gemini_model,
            critic_model=settings.gemini_critic_model,
        )

    raise RuntimeError(
        "No LLM configured. Set GROQ_API_KEY, CURSOR_API_KEY or GEMINI_API_KEY, "
        "or USE_FAKE_LLM=true / LLM_PROVIDER=fake."
    )


async def run_content_job(
    ctx: dict,
    job_id: str,
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    llm_critic_model: str | None = None,
) -> None:
    """Arq task entrypoint. Status is persisted to Postgres; clients poll GET."""
    jid = uuid.UUID(job_id)
    token = current_job_id.set(jid)

    async def on_status(
        job_uuid: uuid.UUID, status: JobStatus, payload: dict | None = None
    ) -> None:
        _ = (job_uuid, status, payload)

    try:
        async with AsyncSessionLocal() as session:
            effective_model = llm_model
            if effective_model is None:
                from app.db.models import Job
                db_job = await session.get(Job, jid)
                if db_job and db_job.llm_model:
                    effective_model = db_job.llm_model

            llm = build_llm(
                llm_model=effective_model,
                llm_api_key=llm_api_key,
                llm_critic_model=llm_critic_model,
            )

            try:
                await run_pipeline(session, jid, llm, on_status=on_status)
            except Exception:
                logger.exception("Job %s failed", job_id)
    finally:
        current_job_id.reset(token)


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
