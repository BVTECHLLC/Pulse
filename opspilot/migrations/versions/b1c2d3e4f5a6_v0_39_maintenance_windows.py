"""v0.39 maintenance windows (suppress alerts during planned maintenance)

Revision ID: b1c2d3e4f5a6
Revises: a9bacbdcefab
Create Date: 2026-06-30 05:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = 'a9bacbdcefab'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_windows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_maintenance_windows_client_id', 'maintenance_windows', ['client_id'])
    op.create_index('ix_maintenance_windows_device_id', 'maintenance_windows', ['device_id'])
    op.create_index('ix_maintenance_windows_starts_at', 'maintenance_windows', ['starts_at'])
    op.create_index('ix_maintenance_windows_ends_at', 'maintenance_windows', ['ends_at'])


def downgrade():
    op.drop_index('ix_maintenance_windows_ends_at', table_name='maintenance_windows')
    op.drop_index('ix_maintenance_windows_starts_at', table_name='maintenance_windows')
    op.drop_index('ix_maintenance_windows_device_id', table_name='maintenance_windows')
    op.drop_index('ix_maintenance_windows_client_id', table_name='maintenance_windows')
    op.drop_table('maintenance_windows')
