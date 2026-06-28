"""v0.15 notification channels

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-28 03:20:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('target', sa.Text(), nullable=False),
        sa.Column('min_severity', sa.String(length=20), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notification_channels_client_id'), 'notification_channels', ['client_id'], unique=False)
    op.create_index(op.f('ix_notification_channels_enabled'), 'notification_channels', ['enabled'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_notification_channels_enabled'), table_name='notification_channels')
    op.drop_index(op.f('ix_notification_channels_client_id'), table_name='notification_channels')
    op.drop_table('notification_channels')
