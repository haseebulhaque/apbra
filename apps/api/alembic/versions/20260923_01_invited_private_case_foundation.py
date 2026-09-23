"""Create the invited identity and private-case foundation.

Revision ID: 20260923_01
Revises: none
"""

import sqlalchemy as sa

from alembic import op

revision = "20260923_01"
down_revision = None
branch_labels = None
depends_on = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def created_at_column() -> sa.Column[object]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "companies",
        id_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at_column(),
    )
    op.create_table(
        "external_identities",
        id_column(),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at_column(),
        sa.UniqueConstraint("issuer", "subject", name="uq_identity_issuer_subject"),
    )
    op.create_table(
        "memberships",
        id_column(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["identity_id"], ["external_identities.id"]),
        sa.UniqueConstraint("id", "company_id", name="uq_membership_company"),
        sa.UniqueConstraint("company_id", "identity_id", name="uq_membership_company_identity"),
        sa.CheckConstraint(
            "role IN ('COMPANY_OWNER','COMPANY_ADMIN','MEMBER','EXPERT')",
            name="ck_membership_role",
        ),
    )
    op.create_table(
        "invitations",
        id_column(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("issued_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("invited_issuer", sa.String(500), nullable=False),
        sa.Column("invited_subject", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_by_identity_id", sa.Uuid()),
        created_at_column(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["issued_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_invitation_issuer_company",
        ),
        sa.ForeignKeyConstraint(["consumed_by_identity_id"], ["external_identities.id"]),
        sa.UniqueConstraint("token_digest", name="uq_invitation_token_digest"),
        sa.CheckConstraint(
            "role IN ('COMPANY_ADMIN','MEMBER','EXPERT')", name="ck_invitation_role"
        ),
    )
    op.create_table(
        "reporting_cases",
        id_column(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("creator_membership_id", sa.Uuid(), nullable=False),
        sa.Column("current_request_version_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        created_at_column(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["creator_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_case_creator_company",
        ),
        sa.UniqueConstraint("id", "company_id", name="uq_case_company"),
        sa.UniqueConstraint(
            "id", "company_id", "current_request_version_id", name="uq_case_current"
        ),
        sa.CheckConstraint("version >= 1", name="ck_case_version_positive"),
    )
    op.create_table(
        "auth_transactions",
        id_column(),
        sa.Column("state_digest", sa.String(64), nullable=False),
        sa.Column("browser_binding_digest", sa.String(64), nullable=False),
        sa.Column("expected_issuer", sa.String(500), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("provider_configuration_digest", sa.String(64), nullable=False),
        sa.Column("response_issuer_required", sa.Boolean(), nullable=False),
        sa.Column("nonce", sa.String(255), nullable=False),
        sa.Column("code_verifier", sa.String(255), nullable=False),
        sa.Column("return_to", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("state_digest", name="uq_auth_state"),
    )
    op.create_table(
        "dev_authorization_codes",
        id_column(),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("nonce", sa.String(255), nullable=False),
        sa.Column("code_challenge", sa.String(255), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("code_digest", name="uq_auth_code"),
    )
    op.create_table(
        "application_sessions",
        id_column(),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        created_at_column(),
        sa.ForeignKeyConstraint(["identity_id"], ["external_identities.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"]),
        sa.UniqueConstraint("token_digest", name="uq_session_token"),
    )
    op.create_table(
        "case_request_versions",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_request_version_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_request_version_actor_company",
        ),
        sa.UniqueConstraint("id", "case_id", "company_id", name="uq_request_version_case_company"),
        sa.UniqueConstraint("case_id", "sequence", name="uq_request_version_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_request_version_sequence_positive"),
    )
    op.create_foreign_key(
        "fk_case_current_version",
        "reporting_cases",
        "case_request_versions",
        ["current_request_version_id", "id", "company_id"],
        ["id", "case_id", "company_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "case_access",
        id_column(),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        created_at_column(),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["case_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_access_case_company",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_access_membership_company",
        ),
        sa.UniqueConstraint("case_id", "membership_id", name="uq_case_access_membership"),
        sa.CheckConstraint("access_level IN ('OWNER','EDITOR','VIEWER')", name="ck_access_level"),
    )
    op.create_table(
        "idempotency_records",
        id_column(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("command_key", sa.String(200), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_idempotency_actor_company",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id", "company_id"],
            ["reporting_cases.id", "reporting_cases.company_id"],
            name="fk_idempotency_case_company",
        ),
        sa.UniqueConstraint(
            "company_id",
            "membership_id",
            "operation",
            "command_key",
            name="uq_idempotency_scope",
        ),
    )
    op.create_table(
        "audit_events",
        id_column(),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        created_at_column(),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["actor_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_audit_actor_company",
        ),
    )
    op.create_index(
        "ix_audit_company_resource",
        "audit_events",
        ["company_id", "resource_type", "resource_id"],
    )
    op.execute(
        """CREATE FUNCTION apbra_reject_request_version_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'case request versions are immutable'; END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_case_request_versions_immutable
        BEFORE UPDATE OR DELETE ON case_request_versions
        FOR EACH ROW EXECUTE FUNCTION apbra_reject_request_version_mutation()"""
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_case_request_versions_immutable ON case_request_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS apbra_reject_request_version_mutation()")
    op.drop_index("ix_audit_company_resource", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("idempotency_records")
    op.drop_table("case_access")
    op.drop_constraint("fk_case_current_version", "reporting_cases", type_="foreignkey")
    op.drop_table("case_request_versions")
    op.drop_table("application_sessions")
    op.drop_table("dev_authorization_codes")
    op.drop_table("auth_transactions")
    op.drop_table("reporting_cases")
    op.drop_table("invitations")
    op.drop_table("memberships")
    op.drop_table("external_identities")
    op.drop_table("companies")
