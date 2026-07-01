"""v0.84 public status page incidents

Revision ID: e1f2a3b4c5d7
Revises: d0e1f2a3b4c6
Create Date: 2026-07-01 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d7'
down_revision = 'd0e1f2a3b4c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'status_incidents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='investigating'),
        sa.Column('impact', sa.String(length=20), nullable=False, server_default='minor'),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_status_incidents_status', 'status_incidents', ['status'])
    op.create_index('ix_status_incidents_started_at', 'status_incidents', ['started_at'])


def downgrade():
    op.drop_index('ix_status_incidents_started_at', table_name='status_incidents')
    op.drop_index('ix_status_incidents_status', table_name='status_incidents')
    op.drop_table('status_incidents')
