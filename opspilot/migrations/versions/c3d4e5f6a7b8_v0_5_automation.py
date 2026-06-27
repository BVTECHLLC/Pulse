"""v0.5 automation engine: rules, runs, notifications

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-27 22:45:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('support_tickets',
                  sa.Column('sla_breach_alerted', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'automation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('trigger', sa.String(length=40), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('actions', sa.JSON(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trigger_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_automation_rules_enabled'), 'automation_rules', ['enabled'], unique=False)
    op.create_index(op.f('ix_automation_rules_trigger'), 'automation_rules', ['trigger'], unique=False)
    op.create_index(op.f('ix_automation_rules_client_id'), 'automation_rules', ['client_id'], unique=False)

    op.create_table(
        'automation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=True),
        sa.Column('rule_name', sa.String(length=200), nullable=True),
        sa.Column('trigger', sa.String(length=40), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_automation_runs_rule_id'), 'automation_runs', ['rule_id'], unique=False)
    op.create_index(op.f('ix_automation_runs_trigger'), 'automation_runs', ['trigger'], unique=False)
    op.create_index(op.f('ix_automation_runs_client_id'), 'automation_runs', ['client_id'], unique=False)
    op.create_index(op.f('ix_automation_runs_created_at'), 'automation_runs', ['created_at'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('target_user_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_client_id'), 'notifications', ['client_id'], unique=False)
    op.create_index(op.f('ix_notifications_target_user_id'), 'notifications', ['target_user_id'], unique=False)
    op.create_index(op.f('ix_notifications_read'), 'notifications', ['read'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)


def downgrade():
    for ix in ('ix_notifications_created_at', 'ix_notifications_read',
               'ix_notifications_target_user_id', 'ix_notifications_client_id'):
        op.drop_index(op.f(ix), table_name='notifications')
    op.drop_table('notifications')
    for ix in ('ix_automation_runs_created_at', 'ix_automation_runs_client_id',
               'ix_automation_runs_trigger', 'ix_automation_runs_rule_id'):
        op.drop_index(op.f(ix), table_name='automation_runs')
    op.drop_table('automation_runs')
    for ix in ('ix_automation_rules_client_id', 'ix_automation_rules_trigger',
               'ix_automation_rules_enabled'):
        op.drop_index(op.f(ix), table_name='automation_rules')
    op.drop_table('automation_rules')
    op.drop_column('support_tickets', 'sla_breach_alerted')
