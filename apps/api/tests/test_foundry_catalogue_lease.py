"""Synthetic memory tokens and directory transports only; no authentication."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_foundry_admin_reads import CANARY, agent_page, profile, request

from apbra_api.foundry_admin_reads import ReadAccess, observe
from apbra_api.foundry_catalogue_lease import (
    CatalogueCredentials,
    CatalogueLeaseError,
    CataloguePlan,
    approval_payload,
    validate_approval,
)
from apbra_api.model_provider import FoundryMemoryTokenCredential


def plan_for(r, **changes):
    return CataloguePlan(
        **{
            "company_id": r.company_id,
            "identity_id": r.identity_id,
            "membership_id": r.membership_id,
            "settings_id": r.settings_id,
            "settings_digest": "a" * 64,
            "tenant_id": uuid4(),
            "client_id": uuid4(),
            "profile": profile(),
            "authorization_deadline": time.time() + 60,
            "page_requests": 1,
            **changes,
        }
    )


@pytest.fixture
def credentials():
    held = []

    def make(r=None, **changes):
        r = r or request()
        p = plan_for(r, **changes)
        state = {"active": True}
        token = FoundryMemoryTokenCredential(
            SimpleNamespace(token=CANARY, expires_on=int(time.time() + 120)),
            authorization_deadline=p.authorization_deadline,
            enabled=lambda: True,
            binding_digest="c" * 64,
        )
        c = CatalogueCredentials(p, "synthetic.account", token, lambda: state["active"])
        held.append(c)
        return r, p, state, token, c

    yield make
    for c in held:
        c.close()


def test_exact_directory_read_works_and_has_no_report_or_file_interface(credentials, capsys):
    r, p, state, token, c = credentials()
    seen = []

    def transport(req):
        seen.append(req)
        assert req.method == "GET" and req.url.path == "/api/projects/project/agents"
        return httpx.Response(200, json=agent_page())

    result = observe(r, p.profile, c, transport=httpx.MockTransport(transport))
    assert result["status"] == "OBSERVED" and len(seen) == 1
    assert c.resolve(r) is None  # An exhausted lease cannot retry silently.
    assert not hasattr(c, "acquire") and not hasattr(c, "get_token")
    assert CANARY not in repr(c) and CANARY not in json.dumps(result)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_id", uuid4()),
        ("identity_id", uuid4()),
        ("membership_id", uuid4()),
        ("settings_id", uuid4()),
        ("profile_id", "foreign"),
        ("configuration_id", "foreign"),
        ("endpoint", "https://foreign.invalid"),
        ("agent_version", "foreign"),
        ("operation", "LIST_AGENT_FILES"),
        ("vector_store_id", "store"),
        ("limit", True),
        ("limit", 11),
        ("after", "../foreign"),
    ],
)
def test_wrong_caller_resource_operation_or_page_does_not_spend_lease(credentials, field, value):
    r, p, state, token, c = credentials()
    assert c.resolve(dataclasses.replace(r, **{field: value})) is None
    access = c.resolve(r)
    assert access is not None and c.ready(r, access)


def test_finite_resolve_is_atomic_under_concurrency_and_access_cannot_be_forged(credentials):
    r, p, state, token, c = credentials()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: c.resolve(r), range(16)))
    admitted = [a for a in results if a is not None]
    assert len(admitted) == 1
    a = admitted[0]
    assert not c.ready(r, ReadAccess(r, a.expires_at, a.credential))
    assert a.credential().token == CANARY and c.ready(r, a)
    with pytest.raises(CatalogueLeaseError):
        a.credential()


def test_current_authority_loss_revokes_existing_reads_permanently(credentials):
    r, p, state, token, c = credentials()
    a = c.resolve(r)
    assert a is not None
    state["active"] = False
    assert not c.ready(r, a) and not token.ready()
    state["active"] = True
    assert not c.ready(r, a) and c.resolve(r) is None
    with pytest.raises(CatalogueLeaseError):
        a.credential()


def test_deadline_expiry_closes_token_and_no_cached_access_survives(credentials, monkeypatch):
    r, p, state, token, c = credentials()
    a = c.resolve(r)
    assert a is not None
    monkeypatch.setattr(time, "time", lambda: p.authorization_deadline + 1)
    assert not c.ready(r, a) and not token.ready()


def test_revoke_between_token_acquisition_and_disclosure_returns_nothing(credentials, monkeypatch):
    r, p, state, token, c = credentials()
    a = c.resolve(r)
    assert a is not None
    original = token.get_token

    def acquire(*args):
        result = original(*args)
        state["active"] = False
        return result

    monkeypatch.setattr(token, "get_token", acquire)
    with pytest.raises(CatalogueLeaseError):
        a.credential()
    assert not token.ready()


def test_frames_bind_every_authority_field_and_reject_bool_numeric_aliases():
    r = request()
    p = plan_for(r)
    nonce = "b" * 64
    original = approval_payload(p, nonce, "synthetic.account")
    assert validate_approval(original, p, nonce) == "synthetic.account"
    for key in original["catalogue"]:
        changed = json.loads(json.dumps(original))
        changed["catalogue"][key] = "foreign"
        with pytest.raises(CatalogueLeaseError):
            validate_approval(changed, p, nonce)
    for changed in [
        dict(original, nonce="c" * 64),
        dict(original, v=True),
        dict(original, extra="x"),
        dict(original, account="bad\naccount"),
    ]:
        with pytest.raises(CatalogueLeaseError):
            validate_approval(changed, p, nonce)
    changed = json.loads(json.dumps(original))
    changed["catalogue"]["page_requests"] = True
    with pytest.raises(CatalogueLeaseError):
        validate_approval(changed, p, nonce)


@pytest.mark.parametrize(
    "changes",
    [
        {"authorization_deadline": 0},
        {"authorization_deadline": float("nan")},
        {"page_requests": True},
        {"page_requests": 0},
        {"settings_digest": "bad"},
        {"identity_id": "foreign"},
    ],
)
def test_invalid_trusted_plan_cannot_be_serialized_or_activated(changes):
    with pytest.raises(CatalogueLeaseError):
        plan_for(request(), **changes).wire()


@pytest.mark.parametrize(
    "fault", ["membership", "identity", "company", "role", "settings", "foreign-caller"]
)
def test_real_database_owner_and_settings_rechecked(client, database, fault):
    from uuid import UUID

    from conftest import sign_in

    from apbra_api.foundry_catalogue_lease import owner_is_current
    from apbra_api.persistence import (
        ApplicationSession,
        CompanyRow,
        ExternalIdentityRow,
        MembershipRow,
    )
    from apbra_api.tenant_settings import current_settings, update_settings

    session = sign_in(client)
    actor = session["actor"]
    identity = session["identity"]
    company_id = UUID(actor["company_id"])
    with database.session() as db:
        assert isinstance(db, ApplicationSession)
        current_actor = db.active_actor(UUID(actor["membership_id"]), UUID(identity["id"]))
        original = current_settings(db, company_id)
        snapshot = update_settings(
            db,
            current_actor,
            original.settings.model_copy(
                update={"provider_profile": profile(), "automatic_generation_enabled": False}
            ),
            expected_version=original.version,
            qualified_profiles=(profile(),),
            reason="Wholly synthetic catalogue lease qualification",
        )
    p = CataloguePlan(
        company_id,
        UUID(identity["id"]),
        UUID(actor["membership_id"]),
        snapshot.id,
        snapshot.digest,
        uuid4(),
        uuid4(),
        profile(),
        time.time() + 60,
        1,
    )
    assert owner_is_current(database, p)
    with database.session() as db:
        assert isinstance(db, ApplicationSession)
        if fault == "membership":
            db.get(MembershipRow, p.membership_id).active = False
        elif fault == "identity":
            db.get(ExternalIdentityRow, p.identity_id).active = False
        elif fault == "company":
            db.get(CompanyRow, p.company_id).active = False
        elif fault == "role":
            db.get(MembershipRow, p.membership_id).role = "MEMBER"
        elif fault == "settings":
            update_settings(
                db,
                db.active_actor(p.membership_id, p.identity_id),
                snapshot.settings.model_copy(
                    update={"clarification_enabled": not snapshot.settings.clarification_enabled}
                ),
                expected_version=snapshot.version,
                qualified_profiles=(profile(),),
                reason="Synthetic current settings advance",
            )
        else:
            p = dataclasses.replace(p, identity_id=uuid4())
    assert not owner_is_current(database, p)
