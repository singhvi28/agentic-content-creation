from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.db.models import (
    FeedbackScope,
    JobStatus,
    JobType,
    Platform,
    PromptTemplateStage,
)


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    stage: PromptTemplateStage
    template: str = Field(..., min_length=1)
    version_tag: str = Field(default="v1", min_length=1, max_length=64)
    description: str | None = None


class PromptTemplateUpdate(BaseModel):
    template: str | None = Field(default=None, min_length=1)
    version_tag: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None


class PromptTemplateOut(BaseModel):
    id: UUID
    name: str
    stage: PromptTemplateStage
    template: str
    version_tag: str
    description: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    brief: str = Field(..., min_length=1, max_length=10_000)
    job_type: JobType = JobType.single
    platform: Platform | None = None
    include_newsletter: bool = False
    ab_variants: int | None = Field(default=None, ge=2, le=3)
    prompt_template_id: UUID | None = Field(
        default=None,
        description="ID of a saved PromptTemplate to use instead of system defaults.",
    )
    llm_model: str | None = Field(
        default=None,
        description="LiteLLM model string, e.g. 'groq/llama-3.3-70b-versatile', 'openai/gpt-4o-mini'",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="Client-supplied API key for the chosen LLM provider. Never persisted in DB.",
    )
    llm_critic_model: str | None = Field(
        default=None,
        description="Optional critic model override.",
    )

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
    prompt_template_id: UUID | None = None
    prompt_template: PromptTemplateOut | None = None
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


class JobSummaryOut(BaseModel):
    job_id: UUID
    created_at: datetime
    status: JobStatus
    job_type: JobType
    platform: Platform | None = None
    brief: str
    ab_variants: int | None = None
    llm_model: str | None = None


class LlmUsageItem(BaseModel):
    id: UUID
    job_id: UUID | None = None
    provider: str
    model: str
    operation: str
    prompt_chars: int
    completion_chars: int
    estimated_tokens: int
    created_at: datetime

    model_config = {"from_attributes": True}


class JobUsageResponse(BaseModel):
    job_id: UUID
    usages: list[LlmUsageItem] = []
    total_prompt_chars: int = 0
    total_completion_chars: int = 0
    total_estimated_tokens: int = 0


class FeedbackItemOut(BaseModel):
    id: UUID
    job_id: UUID
    content_version_id: UUID | None = None
    scope: FeedbackScope
    rating: int
    edited_text: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResetBanditRequest(BaseModel):
    arm_id: str | None = None


class ResetBanditResponse(BaseModel):
    ok: bool = True
    message: str
