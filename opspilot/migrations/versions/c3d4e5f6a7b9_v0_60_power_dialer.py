"""v0.60 power dialer + call coaching tables

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-06-30 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b9'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'call_scripts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('opening', sa.Text(), nullable=True),
        sa.Column('talking_points', sa.JSON(), nullable=True),
        sa.Column('objections', sa.JSON(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_call_scripts_active', 'call_scripts', ['active'])

    op.create_table(
        'dial_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('script_id', sa.Integer(), sa.ForeignKey('call_scripts.id'), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_dial_sessions_status', 'dial_sessions', ['status'])
    op.create_index('ix_dial_sessions_owner_user_id', 'dial_sessions', ['owner_user_id'])
    op.create_index('ix_dial_sessions_created_at', 'dial_sessions', ['created_at'])

    op.create_table(
        'dial_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('dial_sessions.id'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=False),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('crm_contact_id', sa.Integer(), sa.ForeignKey('crm_contacts.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('disposition', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('call_id', sa.String(length=80), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('dialed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_dial_entries_session_id', 'dial_entries', ['session_id'])
    op.create_index('ix_dial_entries_position', 'dial_entries', ['position'])
    op.create_index('ix_dial_entries_status', 'dial_entries', ['status'])
    op.create_index('ix_dial_entries_client_id', 'dial_entries', ['client_id'])
    op.create_index('ix_dial_entries_crm_contact_id', 'dial_entries', ['crm_contact_id'])


def downgrade():
    op.drop_table('dial_entries')
    op.drop_table('dial_sessions')
    op.drop_table('call_scripts')
