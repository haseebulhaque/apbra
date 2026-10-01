"""Register tenant settings, protected credential references and lifecycle bindings.

Revision ID: 20261001_06
Revises: 20260929_05
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_06"
down_revision = "20260929_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_secret_records",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.String(120), nullable=False),
        sa.Column("key_version", sa.String(80), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_tenant_secret_company"),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_tenant_secret_actor_company",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_tenant_secret_company"),
    )
    op.create_index(
        "ix_tenant_secret_company_profile",
        "tenant_secret_records",
        ["company_id", "profile_id", "created_at"],
    )
    op.create_table(
        "tenant_settings_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("settings_digest", sa.String(64), nullable=False),
        sa.Column("secret_reference_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_keys_json", sa.Text(), nullable=False),
        sa.Column("safe_changes_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("restored_from_version_id", sa.Uuid(), nullable=True),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_tenant_settings_company"
        ),
        sa.ForeignKeyConstraint(
            ["secret_reference_id", "company_id"],
            ["tenant_secret_records.id", "tenant_secret_records.company_id"],
            name="fk_tenant_settings_secret_company",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_tenant_settings_actor_company",
        ),
        sa.ForeignKeyConstraint(
            ["restored_from_version_id", "company_id"],
            ["tenant_settings_versions.id", "tenant_settings_versions.company_id"],
            name="fk_tenant_settings_restore_company",
        ),
        sa.UniqueConstraint("company_id", "version", name="uq_tenant_settings_company_version"),
        sa.UniqueConstraint("id", "company_id", name="uq_tenant_settings_identity_company"),
        sa.CheckConstraint("version >= 1", name="ck_tenant_settings_version_positive"),
        sa.CheckConstraint("validation_status = 'PASS'", name="ck_tenant_settings_validated"),
    )
    op.create_table(
        "tenant_settings_current",
        sa.Column("company_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_tenant_current_company"),
        sa.ForeignKeyConstraint(
            ["version_id", "company_id"],
            ["tenant_settings_versions.id", "tenant_settings_versions.company_id"],
            name="fk_tenant_current_version_company",
        ),
    )
    op.create_table(
        "case_clarification_cycles",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("rounds_used", sa.Integer(), nullable=False),
        sa.Column("settings_version_id", sa.Uuid(), nullable=False),
        sa.Column("started_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"], ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_clarification_cycle_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["settings_version_id", "company_id"],
            ["tenant_settings_versions.id", "tenant_settings_versions.company_id"],
            name="fk_clarification_cycle_settings_company",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_clarification_cycle_actor_company",
        ),
        sa.UniqueConstraint("case_id", "cycle_number", name="uq_clarification_cycle_number"),
        sa.UniqueConstraint(
            "case_id", "started_by_membership_id", "command_key",
            name="uq_clarification_cycle_command",
        ),
        sa.CheckConstraint("cycle_number >= 1", name="ck_clarification_cycle_positive"),
        sa.CheckConstraint("rounds_used >= 0", name="ck_clarification_rounds_nonnegative"),
    )
    op.create_index(
        "ix_clarification_cycle_case", "case_clarification_cycles", ["case_id", "cycle_number"]
    )
    for table in (
        "case_interpretation_versions",
        "confirmed_requirement_contracts",
        "automatic_design_attempts",
        "generation_attempts",
        "generated_artifacts",
    ):
        op.add_column(table, sa.Column("settings_version_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_settings_company", table, "tenant_settings_versions",
            ["settings_version_id", "company_id"], ["id", "company_id"],
        )
    op.add_column("generated_artifacts", sa.Column("guide_digest", sa.String(64), nullable=True))
    op.execute(
        "CREATE FUNCTION apbra_reject_settings_version_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'tenant settings versions are immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_tenant_settings_version_immutable BEFORE UPDATE OR DELETE "
        "ON tenant_settings_versions FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_settings_version_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_tenant_settings_version_immutable ON tenant_settings_versions")
    op.execute("DROP FUNCTION apbra_reject_settings_version_mutation()")
    op.drop_column("generated_artifacts", "guide_digest")
    for table in reversed((
        "case_interpretation_versions",
        "confirmed_requirement_contracts",
        "automatic_design_attempts",
        "generation_attempts",
        "generated_artifacts",
    )):
        op.drop_constraint(f"fk_{table}_settings_company", table, type_="foreignkey")
        op.drop_column(table, "settings_version_id")
    op.drop_index("ix_clarification_cycle_case", table_name="case_clarification_cycles")
    op.drop_table("case_clarification_cycles")
    op.drop_table("tenant_settings_current")
    op.drop_table("tenant_settings_versions")
    op.drop_index("ix_tenant_secret_company_profile", table_name="tenant_secret_records")
    op.drop_table("tenant_secret_records")
