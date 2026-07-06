"""v1.2 Pulse Cyber Academy — profiles + completions

Revision ID: bb22cc33dd44
Revises: aa11bb22cc33
Create Date: 2026-07-03 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'bb22cc33dd44'
down_revision = 'aa11bb22cc33'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'academy_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('xp', sa.Integer(), nullable=True),
        sa.Column('streak_days', sa.Integer(), nullable=True),
        sa.Column('last_active_on', sa.Date(), nullable=True),
        sa.Column('badges', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_academy_profiles_user_id', 'academy_profiles', ['user_id'], unique=True)
    op.create_table(
        'academy_completions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('item_id', sa.String(length=60), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('xp', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_academy_completions_user_id', 'academy_completions', ['user_id'])
    op.create_index('ix_academy_completions_item_id', 'academy_completions', ['item_id'])
    op.create_index('ix_academy_completions_created_at', 'academy_completions', ['created_at'])


def downgrade():
    op.drop_index('ix_academy_completions_created_at', table_name='academy_completions')
    op.drop_index('ix_academy_completions_item_id', table_name='academy_completions')
    op.drop_index('ix_academy_completions_user_id', table_name='academy_completions')
    op.drop_table('academy_completions')
    op.drop_index('ix_academy_profiles_user_id', table_name='academy_profiles')
    op.drop_table('academy_profiles')
