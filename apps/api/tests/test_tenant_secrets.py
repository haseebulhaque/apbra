"""Protected tenant credential references never expose plaintext at rest or over API."""

from __future__ import annotations

import base64
import json
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import select

from apbra_api.domain import ConfigurationUnavailable
from apbra_api.persistence import CompanyRow, Database, TenantSecretRow, utcnow
from apbra_api.tenant_secrets import AesGcmTenantCredentialStore, credential_status


def _store() -> AesGcmTenantCredentialStore:
    keyring = {
        "active_version": "synthetic-key-v1",
        "keys": {"synthetic-key-v1": base64.b64encode(secrets.token_bytes(32)).decode()},
    }
    result = AesGcmTenantCredentialStore.from_bootstrap(json.dumps(keyring))
    assert result is not None
    return result


def test_encryption_tenant_and_profile_binding_survive_database_restart(database: Database) -> None:
    store = _store()
    with database.session() as db:
        companies = db.scalars(select(CompanyRow).order_by(CompanyRow.name)).all()
        company_id, foreign_id = companies[0].id, companies[1].id
        reference = store.protect(
            db,
            company_id=company_id,
            profile_id="synthetic-profile-a",
            credential="synthetic-sensitive-test-value",
            actor_membership_id=None,
        )
        row = db.get(TenantSecretRow, reference)
        assert row is not None
        assert b"synthetic-sensitive-test-value" not in row.ciphertext
        assert credential_status(db, company_id=company_id, reference_id=reference) == {
            "status": "CONFIGURED",
            "maskedValue": "***",
            "updatedAt": row.created_at.isoformat(),
            "canReplace": True,
            "canRotate": True,
        }
    database.engine.dispose()
    reopened = Database(str(database.engine.url.render_as_string(hide_password=False)))
    try:
        with reopened.session() as db:
            assert (
                store.resolve(
                    db,
                    company_id=company_id,
                    profile_id="synthetic-profile-a",
                    reference_id=reference,
                )
                == "synthetic-sensitive-test-value"
            )
            for tenant, profile, target in (
                (foreign_id, "synthetic-profile-a", reference),
                (company_id, "synthetic-profile-b", reference),
                (company_id, "synthetic-profile-a", uuid4()),
            ):
                with pytest.raises(ConfigurationUnavailable):
                    store.resolve(db, company_id=tenant, profile_id=profile, reference_id=target)
            row = db.get(TenantSecretRow, reference)
            assert row is not None
            row.revoked_at = utcnow()
        with reopened.session() as db:
            with pytest.raises(ConfigurationUnavailable):
                store.resolve(
                    db,
                    company_id=company_id,
                    profile_id="synthetic-profile-a",
                    reference_id=reference,
                )
    finally:
        reopened.engine.dispose()


def test_missing_or_malformed_deployment_keyring_fails_closed() -> None:
    assert AesGcmTenantCredentialStore.from_bootstrap(None) is None
    for malformed in ("{}", '{"active_version":"a","keys":{"a":"not-base64"}}'):
        with pytest.raises(ConfigurationUnavailable):
            AesGcmTenantCredentialStore.from_bootstrap(malformed)
