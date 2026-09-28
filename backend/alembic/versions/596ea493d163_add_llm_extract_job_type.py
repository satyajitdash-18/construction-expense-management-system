"""Add LLM_EXTRACT job type

Revision ID: 596ea493d163
Revises: c6f41d757b90
Create Date: 2026-09-21 08:11:15.260185

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '596ea493d163'
down_revision: str | None = 'c6f41d757b90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create job_type enum if not exists
    job_type_enum = postgresql.ENUM(
        'MEDIA_DOWNLOAD', 'OCR', 'LLM_EXTRACT', 'RECONCILE', 'NOTIFY_WHATSAPP',
        name='job_type', create_constraint=True
    )
    job_type_enum.create(op.get_bind(), checkfirst=True)

    # Alter job_type column to use the enum
    op.alter_column('processing_jobs', 'job_type',
               existing_type=sa.VARCHAR(length=15),
               type_=job_type_enum,
               postgresql_using="job_type::job_type",
               existing_nullable=False)

    # Create job_status enum if not exists
    job_status_enum = postgresql.ENUM(
        'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'RETRYING',
        name='job_status', create_constraint=True
    )
    job_status_enum.create(op.get_bind(), checkfirst=True)

    # Alter status column to use the enum
    op.alter_column('processing_jobs', 'status',
               existing_type=sa.VARCHAR(length=9),
               type_=job_status_enum,
               postgresql_using="status::job_status",
               existing_nullable=False)

    # Drop index
    op.drop_index('ix_processing_jobs_type_status', table_name='processing_jobs')


def downgrade() -> None:
    # Cannot easily remove enum values
    pass