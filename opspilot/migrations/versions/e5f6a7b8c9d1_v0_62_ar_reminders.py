"""v0.62 A/R payment-reminder fields on invoices

Revision ID: e5f6a7b8c9d1
Revises: d4e5f6a7b8c0
Create Date: 2026-06-30 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d1'
down_revision = 'd4e5f6a7b8c0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('last_reminded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('reminder_count', sa.Integer(), nullable=False,
                                       server_default='0'))


def downgrade():
    op.drop_column('invoices', 'reminder_count')
    op.drop_column('invoices', 'last_reminded_at')
