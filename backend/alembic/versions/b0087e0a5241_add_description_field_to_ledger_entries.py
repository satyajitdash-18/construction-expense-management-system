"""Add description field to ledger_entries

Revision ID: b0087e0a5241
Revises: 596ea493d163
Create Date: 2026-09-26 15:06:16.832276

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b0087e0a5241'
down_revision: str | None = '596ea493d163'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('ledger_entries', sa.Column('description', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('ledger_entries', 'description')