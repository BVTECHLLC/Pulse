"""v0.43 native CRM (contacts/leads + activity timeline)

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-06-30 07:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'crm_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('company', sa.String(length=200), nullable=True),
        sa.Column('title', sa.String(length=160), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('market', sa.String(length=60), nullable=True),
        sa.Column('website', sa.String(length=300), nullable=True),
        sa.Column('address', sa.String(length=300), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('do_not_contact', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sms_opt_in', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_touch_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crm_contacts_email', 'crm_contacts', ['email'])
    op.create_index('ix_crm_contacts_company', 'crm_contacts', ['company'])
    op.create_index('ix_crm_contacts_status', 'crm_contacts', ['status'])
    op.create_index('ix_crm_contacts_client_id', 'crm_contacts', ['client_id'])

    op.create_table(
        'crm_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=True),
        sa.Column('subject', sa.String(length=300), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['contact_id'], ['crm_contacts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crm_activities_contact_id', 'crm_activities', ['contact_id'])
    op.create_index('ix_crm_activities_created_at', 'crm_activities', ['created_at'])


def downgrade():
    op.drop_index('ix_crm_activities_created_at', table_name='crm_activities')
    op.drop_index('ix_crm_activities_contact_id', table_name='crm_activities')
    op.drop_table('crm_activities')
    op.drop_index('ix_crm_contacts_client_id', table_name='crm_contacts')
    op.drop_index('ix_crm_contacts_status', table_name='crm_contacts')
    op.drop_index('ix_crm_contacts_company', table_name='crm_contacts')
    op.drop_index('ix_crm_contacts_email', table_name='crm_contacts')
    op.drop_table('crm_contacts')
