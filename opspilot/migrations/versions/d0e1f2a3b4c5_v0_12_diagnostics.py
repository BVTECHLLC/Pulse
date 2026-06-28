"""v0.12 network diagnostics requests

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-28 02:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'diagnostic_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('target', sa.String(length=200), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('requested_by_email', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_diagnostic_requests_client_id'), 'diagnostic_requests', ['client_id'], unique=False)
    op.create_index(op.f('ix_diagnostic_requests_device_id'), 'diagnostic_requests', ['device_id'], unique=False)
    op.create_index(op.f('ix_diagnostic_requests_status'), 'diagnostic_requests', ['status'], unique=False)
    op.create_index(op.f('ix_diagnostic_requests_created_at'), 'diagnostic_requests', ['created_at'], unique=False)


def downgrade():
    for ix in ('ix_diagnostic_requests_created_at', 'ix_diagnostic_requests_status',
               'ix_diagnostic_requests_device_id', 'ix_diagnostic_requests_client_id'):
        op.drop_index(op.f(ix), table_name='diagnostic_requests')
    op.drop_table('diagnostic_requests')
