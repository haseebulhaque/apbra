"""Append-only neutral document-provider preparation, calls and receipts.

Revision ID: 20261015_10
Revises: 20261013_09
"""

import sqlalchemy as sa

from alembic import op

revision = "20261015_10"
down_revision = "20261013_09"
branch_labels = None
depends_on = None
TABLES = (
    "tenant_knowledge_dispatches",
    "tenant_knowledge_dispatch_calls",
    "tenant_knowledge_dispatch_receipts",
)


def upgrade() -> None:
    op.execute("""
CREATE TABLE tenant_knowledge_dispatches (
	id UUID NOT NULL,
	company_id UUID NOT NULL,
	document_id UUID NOT NULL,
	command_id UUID NOT NULL,
	revision_id UUID NOT NULL,
	settings_id UUID NOT NULL,
	settings_version INTEGER NOT NULL,
	command_key UUID NOT NULL,
	initiator_identity_id UUID NOT NULL,
	initiator_membership_id UUID NOT NULL,
	action VARCHAR(8) NOT NULL,
	payload_digest VARCHAR(64) NOT NULL,
	sequence INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_dispatch_scope UNIQUE (id, document_id, company_id),
	CONSTRAINT uq_dispatch_identity_key UNIQUE (company_id, initiator_identity_id, command_key),
	CONSTRAINT uq_dispatch_sequence UNIQUE (document_id, company_id, sequence),
	FOREIGN KEY(command_id, document_id, company_id)
        REFERENCES tenant_knowledge_commands (id, document_id, company_id),
	FOREIGN KEY(revision_id, document_id, company_id)
        REFERENCES tenant_knowledge_revisions (id, document_id, company_id),
	FOREIGN KEY(settings_id, company_id)
        REFERENCES tenant_settings_versions (id, company_id),
	FOREIGN KEY(initiator_membership_id, company_id)
        REFERENCES memberships (id, company_id),
	CONSTRAINT ck_dispatch_sequence CHECK (sequence > 0 AND settings_version > 0),
	CONSTRAINT ck_dispatch_action CHECK (action IN ('UPLOAD','UPDATE','DELETE')),
	FOREIGN KEY(initiator_identity_id)
        REFERENCES external_identities (id)
)

""")
    op.execute("""
CREATE TABLE tenant_knowledge_dispatch_calls (
	id UUID NOT NULL,
	company_id UUID NOT NULL,
	document_id UUID NOT NULL,
	dispatch_id UUID NOT NULL,
	sequence INTEGER NOT NULL,
	kind VARCHAR(12) NOT NULL,
	manifest_json BYTEA NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_dispatch_call_scope UNIQUE (id, dispatch_id, document_id, company_id),
	CONSTRAINT uq_dispatch_call_sequence UNIQUE (dispatch_id, sequence),
	FOREIGN KEY(dispatch_id, document_id, company_id)
        REFERENCES tenant_knowledge_dispatches (id, document_id, company_id),
	CONSTRAINT ck_dispatch_call_sequence CHECK (sequence > 0),
	CONSTRAINT ck_dispatch_call_kind CHECK (kind IN ('SEND','RECONCILE'))
)

""")
    op.execute("""
CREATE TABLE tenant_knowledge_dispatch_receipts (
	id UUID NOT NULL,
	company_id UUID NOT NULL,
	document_id UUID NOT NULL,
	dispatch_id UUID NOT NULL,
	call_id UUID NOT NULL,
	outcome VARCHAR(16) NOT NULL,
	acknowledged INTEGER NOT NULL,
	rejected INTEGER NOT NULL,
	reason VARCHAR(32) NOT NULL,
	payload_digest VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_dispatch_receipt_call UNIQUE (call_id),
	FOREIGN KEY(call_id, dispatch_id, document_id, company_id)
        REFERENCES tenant_knowledge_dispatch_calls (id, dispatch_id, document_id, company_id),
	CONSTRAINT ck_dispatch_receipt_outcome CHECK
        (outcome IN ('ACKNOWLEDGED','FAILED','PARTIAL','UNKNOWN')),
	CONSTRAINT ck_dispatch_receipt_counts CHECK (acknowledged >= 0 AND rejected >= 0)
)

""")
    op.execute(
        "CREATE UNIQUE INDEX uq_dispatch_single_send ON "
        "tenant_knowledge_dispatch_calls(dispatch_id) "
        "WHERE kind='SEND'"
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION apbra_knowledge_immutable()"
        )
    op.execute(
        "CREATE TRIGGER trg_dispatch_actor "
        "BEFORE INSERT ON tenant_knowledge_dispatches "
        "FOR EACH ROW EXECUTE FUNCTION apbra_knowledge_actor_binding()"
    )
    op.execute("""CREATE FUNCTION apbra_dispatch_binding() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME='tenant_knowledge_dispatches' THEN
                IF NOT EXISTS (SELECT 1 FROM tenant_knowledge_commands c WHERE c.id=NEW.command_id
                    AND c.company_id=NEW.company_id AND c.document_id=NEW.document_id
                    AND c.target_revision_id=NEW.revision_id
                    AND EXISTS (SELECT 1 FROM tenant_settings_versions s
                      WHERE s.id=NEW.settings_id AND s.company_id=NEW.company_id
                        AND s.version=NEW.settings_version)
                    AND c.kind=CASE NEW.action WHEN 'UPLOAD' THEN 'CREATE'
                        WHEN 'UPDATE' THEN 'REVISION' ELSE 'ARCHIVE' END) THEN
                    RAISE EXCEPTION 'knowledge dispatch source binding invalid';
                END IF;
            ELSE
                IF (NEW.kind='SEND' AND NEW.sequence<>1) OR
                   (NEW.kind='RECONCILE' AND (NEW.sequence<=1 OR NOT EXISTS
                      (SELECT 1 FROM tenant_knowledge_dispatch_calls c
                       WHERE c.dispatch_id=NEW.dispatch_id
                       AND c.kind='SEND' AND c.manifest_json=NEW.manifest_json))) THEN
                    RAISE EXCEPTION 'knowledge dispatch call binding invalid';
                END IF;
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    for table in TABLES[:2]:
        op.execute(
            f"CREATE TRIGGER trg_{table}_binding BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION apbra_dispatch_binding()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    for table in TABLES:
        if connection.execute(
            sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)
        ).first():
            raise RuntimeError("Cannot downgrade retained knowledge dispatch history")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION apbra_dispatch_binding()")
