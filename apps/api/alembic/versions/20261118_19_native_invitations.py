"""Native invitations for verified password accounts, separate from federation grants."""

import sqlalchemy as sa

from alembic import op

revision = "20261118_19"
down_revision = "20261108_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE native_invitations (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES companies(id),
            issued_by_membership_id uuid NOT NULL,
            issuer_account_id uuid NOT NULL REFERENCES password_accounts(id),
            issuer_epoch integer NOT NULL CHECK (issuer_epoch > 0),
            delivery_address varchar(320) NOT NULL,
            delivery_key varchar(320) NOT NULL,
            recipient_account_id uuid REFERENCES password_accounts(id),
            recipient_epoch integer CHECK (recipient_epoch > 0),
            role varchar(32) NOT NULL CHECK (role IN ('MEMBER','EXPERT','COMPANY_ADMIN')),
            token_digest varchar(64) NOT NULL UNIQUE,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL CHECK (expires_at > created_at),
            settings_version_id uuid NOT NULL,
            delivery_state varchar(16) NOT NULL
                CHECK (delivery_state IN ('PREPARED','SUBMITTED','FAILED','UNCONFIRMED')),
            revoked_at timestamptz,
            revoke_reason varchar(40),
            consumed_at timestamptz,
            consumed_by_account_id uuid REFERENCES password_accounts(id),
            target_membership_id uuid,
            UNIQUE (id, company_id),
            FOREIGN KEY (issued_by_membership_id,company_id) REFERENCES memberships(id,company_id),
            FOREIGN KEY (target_membership_id,company_id) REFERENCES memberships(id,company_id),
            FOREIGN KEY (settings_version_id,company_id)
                REFERENCES tenant_settings_versions(id,company_id),
            CHECK ((recipient_account_id IS NULL) = (recipient_epoch IS NULL)),
            CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL)),
            CHECK ((consumed_at IS NULL AND consumed_by_account_id IS NULL
                    AND target_membership_id IS NULL)
                OR (consumed_at IS NOT NULL AND consumed_by_account_id IS NOT NULL
                    AND target_membership_id IS NOT NULL AND revoked_at IS NULL
                    AND delivery_state = 'SUBMITTED' AND recipient_account_id IS NOT NULL
                    AND consumed_by_account_id = recipient_account_id))
        );
        CREATE INDEX ix_native_invitations_page ON native_invitations(company_id, created_at, id);

        CREATE TABLE native_invitation_commands (
            company_id uuid NOT NULL REFERENCES companies(id),
            issuer_identity_id uuid NOT NULL REFERENCES external_identities(id),
            command_key varchar(200) NOT NULL,
            payload_digest varchar(64) NOT NULL,
            invitation_id uuid NOT NULL UNIQUE,
            PRIMARY KEY (company_id,issuer_identity_id,command_key),
            FOREIGN KEY (invitation_id, company_id) REFERENCES native_invitations(id, company_id)
        );

        CREATE TABLE native_invitation_audit (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL,
            event varchar(40) NOT NULL CHECK (event IN
                ('ISSUED','SUBMISSION_ACCEPTED','SUBMISSION_FAILED','SUBMISSION_UNCONFIRMED',
                 'REVOKED','ACCEPTED','RECEIPT_REPLAYED','REJECTED','EXPIRED','EPOCH_INVALID')),
            invitation_id uuid REFERENCES native_invitations(id),
            company_id uuid REFERENCES companies(id),
            account_id uuid REFERENCES password_accounts(id),
            membership_id uuid,
            FOREIGN KEY (membership_id,company_id) REFERENCES memberships(id,company_id)
        );

        CREATE FUNCTION apbra_check_native_invitation_parties() RETURNS trigger
            LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.delivery_state <> 'PREPARED' OR NEW.consumed_at IS NOT NULL
                   OR NEW.revoked_at IS NOT NULL OR NOT EXISTS (
                    SELECT FROM memberships m
                    JOIN native_account_principals p ON p.identity_id=m.identity_id
                    WHERE m.id=NEW.issued_by_membership_id AND m.company_id=NEW.company_id
                    AND p.account_id=NEW.issuer_account_id
                ) THEN RAISE EXCEPTION 'native invitation issuer binding invalid'; END IF;
            ELSIF OLD.recipient_account_id IS NULL AND NEW.recipient_account_id IS NOT NULL
                  AND NEW.recipient_epoch <> 1 THEN
                RAISE EXCEPTION 'unresolved native recipient must bind at its initial epoch';
            END IF;
            IF NEW.consumed_at IS NOT NULL AND NOT EXISTS (
                SELECT FROM memberships m
                    JOIN native_account_principals p ON p.identity_id=m.identity_id
                WHERE m.id=NEW.target_membership_id AND m.company_id=NEW.company_id
                AND p.account_id=NEW.consumed_by_account_id AND m.role=NEW.role AND m.active
            ) THEN RAISE EXCEPTION 'native invitation recipient membership invalid'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER native_invitation_parties BEFORE INSERT OR UPDATE ON native_invitations
            FOR EACH ROW EXECUTE FUNCTION apbra_check_native_invitation_parties();

        CREATE FUNCTION apbra_preserve_native_invitation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' OR TG_TABLE_NAME <> 'native_invitations' THEN
                RAISE EXCEPTION 'native invitation history is immutable';
            END IF;
            IF ROW(NEW.id,NEW.company_id,NEW.issued_by_membership_id,NEW.issuer_account_id,
                   NEW.issuer_epoch,NEW.delivery_address,NEW.delivery_key,NEW.role,NEW.token_digest,
                   NEW.created_at,NEW.expires_at,NEW.settings_version_id)
                IS DISTINCT FROM
               ROW(OLD.id,OLD.company_id,OLD.issued_by_membership_id,OLD.issuer_account_id,
                   OLD.issuer_epoch,OLD.delivery_address,OLD.delivery_key,OLD.role,OLD.token_digest,
                   OLD.created_at,OLD.expires_at,OLD.settings_version_id)
               OR (OLD.consumed_at IS NOT NULL OR OLD.revoked_at IS NOT NULL)
               OR (OLD.delivery_state <> 'PREPARED' AND NEW.delivery_state <> OLD.delivery_state)
               OR (ROW(NEW.recipient_account_id,NEW.recipient_epoch) IS DISTINCT FROM
                   ROW(OLD.recipient_account_id,OLD.recipient_epoch)
                   AND (OLD.recipient_account_id IS NOT NULL OR NEW.consumed_at IS NULL)) THEN
                RAISE EXCEPTION 'native invitation binding is immutable';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER native_invitation_guard BEFORE UPDATE OR DELETE ON native_invitations
            FOR EACH ROW EXECUTE FUNCTION apbra_preserve_native_invitation();
        CREATE TRIGGER native_invitation_command_guard BEFORE UPDATE OR DELETE
            ON native_invitation_commands FOR EACH ROW
            EXECUTE FUNCTION apbra_preserve_native_invitation();
        CREATE TRIGGER native_invitation_audit_guard BEFORE UPDATE OR DELETE
            ON native_invitation_audit FOR EACH ROW
            EXECUTE FUNCTION apbra_preserve_native_invitation();
    """)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS(SELECT FROM native_invitations)
            OR EXISTS(SELECT FROM native_invitation_commands)
            OR EXISTS(SELECT FROM native_invitation_audit)
    """)
    ):
        raise RuntimeError("Cannot downgrade retained native invitation history")
    op.drop_table("native_invitation_audit")
    op.drop_table("native_invitation_commands")
    op.drop_table("native_invitations")
    op.execute("DROP FUNCTION apbra_preserve_native_invitation()")
    op.execute("DROP FUNCTION apbra_check_native_invitation_parties()")
