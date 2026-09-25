"""Add durable conversation, evidence and exact acceptance records.

Revision ID: 20260924_02
Revises: 20260923_01
"""

import sqlalchemy as sa

from alembic import op

revision = "20260924_02"
down_revision = "20260923_01"
branch_labels = None
depends_on = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def created_at_column(name: str = "created_at") -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.add_column(
        "reporting_cases",
        sa.Column("semantic_context_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_case_semantic_context_positive", "reporting_cases", "semantic_context_version >= 1"
    )
    op.create_table(
        "case_conversation_events",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_conversation_event_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_conversation_event_actor_company",
        ),
        sa.UniqueConstraint("case_id", "sequence", name="uq_conversation_event_sequence"),
        sa.UniqueConstraint(
            "case_id", "created_by_membership_id", "command_key",
            name="uq_conversation_event_command",
        ),
        sa.CheckConstraint(
            "kind IN ('USER_MESSAGE','RAW_ANSWER','CLARIFICATION_QUESTION',"
            "'AI_ANALYSIS','CORRECTION','ALTERNATIVE_PROPOSED',"
            "'ALTERNATIVE_ACCEPTED','ALTERNATIVE_DECLINED')",
            name="ck_conversation_event_kind",
        ),
    )
    op.create_table(
        "case_evidence_versions",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("observed_schema_json", sa.Text(), nullable=False),
        sa.Column("schema_digest", sa.String(64), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_evidence_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_evidence_request_version",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_evidence_actor_company",
        ),
        sa.UniqueConstraint(
            "case_id", "request_version_id", "content_digest",
            name="uq_case_request_evidence_digest",
        ),
        sa.UniqueConstraint("id", "case_id", "company_id", name="uq_evidence_case_company"),
        sa.UniqueConstraint("storage_key", name="uq_evidence_storage_key"),
        sa.CheckConstraint("format IN ('CSV','XLSX')", name="ck_evidence_format"),
    )
    op.create_table(
        "case_interpretation_versions",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("request_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid()),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("session_json", sa.Text(), nullable=False),
        sa.Column("confirmation_summary_json", sa.Text(), nullable=False),
        sa.Column("readiness_binding_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_interpretation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["request_version_id", "case_id", "company_id"],
            [
                "case_request_versions.id",
                "case_request_versions.case_id",
                "case_request_versions.company_id",
            ],
            name="fk_interpretation_request_version",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "case_id", "company_id"],
            [
                "case_evidence_versions.id",
                "case_evidence_versions.case_id",
                "case_evidence_versions.company_id",
            ],
            name="fk_interpretation_evidence_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_interpretation_actor_company",
        ),
        sa.CheckConstraint(
            "state IN ('NEEDS_CLARIFICATION','READY_FOR_CONFIRMATION')",
            name="ck_interpretation_state",
        ),
        sa.UniqueConstraint(
            "case_id", "context_version", name="uq_interpretation_case_context"
        ),
        sa.UniqueConstraint("id", "case_id", "company_id", name="uq_interpretation_case_company"),
    )
    op.create_table(
        "confirmed_requirement_contracts",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("interpretation_id", sa.Uuid(), nullable=False),
        sa.Column("contract_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("accepted_by_membership_id", sa.Uuid(), nullable=False),
        created_at_column("accepted_at"),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_confirmed_contract_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["interpretation_id", "case_id", "company_id"],
            [
                "case_interpretation_versions.id",
                "case_interpretation_versions.case_id",
                "case_interpretation_versions.company_id",
            ],
            name="fk_confirmed_contract_interpretation_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_confirmed_contract_actor_company",
        ),
        sa.UniqueConstraint("interpretation_id", name="uq_confirmed_contract_interpretation"),
        sa.CheckConstraint("schema_version = 2", name="ck_confirmed_contract_v2"),
    )
    for table in (
        "case_conversation_events",
        "case_evidence_versions",
        "case_interpretation_versions",
        "confirmed_requirement_contracts",
    ):
        function = f"apbra_reject_{table}_mutation"
        trigger = f"trg_{table}_immutable"
        op.execute(
            f"CREATE FUNCTION {function}() RETURNS trigger AS $$ "
            f"BEGIN RAISE EXCEPTION '{table} is immutable'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )


def downgrade() -> None:
    for table in (
        "confirmed_requirement_contracts",
        "case_interpretation_versions",
        "case_evidence_versions",
        "case_conversation_events",
    ):
        op.drop_table(table)
        op.execute(f"DROP FUNCTION apbra_reject_{table}_mutation()")
    op.drop_constraint("ck_case_semantic_context_positive", "reporting_cases", type_="check")
    op.drop_column("reporting_cases", "semantic_context_version")
