"""Bind external identities, invitations and sessions to qualified profiles.

Revision ID: 20261002_07
Revises: 20261001_06

Existing rows remain explicitly legacy-unqualified. The application may reuse
them only for the exact local/test issuer; this migration never guesses an
Entra profile or silently links historical identities to a live provider.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_07"
down_revision = "20261001_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "external_identities",
        "invitations",
        "auth_transactions",
        "application_sessions",
    ):
        op.add_column(
            table,
            sa.Column(
                "provider_profile_id",
                sa.String(64),
                nullable=False,
                server_default="legacy-unqualified",
            ),
        )
    op.drop_constraint("uq_identity_issuer_subject", "external_identities", type_="unique")
    op.create_unique_constraint(
        "uq_identity_profile_issuer_subject",
        "external_identities",
        ["provider_profile_id", "issuer", "subject"],
    )
    op.create_index(
        "ix_invitation_profile_issuer_subject",
        "invitations",
        ["provider_profile_id", "invited_issuer", "invited_subject"],
    )
    op.create_table(
        "authentication_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("provider_profile_id", sa.String(64), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_id"], ["external_identities.id"], name="fk_auth_event_identity"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["application_sessions.id"], name="fk_auth_event_session"
        ),
    )
    op.create_index(
        "ix_auth_event_identity_time", "authentication_events", ["identity_id", "created_at"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    collision = connection.execute(
        sa.text(
            "SELECT issuer, subject FROM external_identities "
            "GROUP BY issuer, subject HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if collision is not None:
        raise RuntimeError(
            "Cannot downgrade provider-qualified identities: legacy issuer/subject key collides"
        )
    op.drop_index("ix_auth_event_identity_time", table_name="authentication_events")
    op.drop_table("authentication_events")
    op.drop_index("ix_invitation_profile_issuer_subject", table_name="invitations")
    op.drop_constraint("uq_identity_profile_issuer_subject", "external_identities", type_="unique")
    op.create_unique_constraint(
        "uq_identity_issuer_subject", "external_identities", ["issuer", "subject"]
    )
    for table in (
        "application_sessions",
        "auth_transactions",
        "invitations",
        "external_identities",
    ):
        op.drop_column(table, "provider_profile_id")
