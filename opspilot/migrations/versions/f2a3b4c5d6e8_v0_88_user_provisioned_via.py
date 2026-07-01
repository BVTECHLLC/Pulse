"""v0.88 user.provisioned_via (SSO self-registration flag)

Revision ID: f2a3b4c5d6e8
Revises: e1f2a3b4c5d7
Create Date: 2026-07-01 05:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c5d6e8'
down_revision = 'e1f2a3b4c5d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('provisioned_via', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('users', 'provisioned_via')
