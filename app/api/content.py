import uuid

from arq import create_pool
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Job, JobStatus
from app.db.session import get_db
from app.schemas import (
    ContentVersionOut,
    FeedbackRequest,
    FeedbackResponse,
    GenerateRequest,
    GenerateResponse,
    JobDetailResponse,
)
from app.services.bandit_service import record_feedback
from app.services.events import hub
from app.worker.tasks import redis_settings_from_url
from app.config import get_settings

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


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    job = Job(
        brief=body.brief,
        content_type=body.content_type,
        status=JobStatus.queued,
    )
    db.add(job)
    # Commit before enqueue so the worker can load the row.
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
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    versions = [ContentVersionOut.model_validate(v) for v in job.versions]
    final_content = None
    if job.final_content_id:
        for v in job.versions:
            if v.id == job.final_content_id:
                final_content = v.text
                break

    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        brief=job.brief,
        content_type=job.content_type,
        versions=versions,
        final_content=final_content,
        error_message=job.error_message,
    )


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
            content_version_id=body.content_version_id,
            rating=body.rating,
            edited_text=body.edited_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FeedbackResponse(ok=True)


@router.websocket("/{job_id}/stream")
async def stream_job(websocket: WebSocket, job_id: uuid.UUID) -> None:
    await websocket.accept()
    await hub.subscribe(job_id, websocket)
    try:
        # Send current snapshot if available
        await websocket.send_json(
            {"job_id": str(job_id), "status": "subscribed"}
        )
        while True:
            # Keep connection alive; client may send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(job_id, websocket)