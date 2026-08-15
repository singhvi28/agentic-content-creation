import uuid

from arq import create_pool
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.campaign_pack import build_campaign_platforms
from app.config import get_settings
from app.db.models import Job, JobStatus, JobType, PromptTemplate
from app.db.session import get_db
from app.platforms import get_preset
from app.schemas import (
    AbVariantOut,
    CampaignAssetOut,
    ChooseRequest,
    ChooseResponse,
    ContentVersionOut,
    FeedbackRequest,
    FeedbackResponse,
    GenerateRequest,
    GenerateResponse,
    JobDetailResponse,
    PromptTemplateOut,
)
from app.services.bandit_service import record_feedback
from app.worker.tasks import redis_settings_from_url

router = APIRouter(prefix="/content", tags=["content"])

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(redis_settings_from_url(get_settings().redis_url))
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None


def _latest_assets(job: Job) -> list[CampaignAssetOut]:
    by_platform: dict[str, object] = {}
    for v in sorted(job.versions, key=lambda x: x.round):
        if v.platform is None:
            continue
        by_platform[v.platform.value] = v
    assets: list[CampaignAssetOut] = []
    for platform, v in by_platform.items():
        assets.append(
            CampaignAssetOut(
                platform=platform,
                version_id=v.id,
                text=v.text,
                critic_score=v.critic_score,
                critic_notes=v.critic_notes,
                bandit_action=v.bandit_action,
            )
        )
    return assets


def _ab_variants(job: Job) -> list[AbVariantOut]:
    variants: list[AbVariantOut] = []
    ordered = sorted(
        [x for x in job.versions if x.variant_index is not None],
        key=lambda x: (x.variant_index or 0, str(x.created_at), str(x.id)),
    )
    for v in ordered:
        variants.append(
            AbVariantOut(
                version_id=v.id,
                variant_index=v.variant_index or 0,
                text=v.text,
                bandit_action=v.bandit_action,
            )
        )
    return variants


def _campaign_pack_markdown(job: Job, assets: list[CampaignAssetOut]) -> str:
    parts = ["# Campaign pack", ""]
    if job.shared_plan:
        parts.extend(["## Shared plan", job.shared_plan, ""])
    for asset in assets:
        label = get_preset(asset.platform).label
        parts.extend([f"## {label}", asset.text, ""])
    if job.cross_surface_notes:
        parts.extend(
            [
                "## Cross-surface review",
                f"Score: {job.cross_surface_score}",
                job.cross_surface_notes,
            ]
        )
    return "\n".join(parts).strip()


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    if body.prompt_template_id:
        pt = await db.get(PromptTemplate, body.prompt_template_id)
        if pt is None or not pt.is_active:
            raise HTTPException(
                status_code=400,
                detail="Prompt template not found or inactive",
            )

    if body.job_type == JobType.campaign:
        platforms = build_campaign_platforms(body.include_newsletter)
        job = Job(
            brief=body.brief,
            job_type=JobType.campaign,
            platform=None,
            platforms=platforms,
            ab_variants=None,
            prompt_template_id=body.prompt_template_id,
            status=JobStatus.queued,
        )
    else:
        job = Job(
            brief=body.brief,
            job_type=JobType.single,
            platform=body.platform,
            platforms=None,
            ab_variants=body.ab_variants,
            prompt_template_id=body.prompt_template_id,
            status=JobStatus.queued,
        )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job("run_content_job", str(job.id))

    return GenerateResponse(job_id=job.id, status=JobStatus.queued)


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.versions),
            selectinload(Job.prompt_template),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    versions = [ContentVersionOut.model_validate(v) for v in job.versions]
    assets = _latest_assets(job)
    variants = _ab_variants(job)

    final_content = None
    if job.job_type == JobType.campaign:
        if job.status.value == "done":
            final_content = _campaign_pack_markdown(job, assets)
    elif job.final_content_id:
        for v in job.versions:
            if v.id == job.final_content_id:
                final_content = v.text
                break

    prompt_template_out = (
        PromptTemplateOut.model_validate(job.prompt_template)
        if job.prompt_template
        else None
    )

    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        brief=job.brief,
        job_type=job.job_type,
        platform=job.platform,
        platforms=job.platforms,
        shared_plan=job.shared_plan,
        cross_surface_score=job.cross_surface_score,
        cross_surface_notes=job.cross_surface_notes,
        ab_variants=job.ab_variants,
        chosen_version_id=job.chosen_version_id,
        prompt_template_id=job.prompt_template_id,
        prompt_template=prompt_template_out,
        versions=versions,
        assets=assets,
        variants=variants,
        final_content=final_content,
        error_message=job.error_message,
    )


@router.post("/{job_id}/choose", response_model=ChooseResponse)
async def choose_variant(
    job_id: uuid.UUID,
    body: ChooseRequest,
    db: AsyncSession = Depends(get_db),
) -> ChooseResponse:
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.awaiting_choice:
        raise HTTPException(
            status_code=400,
            detail="Job is not awaiting an A/B choice",
        )
    if job.chosen_version_id is not None or job.ab_choice_applied_at is not None:
        raise HTTPException(
            status_code=400,
            detail="A/B winner already chosen for this job",
        )

    winner = next(
        (v for v in job.versions if v.id == body.content_version_id), None
    )
    if winner is None or winner.variant_index is None:
        raise HTTPException(
            status_code=400,
            detail="content_version_id must be an A/B variant on this job",
        )

    job.chosen_version_id = winner.id
    job.status = JobStatus.queued
    await db.commit()

    pool = await get_arq_pool()
    await pool.enqueue_job("run_content_job", str(job.id))

    return ChooseResponse(ok=True, status=JobStatus.queued)


@router.post("/{job_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    job_id: uuid.UUID,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        await record_feedback(
            db,
            job_id=job_id,
            rating=body.rating,
            edited_text=body.edited_text,
            scope=body.scope,
            content_version_id=body.content_version_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FeedbackResponse(ok=True)
