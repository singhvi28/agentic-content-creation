import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import get_db
from app.llm.gemini import FakeLLMClient
from app.main import app
from app.orchestrator.pipeline import run_pipeline
from app.services.bandit_service import seed_bandit_arms


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:apitest_ab?mode=memory&cache=shared",
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

    async def fake_enqueue(job_id: str):
        async with factory() as session:
            from numpy.random import default_rng

            from app.bandit.thompson import ThompsonSamplingBandit

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
            "brief": "Write a Medium intro about async Python.",
            "job_type": "single",
            "platform": "medium",
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
    assert body["platform"] == "medium"
    assert body["job_type"] == "single"
    assert body["final_content"]
    assert len(body["versions"]) >= 1

    version_id = body["versions"][0]["id"]
    fb = await client.post(
        f"/content/{job_id}/feedback",
        json={"scope": "asset", "content_version_id": version_id, "rating": 5},
    )
    assert fb.status_code == 200
    assert fb.json()["ok"] is True

    stats = await client.get("/bandit/stats")
    assert stats.status_code == 200
    assert len(stats.json()["arms"]) == 21


@pytest.mark.asyncio
async def test_campaign_generate_flow(client):
    r = await client.post(
        "/content/generate",
        json={
            "brief": "Campaign about async Python for builders.",
            "job_type": "campaign",
            "include_newsletter": True,
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    detail = await client.get(f"/content/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "done"
    assert body["job_type"] == "campaign"
    assert body["shared_plan"]
    assert body["cross_surface_score"] is not None
    assert "newsletter" in (body.get("platforms") or [])
    assert len(body.get("assets") or []) >= 4

    pack_fb = await client.post(
        f"/content/{job_id}/feedback",
        json={"scope": "pack", "rating": 5},
    )
    assert pack_fb.status_code == 200

    asset_id = body["assets"][0]["version_id"]
    asset_fb = await client.post(
        f"/content/{job_id}/feedback",
        json={"scope": "asset", "content_version_id": asset_id, "rating": 4},
    )
    assert asset_fb.status_code == 200


@pytest.mark.asyncio
async def test_ab_generate_choose_flow(client):
    r = await client.post(
        "/content/generate",
        json={
            "brief": "A/B hooks about async Python.",
            "job_type": "single",
            "platform": "linkedin",
            "ab_variants": 2,
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    detail = await client.get(f"/content/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "awaiting_choice"
    assert body["ab_variants"] == 2
    variants = body.get("variants") or []
    assert len(variants) == 2
    assert all("Hook variant" in (v.get("text") or "") for v in variants)

    # Choose rejects wrong status after we finish — first reject non-variant
    bad = await client.post(
        f"/content/{job_id}/choose",
        json={"content_version_id": str(uuid.uuid4())},
    )
    assert bad.status_code == 400

    winner_id = variants[0]["version_id"]
    chosen = await client.post(
        f"/content/{job_id}/choose",
        json={"content_version_id": winner_id},
    )
    assert chosen.status_code == 200
    assert chosen.json()["status"] == "queued"

    detail2 = await client.get(f"/content/{job_id}")
    body2 = detail2.json()
    assert body2["status"] == "done"
    assert body2["chosen_version_id"] == winner_id
    assert body2["final_content"]


@pytest.mark.asyncio
async def test_choose_rejects_non_awaiting(client):
    r = await client.post(
        "/content/generate",
        json={
            "brief": "Plain single job.",
            "job_type": "single",
            "platform": "twitter",
        },
    )
    job_id = r.json()["job_id"]
    detail = (await client.get(f"/content/{job_id}")).json()
    assert detail["status"] == "done"
    version_id = detail["versions"][0]["id"]

    resp = await client.post(
        f"/content/{job_id}/choose",
        json={"content_version_id": version_id},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ab_variants_rejected_on_campaign(client):
    r = await client.post(
        "/content/generate",
        json={
            "brief": "Nope",
            "job_type": "campaign",
            "ab_variants": 2,
        },
    )
    assert r.status_code == 422
