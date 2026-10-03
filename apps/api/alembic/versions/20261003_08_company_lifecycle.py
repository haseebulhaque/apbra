"""Record identity-scoped, replay-safe first-company creation.

Revision ID: 20261003_08
Revises: 20261002_07

The command record cannot be represented by the older membership-scoped case
idempotency table. Downgrade therefore refuses any committed creation record
instead of silently discarding its identity and replay boundary.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261003_08"
down_revision = "20261002_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_creation_commands",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["external_identities.id"], name="fk_company_create_identity"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_company_create_company"
        ),
        sa.ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_company_create_owner_company",
        ),
        sa.UniqueConstraint("identity_id", "command_key", name="uq_company_create_identity_key"),
        sa.UniqueConstraint("company_id", name="uq_company_create_company"),
        sa.UniqueConstraint("membership_id", name="uq_company_create_membership"),
    )
    op.execute(
        "CREATE FUNCTION apbra_reject_company_creation_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'company creation commands are immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_company_creation_immutable BEFORE UPDATE OR DELETE "
        "ON company_creation_commands FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_company_creation_mutation()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE company_creation_commands IN SHARE ROW EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT 1 FROM company_creation_commands LIMIT 1")).first():
        raise RuntimeError(
            "Cannot downgrade committed company creation: identity-scoped replay and "
            "creation provenance have no pre-APBRA-151 representation"
        )
    op.execute("DROP TRIGGER trg_company_creation_immutable ON company_creation_commands")
    op.execute("DROP FUNCTION apbra_reject_company_creation_mutation()")
    op.drop_table("company_creation_commands")
