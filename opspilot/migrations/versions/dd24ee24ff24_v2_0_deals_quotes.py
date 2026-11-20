"""v2.0 deals + quotes — native sales engine (pipeline + signable quotes)

Revision ID: dd24ee24ff24
Revises: cc23dd23ee23
Create Date: 2026-11-20 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'dd24ee24ff24'
down_revision = 'cc23dd23ee23'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('crm_contacts.id'), nullable=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('value', sa.Float(), nullable=False, server_default='0'),
        sa.Column('stage', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('probability', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('expected_close', sa.Date(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.Column('lost_reason', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('won_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lost_at', sa.DateTime(timezone=True), nullable=True),
    )
    for col in ('contact_id', 'client_id', 'stage', 'created_at'):
        op.create_index(f'ix_deals_{col}', 'deals', [col])

    op.create_table(
        'quotes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deal_id', sa.Integer(), sa.ForeignKey('deals.id'), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='USD'),
        sa.Column('line_items', sa.JSON(), nullable=True),
        sa.Column('onboarding_fee', sa.Float(), nullable=False, server_default='0'),
        sa.Column('subtotal', sa.Float(), nullable=False, server_default='0'),
        sa.Column('tax_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total', sa.Float(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('public_token', sa.String(length=64), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_name', sa.String(length=200), nullable=True),
        sa.Column('accepted_title', sa.String(length=160), nullable=True),
        sa.Column('accepted_ip', sa.String(length=64), nullable=True),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('onboarding_invoice_id', sa.Integer(), sa.ForeignKey('invoices.id'), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    for col in ('deal_id', 'number', 'status', 'created_at'):
        op.create_index(f'ix_quotes_{col}', 'quotes', [col])
    op.create_index('ix_quotes_public_token', 'quotes', ['public_token'], unique=True)


def downgrade():
    op.drop_index('ix_quotes_public_token', table_name='quotes')
    for col in ('deal_id', 'number', 'status', 'created_at'):
        op.drop_index(f'ix_quotes_{col}', table_name='quotes')
    op.drop_table('quotes')
    for col in ('contact_id', 'client_id', 'stage', 'created_at'):
        op.drop_index(f'ix_deals_{col}', table_name='deals')
    op.drop_table('deals')
