"""Append-only safe operational errors; bounded tenant/time audit access.

Revision ID: 20261015_11
Revises: 20261015_10
"""

import sqlalchemy as sa

from alembic import op

revision = "20261015_11"
down_revision = "20261015_10"
branch_labels = None
depends_on = None
TABLES = ("system_errors", "system_error_diagnostics")


def upgrade() -> None:
    op.execute("""
CREATE TABLE system_errors (
        id UUID NOT NULL,
        company_id UUID NOT NULL,
        actor_membership_id UUID NOT NULL,
        case_id UUID,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        module VARCHAR(16) NOT NULL,
        operation VARCHAR(100) NOT NULL,
        category VARCHAR(16) NOT NULL,
        safe_code VARCHAR(100) NOT NULL,
        message VARCHAR(500) NOT NULL,
        outcome VARCHAR(16) NOT NULL,
        correlation_id UUID NOT NULL,
        source_kind VARCHAR(24),
        source_id UUID,
        PRIMARY KEY (id),
        CONSTRAINT uq_system_error_company UNIQUE (id, company_id),
        CONSTRAINT uq_system_error_source UNIQUE (company_id, source_kind, source_id),
        CONSTRAINT fk_system_error_actor_company FOREIGN KEY(actor_membership_id, company_id)
REFERENCES memberships (id, company_id),
        CONSTRAINT fk_system_error_case_company FOREIGN KEY(case_id, company_id) REFERENCES
reporting_cases (id, company_id),
        CONSTRAINT ck_system_error_module CHECK (module IN
('Identity','Company','Reports','Settings','Documents','API','Other')),
        CONSTRAINT ck_system_error_category CHECK (category IN
('VALIDATION','ACCESS','CONFLICT','PROVIDER','INTERNAL')),
        CONSTRAINT ck_system_error_outcome CHECK (outcome IN ('FAILED','REJECTED')),
        CONSTRAINT ck_system_error_size CHECK (length(operation) BETWEEN 1 AND 100 AND
length(message) BETWEEN 1 AND 500 AND length(safe_code) BETWEEN 1 AND 100),
        CONSTRAINT ck_system_error_source CHECK ((source_kind IS NULL AND source_id IS NULL) OR
(source_kind IS NOT NULL AND source_kind IN ('AUTOMATIC_DESIGN','GENERATION','INTERPRETATION')
AND source_id IS NOT NULL)),
        FOREIGN KEY(company_id) REFERENCES companies (id)
)
""")
    op.execute("""
CREATE INDEX ix_system_error_case_time ON system_errors (company_id, case_id, occurred_at, id)
""")
    op.execute("""
CREATE INDEX ix_system_error_company_time ON system_errors (company_id, occurred_at, id)
""")
    op.execute("""
CREATE TABLE system_error_diagnostics (
        error_id UUID NOT NULL,
        company_id UUID NOT NULL,
        technical_json TEXT NOT NULL,
        truncated BOOLEAN NOT NULL,
        PRIMARY KEY (error_id),
        CONSTRAINT fk_system_error_diagnostic_company FOREIGN KEY(error_id, company_id)
REFERENCES system_errors (id, company_id),
        CONSTRAINT ck_system_error_diagnostic_size CHECK (octet_length(technical_json) <= 4096)
)
""")
    op.create_index("ix_audit_company_time", "audit_events", ["company_id", "created_at", "id"])
    op.execute("""CREATE FUNCTION apbra_system_error_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'system error occurrences are immutable'; END;
        $$ LANGUAGE plpgsql""")
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION apbra_system_error_immutable()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    for table in TABLES:
        if connection.execute(
            sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)
        ).first():
            raise RuntimeError("Cannot downgrade retained system error occurrences")
    op.drop_index("ix_audit_company_time", table_name="audit_events")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION apbra_system_error_immutable()")
