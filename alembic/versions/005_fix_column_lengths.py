"""Widen jobs status and platform column lengths.

Revision ID: 005_fix_column_lengths
Revises: 004_prompt_templates
Create Date: 2026-09-24

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_fix_column_lengths"
down_revision: Union[str, None] = "004_prompt_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "status",
        existing_type=sa.String(10),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "platform",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=True,
    )


def downgrade() -> None:
    pass
