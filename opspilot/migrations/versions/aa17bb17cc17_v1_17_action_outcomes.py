"""v1.17 action_outcomes — the Autonomy Engine's self-audit ledger

Revision ID: aa17bb17cc17
Revises: ff66aa77bb88
Create Date: 2026-07-08 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'aa17bb17cc17'
down_revision = 'ff66aa77bb88'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'action_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('action_type', sa.String(length=40), nullable=False),
        sa.Column('playbook', sa.String(length=160), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('ref_kind', sa.String(length=20), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        sa.Column('autonomous', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('grade_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('graded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verdict', sa.String(length=16), nullable=True),
        sa.Column('evidence', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    for col in ('action_type', 'playbook', 'client_id', 'device_id', 'ref_id',
                'autonomous', 'taken_at', 'verdict'):
        op.create_index(f'ix_action_outcomes_{col}', 'action_outcomes', [col])


def downgrade():
    for col in ('action_type', 'playbook', 'client_id', 'device_id', 'ref_id',
                'autonomous', 'taken_at', 'verdict'):
        op.drop_index(f'ix_action_outcomes_{col}', table_name='action_outcomes')
    op.drop_table('action_outcomes')
