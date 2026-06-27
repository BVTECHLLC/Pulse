"""v0.6 security posture: assessments and findings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-27 23:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'security_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('authorized_by', sa.String(length=200), nullable=False),
        sa.Column('status', sa.Enum('PLANNED', 'IN_PROGRESS', 'COMPLETED', name='assessmentstatus'), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_security_assessments_client_id'), 'security_assessments', ['client_id'], unique=False)
    op.create_index(op.f('ix_security_assessments_status'), 'security_assessments', ['status'], unique=False)

    op.create_table(
        'security_findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('assessment_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('severity', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='findingseverity'), nullable=False),
        sa.Column('cve', sa.String(length=40), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('OPEN', 'REMEDIATING', 'RESOLVED', 'RISK_ACCEPTED', name='findingstatus'), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('client_visible', sa.Boolean(), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('author_email', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['security_assessments.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_security_findings_client_id'), 'security_findings', ['client_id'], unique=False)
    op.create_index(op.f('ix_security_findings_device_id'), 'security_findings', ['device_id'], unique=False)
    op.create_index(op.f('ix_security_findings_assessment_id'), 'security_findings', ['assessment_id'], unique=False)
    op.create_index(op.f('ix_security_findings_category'), 'security_findings', ['category'], unique=False)
    op.create_index(op.f('ix_security_findings_severity'), 'security_findings', ['severity'], unique=False)
    op.create_index(op.f('ix_security_findings_status'), 'security_findings', ['status'], unique=False)


def downgrade():
    for ix in ('ix_security_findings_status', 'ix_security_findings_severity',
               'ix_security_findings_category', 'ix_security_findings_assessment_id',
               'ix_security_findings_device_id', 'ix_security_findings_client_id'):
        op.drop_index(op.f(ix), table_name='security_findings')
    op.drop_table('security_findings')
    op.drop_index(op.f('ix_security_assessments_status'), table_name='security_assessments')
    op.drop_index(op.f('ix_security_assessments_client_id'), table_name='security_assessments')
    op.drop_table('security_assessments')
