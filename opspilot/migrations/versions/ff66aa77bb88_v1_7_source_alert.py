"""v1.7 support_tickets.source_alert_id (auto-ticket dedup)

Revision ID: ff66aa77bb88
Revises: ee55ff66aa77
Create Date: 2026-07-07 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'ff66aa77bb88'
down_revision = 'ee55ff66aa77'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('support_tickets', sa.Column('source_alert_id', sa.Integer(), nullable=True))
    op.create_index('ix_support_tickets_source_alert_id', 'support_tickets', ['source_alert_id'])


def downgrade():
    op.drop_index('ix_support_tickets_source_alert_id', table_name='support_tickets')
    op.drop_column('support_tickets', 'source_alert_id')
