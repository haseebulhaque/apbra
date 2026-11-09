"""Add isolated password identities; never alter provider accounts or memberships."""

import sqlalchemy as sa

from alembic import op

revision = "20261106_17"
down_revision = "20261105_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_accounts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("email_key", sa.String(320), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "password_proofs",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("email_key", sa.String(320), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512)),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("password_accounts.id")),
        sa.Column("epoch", sa.Integer()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "password_sessions",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("password_accounts.id"), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("touched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "password_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("bucket", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "password_audit",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("account_id", sa.UUID(), sa.ForeignKey("password_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    tables = (
        "password_audit",
        "password_throttles",
        "password_sessions",
        "password_proofs",
        "password_accounts",
    )
    connection = op.get_bind()
    for table in tables:
        connection.exec_driver_sql("LOCK TABLE " + table + " IN ACCESS EXCLUSIVE MODE")
    for table in tables:
        if connection.execute(
            sa.select(sa.select(sa.literal(1)).select_from(sa.table(table)).exists())
        ).scalar_one():
            raise RuntimeError(
                "Retained password authentication data prevents destructive downgrade; "
                "retain tables for application rollback"
            )
    for table in tables:
        op.drop_table(table)
