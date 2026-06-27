"""v0.8 public signup / access requests

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-27 23:58:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'signup_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_signup_requests_email'), 'signup_requests', ['email'], unique=False)
    op.create_index(op.f('ix_signup_requests_status'), 'signup_requests', ['status'], unique=False)
    op.create_index(op.f('ix_signup_requests_created_at'), 'signup_requests', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_signup_requests_created_at'), table_name='signup_requests')
    op.drop_index(op.f('ix_signup_requests_status'), table_name='signup_requests')
    op.drop_index(op.f('ix_signup_requests_email'), table_name='signup_requests')
    op.drop_table('signup_requests')
