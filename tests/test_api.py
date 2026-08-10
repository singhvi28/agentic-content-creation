import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, ContentType, Job, JobStatus
from app.db.session import get_db
from app.llm.gemini import FakeLLMClient
from app.main import app
from app.orchestrator.pipeline import run_pipeline
from app.services.bandit_service import seed_bandit_arms


@pytest_asyncio.fixture
async def client():
    # Shared in-memory DB so enqueue's separate session can see the committed job.
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:apitest?mode=memory&cache=shared",
        connect_args={"uri": True},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as s:
        await seed_bandit_arms(s)

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Avoid real Redis / Arq / Gemini during API tests
    async def fake_enqueue(job_id: str):
        async with factory() as session:
            from app.bandit.thompson import ThompsonSamplingBandit
            from numpy.random import default_rng

            await run_pipeline(
                session,
                uuid.UUID(job_id),
                FakeLLMClient(),
                bandit=ThompsonSamplingBandit(rng=default_rng(0)),
            )

    mock_pool = AsyncMock()

    async def enqueue_job(name, job_id):
        await fake_enqueue(job_id)
        return None

    mock_pool.enqueue_job = enqueue_job

    with patch("app.api.content.get_arq_pool", AsyncMock(return_value=mock_pool)):
        with patch("app.main.init_db", AsyncMock()):
            with patch("app.main.seed_bandit_arms", AsyncMock()):
                with patch("app.main.hub") as mock_hub:
                    mock_hub.connect = AsyncMock()
                    mock_hub.close = AsyncMock()
                    transport = ASGITransport(app=app)
                    async with AsyncClient(
                        transport=transport, base_url="http://test"
                    ) as ac:
                        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_generate_poll_feedback_flow(client):
    r = await client.post(
        "/content/generate",
        json={
            "brief": "Write a blog intro about async Python.",
            "content_type": "blog_post",
        },
    )
    assert r.status_code == 200
    data = r.json()
    job_id = data["job_id"]
    assert data["status"] == "queued"

    detail = await client.get(f"/content/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "done"
    assert body["final_content"]
    assert len(body["versions"]) >= 1

    version_id = body["versions"][0]["id"]
    fb = await client.post(
        f"/content/{job_id}/feedback",
        json={"content_version_id": version_id, "rating": 5},
    )
    assert fb.status_code == 200
    assert fb.json()["ok"] is True

    stats = await client.get("/bandit/stats")
    assert stats.status_code == 200
    assert len(stats.json()["arms"]) == 9  # 3 styles × 3 content types