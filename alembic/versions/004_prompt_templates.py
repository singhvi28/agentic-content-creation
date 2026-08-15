"""Add prompt_templates table and prompt_template_id to jobs.

Revision ID: 004_prompt_templates
Revises: 003_llm_usage
Create Date: 2026-08-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_prompt_templates"
down_revision: Union[str, None] = "003_llm_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUIDType = sa.CHAR(36).with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "prompt_templates" not in tables:
        op.create_table(
            "prompt_templates",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("stage", sa.String(32), nullable=False),
            sa.Column("template", sa.Text(), nullable=False),
            sa.Column("version_tag", sa.String(64), nullable=False, server_default="v1"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )

    columns = [c["name"] for c in sa.inspect(bind).get_columns("jobs")]
    if "prompt_template_id" not in columns:
        op.add_column(
            "jobs",
            sa.Column(
                "prompt_template_id",
                UUIDType,
                sa.ForeignKey("prompt_templates.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    columns = [c["name"] for c in sa.inspect(bind).get_columns("jobs")]
    if "prompt_template_id" in columns:
        op.drop_column("jobs", "prompt_template_id")
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "prompt_templates" in tables:
        op.drop_table("prompt_templates")
