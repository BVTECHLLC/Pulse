"""v0.4 SLA tracking, time entries, knowledge base

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-27 22:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # SLA tracking columns on the existing tickets table.
    op.add_column('support_tickets', sa.Column('first_response_due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('support_tickets', sa.Column('resolution_due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('support_tickets', sa.Column('first_responded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('support_tickets', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'sla_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('response_minutes', sa.Integer(), nullable=False),
        sa.Column('resolution_minutes', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sla_policies_client_id'), 'sla_policies', ['client_id'], unique=False)

    op.create_table(
        'time_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_email', sa.String(length=200), nullable=True),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('billable', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_time_entries_ticket_id'), 'time_entries', ['ticket_id'], unique=False)
    op.create_index(op.f('ix_time_entries_client_id'), 'time_entries', ['client_id'], unique=False)
    op.create_index(op.f('ix_time_entries_created_at'), 'time_entries', ['created_at'], unique=False)

    op.create_table(
        'kb_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(length=20), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_kb_articles_client_id'), 'kb_articles', ['client_id'], unique=False)
    op.create_index(op.f('ix_kb_articles_category'), 'kb_articles', ['category'], unique=False)
    op.create_index(op.f('ix_kb_articles_visibility'), 'kb_articles', ['visibility'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_kb_articles_visibility'), table_name='kb_articles')
    op.drop_index(op.f('ix_kb_articles_category'), table_name='kb_articles')
    op.drop_index(op.f('ix_kb_articles_client_id'), table_name='kb_articles')
    op.drop_table('kb_articles')
    op.drop_index(op.f('ix_time_entries_created_at'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_client_id'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_ticket_id'), table_name='time_entries')
    op.drop_table('time_entries')
    op.drop_index(op.f('ix_sla_policies_client_id'), table_name='sla_policies')
    op.drop_table('sla_policies')
    op.drop_column('support_tickets', 'resolved_at')
    op.drop_column('support_tickets', 'first_responded_at')
    op.drop_column('support_tickets', 'resolution_due_at')
    op.drop_column('support_tickets', 'first_response_due_at')
