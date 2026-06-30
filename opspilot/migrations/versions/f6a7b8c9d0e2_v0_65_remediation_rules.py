"""v0.65 auto-remediation rules table

Revision ID: f6a7b8c9d0e2
Revises: e5f6a7b8c9d1
Create Date: 2026-06-30 23:45:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e2'
down_revision = 'e5f6a7b8c9d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'remediation_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('alert_kind', sa.String(length=40), nullable=False),
        sa.Column('script_id', sa.Integer(), sa.ForeignKey('scripts.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('max_per_day', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fire_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_remediation_rules_alert_kind', 'remediation_rules', ['alert_kind'])
    op.create_index('ix_remediation_rules_client_id', 'remediation_rules', ['client_id'])
    op.create_index('ix_remediation_rules_enabled', 'remediation_rules', ['enabled'])


def downgrade():
    op.drop_table('remediation_rules')
