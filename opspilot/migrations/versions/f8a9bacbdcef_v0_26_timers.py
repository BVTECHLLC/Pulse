"""v0.26 time tracking: timers + task time

Revision ID: f8a9bacbdcef
Revises: e7f8a9bacbdc
Create Date: 2026-06-28 21:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f8a9bacbdcef'
down_revision = 'e7f8a9bacbdc'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'active_timers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_email', sa.String(length=200), nullable=True),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('billable', sa.Boolean(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['project_tasks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_active_timer_user'),
    )
    op.create_index(op.f('ix_active_timers_user_id'), 'active_timers', ['user_id'], unique=False)
    op.create_index(op.f('ix_active_timers_client_id'), 'active_timers', ['client_id'], unique=False)

    # time_entries: ticket_id becomes nullable, add task_id (+ index + FK).
    with op.batch_alter_table('time_entries', schema=None) as batch:
        batch.add_column(sa.Column('task_id', sa.Integer(), nullable=True))
        batch.alter_column('ticket_id', existing_type=sa.Integer(), nullable=True)
        batch.create_index(op.f('ix_time_entries_task_id'), ['task_id'], unique=False)
        batch.create_foreign_key('fk_time_entries_task_id', 'project_tasks', ['task_id'], ['id'])


def downgrade():
    with op.batch_alter_table('time_entries', schema=None) as batch:
        batch.drop_constraint('fk_time_entries_task_id', type_='foreignkey')
        batch.drop_index(op.f('ix_time_entries_task_id'))
        batch.alter_column('ticket_id', existing_type=sa.Integer(), nullable=False)
        batch.drop_column('task_id')

    op.drop_index(op.f('ix_active_timers_client_id'), table_name='active_timers')
    op.drop_index(op.f('ix_active_timers_user_id'), table_name='active_timers')
    op.drop_table('active_timers')
