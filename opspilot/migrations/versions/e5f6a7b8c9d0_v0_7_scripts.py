"""v0.7 script library + deployment governance

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27 23:40:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scripts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_scripts_category'), 'scripts', ['category'], unique=False)
    op.create_index(op.f('ix_scripts_enabled'), 'scripts', ['enabled'], unique=False)

    op.create_table(
        'script_deployments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('script_id', sa.Integer(), nullable=True),
        sa.Column('script_name', sa.String(length=200), nullable=False),
        sa.Column('script_version', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING_APPROVAL', 'APPROVED', 'RUNNING', 'SUCCEEDED',
                                    'FAILED', 'REJECTED', 'CANCELED', name='deploymentstatus'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('consent_ack', sa.Boolean(), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('requested_by_email', sa.String(length=200), nullable=True),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('approved_by_email', sa.String(length=200), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['script_id'], ['scripts.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_script_deployments_script_id'), 'script_deployments', ['script_id'], unique=False)
    op.create_index(op.f('ix_script_deployments_device_id'), 'script_deployments', ['device_id'], unique=False)
    op.create_index(op.f('ix_script_deployments_client_id'), 'script_deployments', ['client_id'], unique=False)
    op.create_index(op.f('ix_script_deployments_status'), 'script_deployments', ['status'], unique=False)
    op.create_index(op.f('ix_script_deployments_created_at'), 'script_deployments', ['created_at'], unique=False)


def downgrade():
    for ix in ('ix_script_deployments_created_at', 'ix_script_deployments_status',
               'ix_script_deployments_client_id', 'ix_script_deployments_device_id',
               'ix_script_deployments_script_id'):
        op.drop_index(op.f(ix), table_name='script_deployments')
    op.drop_table('script_deployments')
    op.drop_index(op.f('ix_scripts_enabled'), table_name='scripts')
    op.drop_index(op.f('ix_scripts_category'), table_name='scripts')
    op.drop_table('scripts')
