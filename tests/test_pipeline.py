import uuid

import pytest
import pytest_asyncio
from numpy.random import default_rng
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bandit.thompson import ThompsonSamplingBandit
from app.campaign_pack import DEFAULT_CAMPAIGN_PLATFORMS, build_campaign_platforms
from app.db.models import BanditState, Base, Job, JobStatus, JobType, Platform
from app.llm.gemini import FakeLLMClient
from app.orchestrator.pipeline import run_pipeline
from app.services.bandit_service import record_feedback, seed_bandit_arms
from app.db.models import FeedbackScope


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


def test_build_campaign_platforms():
    assert build_campaign_platforms(False) == list(DEFAULT_CAMPAIGN_PLATFORMS)
    with_nl = build_campaign_platforms(True)
    assert "newsletter" in with_nl
    assert with_nl[:4] == list(DEFAULT_CAMPAIGN_PLATFORMS)


@pytest.mark.asyncio
async def test_seed_creates_21_arms(session: AsyncSession):
    count = await session.scalar(select(func.count()).select_from(BanditState))
    assert count == 21


@pytest.mark.asyncio
async def test_pipeline_completes_with_fake_llm(session: AsyncSession):
    job = Job(
        id=uuid.uuid4(),
        brief="Write a short tip about remote work.",
        job_type=JobType.single,
        platform=Platform.linkedin,
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
    assert len(llm.calls) >= 2


@pytest.mark.asyncio
async def test_feedback_updates_bandit(session: AsyncSession):
    job = Job(
        brief="Announce a product launch.",
        job_type=JobType.single,
        platform=Platform.newsletter,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()

    llm = FakeLLMClient()
    await run_pipeline(
        session, job.id, llm, bandit=ThompsonSamplingBandit(rng=default_rng(7))
    )
    await session.refresh(job)

    from app.db.models import ContentVersion

    result = await session.execute(
        select(ContentVersion).where(ContentVersion.job_id == job.id)
    )
    version = result.scalars().first()
    assert version is not None
    arm_id = version.bandit_action["arm_id"]
    before = await session.get(BanditState, arm_id)
    alpha_before = before.alpha
    beta_before = before.beta

    await record_feedback(
        session,
        job_id=job.id,
        content_version_id=version.id,
        rating=5,
        edited_text=None,
        scope=FeedbackScope.asset,
    )
    after = await session.get(BanditState, arm_id)
    decayed_a, _ = ThompsonSamplingBandit.apply_decay(alpha_before, beta_before)
    assert after.alpha == pytest.approx(decayed_a + 1.0)

@pytest.mark.asyncio
async def test_campaign_pipeline_and_pack_feedback(session: AsyncSession):
    platforms = build_campaign_platforms(include_newsletter=False)
    job = Job(
        brief="Ship faster with better CI.",
        job_type=JobType.campaign,
        platform=None,
        platforms=platforms,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()

    llm = FakeLLMClient()
    await run_pipeline(
        session, job.id, llm, bandit=ThompsonSamplingBandit(rng=default_rng(3))
    )
    await session.refresh(job)

    assert job.status == JobStatus.done
    assert job.shared_plan
    assert job.cross_surface_score is not None
    assert job.platforms == platforms

    from app.db.models import ContentVersion

    versions = (
        await session.execute(
            select(ContentVersion).where(ContentVersion.job_id == job.id)
        )
    ).scalars().all()
    platforms_seen = {v.platform.value for v in versions if v.platform}
    assert platforms_seen == set(platforms)
    assert len(platforms_seen) >= 4

    # Snapshot alphas for used arms
    finals = {}
    for v in sorted(versions, key=lambda x: x.round):
        if v.platform:
            finals[v.platform.value] = v
    arm_ids = [(v.bandit_action or {}).get("arm_id") for v in finals.values()]
    arm_ids = [a for a in arm_ids if a]
    before = {}
    for arm_id in arm_ids:
        row = await session.get(BanditState, arm_id)
        before[arm_id] = (row.alpha, row.beta)

    await record_feedback(
        session,
        job_id=job.id,
        rating=5,
        edited_text=None,
        scope=FeedbackScope.pack,
    )
    for arm_id, (alpha0, beta0) in before.items():
        row = await session.get(BanditState, arm_id)
        decayed_a, _ = ThompsonSamplingBandit.apply_decay(alpha0, beta0)
        assert row.alpha == pytest.approx(decayed_a + 1.0)

@pytest.mark.asyncio
async def test_ab_pipeline_pauses_then_resumes(session: AsyncSession):
    job = Job(
        brief="A/B hooks for remote work tip.",
        job_type=JobType.single,
        platform=Platform.linkedin,
        ab_variants=2,
        status=JobStatus.queued,
    )
    session.add(job)
    await session.commit()

    llm = FakeLLMClient()
    bandit = ThompsonSamplingBandit(rng=default_rng(11))
    await run_pipeline(session, job.id, llm, bandit=bandit)

    await session.refresh(job)
    assert job.status == JobStatus.awaiting_choice
    assert job.final_content_id is None

    from app.db.models import ContentVersion
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(Job)
        .where(Job.id == job.id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one()
    variants = [v for v in job.versions if v.variant_index is not None]
    assert len(variants) == 2
    assert all("Hook variant" in v.text for v in variants)
    arm_ids = {(v.bandit_action or {}).get("arm_id") for v in variants}
    assert len(arm_ids) == 2

    # Worker re-entry without choice is a no-op
    await run_pipeline(session, job.id, llm, bandit=bandit)
    await session.refresh(job)
    assert job.status == JobStatus.awaiting_choice

    winner = variants[0]
    job.chosen_version_id = winner.id
    job.status = JobStatus.queued
    await session.commit()

    await run_pipeline(session, job.id, llm, bandit=bandit)
    await session.refresh(job)
    assert job.status == JobStatus.done
    assert job.final_content_id is not None


@pytest.mark.asyncio
async def test_apply_ab_choice_bandit_pairwise(session: AsyncSession):
    from app.db.models import ContentVersion
    from app.services.bandit_service import apply_ab_choice
    from sqlalchemy.orm import selectinload

    job = Job(
        brief="Pairwise bandit signal.",
        job_type=JobType.single,
        platform=Platform.twitter,
        ab_variants=2,
        status=JobStatus.awaiting_choice,
    )
    session.add(job)
    await session.flush()

    arm_w = "concise|twitter"
    arm_l = "storytelling|twitter"
    v0 = ContentVersion(
        job_id=job.id,
        platform=Platform.twitter,
        round=0,
        variant_index=0,
        text="Hook variant 1",
        bandit_action={"arm_id": arm_w, "prompt_style": "concise"},
    )
    v1 = ContentVersion(
        job_id=job.id,
        platform=Platform.twitter,
        round=0,
        variant_index=1,
        text="Hook variant 2",
        bandit_action={"arm_id": arm_l, "prompt_style": "storytelling"},
    )
    session.add_all([v0, v1])
    await session.commit()

    w_before = await session.get(BanditState, arm_w)
    l_before = await session.get(BanditState, arm_l)
    w_a, w_b = w_before.alpha, w_before.beta
    l_a, l_b = l_before.alpha, l_before.beta

    result = await session.execute(
        select(Job)
        .where(Job.id == job.id)
        .options(selectinload(Job.versions))
    )
    job = result.scalar_one()
    await apply_ab_choice(session, job, v0.id)
    await session.commit()

    w_after = await session.get(BanditState, arm_w)
    l_after = await session.get(BanditState, arm_l)
    decayed_wa, decayed_wb = ThompsonSamplingBandit.apply_decay(w_a, w_b)
    decayed_la, decayed_lb = ThompsonSamplingBandit.apply_decay(l_a, l_b)
    assert w_after.alpha == pytest.approx(decayed_wa + 1.0)
    assert w_after.beta == pytest.approx(decayed_wb)
    assert l_after.alpha == pytest.approx(decayed_la)
    assert l_after.beta == pytest.approx(decayed_lb + 1.0)
