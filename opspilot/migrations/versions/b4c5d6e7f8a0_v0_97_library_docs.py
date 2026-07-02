"""v0.97 document library catalog

Revision ID: b4c5d6e7f8a0
Revises: a3b4c5d6e7f9
Create Date: 2026-07-02 07:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c5d6e7f8a0'
down_revision = 'a3b4c5d6e7f9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'library_docs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('doc_id', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=20), server_default=''),
        sa.Column('category_label', sa.String(length=80), server_default=''),
        sa.Column('visibility', sa.String(length=20), nullable=False, server_default='internal'),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_library_docs_doc_id', 'library_docs', ['doc_id'], unique=True)
    op.create_index('ix_library_docs_category', 'library_docs', ['category'])
    op.create_index('ix_library_docs_visibility', 'library_docs', ['visibility'])


def downgrade():
    op.drop_index('ix_library_docs_visibility', table_name='library_docs')
    op.drop_index('ix_library_docs_category', table_name='library_docs')
    op.drop_index('ix_library_docs_doc_id', table_name='library_docs')
    op.drop_table('library_docs')
