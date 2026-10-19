"""Add immutable native stage/input bindings; retain all original receipts.

Revision ID: 20261017_13
Revises: 20261017_12
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_13"
down_revision = "20261017_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE native_contract_bindings (
 operation_id UUID PRIMARY KEY, company_id UUID NOT NULL, case_id UUID NOT NULL,
 context_version INTEGER NOT NULL, task VARCHAR(32) NOT NULL, contract_id UUID,
 input_digest VARCHAR(64) NOT NULL, profile_digest VARCHAR(64) NOT NULL,
 metadata_json TEXT NOT NULL,
 FOREIGN KEY (operation_id, company_id, case_id, context_version) REFERENCES
 native_receive_commands (id, company_id, case_id, context_version),
 CONSTRAINT ck_native_binding_stage CHECK
 ((task = 'REQUIREMENT_ANALYSIS' AND contract_id IS NULL) OR
  (task = 'REPORT_DESIGN' AND contract_id IS NOT NULL)),
 CONSTRAINT ck_native_binding_digests CHECK
 (length(input_digest) = 64 AND length(profile_digest) = 64),
 CONSTRAINT ck_native_binding_metadata CHECK (octet_length(metadata_json) <= 4096)
)""")
    op.execute("""CREATE TRIGGER trg_native_binding_immutable
 BEFORE UPDATE OR DELETE ON native_contract_bindings
 FOR EACH ROW EXECUTE FUNCTION apbra_native_receipt_immutable()""")


def downgrade() -> None:
    db = op.get_bind()
    db.execute(sa.text("LOCK TABLE native_contract_bindings IN ACCESS EXCLUSIVE MODE"))
    if db.execute(sa.text("SELECT 1 FROM native_contract_bindings LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade retained native-contract bindings")
    op.drop_table("native_contract_bindings")
