"""v0.3 alerts, alert policies, ticket comments

Revision ID: a1b2c3d4e5f6
Revises: cdef051e7149
Create Date: 2026-06-27 21:40:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'cdef051e7149'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('severity', sa.Enum('INFO', 'WARNING', 'CRITICAL', name='alertseverity'), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED', name='alertstatus'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_resolved', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_alerts_client_id'), 'alerts', ['client_id'], unique=False)
    op.create_index(op.f('ix_alerts_device_id'), 'alerts', ['device_id'], unique=False)
    op.create_index(op.f('ix_alerts_kind'), 'alerts', ['kind'], unique=False)
    op.create_index(op.f('ix_alerts_status'), 'alerts', ['status'], unique=False)

    op.create_table(
        'alert_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('disk_pct_max', sa.Float(), nullable=False),
        sa.Column('cpu_pct_max', sa.Float(), nullable=False),
        sa.Column('ram_pct_max', sa.Float(), nullable=False),
        sa.Column('health_min', sa.Integer(), nullable=False),
        sa.Column('offline_minutes', sa.Integer(), nullable=False),
        sa.Column('alert_on_av_off', sa.Boolean(), nullable=False),
        sa.Column('alert_on_patch_behind', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id'),
    )

    op.create_table(
        'ticket_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('author_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('author_role', sa.String(length=40), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('internal', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['support_tickets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ticket_comments_ticket_id'), 'ticket_comments', ['ticket_id'], unique=False)
    op.create_index(op.f('ix_ticket_comments_internal'), 'ticket_comments', ['internal'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ticket_comments_internal'), table_name='ticket_comments')
    op.drop_index(op.f('ix_ticket_comments_ticket_id'), table_name='ticket_comments')
    op.drop_table('ticket_comments')
    op.drop_table('alert_policies')
    op.drop_index(op.f('ix_alerts_status'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_kind'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_device_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_client_id'), table_name='alerts')
    op.drop_table('alerts')
    sa.Enum(name='alertstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='alertseverity').drop(op.get_bind(), checkfirst=True)
