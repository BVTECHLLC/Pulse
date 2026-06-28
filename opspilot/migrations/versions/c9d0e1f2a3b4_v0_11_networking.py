"""v0.11 networking / IPAM: sites, networks, ip addresses

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-28 01:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sites_client_id'), 'sites', ['client_id'], unique=False)

    op.create_table(
        'networks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('cidr', sa.String(length=64), nullable=False),
        sa.Column('vlan', sa.Integer(), nullable=True),
        sa.Column('gateway', sa.String(length=64), nullable=True),
        sa.Column('dns', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_networks_client_id'), 'networks', ['client_id'], unique=False)
    op.create_index(op.f('ix_networks_site_id'), 'networks', ['site_id'], unique=False)

    op.create_table(
        'ip_addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('network_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('address', sa.String(length=64), nullable=False),
        sa.Column('hostname', sa.String(length=200), nullable=True),
        sa.Column('mac', sa.String(length=40), nullable=True),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['network_id'], ['networks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('network_id', 'address', name='uq_ip_per_network'),
    )
    op.create_index(op.f('ix_ip_addresses_network_id'), 'ip_addresses', ['network_id'], unique=False)
    op.create_index(op.f('ix_ip_addresses_client_id'), 'ip_addresses', ['client_id'], unique=False)
    op.create_index(op.f('ix_ip_addresses_address'), 'ip_addresses', ['address'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ip_addresses_address'), table_name='ip_addresses')
    op.drop_index(op.f('ix_ip_addresses_client_id'), table_name='ip_addresses')
    op.drop_index(op.f('ix_ip_addresses_network_id'), table_name='ip_addresses')
    op.drop_table('ip_addresses')
    op.drop_index(op.f('ix_networks_site_id'), table_name='networks')
    op.drop_index(op.f('ix_networks_client_id'), table_name='networks')
    op.drop_table('networks')
    op.drop_index(op.f('ix_sites_client_id'), table_name='sites')
    op.drop_table('sites')
