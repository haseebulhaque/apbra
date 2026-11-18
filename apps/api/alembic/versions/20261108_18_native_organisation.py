"""Explicit native principals and parent-bound workspace sessions; preserve old IDs."""

import sqlalchemy as sa

from alembic import op

revision = "20261108_18"
down_revision = "20261106_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("external_identities", "issuer", nullable=True)
    op.alter_column("external_identities", "subject", nullable=True)
    op.create_check_constraint(
        "ck_identity_binding_shape",
        "external_identities",
        "(issuer IS NOT NULL AND subject IS NOT NULL) OR "
        "(issuer IS NULL AND subject IS NULL AND provider_profile_id = 'native-password')",
    )
    op.create_table(
        "native_account_principals",
        sa.Column(
            "identity_id", sa.Uuid(), sa.ForeignKey("external_identities.id"), primary_key=True
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("password_accounts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "native_workspace_sessions",
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("application_sessions.id"), primary_key=True
        ),
        sa.Column(
            "parent_digest",
            sa.String(64),
            sa.ForeignKey("password_sessions.digest"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Cross-table binding validation and immutability belong to persistence too.
    op.execute("""
        CREATE FUNCTION apbra_native_binding_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND (NEW.identity_id <> OLD.identity_id
              OR NEW.account_id <> OLD.account_id) THEN
            RAISE EXCEPTION 'native principal binding is immutable';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM external_identities
              WHERE id = NEW.identity_id AND issuer IS NULL AND subject IS NULL
                AND provider_profile_id = 'native-password') THEN
            RAISE EXCEPTION 'native principal requires absent external claims';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER native_binding_guard BEFORE INSERT OR UPDATE
          ON native_account_principals FOR EACH ROW
          EXECUTE FUNCTION apbra_native_binding_guard();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM native_account_principals) OR "
            "EXISTS(SELECT 1 FROM external_identities WHERE issuer IS NULL OR subject IS NULL)"
        )
    ):
        raise RuntimeError("Native principals require preservation; downgrade refused")
    op.execute("DROP TRIGGER native_binding_guard ON native_account_principals")
    op.execute("DROP FUNCTION apbra_native_binding_guard()")
    op.drop_table("native_workspace_sessions")
    op.drop_table("native_account_principals")
    op.drop_constraint("ck_identity_binding_shape", "external_identities", type_="check")
    op.alter_column("external_identities", "subject", nullable=False)
    op.alter_column("external_identities", "issuer", nullable=False)
