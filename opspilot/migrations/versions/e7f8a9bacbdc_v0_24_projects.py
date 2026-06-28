"""v0.24 PSA projects & kanban

Revision ID: e7f8a9bacbdc
Revises: d6e7f8a9bacb
Create Date: 2026-06-28 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9bacbdc'
down_revision = 'd6e7f8a9bacb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('ACTIVE', 'ON_HOLD', 'COMPLETED', 'CANCELLED', name='projectstatus'), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('budget_hours', sa.Float(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_client_id'), 'projects', ['client_id'], unique=False)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)

    op.create_table(
        'project_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assignee_user_id', sa.Integer(), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('estimate_hours', sa.Float(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['assignee_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_tasks_project_id'), 'project_tasks', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_tasks_client_id'), 'project_tasks', ['client_id'], unique=False)
    op.create_index(op.f('ix_project_tasks_status'), 'project_tasks', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_project_tasks_status'), table_name='project_tasks')
    op.drop_index(op.f('ix_project_tasks_client_id'), table_name='project_tasks')
    op.drop_index(op.f('ix_project_tasks_project_id'), table_name='project_tasks')
    op.drop_table('project_tasks')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_index(op.f('ix_projects_client_id'), table_name='projects')
    op.drop_table('projects')
    sa.Enum(name='projectstatus').drop(op.get_bind(), checkfirst=True)
