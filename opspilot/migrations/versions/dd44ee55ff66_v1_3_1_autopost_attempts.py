"""v1.3.1 social_posts.attempts (publish retry counter)

Revision ID: dd44ee55ff66
Revises: cc33dd44ee55
Create Date: 2026-07-06 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'dd44ee55ff66'
down_revision = 'cc33dd44ee55'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_posts', sa.Column('attempts', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('social_posts', 'attempts')
