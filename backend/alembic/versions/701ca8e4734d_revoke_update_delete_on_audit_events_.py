"""revoke update delete on audit_events for app role

Revision ID: 701ca8e4734d
Revises: 2104e97b75b2
Create Date: 2026-09-20 22:03:36.838641
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '701ca8e4734d'
down_revision: str | None = '2104e97b75b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Get the current database user (the app role)
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT current_user")).scalar()
    app_role = result

    # Revoke UPDATE and DELETE on audit_events for the app role
    op.execute(f'REVOKE UPDATE, DELETE ON audit_events FROM "{app_role}"')

    # Also revoke TRUNCATE for completeness
    op.execute(f'REVOKE TRUNCATE ON audit_events FROM "{app_role}"')


def downgrade() -> None:
    # Grant back UPDATE, DELETE, TRUNCATE on audit_events
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT current_user")).scalar()
    app_role = result

    op.execute(f'GRANT UPDATE, DELETE, TRUNCATE ON audit_events TO "{app_role}"')