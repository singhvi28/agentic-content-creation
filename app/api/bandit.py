from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas import BanditStatsResponse
from app.services.bandit_service import get_bandit_stats

router = APIRouter(prefix="/bandit", tags=["bandit"])


@router.get("/stats", response_model=BanditStatsResponse)
async def bandit_stats(db: AsyncSession = Depends(get_db)) -> BanditStatsResponse:
    arms = await get_bandit_stats(db)
    return BanditStatsResponse(arms=arms)