"""Bandit persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bandit.thompson import PROMPT_STYLES, Arm, ThompsonSamplingBandit, expected_value
from app.db.models import BanditState, ContentType, ContentVersion, Feedback
from app.schemas import ArmStats


async def seed_bandit_arms(session: AsyncSession) -> None:
    """Ensure all (prompt_style, content_type) arms exist with Beta(1,1)."""
    for ctype in ContentType:
        for style in PROMPT_STYLES:
            arm_id = Arm(style, ctype.value).arm_id
            existing = await session.get(BanditState, arm_id)
            if existing is None:
                session.add(BanditState(arm_id=arm_id, alpha=1.0, beta=1.0))
    await session.commit()


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
        # Fallback: cannot update without arm
        return

    row = await session.get(BanditState, arm_id)
    if row is None:
        row = BanditState(arm_id=arm_id, alpha=1.0, beta=1.0)
        session.add(row)
        await session.flush()

    row.alpha, row.beta = ThompsonSamplingBandit.update_from_rating(
        row.alpha, row.beta, rating
    )


async def get_bandit_stats(session: AsyncSession) -> list[ArmStats]:
    result = await session.execute(select(BanditState).order_by(BanditState.arm_id))
    rows = result.scalars().all()
    stats: list[ArmStats] = []
    for row in rows:
        try:
            arm = Arm.from_arm_id(row.arm_id)
            style, ctype = arm.prompt_style, arm.content_type
        except ValueError:
            style, ctype = row.arm_id, "unknown"
        stats.append(
            ArmStats(
                arm_id=row.arm_id,
                prompt_style=style,
                content_type=ctype,
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
    content_version_id,
    rating: int,
    edited_text: str | None,
) -> Feedback:
    version = await session.get(ContentVersion, content_version_id)
    if version is None or version.job_id != job_id:
        raise ValueError("content_version does not belong to this job")

    fb = Feedback(
        job_id=job_id,
        content_version_id=content_version_id,
        rating=rating,
        edited_text=edited_text,
    )
    session.add(fb)
    await apply_feedback_to_bandit(session, content_version_id, rating)
    await session.commit()
    await session.refresh(fb)
    return fb