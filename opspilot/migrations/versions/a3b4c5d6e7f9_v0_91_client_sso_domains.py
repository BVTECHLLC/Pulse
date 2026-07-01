"""v0.91 client.sso_domains (explicit SSO auto-provision domains)

Revision ID: a3b4c5d6e7f9
Revises: f2a3b4c5d6e8
Create Date: 2026-07-01 06:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3b4c5d6e7f9'
down_revision = 'f2a3b4c5d6e8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clients', sa.Column('sso_domains', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('clients', 'sso_domains')
