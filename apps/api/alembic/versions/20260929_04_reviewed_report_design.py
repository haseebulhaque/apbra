"""Persist immutable, expert-reviewed ReportDesign and bind generation attempts.

Revision ID: 20260929_04
Revises: 20260924_03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260929_04"
down_revision = "20260924_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviewed_report_designs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_contract_id", sa.Uuid(), nullable=False),
        sa.Column("interpretation_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("semantic_context_version", sa.Integer(), nullable=False),
        sa.Column("binding_json", sa.Text(), nullable=False),
        sa.Column("binding_digest", sa.String(64), nullable=False),
        sa.Column("semantic_input_digest", sa.String(64), nullable=False),
        sa.Column("evidence_binding_digest", sa.String(64), nullable=False),
        sa.Column("design_json", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("reviewer_membership_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_identity_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_role", sa.String(32), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_reviewed_design_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_contract_id", "case_id", "company_id"],
            [
                "confirmed_requirement_contracts.id",
                "confirmed_requirement_contracts.case_id",
                "confirmed_requirement_contracts.company_id",
            ],
            name="fk_reviewed_design_contract_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["interpretation_id", "case_id", "company_id"],
            [
                "case_interpretation_versions.id",
                "case_interpretation_versions.case_id",
                "case_interpretation_versions.company_id",
            ],
            name="fk_reviewed_design_interpretation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_reviewed_design_request_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_reviewed_design_reviewer_company",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_identity_id"],
            ["external_identities.id"],
            name="fk_reviewed_design_reviewer_identity",
        ),
        sa.UniqueConstraint(
            "id", "case_id", "company_id", "confirmed_contract_id",
            name="uq_reviewed_design_attempt_binding",
        ),
        sa.CheckConstraint(
            "reviewer_role = 'EXPERT'", name="ck_reviewed_design_expert_role"
        ),
        sa.CheckConstraint(
            "semantic_context_version >= 1", name="ck_reviewed_design_context"
        ),
    )
    op.create_index(
        "ix_reviewed_design_case_contract",
        "reviewed_report_designs",
        ["case_id", "confirmed_contract_id", "reviewed_at"],
    )
    op.add_column(
        "generation_attempts",
        sa.Column("reviewed_design_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_generation_reviewed_design_binding",
        "generation_attempts",
        "reviewed_report_designs",
        ["reviewed_design_id", "case_id", "company_id", "confirmed_contract_id"],
        ["id", "case_id", "company_id", "confirmed_contract_id"],
    )
    op.execute(
        "CREATE FUNCTION apbra_reject_reviewed_design_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'reviewed report design is immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_reviewed_design_immutable BEFORE UPDATE OR DELETE "
        "ON reviewed_report_designs FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_reviewed_design_mutation()"
    )
    op.execute(
        "CREATE FUNCTION apbra_guard_generation_reviewed_design() RETURNS trigger AS $$ "
        "BEGIN IF NEW.reviewed_design_id IS DISTINCT FROM OLD.reviewed_design_id "
        "THEN RAISE EXCEPTION 'generation reviewed design association is immutable'; "
        "END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_generation_reviewed_design_guard BEFORE UPDATE "
        "ON generation_attempts FOR EACH ROW EXECUTE FUNCTION "
        "apbra_guard_generation_reviewed_design()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_generation_reviewed_design_guard ON generation_attempts")
    op.execute("DROP FUNCTION apbra_guard_generation_reviewed_design()")
    op.execute("DROP TRIGGER trg_reviewed_design_immutable ON reviewed_report_designs")
    op.execute("DROP FUNCTION apbra_reject_reviewed_design_mutation()")
    op.drop_constraint(
        "fk_generation_reviewed_design_binding", "generation_attempts", type_="foreignkey"
    )
    op.drop_column("generation_attempts", "reviewed_design_id")
    op.drop_index("ix_reviewed_design_case_contract", table_name="reviewed_report_designs")
    op.drop_table("reviewed_report_designs")
