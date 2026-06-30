"""v0.67 posture snapshots table

Revision ID: a7b8c9d0e1f3
Revises: f6a7b8c9d0e2
Create Date: 2026-07-01 00:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f3'
down_revision = 'f6a7b8c9d0e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'posture_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('grade', sa.String(length=4), nullable=False, server_default='N/A'),
        sa.Column('domains', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_posture_snapshots_client_id', 'posture_snapshots', ['client_id'])
    op.create_index('ix_posture_snapshots_created_at', 'posture_snapshots', ['created_at'])


def downgrade():
    op.drop_table('posture_snapshots')
