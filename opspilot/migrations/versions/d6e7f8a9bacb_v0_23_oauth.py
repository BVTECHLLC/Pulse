"""v0.23 oauth2 sso + connectors

Revision ID: d6e7f8a9bacb
Revises: c5d6e7f8a9ba
Create Date: 2026-06-28 17:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'd6e7f8a9bacb'
down_revision = 'c5d6e7f8a9ba'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'oauth_states',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('code_verifier', sa.String(length=128), nullable=False),
        sa.Column('redirect_uri', sa.Text(), nullable=False),
        sa.Column('next_url', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'oauth_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('account_email', sa.String(length=200), nullable=True),
        sa.Column('access_token_enc', sa.Text(), nullable=False),
        sa.Column('refresh_token_enc', sa.Text(), nullable=True),
        sa.Column('scope', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_oauth_tokens_provider'), 'oauth_tokens', ['provider'], unique=False)
    op.create_index(op.f('ix_oauth_tokens_user_id'), 'oauth_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_oauth_tokens_client_id'), 'oauth_tokens', ['client_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_oauth_tokens_client_id'), table_name='oauth_tokens')
    op.drop_index(op.f('ix_oauth_tokens_user_id'), table_name='oauth_tokens')
    op.drop_index(op.f('ix_oauth_tokens_provider'), table_name='oauth_tokens')
    op.drop_table('oauth_tokens')
    op.drop_table('oauth_states')
