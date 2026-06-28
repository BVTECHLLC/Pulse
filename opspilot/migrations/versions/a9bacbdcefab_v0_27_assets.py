"""v0.27 asset management (CMDB)

Revision ID: a9bacbdcefab
Revises: f8a9bacbdcef
Create Date: 2026-06-28 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9bacbdcefab'
down_revision = 'f8a9bacbdcef'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('asset_type', sa.String(length=30), nullable=False),
        sa.Column('make', sa.String(length=120), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('serial', sa.String(length=120), nullable=True),
        sa.Column('asset_tag', sa.String(length=80), nullable=True),
        sa.Column('location', sa.String(length=160), nullable=True),
        sa.Column('assigned_to', sa.String(length=160), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('warranty_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_assets_client_id'), 'assets', ['client_id'], unique=False)
    op.create_index(op.f('ix_assets_asset_type'), 'assets', ['asset_type'], unique=False)
    op.create_index(op.f('ix_assets_serial'), 'assets', ['serial'], unique=False)
    op.create_index(op.f('ix_assets_asset_tag'), 'assets', ['asset_tag'], unique=False)
    op.create_index(op.f('ix_assets_status'), 'assets', ['status'], unique=False)
    op.create_index(op.f('ix_assets_warranty_expires'), 'assets', ['warranty_expires'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_assets_warranty_expires'), table_name='assets')
    op.drop_index(op.f('ix_assets_status'), table_name='assets')
    op.drop_index(op.f('ix_assets_asset_tag'), table_name='assets')
    op.drop_index(op.f('ix_assets_serial'), table_name='assets')
    op.drop_index(op.f('ix_assets_asset_type'), table_name='assets')
    op.drop_index(op.f('ix_assets_client_id'), table_name='assets')
    op.drop_table('assets')
