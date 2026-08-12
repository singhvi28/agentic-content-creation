"""Repair A/B columns and chosen_version_id UUID type.

Revision ID: 002_repair_ab
Revises: 001_initial
Create Date: 2026-08-12

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_repair_ab"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _add_column_if_missing(table: str, column: str, col: sa.Column) -> None:
    bind = op.get_bind()
    if column in _column_names(bind, table):
        return
    op.add_column(table, col)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    _add_column_if_missing("jobs", "ab_variants", sa.Column("ab_variants", sa.Integer()))
    _add_column_if_missing(
        "jobs",
        "ab_choice_applied_at",
        sa.Column("ab_choice_applied_at", sa.DateTime(timezone=True)),
    )
    _add_column_if_missing(
        "content_versions",
        "variant_index",
        sa.Column("variant_index", sa.Integer()),
    )

    cols = {c["name"]: c for c in sa.inspect(bind).get_columns("jobs")}
    if "chosen_version_id" not in cols:
        op.add_column(
            "jobs",
            sa.Column(
                "chosen_version_id",
                sa.CHAR(36).with_variant(postgresql.UUID(as_uuid=True), "postgresql"),
            ),
        )
    elif dialect == "postgresql":
        col_type = cols["chosen_version_id"]["type"]
        type_name = type(col_type).__name__.lower()
        # Hand-rolled migrate used CHAR(36); normalize to UUID
        if "uuid" not in type_name:
            op.execute(
                sa.text(
                    """
                    ALTER TABLE jobs
                    ALTER COLUMN chosen_version_id
                    TYPE UUID USING NULLIF(trim(chosen_version_id::text), '')::uuid
                    """
                )
            )

        # Ensure FK exists (best-effort)
        fks = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("jobs")}
        if "fk_jobs_chosen_version" not in fks:
            op.create_foreign_key(
                "fk_jobs_chosen_version",
                "jobs",
                "content_versions",
                ["chosen_version_id"],
                ["id"],
            )


def downgrade() -> None:
    # Non-destructive downgrade omitted — columns may hold data
    pass
