"""v0.47 remote sessions (native WebRTC remote-desktop signaling)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-30 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'remote_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('operator_user_id', sa.Integer(), nullable=True),
        sa.Column('operator_email', sa.String(length=200), nullable=True),
        sa.Column('agent_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('operator_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index('ix_remote_sessions_device_id', 'remote_sessions', ['device_id'])
    op.create_index('ix_remote_sessions_client_id', 'remote_sessions', ['client_id'])
    op.create_index('ix_remote_sessions_token', 'remote_sessions', ['token'], unique=True)
    op.create_index('ix_remote_sessions_status', 'remote_sessions', ['status'])
    op.create_index('ix_remote_sessions_created_at', 'remote_sessions', ['created_at'])


def downgrade():
    op.drop_index('ix_remote_sessions_created_at', table_name='remote_sessions')
    op.drop_index('ix_remote_sessions_status', table_name='remote_sessions')
    op.drop_index('ix_remote_sessions_token', table_name='remote_sessions')
    op.drop_index('ix_remote_sessions_client_id', table_name='remote_sessions')
    op.drop_index('ix_remote_sessions_device_id', table_name='remote_sessions')
    op.drop_table('remote_sessions')
