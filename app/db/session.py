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


async def _column_names(conn, table: str) -> set[str]:
    dialect = conn.dialect.name
    if dialect == "postgresql":
        result = await conn.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :table
                """
            ),
            {"table": table},
        )
        return {row[0] for row in result.fetchall()}
    if dialect == "sqlite":
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result.fetchall()}
    return set()


async def _migrate_content_type_to_platform(conn) -> None:
    """One-shot: rename jobs.content_type → platform when upgrading old DBs."""
    cols = await _column_names(conn, "jobs")
    if "content_type" in cols and "platform" not in cols:
        await conn.execute(
            text("ALTER TABLE jobs RENAME COLUMN content_type TO platform")
        )


async def _add_column_if_missing(
    conn, table: str, column: str, ddl_type: str
) -> None:
    cols = await _column_names(conn, table)
    if column in cols:
        return
    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


async def _migrate_campaign_columns(conn) -> None:
    dialect = conn.dialect.name
    # Jobs table campaign fields
    await _add_column_if_missing(conn, "jobs", "job_type", "VARCHAR(32) DEFAULT 'single'")
    await _add_column_if_missing(conn, "jobs", "platforms", "JSON" if dialect != "postgresql" else "JSONB")
    await _add_column_if_missing(conn, "jobs", "shared_plan", "TEXT")
    await _add_column_if_missing(conn, "jobs", "cross_surface_score", "FLOAT")
    await _add_column_if_missing(conn, "jobs", "cross_surface_notes", "TEXT")

    # Make platform nullable (Postgres)
    if dialect == "postgresql":
        await conn.execute(
            text("ALTER TABLE jobs ALTER COLUMN platform DROP NOT NULL")
        )
        await conn.execute(
            text(
                "UPDATE jobs SET job_type = 'single' WHERE job_type IS NULL OR job_type = ''"
            )
        )

    # Content versions: platform tag
    await _add_column_if_missing(
        conn, "content_versions", "platform", "VARCHAR(64)"
    )

    # Feedback: nullable version + scope
    await _add_column_if_missing(
        conn, "feedback", "scope", "VARCHAR(32) DEFAULT 'asset'"
    )
    if dialect == "postgresql":
        await conn.execute(
            text("ALTER TABLE feedback ALTER COLUMN content_version_id DROP NOT NULL")
        )


async def _migrate_ab_columns(conn) -> None:
    await _add_column_if_missing(conn, "jobs", "ab_variants", "INTEGER")
    await _add_column_if_missing(conn, "jobs", "chosen_version_id", "CHAR(36)")
    await _add_column_if_missing(conn, "content_versions", "variant_index", "INTEGER")


async def init_db() -> None:
    from app.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_content_type_to_platform(conn)
        await _migrate_campaign_columns(conn)
        await _migrate_ab_columns(conn)
