"""Bandit persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bandit.thompson import PROMPT_STYLES, Arm, ThompsonSamplingBandit, expected_value
from app.db.models import (
    BanditState,
    ContentVersion,
    Feedback,
    FeedbackScope,
    Job,
    Platform,
)
from app.schemas import ArmStats


async def seed_bandit_arms(session: AsyncSession) -> None:
    """Ensure all (prompt_style, platform) arms exist with Beta(1,1)."""
    expected_ids = {
        Arm(style, platform.value).arm_id
        for platform in Platform
        for style in PROMPT_STYLES
    }
    for arm_id in expected_ids:
        existing = await session.get(BanditState, arm_id)
        if existing is None:
            session.add(BanditState(arm_id=arm_id, alpha=1.0, beta=1.0))

    result = await session.execute(select(BanditState))
    for row in result.scalars().all():
        if row.arm_id not in expected_ids:
            await session.delete(row)
    await session.commit()


async def _bump_arm(session: AsyncSession, arm_id: str, rating: int) -> None:
    row = await session.get(BanditState, arm_id)
    if row is None:
        row = BanditState(arm_id=arm_id, alpha=1.0, beta=1.0)
        session.add(row)
        await session.flush()
    row.alpha, row.beta = ThompsonSamplingBandit.update_from_rating(
        row.alpha, row.beta, rating
    )


async def apply_feedback_to_bandit(
    session: AsyncSession,
    content_version_id,
    rating: int,
) -> None:
    version = await session.get(ContentVersion, content_version_id)
    if version is None:
        raise ValueError("content_version not found")
    action = version.bandit_action or {}
    arm_id = action.get("arm_id")
    if not arm_id:
        return
    await _bump_arm(session, arm_id, rating)


async def apply_ab_choice(
    session: AsyncSession,
    job: Job,
    winner_version_id,
) -> None:
    """Pairwise bandit update: winner success, other variant arms failure."""
    variants = [v for v in job.versions if v.variant_index is not None]
    if not variants:
        return

    winner = next((v for v in variants if v.id == winner_version_id), None)
    if winner is None:
        raise ValueError("winner is not an A/B variant on this job")

    winner_arm = (winner.bandit_action or {}).get("arm_id")
    loser_arms: set[str] = set()
    for v in variants:
        if v.id == winner_version_id:
            continue
        arm_id = (v.bandit_action or {}).get("arm_id")
        if arm_id and arm_id != winner_arm:
            loser_arms.add(arm_id)

    if winner_arm:
        await _bump_arm(session, winner_arm, 5)
    for arm_id in loser_arms:
        await _bump_arm(session, arm_id, 1)


async def apply_pack_feedback_to_bandit(
    session: AsyncSession,
    job: Job,
    rating: int,
) -> None:
    """Update every arm used by the latest asset per platform."""
    arm_ids: set[str] = set()
    # Latest version per platform
    by_platform: dict[str, ContentVersion] = {}
    for v in sorted(job.versions, key=lambda x: (x.round, str(x.created_at))):
        key = v.platform.value if v.platform else None
        if key:
            by_platform[key] = v
    for v in by_platform.values():
        arm_id = (v.bandit_action or {}).get("arm_id")
        if arm_id:
            arm_ids.add(arm_id)
    for arm_id in arm_ids:
        await _bump_arm(session, arm_id, rating)


async def get_bandit_stats(session: AsyncSession) -> list[ArmStats]:
    result = await session.execute(select(BanditState).order_by(BanditState.arm_id))
    rows = result.scalars().all()
    stats: list[ArmStats] = []
    for row in rows:
        try:
            arm = Arm.from_arm_id(row.arm_id)
            style, platform = arm.prompt_style, arm.platform
        except ValueError:
            style, platform = row.arm_id, "unknown"
        stats.append(
            ArmStats(
                arm_id=row.arm_id,
                prompt_style=style,
                platform=platform,
                alpha=row.alpha,
                beta=row.beta,
                mean=expected_value(row.alpha, row.beta),
                updated_at=row.updated_at,
            )
        )
    return stats


async def record_feedback(
    session: AsyncSession,
    job_id,
    rating: int,
    edited_text: str | None,
    scope: FeedbackScope = FeedbackScope.asset,
    content_version_id=None,
) -> Feedback:
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise ValueError("job not found")

    if scope == FeedbackScope.pack:
        fb = Feedback(
            job_id=job_id,
            content_version_id=None,
            scope=FeedbackScope.pack,
            rating=rating,
            edited_text=edited_text,
        )
        session.add(fb)
        await apply_pack_feedback_to_bandit(session, job, rating)
        await session.commit()
        await session.refresh(fb)
        return fb

    if content_version_id is None:
        raise ValueError("content_version_id is required for asset feedback")
    version = await session.get(ContentVersion, content_version_id)
    if version is None or version.job_id != job_id:
        raise ValueError("content_version does not belong to this job")

    fb = Feedback(
        job_id=job_id,
        content_version_id=content_version_id,
        scope=FeedbackScope.asset,
        rating=rating,
        edited_text=edited_text,
    )
    session.add(fb)
    await apply_feedback_to_bandit(session, content_version_id, rating)
    await session.commit()
    await session.refresh(fb)
    return fb
