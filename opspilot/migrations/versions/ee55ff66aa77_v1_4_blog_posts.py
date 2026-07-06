"""v1.4 blog_posts — WordPress auto-blogger history

Revision ID: ee55ff66aa77
Revises: dd44ee55ff66
Create Date: 2026-07-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'ee55ff66aa77'
down_revision = 'dd44ee55ff66'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'blog_posts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=220), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('html', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('wp_post_id', sa.Integer(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('error', sa.String(length=400), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_blog_posts_status', 'blog_posts', ['status'])
    op.create_index('ix_blog_posts_created_at', 'blog_posts', ['created_at'])


def downgrade():
    op.drop_index('ix_blog_posts_created_at', table_name='blog_posts')
    op.drop_index('ix_blog_posts_status', table_name='blog_posts')
    op.drop_table('blog_posts')
