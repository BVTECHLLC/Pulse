"""v1.23 browser_items + browser_policies — Browser & SaaS Guardian

Revision ID: cc23dd23ee23
Revises: bb19cc19dd19
Create Date: 2026-07-09 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'cc23dd23ee23'
down_revision = 'bb19cc19dd19'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'browser_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('device_id', sa.Integer(), sa.ForeignKey('devices.id'), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('browser', sa.String(length=20), nullable=True),
        sa.Column('identifier', sa.String(length=200), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('version', sa.String(length=40), nullable=True),
        sa.Column('permissions', sa.String(length=500), nullable=True),
        sa.Column('hits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    )
    for col in ('client_id', 'device_id', 'kind', 'identifier'):
        op.create_index(f'ix_browser_items_{col}', 'browser_items', [col])
    op.create_table(
        'browser_policies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('decisions', sa.JSON(), nullable=True),
        sa.Column('protect', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_browser_policies_client_id', 'browser_policies',
                    ['client_id'], unique=True)


def downgrade():
    op.drop_index('ix_browser_policies_client_id', table_name='browser_policies')
    op.drop_table('browser_policies')
    for col in ('client_id', 'device_id', 'kind', 'identifier'):
        op.drop_index(f'ix_browser_items_{col}', table_name='browser_items')
    op.drop_table('browser_items')
