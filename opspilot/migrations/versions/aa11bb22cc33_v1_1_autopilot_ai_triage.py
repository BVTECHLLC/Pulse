"""v1.1 Autopilot scheduler runs + AI ticket triage columns

Revision ID: aa11bb22cc33
Revises: b4c5d6e7f8a0
Create Date: 2026-07-03 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'aa11bb22cc33'
down_revision = 'b4c5d6e7f8a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scheduler_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ran_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(length=10), nullable=True),
        sa.Column('ok', sa.Boolean(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
    )
    op.create_index('ix_scheduler_runs_ran_at', 'scheduler_runs', ['ran_at'])
    op.add_column('support_tickets', sa.Column('ai_priority', sa.String(length=20), nullable=True))
    op.add_column('support_tickets', sa.Column('ai_summary', sa.Text(), nullable=True))
    op.add_column('support_tickets', sa.Column('ai_next_step', sa.Text(), nullable=True))
    op.add_column('support_tickets', sa.Column('ai_triaged_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('support_tickets', 'ai_triaged_at')
    op.drop_column('support_tickets', 'ai_next_step')
    op.drop_column('support_tickets', 'ai_summary')
    op.drop_column('support_tickets', 'ai_priority')
    op.drop_index('ix_scheduler_runs_ran_at', table_name='scheduler_runs')
    op.drop_table('scheduler_runs')
