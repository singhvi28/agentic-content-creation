from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import JobStatus, Platform


class GenerateRequest(BaseModel):
    brief: str = Field(..., min_length=1, max_length=10_000)
    platform: Platform


class GenerateResponse(BaseModel):
    job_id: UUID
    status: JobStatus = JobStatus.queued


class ContentVersionOut(BaseModel):
    id: UUID
    round: int
    text: str
    critic_score: float | None = None
    critic_notes: str | None = None
    bandit_action: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobDetailResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    brief: str
    platform: Platform
    versions: list[ContentVersionOut] = []
    final_content: str | None = None
    error_message: str | None = None


class FeedbackRequest(BaseModel):
    content_version_id: UUID
    rating: int = Field(..., ge=1, le=5)
    edited_text: str | None = None


class FeedbackResponse(BaseModel):
    ok: bool = True


class ArmStats(BaseModel):
    arm_id: str
    prompt_style: str
    platform: str
    alpha: float
    beta: float
    mean: float
    updated_at: datetime | None = None


class BanditStatsResponse(BaseModel):
    arms: list[ArmStats]
