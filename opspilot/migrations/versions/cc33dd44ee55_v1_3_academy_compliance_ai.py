"""v1.3 Academy: streak-reminder dedupe column + AI question bank

Revision ID: cc33dd44ee55
Revises: bb22cc33dd44
Create Date: 2026-07-06 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'cc33dd44ee55'
down_revision = 'bb22cc33dd44'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('academy_profiles', sa.Column('last_reminder_on', sa.Date(), nullable=True))
    op.create_table(
        'academy_ai_questions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('lesson_id', sa.String(length=60), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('q', sa.Text(), nullable=False),
        sa.Column('choices', sa.Text(), nullable=False),
        sa.Column('answer', sa.Integer(), nullable=False),
        sa.Column('explain', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_academy_ai_questions_lesson_id', 'academy_ai_questions', ['lesson_id'])
    op.create_index('ix_academy_ai_questions_month', 'academy_ai_questions', ['month'])
    op.create_index('ix_academy_ai_questions_active', 'academy_ai_questions', ['active'])


def downgrade():
    op.drop_index('ix_academy_ai_questions_active', table_name='academy_ai_questions')
    op.drop_index('ix_academy_ai_questions_month', table_name='academy_ai_questions')
    op.drop_index('ix_academy_ai_questions_lesson_id', table_name='academy_ai_questions')
    op.drop_table('academy_ai_questions')
    op.drop_column('academy_profiles', 'last_reminder_on')
