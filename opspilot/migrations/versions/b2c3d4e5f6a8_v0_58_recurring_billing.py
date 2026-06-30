"""v0.58 recurring billing fields on contracts

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-30 19:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('contracts', sa.Column('auto_invoice', sa.Boolean(), nullable=False,
                                         server_default=sa.false()))
    op.add_column('contracts', sa.Column('last_invoiced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('contracts', 'last_invoiced_at')
    op.drop_column('contracts', 'auto_invoice')
