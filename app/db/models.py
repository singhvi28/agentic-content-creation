import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


# JSONB on Postgres; plain JSON elsewhere (e.g. SQLite in tests)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class JobStatus(str, enum.Enum):
    queued = "queued"
    planning = "planning"
    drafting = "drafting"
    critiquing = "critiquing"
    revising = "revising"
    awaiting_choice = "awaiting_choice"
    done = "done"
    failed = "failed"


class JobType(str, enum.Enum):
    single = "single"
    campaign = "campaign"


class FeedbackScope(str, enum.Enum):
    asset = "asset"
    pack = "pack"


class Platform(str, enum.Enum):
    linkedin = "linkedin"
    twitter = "twitter"
    medium = "medium"
    youtube_script = "youtube_script"
    newsletter = "newsletter"
    instagram = "instagram"
    threads = "threads"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        default=JobStatus.queued,
        nullable=False,
    )
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", native_enum=False),
        default=JobType.single,
        nullable=False,
    )
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[Platform | None] = mapped_column(
        Enum(Platform, name="platform", native_enum=False),
        nullable=True,
    )
    platforms: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    shared_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    cross_surface_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cross_surface_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ab_variants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chosen_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "content_versions.id",
            use_alter=True,
            name="fk_jobs_chosen_version",
        ),
        nullable=True,
    )
    ab_choice_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    final_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_versions.id", use_alter=True, name="fk_jobs_final_content"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list["ContentVersion"]] = relationship(
        "ContentVersion",
        back_populates="job",
        foreign_keys="ContentVersion.job_id",
        order_by="ContentVersion.round, ContentVersion.variant_index, ContentVersion.created_at",
    )
    feedback_items: Mapped[list["Feedback"]] = relationship(
        "Feedback", back_populates="job"
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True
    )
    platform: Mapped[Platform | None] = mapped_column(
        Enum(Platform, name="version_platform", native_enum=False),
        nullable=True,
    )
    variant_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    critic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    critic_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    bandit_action: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship(
        "Job", back_populates="versions", foreign_keys=[job_id]
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True
    )
    content_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_versions.id"), nullable=True
    )
    scope: Mapped[FeedbackScope] = mapped_column(
        Enum(FeedbackScope, name="feedback_scope", native_enum=False),
        default=FeedbackScope.asset,
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["Job"] = relationship("Job", back_populates="feedback_items")


class BanditState(Base):
    __tablename__ = "bandit_state"

    # Spec says arm_id as pk; contextual bandit uses "{prompt_style}|{platform}".
    arm_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    alpha: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    beta: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
