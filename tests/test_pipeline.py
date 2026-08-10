import uuid

import pytest
import pytest_asyncio
from numpy.random import default_rng
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bandit.thompson import ThompsonSamplingBandit
from app.db.models import Base, ContentType, Job, JobStatus
from app.llm.gemini import FakeLLMClient
from app.orchestrator.pipeline import run_pipeline
from app.services.bandit_service import record_feedback, seed_bandit_arms


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await seed_bandit_arms(s)
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_completes_with_fake_llm(session: AsyncSession):
    job = Job(
        id=uuid.uuid4(),
        brief="Write a short tip about remote work.",
        content_type=ContentType.social_post,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()

    llm = FakeLLMClient()
    bandit = ThompsonSamplingBandit(rng=default_rng(1))
    await run_pipeline(session, job.id, llm, bandit=bandit)

    await session.refresh(job)
    assert job.status == JobStatus.done
    assert job.final_content_id is not None
    assert len(llm.calls) >= 2  # at least plan + draft


@pytest.mark.asyncio
async def test_feedback_updates_bandit(session: AsyncSession):
    job = Job(
        brief="Announce a product launch.",
        content_type=ContentType.email,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()

    llm = FakeLLMClient()
    await run_pipeline(
        session, job.id, llm, bandit=ThompsonSamplingBandit(rng=default_rng(7))
    )
    await session.refresh(job)

    from sqlalchemy import select
    from app.db.models import ContentVersion, BanditState

    result = await session.execute(
        select(ContentVersion).where(ContentVersion.job_id == job.id)
    )
    version = result.scalars().first()
    assert version is not None
    arm_id = version.bandit_action["arm_id"]
    before = await session.get(BanditState, arm_id)
    alpha_before = before.alpha

    await record_feedback(
        session,
        job_id=job.id,
        content_version_id=version.id,
        rating=5,
        edited_text=None,
    )
    after = await session.get(BanditState, arm_id)
    assert after.alpha == alpha_before + 1.0