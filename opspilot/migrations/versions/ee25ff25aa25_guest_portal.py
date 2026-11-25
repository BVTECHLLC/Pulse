"""guest portal: GUEST role value + guest_scopes table

Scoped, read-only external-helper accounts (Fiverr / LinkedIn / referral
partners). Idempotent so it coexists with the boot-time schema reconcile in
main.py (which may have already created the table / added the enum value).

Revision ID: ee25ff25aa25
Revises: dd24ee24ff24
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "ee25ff25aa25"
down_revision = "dd24ee24ff24"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("guest_scopes"):
        op.create_table(
            "guest_scopes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False, unique=True, index=True),
            sa.Column("label", sa.String(length=200)),
            sa.Column("allowed_emails", sa.Text(), server_default="[]"),
            sa.Column("labels", sa.Text(), server_default="{}"),
            sa.Column("mailbox", sa.String(length=200)),
            sa.Column("can_view_body", sa.Boolean(), server_default=sa.true()),
            sa.Column("active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )
    # Add the 'guest' enum value on Postgres via a side autocommit connection, so
    # a failure here (e.g. value already present) never poisons this migration's
    # transaction. The boot reconcile is the ultimate safety net regardless.
    if bind.dialect.name == "postgresql":
        try:
            conn = bind.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql("ALTER TYPE role ADD VALUE IF NOT EXISTS 'guest'")
            conn.close()
        except Exception:
            pass


def downgrade():
    op.drop_table("guest_scopes")
    # Postgres cannot cleanly drop an enum value; 'guest' is left in place (inert).
