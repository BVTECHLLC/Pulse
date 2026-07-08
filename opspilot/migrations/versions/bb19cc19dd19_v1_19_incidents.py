"""v1.19 incidents — alert-storm correlation (one incident, one ticket)

Revision ID: bb19cc19dd19
Revises: aa17bb17cc17
Create Date: 2026-07-08 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'bb19cc19dd19'
down_revision = 'aa17bb17cc17'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=220), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('severity', sa.String(length=16), nullable=False, server_default='critical'),
        sa.Column('alert_ids', sa.JSON(), nullable=True),
        sa.Column('alert_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ticket_id', sa.Integer(), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    for col in ('client_id', 'kind', 'status'):
        op.create_index(f'ix_incidents_{col}', 'incidents', [col])


def downgrade():
    for col in ('client_id', 'kind', 'status'):
        op.drop_index(f'ix_incidents_{col}', table_name='incidents')
    op.drop_table('incidents')
