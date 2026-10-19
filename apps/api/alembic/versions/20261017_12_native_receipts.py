"""Add private native-response receipt metadata without changing report history.

Revision ID: 20261017_12
Revises: 20261015_11
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_12"
down_revision = "20261015_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE native_receive_commands (
 id UUID PRIMARY KEY, company_id UUID NOT NULL, case_id UUID NOT NULL,
 actor_membership_id UUID NOT NULL, context_version INTEGER NOT NULL,
 settings_id UUID NOT NULL, command_key UUID NOT NULL, state VARCHAR(16) NOT NULL,
 http_status INTEGER, provider_status VARCHAR(16), diagnostic_json TEXT,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 CONSTRAINT uq_native_command_scope UNIQUE (id, company_id, case_id, context_version),
 CONSTRAINT uq_native_command_key UNIQUE (company_id, case_id, command_key),
 FOREIGN KEY (case_id, company_id) REFERENCES reporting_cases (id, company_id),
 FOREIGN KEY (actor_membership_id, company_id) REFERENCES memberships (id, company_id),
 CONSTRAINT ck_native_command_context CHECK (context_version >= 1),
 CONSTRAINT ck_native_command_state CHECK
 (state IN ('ADMITTED','RECEIVED','HTTP_ERROR','UNCERTAIN')),
 CONSTRAINT ck_native_command_http CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
 CONSTRAINT ck_native_command_provider_status CHECK (provider_status IS NULL OR provider_status IN
 ('completed','failed','incomplete','queued','in_progress','cancelled','UNKNOWN')),
 CONSTRAINT ck_native_command_diagnostic CHECK
 (diagnostic_json IS NULL OR octet_length(diagnostic_json) <= 4096)
)
""")
    op.execute("""
CREATE TABLE native_response_receipts (
 id UUID PRIMARY KEY, operation_id UUID NOT NULL, company_id UUID NOT NULL,
 case_id UUID NOT NULL, context_version INTEGER NOT NULL, digest VARCHAR(64) NOT NULL,
 size INTEGER NOT NULL, storage_key VARCHAR(1024) NOT NULL,
 created_at TIMESTAMP WITH TIME ZONE NOT NULL,
 CONSTRAINT uq_native_receipt_operation UNIQUE (operation_id),
 FOREIGN KEY (operation_id, company_id, case_id, context_version) REFERENCES
 native_receive_commands (id, company_id, case_id, context_version),
 CONSTRAINT ck_native_receipt_size CHECK (size BETWEEN 1 AND 4000000),
 CONSTRAINT ck_native_receipt_digest CHECK (length(digest) = 64)
)
""")
    op.execute("""CREATE FUNCTION apbra_native_receipt_immutable() RETURNS trigger AS $$
 BEGIN RAISE EXCEPTION 'native receipts are immutable'; END;
 $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER trg_native_receipt_immutable
 BEFORE UPDATE OR DELETE ON native_response_receipts
 FOR EACH ROW EXECUTE FUNCTION apbra_native_receipt_immutable()""")


def downgrade() -> None:
    connection = op.get_bind()
    tables = ("native_receive_commands", "native_response_receipts")
    connection.execute(sa.text("LOCK TABLE " + ", ".join(tables) + " IN ACCESS EXCLUSIVE MODE"))
    for table in tables:
        if connection.execute(
            sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)
        ).first():
            raise RuntimeError("Cannot downgrade retained native-response history")
    op.drop_table("native_response_receipts")
    op.drop_table("native_receive_commands")
    op.execute("DROP FUNCTION apbra_native_receipt_immutable()")
