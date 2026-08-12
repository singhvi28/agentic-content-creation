"""Initial schema matching current SQLAlchemy models.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-12

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUIDType = sa.CHAR(36).with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "jobs" not in tables:
        op.create_table(
            "jobs",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("job_type", sa.String(32), nullable=False, server_default="single"),
            sa.Column("brief", sa.Text(), nullable=False),
            sa.Column("platform", sa.String(64), nullable=True),
            sa.Column("platforms", JSONType, nullable=True),
            sa.Column("shared_plan", sa.Text(), nullable=True),
            sa.Column("cross_surface_score", sa.Float(), nullable=True),
            sa.Column("cross_surface_notes", sa.Text(), nullable=True),
            sa.Column("ab_variants", sa.Integer(), nullable=True),
            sa.Column("chosen_version_id", UUIDType, nullable=True),
            sa.Column("ab_choice_applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("final_content_id", UUIDType, nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )

    if "content_versions" not in tables:
        op.create_table(
            "content_versions",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("job_id", UUIDType, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("platform", sa.String(64), nullable=True),
            sa.Column("variant_index", sa.Integer(), nullable=True),
            sa.Column("round", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("critic_score", sa.Float(), nullable=True),
            sa.Column("critic_notes", sa.Text(), nullable=True),
            sa.Column("bandit_action", JSONType, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )
        op.create_index("ix_content_versions_job_id", "content_versions", ["job_id"])

    if "feedback" not in tables:
        op.create_table(
            "feedback",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("job_id", UUIDType, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column(
                "content_version_id",
                UUIDType,
                sa.ForeignKey("content_versions.id"),
                nullable=True,
            ),
            sa.Column("scope", sa.String(32), nullable=False, server_default="asset"),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("edited_text", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )
        op.create_index("ix_feedback_job_id", "feedback", ["job_id"])

    if "bandit_state" not in tables:
        op.create_table(
            "bandit_state",
            sa.Column("arm_id", sa.String(128), primary_key=True),
            sa.Column("alpha", sa.Float(), nullable=False),
            sa.Column("beta", sa.Float(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("bandit_state")
    op.drop_table("feedback")
    op.drop_table("content_versions")
    op.drop_table("jobs")
