"""v0.20 patch management + scheduled reports

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-28 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('devices', sa.Column('patches_pending', sa.Integer(), nullable=True))

    op.create_table(
        'device_patches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=400), nullable=False),
        sa.Column('kb', sa.String(length=60), nullable=True),
        sa.Column('severity', sa.String(length=40), nullable=True),
        sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_device_patches_device_id'), 'device_patches', ['device_id'], unique=False)
    op.create_index(op.f('ix_device_patches_client_id'), 'device_patches', ['client_id'], unique=False)

    op.create_table(
        'report_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('recipient_email', sa.String(length=200), nullable=False),
        sa.Column('cadence', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_report_schedules_client_id'), 'report_schedules', ['client_id'], unique=False)
    op.create_index(op.f('ix_report_schedules_enabled'), 'report_schedules', ['enabled'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_report_schedules_enabled'), table_name='report_schedules')
    op.drop_index(op.f('ix_report_schedules_client_id'), table_name='report_schedules')
    op.drop_table('report_schedules')
    op.drop_index(op.f('ix_device_patches_client_id'), table_name='device_patches')
    op.drop_index(op.f('ix_device_patches_device_id'), table_name='device_patches')
    op.drop_table('device_patches')
    op.drop_column('devices', 'patches_pending')
