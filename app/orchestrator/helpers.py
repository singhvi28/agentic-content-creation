"""Shared orchestrator helpers used by single and campaign pipelines."""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bandit.thompson import Arm, ArmParams, ThompsonSamplingBandit
from app.config import get_settings
from app.db.models import BanditState, ContentVersion, Job, JobStatus, Platform
from app.llm.gemini import LLMClient
from app.orchestrator.evaluator import critique_draft
from app.orchestrator.prompts import revise_prompt

StatusCallback = Callable[[uuid.UUID, JobStatus, dict | None], Awaitable[None]]


async def noop_callback(
    job_id: uuid.UUID, status: JobStatus, payload: dict | None = None
) -> None:
    return None


async def set_status(
    session: AsyncSession,
    job: Job,
    status: JobStatus,
    on_status: StatusCallback,
    payload: dict | None = None,
) -> None:
    job.status = status
    await session.commit()
    await on_status(job.id, status, payload)


async def load_bandit_params(
    session: AsyncSession, platform: str
) -> list[ArmParams]:
    bandit = ThompsonSamplingBandit()
    arm_ids = [a.arm_id for a in bandit.all_arms_for_context(platform)]
    result = await session.execute(
        select(BanditState).where(BanditState.arm_id.in_(arm_ids))
    )
    rows = result.scalars().all()
    return [ArmParams(r.arm_id, r.alpha, r.beta) for r in rows]


async def ensure_arm_row(session: AsyncSession, arm_id: str) -> BanditState:
    row = await session.get(BanditState, arm_id)
    if row is None:
        row = BanditState(arm_id=arm_id, alpha=1.0, beta=1.0)
        session.add(row)
        await session.flush()
    return row


async def soft_update_bandit(
    session: AsyncSession,
    arm_id: str,
    critic_score: float,
    weight: float | None = None,
) -> None:
    settings = get_settings()
    row = await ensure_arm_row(session, arm_id)
    alpha, beta = ThompsonSamplingBandit.apply_decay(
        row.alpha, row.beta, settings.bandit_decay
    )
    row.alpha, row.beta = ThompsonSamplingBandit.update_from_critic(
        alpha,
        beta,
        critic_score,
        weight=settings.critic_reward_weight if weight is None else weight,
        threshold=settings.critic_score_threshold,
    )
    await session.flush()


async def critique_and_maybe_revise(
    session: AsyncSession,
    job: Job,
    llm: LLMClient,
    arm: Arm,
    action: dict,
    draft: str,
    version: ContentVersion,
    max_rounds: int,
    on_status: StatusCallback,
    platform: str | None = None,
) -> ContentVersion:
    """Critique/revise loop; applies one soft bandit update on the final version."""
    settings = get_settings()
    plat = platform or (job.platform.value if job.platform else None)
    if not plat:
        raise ValueError("platform required for critique loop")
    current_draft = draft
    current_version = version

    for rev_round in range(1, max_rounds + 1):
        await set_status(session, job, JobStatus.critiquing, on_status)
        critique = await critique_draft(llm, job.brief, plat, current_draft)

        current_version.critic_score = critique.critic_score
        current_version.critic_notes = critique.critic_notes
        await session.commit()
        await on_status(
            job.id,
            JobStatus.critiquing,
            {
                "platform": plat,
                "round": current_version.round,
                "critic_score": critique.critic_score,
                "critic_notes": critique.critic_notes,
            },
        )

        if (
            critique.critic_score >= settings.critic_score_threshold
            and critique.length_score >= 8.0
        ):
            await soft_update_bandit(session, arm.arm_id, critique.critic_score)
            await session.commit()
            return current_version

        length_note = ""
        if critique.length_score < 8.0:
            length_note = (
                " Also shorten to fit the platform length cap "
                f"(length_score={critique.length_score})."
            )
        await set_status(session, job, JobStatus.revising, on_status)
        current_draft = await llm.generate(
            revise_prompt(
                job.brief,
                current_draft,
                critique.critic_notes + length_note,
                platform=plat,
            ),
            temperature=float(action["temperature"]),
        )
        current_version = ContentVersion(
            job_id=job.id,
            platform=Platform(plat),
            round=rev_round,
            text=current_draft,
            bandit_action=action,
            variant_index=None,
        )
        session.add(current_version)
        await session.commit()
        await session.refresh(current_version)
        await on_status(
            job.id,
            JobStatus.revising,
            {
                "platform": plat,
                "version_id": str(current_version.id),
                "round": rev_round,
                "text": current_draft,
            },
        )

    if current_version.critic_score is None:
        await set_status(session, job, JobStatus.critiquing, on_status)
        critique = await critique_draft(llm, job.brief, plat, current_draft)
        current_version.critic_score = critique.critic_score
        current_version.critic_notes = critique.critic_notes
        await session.commit()

    if current_version.critic_score is not None:
        await soft_update_bandit(
            session, arm.arm_id, current_version.critic_score
        )
        await session.commit()

    return current_version