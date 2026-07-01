"""v0.78 ticket CSAT fields

Revision ID: d0e1f2a3b4c6
Revises: c9d0e1f2a3b5
Create Date: 2026-07-01 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a3b4c6'
down_revision = 'c9d0e1f2a3b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('support_tickets', sa.Column('csat_rating', sa.Integer(), nullable=True))
    op.add_column('support_tickets', sa.Column('csat_comment', sa.Text(), nullable=True))
    op.add_column('support_tickets', sa.Column('csat_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('support_tickets', 'csat_at')
    op.drop_column('support_tickets', 'csat_comment')
    op.drop_column('support_tickets', 'csat_rating')
