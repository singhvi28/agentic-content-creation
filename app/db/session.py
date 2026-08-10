from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _migrate_content_type_to_platform(conn) -> None:
    """One-shot: rename jobs.content_type → platform when upgrading old DBs."""
    dialect = conn.dialect.name
    if dialect == "postgresql":
        exists = await conn.scalar(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'content_type'
                """
            )
        )
        platform_exists = await conn.scalar(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'platform'
                """
            )
        )
        if exists and not platform_exists:
            await conn.execute(
                text("ALTER TABLE jobs RENAME COLUMN content_type TO platform")
            )
    elif dialect == "sqlite":
        # SQLite: inspect via PRAGMA
        result = await conn.execute(text("PRAGMA table_info(jobs)"))
        cols = {row[1] for row in result.fetchall()}
        if "content_type" in cols and "platform" not in cols:
            await conn.execute(
                text("ALTER TABLE jobs RENAME COLUMN content_type TO platform")
            )


async def init_db() -> None:
    from app.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_content_type_to_platform(conn)
