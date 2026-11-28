"""Synthetic-only recovery qualification; never access deployment credentials."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import MetaData, Table, select, text
from sqlalchemy.exc import OperationalError

from apbra_api import rekey_tenant_secrets as cli
from apbra_api.domain import ConfigurationUnavailable
from apbra_api.persistence import (
    CompanyRow,
    Database,
    TenantSecretRow,
    TenantSettingsVersionRow,
    utcnow,
)
from apbra_api.tenant_secrets import AesGcmTenantCredentialStore, rekey_tenant_credentials

CANARY = "synthetic-credential-never-print"


def stores() -> tuple[AesGcmTenantCredentialStore, AesGcmTenantCredentialStore]:
    old, new = secrets.token_bytes(32), secrets.token_bytes(32)
    return (
        AesGcmTenantCredentialStore("synthetic-v1", {"synthetic-v1": old}),
        AesGcmTenantCredentialStore("synthetic-v2", {"synthetic-v1": old, "synthetic-v2": new}),
    )


def encoded(store: AesGcmTenantCredentialStore) -> str:
    return json.dumps(
        {
            "active_version": store.active_version,
            "keys": {name: base64.b64encode(key).decode() for name, key in store.keys.items()},
        }
    )


def seed(database: Database, store: AesGcmTenantCredentialStore) -> None:
    with database.session() as db:
        companies = list(db.scalars(select(CompanyRow).order_by(CompanyRow.id)))
        for index, company in enumerate(companies):
            reference = store.protect(
                db,
                company_id=company.id,
                profile_id="synthetic-provider",
                credential=CANARY + str(index),
                actor_membership_id=None,
            )
            settings = db.scalar(
                select(TenantSettingsVersionRow).where(
                    TenantSettingsVersionRow.company_id == company.id
                )
            )
            assert settings is not None
            for version in (2, 3):
                db.add(
                    TenantSettingsVersionRow(
                        company_id=company.id,
                        version=version,
                        settings_json=settings.settings_json,
                        settings_digest=settings.settings_digest,
                        secret_reference_id=reference,
                        created_by_membership_id=None,
                        changed_keys_json="[]",
                        safe_changes_json="{}",
                        reason="Synthetic immutable history fixture",
                        validation_status="PASS",
                    )
                )
            row = db.get(TenantSecretRow, reference)
            assert row is not None
            if index:
                row.revoked_at = utcnow()


def snapshot(database: Database) -> dict[str, list[str]]:
    def safe_json(value: object) -> str:
        return "\\x" + value.hex() if isinstance(value, bytes) else str(value)

    with database.engine.connect() as connection:
        names = list(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            ).scalars()
        )
        result = {}
        for name in names:
            table = Table(name, MetaData(), autoload_with=connection)
            result[name] = sorted(
                json.dumps(dict(row), sort_keys=True, default=safe_json)
                for row in connection.execute(select(table)).mappings()
            )
        return result


def test_authenticated_dry_run_commit_and_old_backup_preserve_history(database: Database) -> None:
    source, target = stores()
    seed(database, source)
    before = snapshot(database)
    with database.session() as db:
        dry = rekey_tenant_credentials(db, source, target)
        assert dry.dry_run and dry.row_count == 2
    assert snapshot(database) == before
    with database.session() as db:
        result = rekey_tenant_credentials(
            db, source, target, dry_run=False, expected_snapshot_digest=dry.snapshot_digest
        )
        assert result.row_count == 2 and not result.dry_run
    after = snapshot(database)
    assert {k: v for k, v in before.items() if k != "tenant_secret_records"} == {
        k: v for k, v in after.items() if k != "tenant_secret_records"
    }
    original = {json.loads(v)["id"]: json.loads(v) for v in before["tenant_secret_records"]}
    changed = {json.loads(v)["id"]: json.loads(v) for v in after["tenant_secret_records"]}
    assert set(original) == set(changed)
    for identifier, old in original.items():
        new = changed[identifier]
        assert new["key_version"] == target.active_version
        assert new["nonce"] != old["nonce"] and new["ciphertext"] != old["ciphertext"]
        for field in (
            "id",
            "company_id",
            "profile_id",
            "created_by_membership_id",
            "created_at",
            "revoked_at",
        ):
            assert new[field] == old[field]
        aad = source._associated_data(UUID(old["company_id"]), old["profile_id"], UUID(identifier))
        old_plain = AESGCM(target.keys[old["key_version"]]).decrypt(
            bytes.fromhex(old["nonce"][2:]), bytes.fromhex(old["ciphertext"][2:]), aad
        )
        new_plain = AESGCM(target.keys[new["key_version"]]).decrypt(
            bytes.fromhex(new["nonce"][2:]), bytes.fromhex(new["ciphertext"][2:]), aad
        )
        assert old_plain == new_plain and new_plain.decode().startswith(CANARY)
    with database.session() as db:
        for row in db.scalars(select(TenantSecretRow)):
            if row.revoked_at is None:
                assert target.resolve(
                    db, company_id=row.company_id, profile_id=row.profile_id, reference_id=row.id
                ).startswith(CANARY)
            for store in [source, target] if row.revoked_at else [source]:
                with pytest.raises(ConfigurationUnavailable):
                    store.resolve(
                        db,
                        company_id=row.company_id,
                        profile_id=row.profile_id,
                        reference_id=row.id,
                    )


@pytest.mark.parametrize("fault", ["wrong-key", "missing-key", "tampered", "wrong-aad"])
def test_bad_original_envelope_is_atomic(database: Database, fault: str) -> None:
    source, target = stores()
    seed(database, source)
    if fault in {"tampered", "wrong-aad"}:
        with database.session() as db:
            row = db.scalar(select(TenantSecretRow).order_by(TenantSecretRow.id.desc()))
            assert row is not None
            if fault == "wrong-aad":
                row.profile_id = "synthetic-altered-binding"
            else:
                row.ciphertext = row.ciphertext[:-1] + bytes([row.ciphertext[-1] ^ 1])
    else:
        version = source.active_version if fault == "wrong-key" else "synthetic-missing"
        source = AesGcmTenantCredentialStore(version, {version: secrets.token_bytes(32)})
        target = AesGcmTenantCredentialStore(
            target.active_version,
            {**source.keys, target.active_version: target.keys[target.active_version]},
        )
    before = snapshot(database)
    with database.session() as db, pytest.raises(ConfigurationUnavailable):
        rekey_tenant_credentials(db, source, target)
    assert snapshot(database) == before


@pytest.mark.parametrize(
    "fault", ["remove-old", "change-old", "reuse-version", "reuse-key", "bad-key"]
)
def test_replacement_keeps_backup_recovery(database: Database, fault: str) -> None:
    source, target = stores()
    seed(database, source)
    keys, version = dict(target.keys), target.active_version
    if fault == "remove-old":
        keys.pop(source.active_version)
    elif fault == "change-old":
        keys[source.active_version] = secrets.token_bytes(32)
    elif fault == "reuse-version":
        version = source.active_version
    elif fault == "reuse-key":
        keys[version] = source.keys[source.active_version]
    else:
        keys[version] = b"bad"
    before = snapshot(database)
    with database.session() as db, pytest.raises(ConfigurationUnavailable):
        rekey_tenant_credentials(db, source, AesGcmTenantCredentialStore(version, keys))
    assert snapshot(database) == before


def test_commit_requires_matching_dry_run_snapshot(database: Database) -> None:
    source, target = stores()
    seed(database, source)
    with database.session() as db, pytest.raises(ConfigurationUnavailable):
        rekey_tenant_credentials(db, source, target, dry_run=False)
    with database.session() as db:
        dry = rekey_tenant_credentials(db, source, target)
    with database.session() as db:
        row = db.scalar(select(TenantSecretRow))
        assert row is not None
        row.revoked_at = utcnow()
    before = snapshot(database)
    with database.session() as db, pytest.raises(ConfigurationUnavailable):
        rekey_tenant_credentials(
            db, source, target, dry_run=False, expected_snapshot_digest=dry.snapshot_digest
        )
    assert snapshot(database) == before


@pytest.mark.parametrize("stage", ["flush", "readback", "created_at", "creator", "revoked_at"])
def test_late_failure_rolls_back(
    database: Database, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    source, target = stores()
    seed(database, source)
    before = snapshot(database)
    with database.session() as db:
        if stage == "flush":
            monkeypatch.setattr(db, "flush", Mock(side_effect=RuntimeError(CANARY)))
            with pytest.raises(RuntimeError):
                rekey_tenant_credentials(db, source, target)
        else:
            original = db.refresh

            def bad_readback(row: TenantSecretRow) -> None:
                original(row)
                if stage == "created_at":
                    row.created_at += timedelta(seconds=1)
                elif stage == "creator":
                    row.created_by_membership_id = uuid4()
                elif stage == "revoked_at":
                    row.revoked_at = None if row.revoked_at else utcnow()
                else:
                    row.ciphertext = b"invalid synthetic readback"

            monkeypatch.setattr(db, "refresh", bad_readback)
            with pytest.raises(ConfigurationUnavailable):
                rekey_tenant_credentials(db, source, target)
    assert snapshot(database) == before


def test_writer_lock_blocks_rekey_without_changes(database: Database) -> None:
    source, target = stores()
    seed(database, source)
    before = snapshot(database)
    with database.engine.begin() as blocker:
        blocker.execute(text("LOCK TABLE tenant_secret_records IN SHARE ROW EXCLUSIVE MODE"))
        with database.session() as db, pytest.raises(OperationalError):
            rekey_tenant_credentials(db, source, target)
    assert snapshot(database) == before


def test_empty_database_and_active_transaction_rejected(database: Database) -> None:
    source, target = stores()
    with database.session() as db:
        with pytest.raises(ConfigurationUnavailable):
            rekey_tenant_credentials(db, source, target)
        db.execute(text("SELECT 1"))
        with pytest.raises(ConfigurationUnavailable):
            rekey_tenant_credentials(db, source, target)


@pytest.mark.parametrize(
    "raw,profile",
    [
        ("postgresql+psycopg://postgres@external.example:5432/apbra", "development"),
        ("postgresql+psycopg://postgres@127.0.0.1:5432/apbra", "hosted"),
        ("postgresql+psycopg://postgres@127.0.0.1/apbra", "test"),
        ("postgresql+psycopg://postgres@127.0.0.1:5432/apbra?host=external.example", "test"),
        ("sqlite://", "test"),
    ],
)
def test_external_or_ambiguous_target_rejected(raw: str, profile: str) -> None:
    with pytest.raises((ConfigurationUnavailable, ValueError)):
        cli.qualified_local_target(raw, profile)


@pytest.mark.parametrize("name", cli._TARGET_ENV)
def test_inherited_libpq_target_rejected(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "synthetic-ambiguous")
    with pytest.raises(ConfigurationUnavailable):
        cli.qualified_local_target("postgresql+psycopg://postgres@127.0.0.1:5432/apbra", "test")


@pytest.mark.parametrize(
    "mode", ["commit", "cancel", "wrong-target", "wrong-maintenance", "bad-keyring", "error"]
)
def test_hidden_cli_and_safe_errors(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    source, target = stores()
    seed(database, source)
    before = snapshot(database)
    for name in cli._TARGET_ENV:
        monkeypatch.delenv(name, raising=False)
    raw = database.engine.url.render_as_string(hide_password=False)
    _, label = cli.qualified_local_target(raw, "test")
    answers = iter(
        [
            "test",
            "wrong" if mode == "wrong-target" else label,
            "wrong"
            if mode == "wrong-maintenance"
            else "BACKUP VERIFIED API STOPPED TERMINAL RECORDING OFF",
            f"REKEY {label}" if mode == "commit" else "cancel",
        ]
    )
    hidden = iter(
        [raw, encoded(source), "invalid " + CANARY if mode == "bad-keyring" else encoded(target)]
    )
    for stream in (cli.sys.stdin, cli.sys.stdout, cli.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys, "argv", ["rekey"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    def hidden_prompt(prompt: str, *, stream: object) -> str:
        assert stream is cli.sys.stderr and "hidden" in prompt
        return next(hidden)

    monkeypatch.setattr(cli.getpass, "getpass", hidden_prompt)
    if mode == "error":
        monkeypatch.setattr(cli, "rekey_tenant_credentials", Mock(side_effect=RuntimeError(CANARY)))
    result = cli.main()
    output = capsys.readouterr()
    assert all(
        value not in output.out + output.err
        for value in [CANARY, raw, encoded(source), encoded(target)]
    )
    if mode == "commit":
        assert result == 0 and snapshot(database) != before and "Committed" in output.out
    else:
        assert result == (0 if mode == "cancel" else 2)
        assert snapshot(database) == before


def test_secret_arguments_and_non_tty_fail_before_connect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = Mock()
    monkeypatch.setattr(cli, "create_engine", engine)
    monkeypatch.setattr(cli.sys, "argv", ["rekey", "--credential", CANARY])
    assert cli.main() == 2
    assert CANARY not in capsys.readouterr().err
    monkeypatch.setattr(cli.sys, "argv", ["rekey"])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli.main() == 2
    engine.assert_not_called()


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        "null",
        "not json",
        '{"active_version":"a","active_version":"b","keys":{}}',
        '{"active_version":"a","keys":{"a":"bad","a":"bad"}}',
        '{"active_version":"a","keys":{"a":"bad"},"extra":"bad"}',
    ],
)
def test_malformed_and_ambiguous_keyring_fails_closed(raw: str) -> None:
    with pytest.raises(ConfigurationUnavailable):
        AesGcmTenantCredentialStore.from_bootstrap(raw)
