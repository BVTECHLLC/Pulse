"""v0.52 integration health watchdog columns

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-30 15:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('integration_connections', sa.Column('last_health_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('integration_connections', sa.Column('last_health_ok', sa.Boolean(), nullable=True))
    op.add_column('integration_connections', sa.Column('last_health_error', sa.String(length=300), nullable=True))


def downgrade():
    op.drop_column('integration_connections', 'last_health_error')
    op.drop_column('integration_connections', 'last_health_ok')
    op.drop_column('integration_connections', 'last_health_at')
