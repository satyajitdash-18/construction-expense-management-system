"""Project membership, ledger postings, and financial integrity constraints

Revision ID: d4e5f6a7b8c9
Revises: cfb28e2612c1
Create Date: 2026-10-01 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create project_members table
    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="site_user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"], unique=False)
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"], unique=False)

    # 2. Backfill existing projects with their creators as project_manager
    op.execute(
        """
        INSERT INTO project_members (id, project_id, user_id, role, created_at)
        SELECT gen_random_uuid(), id, created_by, 'project_manager', created_at
        FROM projects
        ON CONFLICT (project_id, user_id) DO NOTHING;
        """
    )

    # 3. Create ledger_postings table for posting batch tracking & reversal auditability
    op.create_table(
        "ledger_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("expense_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="POSTED", nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.String(length=500), nullable=True),
        sa.Column("source_audit_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reversal_audit_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversal_audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ledger_postings_expense_id", "ledger_postings", ["expense_id"], unique=False)
    op.create_index("ix_ledger_postings_project_id", "ledger_postings", ["project_id"], unique=False)
    op.create_index(
        "uq_ledger_postings_active_expense",
        "ledger_postings",
        ["expense_id"],
        unique=True,
        postgresql_where=sa.text("status = 'POSTED'"),
    )

    # 4. Add is_reversal column to ledger_entries
    op.add_column(
        "ledger_entries",
        sa.Column("is_reversal", sa.Boolean(), server_default="false", nullable=False),
    )

    # 5. Add check constraint on ledger_entries amount > 0
    op.create_check_constraint(
        "chk_ledger_entry_amount_positive",
        "ledger_entries",
        "amount > 0",
    )

    # 6. Add non-negative check constraints on expenses
    op.create_check_constraint(
        "chk_expense_subtotal_non_negative",
        "expenses",
        "subtotal >= 0",
    )
    op.create_check_constraint(
        "chk_expense_tax_non_negative",
        "expenses",
        "tax_amount >= 0",
    )
    op.create_check_constraint(
        "chk_expense_total_non_negative",
        "expenses",
        "total >= 0",
    )
    op.create_check_constraint(
        "chk_expense_cgst_non_negative",
        "expenses",
        "cgst_amount IS NULL OR cgst_amount >= 0",
    )
    op.create_check_constraint(
        "chk_expense_sgst_non_negative",
        "expenses",
        "sgst_amount IS NULL OR sgst_amount >= 0",
    )
    op.create_check_constraint(
        "chk_expense_igst_non_negative",
        "expenses",
        "igst_amount IS NULL OR igst_amount >= 0",
    )

    # 7. Add non-negative check constraint on project_budgets amount >= 0
    op.create_check_constraint(
        "chk_budget_amount_positive",
        "project_budgets",
        "amount >= 0",
    )

    # 8. Create partial unique index on reconciliation_records for active payment matches
    op.create_index(
        "uq_active_payment_reconciliation",
        "reconciliation_records",
        ["payment_event_id"],
        unique=True,
        postgresql_where=sa.text("payment_event_id IS NOT NULL AND status IN ('MATCHED', 'MANUALLY_RESOLVED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_payment_reconciliation", table_name="reconciliation_records")
    op.drop_constraint("chk_budget_amount_positive", "project_budgets", type_="check")
    op.drop_constraint("chk_expense_igst_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_expense_sgst_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_expense_cgst_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_expense_total_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_expense_tax_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_expense_subtotal_non_negative", "expenses", type_="check")
    op.drop_constraint("chk_ledger_entry_amount_positive", "ledger_entries", type_="check")
    op.drop_column("ledger_entries", "is_reversal")
    op.drop_index("uq_ledger_postings_active_expense", table_name="ledger_postings")
    op.drop_index("ix_ledger_postings_project_id", table_name="ledger_postings")
    op.drop_index("ix_ledger_postings_expense_id", table_name="ledger_postings")
    op.drop_table("ledger_postings")
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")
