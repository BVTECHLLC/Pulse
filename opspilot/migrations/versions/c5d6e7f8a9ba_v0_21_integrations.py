"""v0.21 integrations & command center

Revision ID: c5d6e7f8a9ba
Revises: b4c5d6e7f8a9
Create Date: 2026-06-28 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d6e7f8a9ba'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=True),
        sa.Column('key_hash', sa.String(length=80), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_keys_user_id'), 'api_keys', ['user_id'], unique=False)
    op.create_index(op.f('ix_api_keys_prefix'), 'api_keys', ['prefix'], unique=False)
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=False)
    op.create_index(op.f('ix_api_keys_revoked'), 'api_keys', ['revoked'], unique=False)

    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('events', sa.JSON(), nullable=True),
        sa.Column('secret', sa.String(length=120), nullable=True),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('last_status', sa.Integer(), nullable=True),
        sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_webhook_subscriptions_client_id'), 'webhook_subscriptions', ['client_id'], unique=False)
    op.create_index(op.f('ix_webhook_subscriptions_enabled'), 'webhook_subscriptions', ['enabled'], unique=False)

    op.create_table(
        'inbound_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('last_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inbound_sources_token'), 'inbound_sources', ['token'], unique=False)
    op.create_index(op.f('ix_inbound_sources_client_id'), 'inbound_sources', ['client_id'], unique=False)
    op.create_index(op.f('ix_inbound_sources_enabled'), 'inbound_sources', ['enabled'], unique=False)

    op.create_table(
        'integration_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('category', sa.String(length=60), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('client_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_integration_connections_provider'), 'integration_connections', ['provider'], unique=False)
    op.create_index(op.f('ix_integration_connections_client_id'), 'integration_connections', ['client_id'], unique=False)
    op.create_index(op.f('ix_integration_connections_enabled'), 'integration_connections', ['enabled'], unique=False)


def downgrade():
    op.drop_table('integration_connections')
    op.drop_index(op.f('ix_inbound_sources_enabled'), table_name='inbound_sources')
    op.drop_index(op.f('ix_inbound_sources_client_id'), table_name='inbound_sources')
    op.drop_index(op.f('ix_inbound_sources_token'), table_name='inbound_sources')
    op.drop_table('inbound_sources')
    op.drop_index(op.f('ix_webhook_subscriptions_enabled'), table_name='webhook_subscriptions')
    op.drop_index(op.f('ix_webhook_subscriptions_client_id'), table_name='webhook_subscriptions')
    op.drop_table('webhook_subscriptions')
    op.drop_index(op.f('ix_api_keys_revoked'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_user_id'), table_name='api_keys')
    op.drop_table('api_keys')
