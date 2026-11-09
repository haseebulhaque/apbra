"""Add optional contact snapshots without rewriting existing identities or sessions."""

import sqlalchemy as sa

from alembic import op

revision = "20261105_16"
down_revision = "20261105_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_identity_contacts",
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("application_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("LOCK TABLE session_identity_contacts IN ACCESS EXCLUSIVE MODE")
    if connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM session_identity_contacts)")
    ).scalar_one():
        raise RuntimeError(
            "Cannot downgrade retained authenticated email snapshots; "
            "retain this table for application rollback"
        )
    op.drop_table("session_identity_contacts")
