from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BanditState, Feedback
from app.db.session import get_db
from app.schemas import (
    BanditStatsResponse,
    FeedbackItemOut,
    ResetBanditRequest,
    ResetBanditResponse,
)
from app.services.bandit_service import get_bandit_stats

router = APIRouter(prefix="/bandit", tags=["bandit"])


@router.get("/stats", response_model=BanditStatsResponse)
async def bandit_stats(db: AsyncSession = Depends(get_db)) -> BanditStatsResponse:
    arms = await get_bandit_stats(db)
    return BanditStatsResponse(arms=arms)


@router.get("/feedback", response_model=list[FeedbackItemOut])
async def list_feedback(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackItemOut]:
    result = await db.execute(
        select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    )
    feedbacks = result.scalars().all()
    return [FeedbackItemOut.model_validate(f) for f in feedbacks]


@router.post("/reset", response_model=ResetBanditResponse)
async def reset_bandit(
    body: ResetBanditRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ResetBanditResponse:
    if body and body.arm_id:
        arm = await db.get(BanditState, body.arm_id)
        if arm:
            arm.alpha = 1.0
            arm.beta = 1.0
            await db.commit()
            return ResetBanditResponse(ok=True, message=f"Reset arm '{body.arm_id}' to α=1.0, β=1.0")
        else:
            raise HTTPException(status_code=404, detail="Arm not found")
    else:
        result = await db.execute(select(BanditState))
        arms = result.scalars().all()
        for arm in arms:
            arm.alpha = 1.0
            arm.beta = 1.0
        await db.commit()
        return ResetBanditResponse(ok=True, message=f"Reset {len(arms)} bandit arm(s) to α=1.0, β=1.0")