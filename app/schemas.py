from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.db.models import FeedbackScope, JobStatus, JobType, Platform


class GenerateRequest(BaseModel):
    brief: str = Field(..., min_length=1, max_length=10_000)
    job_type: JobType = JobType.single
    platform: Platform | None = None
    include_newsletter: bool = False
    ab_variants: int | None = Field(default=None, ge=2, le=3)

    @model_validator(mode="after")
    def validate_job_fields(self) -> Self:
        if self.job_type == JobType.single and self.platform is None:
            raise ValueError("platform is required when job_type is single")
        if self.ab_variants is not None and self.job_type != JobType.single:
            raise ValueError("ab_variants is only supported for single jobs")
        return self


class GenerateResponse(BaseModel):
    job_id: UUID
    status: JobStatus = JobStatus.queued


class ContentVersionOut(BaseModel):
    id: UUID
    round: int
    text: str
    platform: Platform | None = None
    variant_index: int | None = None
    critic_score: float | None = None
    critic_notes: str | None = None
    bandit_action: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignAssetOut(BaseModel):
    platform: str
    version_id: UUID
    text: str
    critic_score: float | None = None
    critic_notes: str | None = None
    bandit_action: dict | None = None


class AbVariantOut(BaseModel):
    version_id: UUID
    variant_index: int
    text: str
    bandit_action: dict | None = None


class JobDetailResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    brief: str
    job_type: JobType = JobType.single
    platform: Platform | None = None
    platforms: list[str] | None = None
    shared_plan: str | None = None
    cross_surface_score: float | None = None
    cross_surface_notes: str | None = None
    ab_variants: int | None = None
    chosen_version_id: UUID | None = None
    versions: list[ContentVersionOut] = []
    assets: list[CampaignAssetOut] = []
    variants: list[AbVariantOut] = []
    final_content: str | None = None
    error_message: str | None = None


class FeedbackRequest(BaseModel):
    scope: FeedbackScope = FeedbackScope.asset
    content_version_id: UUID | None = None
    rating: int = Field(..., ge=1, le=5)
    edited_text: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.scope == FeedbackScope.asset and self.content_version_id is None:
            raise ValueError("content_version_id is required when scope is asset")
        return self


class FeedbackResponse(BaseModel):
    ok: bool = True


class ChooseRequest(BaseModel):
    content_version_id: UUID


class ChooseResponse(BaseModel):
    ok: bool = True
    status: JobStatus = JobStatus.queued


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
