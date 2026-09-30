"""Add business-user reference material and automatic design provenance.

Revision ID: 20260929_05
Revises: 20260929_04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260929_05"
down_revision = "20260929_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reporting_cases",
        sa.Column("report_title", sa.String(160), nullable=False, server_default="Untitled report"),
    )
    op.create_table(
        "case_reference_materials",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("interpretation_state", sa.String(32), nullable=False),
        sa.Column("capability_profile_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_reference_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_reference_request_version",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_reference_actor_company",
        ),
        sa.UniqueConstraint(
            "case_id",
            "request_version_id",
            "content_digest",
            name="uq_case_request_reference_digest",
        ),
        sa.UniqueConstraint("id", "case_id", "company_id", name="uq_reference_case_company"),
        sa.CheckConstraint(
            "media_type IN ('image/png','image/jpeg')", name="ck_reference_media_type"
        ),
        sa.CheckConstraint(
            "interpretation_state IN ('NOT_INTERPRETED','VISION_AVAILABLE')",
            name="ck_reference_interpretation_state",
        ),
    )
    op.create_index(
        "ix_reference_case_request",
        "case_reference_materials",
        ["case_id", "request_version_id", "created_at"],
    )
    op.create_table(
        "automatic_design_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_contract_id", sa.Uuid(), nullable=False),
        sa.Column("interpretation_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_context_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("command_payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_profile_id", sa.String(120), nullable=True),
        sa.Column("model_or_deployment", sa.String(255), nullable=True),
        sa.Column("prompt_version", sa.String(120), nullable=True),
        sa.Column("configuration_id", sa.String(120), nullable=True),
        sa.Column("capability_profile_json", sa.Text(), nullable=False),
        sa.Column("usage_json", sa.Text(), nullable=False),
        sa.Column("safe_failure_code", sa.String(100), nullable=True),
        sa.Column("requirement_binding_digest", sa.String(64), nullable=False),
        sa.Column("evidence_binding_digest", sa.String(64), nullable=False),
        sa.Column("reference_binding_digest", sa.String(64), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=True),
        sa.Column("candidate_digest", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_design_attempt_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_contract_id", "case_id", "company_id"],
            [
                "confirmed_requirement_contracts.id",
                "confirmed_requirement_contracts.case_id",
                "confirmed_requirement_contracts.company_id",
            ],
            name="fk_design_attempt_contract_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["interpretation_id", "case_id", "company_id"],
            [
                "case_interpretation_versions.id",
                "case_interpretation_versions.case_id",
                "case_interpretation_versions.company_id",
            ],
            name="fk_design_attempt_interpretation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_design_attempt_request_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_design_attempt_actor_company",
        ),
        sa.UniqueConstraint(
            "case_id", "requested_by_membership_id", "command_key",
            name="uq_design_attempt_command",
        ),
        sa.UniqueConstraint(
            "id", "case_id", "company_id", "confirmed_contract_id",
            name="uq_design_attempt_binding",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','ELIGIBLE','FAILED','CANCELLED')",
            name="ck_design_attempt_status",
        ),
        sa.CheckConstraint(
            "semantic_context_version >= 1", name="ck_design_attempt_context"
        ),
    )
    op.create_index(
        "ix_design_attempt_case_contract",
        "automatic_design_attempts",
        ["case_id", "confirmed_contract_id", "created_at"],
    )
    op.drop_constraint(
        "ck_reviewed_design_expert_role", "reviewed_report_designs", type_="check"
    )
    op.alter_column("reviewed_report_designs", "reviewer_membership_id", nullable=True)
    op.alter_column("reviewed_report_designs", "reviewer_identity_id", nullable=True)
    op.alter_column("reviewed_report_designs", "reviewer_role", nullable=True)
    op.add_column(
        "reviewed_report_designs",
        sa.Column(
            "origin", sa.String(32), nullable=False, server_default="EXPERT_REVIEWED"
        ),
    )
    op.add_column(
        "reviewed_report_designs", sa.Column("design_attempt_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "reviewed_report_designs",
        sa.Column("eligibility_validation_json", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_reviewed_design_automatic_attempt",
        "reviewed_report_designs",
        "automatic_design_attempts",
        ["design_attempt_id", "case_id", "company_id", "confirmed_contract_id"],
        ["id", "case_id", "company_id", "confirmed_contract_id"],
    )
    op.create_check_constraint(
        "ck_reviewed_design_origin",
        "reviewed_report_designs",
        "(origin = 'EXPERT_REVIEWED' AND reviewer_membership_id IS NOT NULL "
        "AND reviewer_identity_id IS NOT NULL AND reviewer_role = 'EXPERT' "
        "AND design_attempt_id IS NULL) OR "
        "(origin = 'AUTO_ELIGIBLE' AND reviewer_membership_id IS NULL "
        "AND reviewer_identity_id IS NULL AND reviewer_role IS NULL "
        "AND design_attempt_id IS NOT NULL AND eligibility_validation_json IS NOT NULL)",
    )
    op.execute(
        "CREATE FUNCTION apbra_reject_reference_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'reference material is immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_reference_immutable BEFORE UPDATE OR DELETE "
        "ON case_reference_materials FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_reference_mutation()"
    )
    op.execute(
        "CREATE FUNCTION apbra_reject_design_attempt_delete() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'automatic design attempt cannot be deleted'; "
        "END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_design_attempt_no_delete BEFORE DELETE "
        "ON automatic_design_attempts FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_design_attempt_delete()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_design_attempt_no_delete ON automatic_design_attempts")
    op.execute("DROP FUNCTION apbra_reject_design_attempt_delete()")
    op.execute("DROP TRIGGER trg_reference_immutable ON case_reference_materials")
    op.execute("DROP FUNCTION apbra_reject_reference_mutation()")
    op.drop_constraint("ck_reviewed_design_origin", "reviewed_report_designs", type_="check")
    op.drop_constraint(
        "fk_reviewed_design_automatic_attempt", "reviewed_report_designs", type_="foreignkey"
    )
    op.drop_column("reviewed_report_designs", "eligibility_validation_json")
    op.drop_column("reviewed_report_designs", "design_attempt_id")
    op.drop_column("reviewed_report_designs", "origin")
    op.alter_column("reviewed_report_designs", "reviewer_role", nullable=False)
    op.alter_column("reviewed_report_designs", "reviewer_identity_id", nullable=False)
    op.alter_column("reviewed_report_designs", "reviewer_membership_id", nullable=False)
    op.create_check_constraint(
        "ck_reviewed_design_expert_role",
        "reviewed_report_designs",
        "reviewer_role = 'EXPERT'",
    )
    op.drop_index("ix_design_attempt_case_contract", table_name="automatic_design_attempts")
    op.drop_table("automatic_design_attempts")
    op.drop_index("ix_reference_case_request", table_name="case_reference_materials")
    op.drop_table("case_reference_materials")
    op.drop_column("reporting_cases", "report_title")
