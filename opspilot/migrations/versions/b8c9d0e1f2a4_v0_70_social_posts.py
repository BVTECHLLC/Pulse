"""v0.70 social posts (auto-post queue)

Revision ID: b8c9d0e1f2a4
Revises: a7b8c9d0e1f3
Create Date: 2026-07-01 01:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a4'
down_revision = 'a7b8c9d0e1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'social_posts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('channels', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', sa.String(length=400), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_social_posts_status', 'social_posts', ['status'])
    op.create_index('ix_social_posts_created_at', 'social_posts', ['created_at'])


def downgrade():
    op.drop_table('social_posts')
