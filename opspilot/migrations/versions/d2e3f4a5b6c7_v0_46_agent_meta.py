"""v0.46 device agent metadata (agent_version, platform)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-30 13:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('devices', sa.Column('agent_version', sa.String(length=40), nullable=True))
    op.add_column('devices', sa.Column('platform', sa.String(length=40), nullable=True))


def downgrade():
    op.drop_column('devices', 'platform')
    op.drop_column('devices', 'agent_version')
