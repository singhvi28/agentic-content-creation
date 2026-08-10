"""Cleaner Plan → Draft → Critique → Revise → Finalize state machine."""

from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bandit.thompson import Arm, ArmParams, ThompsonSamplingBandit
from app.config import get_settings
from app.db.models import BanditState, ContentVersion, Job, JobStatus
from app.llm.gemini import LLMClient
from app.orchestrator.evaluator import critique_draft
from app.orchestrator.prompts import draft_prompt, plan_prompt, revise_prompt

logger = logging.getLogger(__name__)

StatusCallback = Callable[[uuid.UUID, JobStatus, dict | None], Awaitable[None]]


async def _noop_callback(
    job_id: uuid.UUID, status: JobStatus, payload: dict | None = None
) -> None:
    return None


async def _set_status(
    session: AsyncSession,
    job: Job,
    status: JobStatus,
    on_status: StatusCallback,
    payload: dict | None = None,
) -> None:
    job.status = status
    await session.commit()
    await on_status(job.id, status, payload)


async def _load_bandit_params(
    session: AsyncSession, platform: str
) -> list[ArmParams]:
    bandit = ThompsonSamplingBandit()
    arm_ids = [a.arm_id for a in bandit.all_arms_for_context(platform)]
    result = await session.execute(
        select(BanditState).where(BanditState.arm_id.in_(arm_ids))
    )
    rows = result.scalars().all()
    return [ArmParams(r.arm_id, r.alpha, r.beta) for r in rows]


async def _ensure_arm_row(session: AsyncSession, arm_id: str) -> BanditState:
    row = await session.get(BanditState, arm_id)
    if row is None:
        row = BanditState(arm_id=arm_id, alpha=1.0, beta=1.0)
        session.add(row)
        await session.flush()
    return row


async def _soft_update_bandit(
    session: AsyncSession,
    arm_id: str,
    critic_score: float,
) -> None:
    settings = get_settings()
    row = await _ensure_arm_row(session, arm_id)
    row.alpha, row.beta = ThompsonSamplingBandit.update_from_critic(
        row.alpha,
        row.beta,
        critic_score,
        weight=settings.critic_reward_weight,
        threshold=settings.critic_score_threshold,
    )
    await session.flush()


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


async def _critique_and_maybe_revise(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    arm: Arm,
    action: dict,
    draft: str,
    version: ContentVersion,
    max_rounds: int,
    on_status: StatusCallback,
) -> ContentVersion:
    settings = get_settings()
    platform = job.platform.value
    current_draft = draft
    current_version = version

    for rev_round in range(1, max_rounds + 1):
        await _set_status(session, job, JobStatus.critiquing, on_status)
        critique = await critique_draft(llm, job.brief, platform, current_draft)

        current_version.critic_score = critique.critic_score
        current_version.critic_notes = critique.critic_notes
        await _soft_update_bandit(session, arm.arm_id, critique.critic_score)
        await session.commit()
        await on_status(
            job.id,
            JobStatus.critiquing,
            {
                "round": current_version.round,
                "critic_score": critique.critic_score,
                "critic_notes": critique.critic_notes,
            },
        )

        if critique.critic_score >= settings.critic_score_threshold:
            return current_version

        await _set_status(session, job, JobStatus.revising, on_status)
        current_draft = await llm.generate(
            revise_prompt(
                job.brief, current_draft, critique.critic_notes, platform=platform
            ),
            temperature=float(action["temperature"]),
        )
        current_version = ContentVersion(
            job_id=job.id,
            round=rev_round,
            text=current_draft,
            bandit_action=action,
        )
        session.add(current_version)
        await session.commit()
        await session.refresh(current_version)
        await on_status(
            job.id,
            JobStatus.revising,
            {
                "version_id": str(current_version.id),
                "round": rev_round,
                "text": current_draft,
            },
        )

    if current_version.critic_score is None:
        await _set_status(session, job, JobStatus.critiquing, on_status)
        critique = await critique_draft(llm, job.brief, platform, current_draft)
        current_version.critic_score = critique.critic_score
        current_version.critic_notes = critique.critic_notes
        await _soft_update_bandit(session, arm.arm_id, critique.critic_score)
        await session.commit()

    return current_version


async def run_pipeline(
    session: AsyncSession,
    job_id: uuid.UUID,
    llm: LLMClient,
    bandit: ThompsonSamplingBandit | None = None,
    on_status: StatusCallback | None = None,
) -> None:
    settings = get_settings()
    bandit = bandit or ThompsonSamplingBandit()
    on_status = on_status or _noop_callback

    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    try:
        platform = job.platform.value
        params = await _load_bandit_params(session, platform)
        arm = bandit.select_arm(platform, params)
        action = arm.to_action()
        await _ensure_arm_row(session, arm.arm_id)

        await _set_status(
            session, job, JobStatus.planning, on_status, {"arm": action}
        )
        await _set_status(session, job, JobStatus.drafting, on_status)

        _plan, draft = await plan_and_draft(
            llm,
            job.brief,
            platform,
            arm,
            temperature=float(action["temperature"]),
        )

        version = ContentVersion(
            job_id=job.id,
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
        final_version = await _critique_and_maybe_revise(
            session,
            job,
            llm,
            arm,
            action,
            draft,
            version,
            max_rounds,
            on_status,
        )

        job.final_content_id = final_version.id
        await _set_status(
            session,
            job,
            JobStatus.done,
            on_status,
            {
                "final_content_id": str(final_version.id),
                "final_content": final_version.text,
            },
        )
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        job.status = JobStatus.failed
        job.error_message = str(exc)[:2000]
        await session.commit()
        await on_status(job.id, JobStatus.failed, {"error": str(exc)})
        raise
