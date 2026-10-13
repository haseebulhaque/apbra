"""Retained tenant-private plaintext drafts, without provider dispatch.

Revision ID: 20261013_09
Revises: 20261003_08
"""

import sqlalchemy as sa

from alembic import op

revision = "20261013_09"
down_revision = "20261003_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("current_revision_id", sa.Uuid()),
        sa.Column("current_operation_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("id", "company_id", name="uq_knowledge_document_company"),
    )
    op.create_table(
        "tenant_knowledge_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_revision_id", sa.Uuid()),
        sa.Column("creator_membership_id", sa.Uuid(), nullable=False),
        sa.Column("creator_identity_id", sa.Uuid(), nullable=False),
        sa.Column("title_original", sa.LargeBinary(), nullable=False),
        sa.Column("source_version_original", sa.LargeBinary(), nullable=False),
        sa.Column("text_original", sa.LargeBinary(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("text_byte_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "document_id", "company_id", name="uq_knowledge_revision_scope"),
        sa.ForeignKeyConstraint(
            ["document_id", "company_id"],
            ["tenant_knowledge_documents.id", "tenant_knowledge_documents.company_id"],
            name="fk_knowledge_revision_document",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_revision_id", "document_id", "company_id"],
            [
                "tenant_knowledge_revisions.id",
                "tenant_knowledge_revisions.document_id",
                "tenant_knowledge_revisions.company_id",
            ],
            name="fk_knowledge_revision_predecessor",
        ),
        sa.ForeignKeyConstraint(
            ["creator_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_knowledge_revision_creator",
        ),
        sa.ForeignKeyConstraint(["creator_identity_id"], ["external_identities.id"]),
        sa.CheckConstraint("text_byte_count >= 0", name="ck_knowledge_revision_size"),
    )
    op.create_table(
        "tenant_knowledge_commands",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.Uuid(), nullable=False),
        sa.Column("initiator_identity_id", sa.Uuid(), nullable=False),
        sa.Column("initiator_membership_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("target_revision_id", sa.Uuid(), nullable=False),
        sa.Column("expected_current_revision_id", sa.Uuid()),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "document_id", "company_id", name="uq_knowledge_command_scope"),
        sa.UniqueConstraint(
            "company_id",
            "initiator_identity_id",
            "command_key",
            name="uq_knowledge_command_identity_key",
        ),
        sa.UniqueConstraint(
            "company_id", "document_id", "sequence", name="uq_knowledge_command_sequence"
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "company_id"],
            ["tenant_knowledge_documents.id", "tenant_knowledge_documents.company_id"],
            name="fk_knowledge_command_document",
        ),
        sa.ForeignKeyConstraint(
            ["target_revision_id", "document_id", "company_id"],
            [
                "tenant_knowledge_revisions.id",
                "tenant_knowledge_revisions.document_id",
                "tenant_knowledge_revisions.company_id",
            ],
            name="fk_knowledge_command_target",
        ),
        sa.ForeignKeyConstraint(
            ["expected_current_revision_id", "document_id", "company_id"],
            [
                "tenant_knowledge_revisions.id",
                "tenant_knowledge_revisions.document_id",
                "tenant_knowledge_revisions.company_id",
            ],
            name="fk_knowledge_command_expected",
        ),
        sa.ForeignKeyConstraint(
            ["initiator_membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
            name="fk_knowledge_command_initiator",
        ),
        sa.ForeignKeyConstraint(["initiator_identity_id"], ["external_identities.id"]),
        sa.CheckConstraint(
            "kind IN ('CREATE','REVISION','ARCHIVE')", name="ck_knowledge_command_kind"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_knowledge_command_sequence"),
    )
    for column, table, name in (
        (
            "current_revision_id",
            "tenant_knowledge_revisions",
            "fk_knowledge_document_current_revision",
        ),
        (
            "current_operation_id",
            "tenant_knowledge_commands",
            "fk_knowledge_document_current_operation",
        ),
    ):
        op.create_foreign_key(
            name,
            "tenant_knowledge_documents",
            table,
            [column, "id", "company_id"],
            ["id", "document_id", "company_id"],
            deferrable=True,
            initially="DEFERRED",
        )
    op.execute("""CREATE FUNCTION apbra_knowledge_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'knowledge originals and commands are immutable'; END;
        $$ LANGUAGE plpgsql""")
    for table in ("tenant_knowledge_revisions", "tenant_knowledge_commands"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION apbra_knowledge_immutable()"
        )
    op.execute(
        "CREATE TRIGGER trg_knowledge_document_retained BEFORE DELETE ON "
        "tenant_knowledge_documents FOR EACH ROW EXECUTE FUNCTION apbra_knowledge_immutable()"
    )
    op.execute("""CREATE FUNCTION apbra_knowledge_actor_binding() RETURNS trigger AS $$
        DECLARE member_id uuid; actor_identity uuid;
        BEGIN
            IF TG_TABLE_NAME = 'tenant_knowledge_revisions' THEN
                member_id := NEW.creator_membership_id; actor_identity := NEW.creator_identity_id;
            ELSE
                member_id := NEW.initiator_membership_id;
                actor_identity := NEW.initiator_identity_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM memberships WHERE id=member_id
                AND company_id=NEW.company_id AND memberships.identity_id=actor_identity) THEN
                RAISE EXCEPTION 'knowledge actor binding invalid';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    for table in ("tenant_knowledge_revisions", "tenant_knowledge_commands"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_actor BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION apbra_knowledge_actor_binding()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE tenant_knowledge_documents, tenant_knowledge_revisions, "
            "tenant_knowledge_commands IN ACCESS EXCLUSIVE MODE"
        )
    )
    queries = (
        sa.text("SELECT 1 FROM tenant_knowledge_documents LIMIT 1"),
        sa.text("SELECT 1 FROM tenant_knowledge_revisions LIMIT 1"),
        sa.text("SELECT 1 FROM tenant_knowledge_commands LIMIT 1"),
    )
    for query in queries:
        if connection.execute(query).first():
            raise RuntimeError(
                "Cannot downgrade committed knowledge drafts: retained originals and history"
            )
    op.drop_constraint("fk_knowledge_document_current_operation", "tenant_knowledge_documents")
    op.drop_constraint("fk_knowledge_document_current_revision", "tenant_knowledge_documents")
    for table in (
        "tenant_knowledge_commands",
        "tenant_knowledge_revisions",
        "tenant_knowledge_documents",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION apbra_knowledge_actor_binding()")
    op.execute("DROP FUNCTION apbra_knowledge_immutable()")
