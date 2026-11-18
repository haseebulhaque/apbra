"""Add date-display preferences without rewriting existing settings or timestamps."""

import sqlalchemy as sa

from alembic import op

revision = "20261105_15"
down_revision = "20261018_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_date_display_versions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("time_zone", sa.String(255)),
        sa.Column("created_by_membership_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_date_display_actor_company",
        ),
        sa.UniqueConstraint("company_id", "version", name="uq_date_display_company_version"),
        sa.UniqueConstraint("id", "company_id", "version", name="uq_date_display_identity_version"),
        sa.CheckConstraint("version >= 1", name="ck_date_display_version"),
    )
    op.create_table(
        "tenant_date_display_current",
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id", "company_id", "version"],
            [
                "tenant_date_display_versions.id",
                "tenant_date_display_versions.company_id",
                "tenant_date_display_versions.version",
            ],
            name="fk_date_display_current_version",
        ),
    )
    op.execute("""CREATE TRIGGER trg_date_display_immutable BEFORE UPDATE OR DELETE
    ON tenant_date_display_versions FOR EACH ROW
    EXECUTE FUNCTION apbra_native_receipt_immutable()""")


def downgrade() -> None:
    db = op.get_bind()
    db.execute(sa.text("LOCK TABLE tenant_date_display_versions IN ACCESS EXCLUSIVE MODE"))
    if db.execute(sa.text("SELECT 1 FROM tenant_date_display_versions LIMIT 1")).first():
        raise RuntimeError(
            "Cannot downgrade retained date-display history; retain tables for rollback"
        )
    op.drop_table("tenant_date_display_current")
    op.drop_table("tenant_date_display_versions")
