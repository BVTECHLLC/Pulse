"""v0.54 client documentation & password vault

Revision ID: a1b2c3d4e5f7
Revises: f4a5b6c7d8e9
Create Date: 2026-06-30 18:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f7'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='article'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('username', sa.String(length=200), nullable=True),
        sa.Column('url', sa.String(length=400), nullable=True),
        sa.Column('secret_enc', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_client_id', 'documents', ['client_id'])
    op.create_index('ix_documents_kind', 'documents', ['kind'])


def downgrade():
    op.drop_index('ix_documents_kind', table_name='documents')
    op.drop_index('ix_documents_client_id', table_name='documents')
    op.drop_table('documents')
