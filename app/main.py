import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import bandit, content
from app.api.content import close_arq_pool
from app.db.session import AsyncSessionLocal, init_db
from app.services.bandit_service import seed_bandit_arms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_bandit_arms(session)
    yield
    await close_arq_pool()


app = FastAPI(
    title="Agentic Content Pipeline",
    description=(
        "Multi-step content generation (Plan → Draft → Critique → Revise) "
        "with Thompson Sampling bandit optimization over prompt strategies."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(content.router)
app.include_router(bandit.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
