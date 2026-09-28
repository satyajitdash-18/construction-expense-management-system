"""Add result column to processing_jobs for OCR results

Revision ID: c6f41d757b90
Revises: eadd1a89dab6
Create Date: 2026-09-21 07:16:18.983442

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6f41d757b90'
down_revision: str | None = 'eadd1a89dab6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('processing_jobs', sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('processing_jobs', 'result')