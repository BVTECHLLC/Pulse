"""v0.71 social post image_url (Google Business photos)

Revision ID: c9d0e1f2a3b5
Revises: b8c9d0e1f2a4
Create Date: 2026-07-01 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b5'
down_revision = 'b8c9d0e1f2a4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_posts', sa.Column('image_url', sa.String(length=800), nullable=True))


def downgrade():
    op.drop_column('social_posts', 'image_url')
