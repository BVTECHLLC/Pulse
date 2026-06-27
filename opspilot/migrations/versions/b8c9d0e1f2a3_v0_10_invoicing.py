"""v0.10 invoicing

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-28 00:50:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('time_entries', sa.Column('invoiced', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('time_entries', sa.Column('invoice_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_time_entries_invoiced'), 'time_entries', ['invoiced'], unique=False)
    op.create_index(op.f('ix_time_entries_invoice_id'), 'time_entries', ['invoice_id'], unique=False)

    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'SENT', 'PAID', 'VOID', name='invoicestatus'), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subtotal', sa.Float(), nullable=False),
        sa.Column('tax_rate', sa.Float(), nullable=False),
        sa.Column('tax_amount', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoices_client_id'), 'invoices', ['client_id'], unique=False)
    op.create_index(op.f('ix_invoices_number'), 'invoices', ['number'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)
    op.create_index(op.f('ix_invoices_created_at'), 'invoices', ['created_at'], unique=False)

    op.create_table(
        'invoice_line_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoice_line_items_invoice_id'), 'invoice_line_items', ['invoice_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_invoice_line_items_invoice_id'), table_name='invoice_line_items')
    op.drop_table('invoice_line_items')
    for ix in ('ix_invoices_created_at', 'ix_invoices_status', 'ix_invoices_number', 'ix_invoices_client_id'):
        op.drop_index(op.f(ix), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_time_entries_invoice_id'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_invoiced'), table_name='time_entries')
    op.drop_column('time_entries', 'invoice_id')
    op.drop_column('time_entries', 'invoiced')
