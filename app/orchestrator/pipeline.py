"""Cleaner Plan → Draft → Critique → Revise → Finalize state machine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bandit.thompson import Arm, ThompsonSamplingBandit
from app.config import get_settings
from app.db.models import ContentVersion, Job, JobStatus, JobType
from app.llm.gemini import LLMClient
from app.orchestrator.campaign import run_campaign_pipeline
from app.orchestrator.helpers import (
    StatusCallback,
    critique_and_maybe_revise,
    ensure_arm_row,
    load_bandit_params,
    noop_callback,
    set_status,
)
from app.orchestrator.prompts import (
    draft_prompt,
    draft_with_hook_variant_prompt,
    plan_prompt,
)
from app.services.bandit_service import apply_ab_choice

logger = logging.getLogger(__name__)


async def plan_and_draft(
    llm: LLMClient,
    brief: str,
    platform: str,
    arm: Arm,
    temperature: float,
) -> tuple[str, str]:
    plan = await llm.generate(
        plan_prompt(brief, platform, arm.prompt_style),
        temperature=temperature,
    )
    draft = await llm.generate(
        draft_prompt(brief, platform, arm.prompt_style, plan),
        temperature=temperature,
    )
    return plan, draft


async def _run_ab_phase_a(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    bandit: ThompsonSamplingBandit,
    on_status: StatusCallback,
) -> None:
    """Generate N hook variants and pause for user choice."""
    assert job.platform is not None and job.ab_variants is not None
    platform = job.platform.value
    n = job.ab_variants

    await set_status(
        session, job, JobStatus.drafting, on_status, {"ab_variants": n}
    )

    params = await load_bandit_params(session, platform)
    arms = bandit.select_arms_without_replacement(platform, params, n)
    logger.info(
        "A/B job %s arms=%s",
        job.id,
        [a.arm_id for a in arms],
    )

    for i, arm in enumerate(arms):
        action = arm.to_action()
        await ensure_arm_row(session, arm.arm_id)

        draft = await llm.generate(
            draft_with_hook_variant_prompt(
                job.brief, platform, arm.prompt_style, i, n
            ),
            temperature=float(action["temperature"]),
        )
        version = ContentVersion(
            job_id=job.id,
            platform=job.platform,
            round=0,
            variant_index=i,
            text=draft,
            bandit_action=action,
        )
        session.add(version)
        await session.commit()
        await session.refresh(version)
        await on_status(
            job.id,
            JobStatus.drafting,
            {
                "variant_index": i,
                "version_id": str(version.id),
                "text": draft,
                "arm": action,
            },
        )

    await set_status(
        session,
        job,
        JobStatus.awaiting_choice,
        on_status,
        {"ab_variants": n},
    )


async def _run_ab_phase_b(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    on_status: StatusCallback,
) -> None:
    """Resume after user chose a winner: bandit update + critique/revise."""
    settings = get_settings()
    assert job.platform is not None and job.chosen_version_id is not None

    await session.refresh(job, attribute_names=["versions"])

    winner = await session.get(ContentVersion, job.chosen_version_id)
    if winner is None or winner.job_id != job.id:
        raise ValueError("chosen_version_id is invalid for this job")
    if winner.variant_index is None:
        raise ValueError("chosen version is not an A/B variant")

    if job.ab_choice_applied_at is None:
        await apply_ab_choice(session, job, winner.id)
        job.ab_choice_applied_at = datetime.now(timezone.utc)
        await session.commit()

    action = winner.bandit_action or {}
    arm_id = action.get("arm_id")
    if not arm_id:
        arm = Arm("concise", job.platform.value)
        action = arm.to_action()

    style = action.get("prompt_style", "concise")
    arm = Arm(style, job.platform.value)
    await ensure_arm_row(session, arm.arm_id)

    max_rounds = int(
        action.get("max_revision_rounds", settings.max_revision_rounds)
    )
    final_version = await critique_and_maybe_revise(
        session,
        job,
        llm,
        arm,
        action,
        winner.text,
        winner,
        max_rounds,
        on_status,
        platform=job.platform.value,
    )

    job.final_content_id = final_version.id
    await set_status(
        session,
        job,
        JobStatus.done,
        on_status,
        {
            "final_content_id": str(final_version.id),
            "final_content": final_version.text,
        },
    )


async def _run_single_pipeline(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    bandit: ThompsonSamplingBandit,
    on_status: StatusCallback,
) -> None:
    settings = get_settings()
    if job.platform is None:
        raise ValueError("Single job requires platform")

    if job.chosen_version_id is not None:
        await _run_ab_phase_b(session, job, llm, on_status)
        return

    if job.status == JobStatus.awaiting_choice:
        logger.info("Job %s still awaiting_choice; skipping", job.id)
        return

    if job.ab_variants:
        await _run_ab_phase_a(session, job, llm, bandit, on_status)
        return

    platform = job.platform.value
    params = await load_bandit_params(session, platform)
    arm = bandit.select_arm(platform, params)
    action = arm.to_action()
    await ensure_arm_row(session, arm.arm_id)

    await set_status(
        session, job, JobStatus.planning, on_status, {"arm": action}
    )
    await set_status(session, job, JobStatus.drafting, on_status)

    _plan, draft = await plan_and_draft(
        llm,
        job.brief,
        platform,
        arm,
        temperature=float(action["temperature"]),
    )

    version = ContentVersion(
        job_id=job.id,
        platform=job.platform,
        round=0,
        text=draft,
        bandit_action=action,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    await on_status(
        job.id,
        JobStatus.drafting,
        {"version_id": str(version.id), "round": 0, "text": draft},
    )

    max_rounds = int(
        action.get("max_revision_rounds", settings.max_revision_rounds)
    )
    final_version = await critique_and_maybe_revise(
        session,
        job,
        llm,
        arm,
        action,
        draft,
        version,
        max_rounds,
        on_status,
        platform=platform,
    )

    job.final_content_id = final_version.id
    await set_status(
        session,
        job,
        JobStatus.done,
        on_status,
        {
            "final_content_id": str(final_version.id),
            "final_content": final_version.text,
        },
    )


async def run_pipeline(
    session: AsyncSession,
    job_id: uuid.UUID,
    llm: LLMClient,
    bandit: ThompsonSamplingBandit | None = None,
    on_status: StatusCallback | None = None,
) -> None:
    bandit = bandit or ThompsonSamplingBandit()
    on_status = on_status or noop_callback

    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if job.status == JobStatus.done:
        logger.info("Job %s already done; skipping", job_id)
        return

    try:
        if job.job_type == JobType.campaign:
            await run_campaign_pipeline(session, job, llm, bandit, on_status)
            return

        await _run_single_pipeline(session, job, llm, bandit, on_status)
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        job.status = JobStatus.failed
        job.error_message = str(exc)[:2000]
        await session.commit()
        await on_status(job.id, JobStatus.failed, {"error": str(exc)})
        raise
