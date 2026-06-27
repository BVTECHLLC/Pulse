"""v0.9 Microsoft 365 connections

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-28 00:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'm365_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('access_token_enc', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('secure_score', sa.Integer(), nullable=True),
        sa.Column('secure_score_max', sa.Integer(), nullable=True),
        sa.Column('license_count', sa.Integer(), nullable=True),
        sa.Column('risky_signin_count', sa.Integer(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.String(length=200), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id'),
    )
    op.create_index(op.f('ix_m365_connections_client_id'), 'm365_connections', ['client_id'], unique=False)
    op.create_index(op.f('ix_m365_connections_status'), 'm365_connections', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_m365_connections_status'), table_name='m365_connections')
    op.drop_index(op.f('ix_m365_connections_client_id'), table_name='m365_connections')
    op.drop_table('m365_connections')
