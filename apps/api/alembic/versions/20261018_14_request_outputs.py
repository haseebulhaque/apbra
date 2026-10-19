"""Add immutable request-bound opaque outputs; retain all existing history."""
import sqlalchemy as sa

from alembic import op

revision = '20261018_14'
down_revision = '20261017_13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint('uq_native_receipt_case_company', 'native_response_receipts',
                                ['id', 'case_id', 'company_id'])
    op.execute('''CREATE TABLE request_outputs (
 id UUID PRIMARY KEY, company_id UUID NOT NULL, case_id UUID NOT NULL,
 request_version_id UUID NOT NULL, context_version INTEGER NOT NULL,
 actor_membership_id UUID NOT NULL, command_key UUID NOT NULL,
 payload_digest VARCHAR(64) NOT NULL, native_receipt_id UUID,
 origin VARCHAR(24) NOT NULL, filename VARCHAR(255) NOT NULL,
 storage_key VARCHAR(600) NOT NULL UNIQUE, content_digest VARCHAR(64) NOT NULL,
 byte_size INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 CONSTRAINT fk_output_request FOREIGN KEY(request_version_id,case_id,company_id)
 REFERENCES case_request_versions(id,case_id,company_id),
 CONSTRAINT fk_output_actor FOREIGN KEY(actor_membership_id,company_id)
 REFERENCES memberships(id,company_id),
 CONSTRAINT fk_output_native FOREIGN KEY(native_receipt_id,case_id,company_id)
 REFERENCES native_response_receipts(id,case_id,company_id),
 CONSTRAINT uq_request_output_command UNIQUE(company_id,case_id,actor_membership_id,command_key),
 CONSTRAINT ck_request_output_bytes CHECK(byte_size BETWEEN 1 AND 25000000),
 CONSTRAINT ck_request_output_context CHECK(context_version >= 1),
 CONSTRAINT ck_request_output_digest CHECK(length(content_digest)=64 AND length(payload_digest)=64),
 CONSTRAINT ck_request_output_origin CHECK
 ((origin='IMPORTED_OUTPUT' AND native_receipt_id IS NULL) OR
 (origin IN ('NATIVE_FILE_TREE','NATIVE_OUTPUT') AND native_receipt_id IS NOT NULL))
)''')
    op.create_index('ix_request_outputs_case_created','request_outputs',['case_id','created_at'])
    op.execute('''CREATE TRIGGER trg_request_outputs_immutable BEFORE UPDATE OR DELETE
 ON request_outputs FOR EACH ROW EXECUTE FUNCTION apbra_native_receipt_immutable()''')


def downgrade() -> None:
    db = op.get_bind()
    db.execute(sa.text('LOCK TABLE request_outputs IN ACCESS EXCLUSIVE MODE'))
    if db.execute(sa.text('SELECT 1 FROM request_outputs LIMIT 1')).first():
        raise RuntimeError('Cannot downgrade retained request outputs')
    op.drop_table('request_outputs')
    op.drop_constraint('uq_native_receipt_case_company','native_response_receipts',type_='unique')
