"""Add expense subtotal + tax = total check constraint

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-01 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enforce mathematical invariant in PostgreSQL: subtotal + tax_amount = total
    op.create_check_constraint(
        "chk_expense_subtotal_plus_tax_eq_total",
        "expenses",
        "subtotal + tax_amount = total",
    )


def downgrade() -> None:
    op.drop_constraint("chk_expense_subtotal_plus_tax_eq_total", "expenses", type_="check")
