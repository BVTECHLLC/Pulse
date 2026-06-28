"""v0.19 device software inventory

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-06-28 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'device_software',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('version', sa.String(length=120), nullable=True),
        sa.Column('publisher', sa.String(length=200), nullable=True),
        sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'name', 'version', name='uq_device_software'),
    )
    op.create_index(op.f('ix_device_software_device_id'), 'device_software', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_software_client_id'), 'device_software', ['client_id'], unique=False)
    op.create_index(op.f('ix_device_software_name'), 'device_software', ['name'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_device_software_name'), table_name='device_software')
    op.drop_index(op.f('ix_device_software_client_id'), table_name='device_software')
    op.drop_index(op.f('ix_device_software_device_id'), table_name='device_software')
    op.drop_table('device_software')
