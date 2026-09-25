"""Add protected generation attempts and validated output history.

Revision ID: 20260924_03
Revises: 20260924_02
"""

import sqlalchemy as sa

from alembic import op

revision = "20260924_03"
down_revision = "20260924_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_confirmed_contract_case",
        "confirmed_requirement_contracts",
        ["id", "case_id", "company_id"],
    )
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_contract_id", sa.Uuid(), nullable=False),
        sa.Column("interpretation_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("command_payload_digest", sa.String(64), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("evidence_binding_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("retry_of_attempt_id", sa.Uuid()),
        sa.Column("supersedes_attempt_id", sa.Uuid()),
        sa.Column("fence_token", sa.Uuid(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text()),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column("artifact_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_generation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_contract_id", "case_id", "company_id"],
            [
                "confirmed_requirement_contracts.id",
                "confirmed_requirement_contracts.case_id",
                "confirmed_requirement_contracts.company_id",
            ],
            name="fk_generation_contract_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["interpretation_id", "case_id", "company_id"],
            [
                "case_interpretation_versions.id",
                "case_interpretation_versions.case_id",
                "case_interpretation_versions.company_id",
            ],
            name="fk_generation_interpretation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_generation_request_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_generation_actor_company",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_attempt_id"], ["generation_attempts.id"], name="fk_generation_retry"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_attempt_id"],
            ["generation_attempts.id"],
            name="fk_generation_supersedes",
        ),
        sa.UniqueConstraint(
            "company_id",
            "created_by_membership_id",
            "case_id",
            "command_key",
            name="uq_generation_command",
        ),
        sa.UniqueConstraint("case_id", "attempt_number", name="uq_generation_attempt_number"),
        sa.UniqueConstraint("id", "case_id", "company_id", name="uq_generation_case_company"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_generation_attempt_number"),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_generation_status",
        ),
    )
    op.create_index("ix_generation_case_created", "generation_attempts", ["case_id", "created_at"])
    op.create_index(
        "uq_generation_case_active",
        "generation_attempts",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING','RUNNING')"),
    )
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(600), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id", "case_id", "company_id"],
            [
                "generation_attempts.id",
                "generation_attempts.case_id",
                "generation_attempts.company_id",
            ],
            name="fk_artifact_attempt_case_company",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_artifact_attempt"),
        sa.UniqueConstraint(
            "id",
            "attempt_id",
            "case_id",
            "company_id",
            name="uq_artifact_identity_attempt_case_company",
        ),
        sa.UniqueConstraint("storage_key", name="uq_artifact_storage_key"),
        sa.CheckConstraint("byte_size > 0", name="ck_artifact_size"),
        sa.CheckConstraint("validation_status = 'PASS'", name="ck_artifact_validation_pass"),
    )
    op.create_foreign_key(
        "fk_generation_artifact_identity",
        "generation_attempts",
        "generated_artifacts",
        ["artifact_id", "id", "case_id", "company_id"],
        ["id", "attempt_id", "case_id", "company_id"],
    )
    op.execute(
        "CREATE FUNCTION apbra_guard_generation_attempt_mutation() RETURNS trigger AS $$ "
        "BEGIN "
        "IF TG_OP = 'DELETE' THEN "
        "RAISE EXCEPTION 'generation attempt is immutable'; END IF; "
        "IF OLD.status IN ('SUCCEEDED','FAILED','CANCELLED') THEN "
        "RAISE EXCEPTION 'terminal generation attempt is immutable'; END IF; "
        "IF NEW.id <> OLD.id OR NEW.case_id <> OLD.case_id OR "
        "NEW.company_id <> OLD.company_id OR "
        "NEW.confirmed_contract_id <> OLD.confirmed_contract_id OR "
        "NEW.interpretation_id <> OLD.interpretation_id OR "
        "NEW.request_version_id <> OLD.request_version_id OR "
        "NEW.created_by_membership_id <> OLD.created_by_membership_id OR "
        "NEW.retry_of_attempt_id IS DISTINCT FROM OLD.retry_of_attempt_id OR "
        "NEW.supersedes_attempt_id IS DISTINCT FROM OLD.supersedes_attempt_id OR "
        "NEW.command_key <> OLD.command_key OR "
        "NEW.command_payload_digest <> OLD.command_payload_digest OR "
        "NEW.input_digest <> OLD.input_digest OR "
        "NEW.evidence_binding_digest <> OLD.evidence_binding_digest OR "
        "NEW.attempt_number <> OLD.attempt_number OR "
        "NEW.fence_token <> OLD.fence_token OR NEW.provenance_json <> OLD.provenance_json OR "
        "NEW.created_at <> OLD.created_at "
        "THEN RAISE EXCEPTION 'generation identity is immutable'; END IF; "
        "IF OLD.artifact_id IS NOT NULL AND NEW.artifact_id IS DISTINCT FROM OLD.artifact_id "
        "THEN RAISE EXCEPTION 'generation artifact identity is immutable'; END IF; "
        "IF OLD.status = 'PENDING' AND NEW.status NOT IN ('RUNNING','CANCELLED') THEN "
        "RAISE EXCEPTION 'invalid generation status transition'; END IF; "
        "IF OLD.status = 'RUNNING' AND NEW.status NOT IN ('SUCCEEDED','FAILED','CANCELLED') "
        "THEN RAISE EXCEPTION 'invalid generation status transition'; END IF; "
        "IF NEW.status = 'SUCCEEDED' AND (NEW.artifact_id IS NULL OR "
        "NEW.validation_json IS NULL OR NEW.completed_at IS NULL) THEN "
        "RAISE EXCEPTION 'successful generation requires validated artifact'; END IF; "
        "IF NEW.status IN ('FAILED','CANCELLED') AND NEW.artifact_id IS NOT NULL THEN "
        "RAISE EXCEPTION 'unsuccessful generation cannot retain artifact'; END IF; "
        "IF NEW.artifact_id IS NOT NULL AND NEW.status <> 'SUCCEEDED' THEN "
        "RAISE EXCEPTION 'artifact requires successful generation'; END IF; "
        "RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_generation_attempt_guard BEFORE UPDATE OR DELETE "
        "ON generation_attempts FOR EACH ROW EXECUTE FUNCTION "
        "apbra_guard_generation_attempt_mutation()"
    )
    op.execute(
        "CREATE FUNCTION apbra_reject_generated_artifact_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'generated artifact is immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_generated_artifact_immutable BEFORE UPDATE OR DELETE "
        "ON generated_artifacts FOR EACH ROW EXECUTE FUNCTION "
        "apbra_reject_generated_artifact_mutation()"
    )


def downgrade() -> None:
    op.drop_constraint("fk_generation_artifact_identity", "generation_attempts", type_="foreignkey")
    op.drop_table("generated_artifacts")
    op.execute("DROP FUNCTION apbra_reject_generated_artifact_mutation()")
    op.drop_table("generation_attempts")
    op.execute("DROP FUNCTION apbra_guard_generation_attempt_mutation()")
    op.drop_constraint(
        "uq_confirmed_contract_case", "confirmed_requirement_contracts", type_="unique"
    )
