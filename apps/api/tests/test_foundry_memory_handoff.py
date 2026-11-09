"""Synthetic receiver protocol and selected-company lease boundaries."""

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from test_foundry_agent_details import CANARY
from test_foundry_browser_metadata import setup

from apbra_api import foundry_memory_handoff as m
from apbra_api.foundry_memory_handoff import HandoffError

NONCE = "a" * 64


def frame(plan: Any, **changes: Any) -> bytes:
    value = dict(
        v=1,
        nonce=NONCE,
        company=str(plan.company_id),
        tenant=str(plan.tenant_id),
        client=str(plan.client_id),
        deadline=plan.authorization_deadline,
        account="synthetic.account",
        token=CANARY,
        expires=int(time.time() + 100),
    )
    value.update(changes)
    raw = json.dumps(value).encode()
    return len(raw).to_bytes(4, "big") + raw


def account_frame(plan: Any, **changes: Any) -> bytes:
    token_frame = frame(plan, **changes)
    value = json.loads(token_frame[4:])
    value.pop("token")
    value.pop("expires")
    raw = json.dumps(value).encode()
    return len(raw).to_bytes(4, "big") + raw


class Pipe:
    def __init__(self, value: bytes) -> None:
        self.value = io.BytesIO(value)
        self.output = bytearray()
        self.closed = False
        self.alive = True

    def read(self, n: int, deadline: float) -> bytes:
        return self.value.read(min(n, 7))

    def write(self, value: bytes) -> None:
        self.output.extend(value)

    def connected(self, timeout: float) -> bool:
        time.sleep(min(timeout, 0.01))
        return self.alive

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "changes",
    [
        dict(v=True),
        dict(v=2),
        dict(nonce="b" * 64),
        dict(company=str(uuid4())),
        dict(tenant=str(uuid4())),
        dict(client=str(uuid4())),
        dict(deadline=0),
        dict(account="\n"),
        dict(token=""),
        {"token": "x\n"},
        {"token": "é"},
        dict(expires=True),
        dict(expires=0),
        dict(expires=1.1),
        dict(extra=CANARY),
    ],
)
def test_invalid_frames_never_construct_lease(monkeypatch: Any, changes: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(frame(c.plan, **changes))
    with pytest.raises(HandoffError, match=m.ERROR) as error:
        m.receive(p, c.plan, NONCE)
    assert CANARY not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\0\0",
        b"\0\0\0\0",
        (m.MAX_FRAME + 1).to_bytes(4, "big"),
        b"\0\0\0\x02{}",
        b'\0\0\0\x0d{"v":1,"v":1}',
        b"\0\0\0\x04null",
    ],
)
def test_truncation_duplicate_shape_bounds(monkeypatch: Any, payload: bytes) -> None:
    c = setup(monkeypatch)
    with pytest.raises(HandoffError, match=m.ERROR):
        m.receive(Pipe(payload), c.plan, NONCE)


def test_receiver_lease_current_settings_and_company(monkeypatch: Any, capsys: Any) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    held = []

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        credential = app["foundry_metadata_credentials"]
        held.append(credential)
        assert app["foundry_credentials"] is None
        assert credential.ready(c.plan.company_id, c.profile)
        assert not credential.ready(uuid4(), c.profile)
        assert credential.resolve(c.plan.company_id, c.profile).credential().token == CANARY
        c.snapshot = replace(c.snapshot, id=uuid4())
        assert not credential.ready(c.plan.company_id, c.profile)
        assert stopped.wait(1)
        assert not credential.ready(c.plan.company_id, c.profile)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed and held and not held[0].ready(c.plan.company_id, c.profile)
    assert CANARY.encode() not in p.output
    assert capsys.readouterr().out == ""


def test_disconnect_revokes_and_stops(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        p.alive = False
        assert stopped.wait(1)
        assert not app["foundry_metadata_credentials"].ready(c.plan.company_id, c.profile)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed


def test_cleanup_errors_sanitized_and_all_resources_attempted(
    monkeypatch: Any, capsys: Any
) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def broken() -> None:
        p.closed = True
        print(CANARY)
        raise RuntimeError(CANARY)

    p.close = broken
    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_receiver(
            c.plan,
            p,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            nonce_factory=lambda: NONCE,
        )
    assert p.closed and CANARY not in capsys.readouterr().out


def test_runtime_attestation_required_before_challenge(monkeypatch: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_receiver(
            c.plan, p, settings=c.settings, snapshot_loader=lambda: c.snapshot, runtime=True
        )
    assert p.closed and p.output == b""


@pytest.mark.parametrize(
    "changes",
    [
        dict(nonce="b" * 64),
        dict(company=str(uuid4())),
        dict(tenant=str(uuid4())),
        dict(client=str(uuid4())),
        dict(account="\n"),
        dict(deadline=0),
    ],
)
def test_account_preflight_refuses_before_bearer(monkeypatch: Any, changes: Any) -> None:
    c = setup(monkeypatch)
    p = Pipe(m.HELLO + account_frame(c.plan, **changes) + frame(c.plan))
    with pytest.raises(HandoffError):
        m.run_receiver(
            c.plan,
            p,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            nonce_factory=lambda: NONCE,
        )
    assert b"ACCOUNT_ACCEPTED" not in p.output and b"HANDOFF_READY" not in p.output and p.closed


@pytest.mark.parametrize("gate", [None, lambda: False, lambda: True])
def test_existing_runtime_attestation_and_trusted_gate_only(monkeypatch: Any, gate: Any) -> None:
    from pydantic import SecretStr

    from apbra_api.config import FoundryHostBinding

    c = setup(monkeypatch)
    c.settings.profile = "development"
    binding = FoundryHostBinding(
        company_id=c.plan.company_id,
        tenant_id=c.plan.tenant_id,
        client_id=c.plan.client_id,
        home_account_id="synthetic.account",
        provider_profile=c.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=c.plan.authorization_deadline,
    )
    c.settings.foundry_host_enabled = True
    c.settings.foundry_host_binding_json = SecretStr(binding.model_dump_json())
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)

    def serve(app: Any, *args: Any) -> None:
        assert app["foundry_credentials"].ready(c.plan.company_id, c.profile) is (
            gate is not None and gate()
        )
        assert app["foundry_metadata_credentials"].ready(c.plan.company_id, c.profile)

    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))
    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
        runtime=True,
        invocation_gate=gate,
    )
    assert p.closed


def test_monitor_never_reads_settings_and_cannot_outlive_suppression(
    monkeypatch: Any, capsys: Any
) -> None:
    c = setup(monkeypatch)
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    owner = threading.get_ident()
    seen = []
    entered = threading.Event()
    released = threading.Event()
    finished = threading.Event()
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def load() -> Any:
        seen.append(threading.get_ident())
        assert threading.get_ident() == owner
        return c.snapshot

    def connected(timeout: float) -> bool:
        entered.set()
        assert released.wait(1)
        print(CANARY)
        finished.set()
        return False

    def close() -> None:
        p.closed = True
        released.set()

    p.connected = connected
    p.close = close

    def serve(*args: Any) -> None:
        assert entered.wait(1)

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=load,
        serve=serve,
        nonce_factory=lambda: NONCE,
    )
    assert p.closed and finished.is_set() and seen and set(seen) == {owner}
    assert CANARY not in capsys.readouterr().out


def test_docker_server_uses_explicit_internal_listener(monkeypatch: Any) -> None:
    import uvicorn

    captured = {}

    class Server:
        def __init__(self, config: Any) -> None:
            self.should_exit = False

        def run(self) -> None:
            pass

    def config(app: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(uvicorn, "Config", config)
    monkeypatch.setattr(uvicorn, "Server", Server)
    stop = threading.Event()
    m._serve(object(), (m.CONTAINER_LISTEN, 8000), stop)
    assert captured["host"] == m.CONTAINER_LISTEN and captured["port"] == 8000
    assert captured["access_log"] is False and stop.is_set()


def test_runtime_drift_clears_lease_without_metadata_request(monkeypatch: Any) -> None:
    from pydantic import SecretStr

    from apbra_api.config import FoundryHostBinding

    c = setup(monkeypatch)
    c.settings.profile = "development"
    binding = FoundryHostBinding(
        company_id=c.plan.company_id,
        tenant_id=c.plan.tenant_id,
        client_id=c.plan.client_id,
        home_account_id="synthetic.account",
        provider_profile=c.profile,
        knowledge_binding="explicit-fixture-knowledge",
        knowledge_scope="TENANT_PRIVATE",
        agent_version="configured-version",
        qualification="LIVE_METADATA_VERIFIED",
        manual_authentication_approved=True,
        authorization_deadline=c.plan.authorization_deadline,
    )
    c.settings.foundry_host_enabled = True
    c.settings.foundry_host_binding_json = SecretStr(binding.model_dump_json())
    monkeypatch.setattr(m, "create_app", lambda **kw: kw)
    p = Pipe(m.HELLO + account_frame(c.plan) + frame(c.plan))

    def serve(app: Any, settings: Any, stopped: threading.Event) -> None:
        runtime = app["foundry_credentials"]
        assert runtime.ready(c.plan.company_id, c.profile)
        c.snapshot = replace(c.snapshot, id=uuid4())
        assert not runtime.ready(c.plan.company_id, c.profile)
        assert stopped.is_set()
        assert not app["foundry_metadata_credentials"]._token.ready()

    m.run_receiver(
        c.plan,
        p,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
        runtime=True,
        invocation_gate=lambda: True,
    )
    assert p.closed


def catalogue_setup(monkeypatch):
    c = setup(monkeypatch)
    c.settings = c.settings.model_copy(update={"automatic_generation_enabled": False})
    return c


def catalogue_plan(c: Any, **changes: Any) -> Any:
    from apbra_api.foundry_catalogue_lease import CataloguePlan

    return CataloguePlan(
        **{
            "company_id": c.plan.company_id,
            "identity_id": uuid4(),
            "membership_id": uuid4(),
            "settings_id": c.snapshot.id,
            "settings_digest": c.snapshot.digest,
            "tenant_id": c.plan.tenant_id,
            "client_id": c.plan.client_id,
            "profile": c.profile,
            "authorization_deadline": c.plan.authorization_deadline,
            "page_requests": 2,
            **changes,
        }
    )


def catalogue_frame(plan: Any, **changes: Any) -> bytes:
    from apbra_api.foundry_catalogue_lease import approval_payload

    value = approval_payload(plan, NONCE, "synthetic.account")
    value.update(changes)
    raw = json.dumps(value).encode()
    return len(raw).to_bytes(4, "big") + raw


def test_catalogue_receiver_has_only_caller_bound_directory_credential(monkeypatch, capsys):
    from apbra_api.foundry_admin_reads import ReadRequest

    c = catalogue_setup(monkeypatch)
    plan = catalogue_plan(c)
    monkeypatch.setattr(m, "create_app", lambda **kwargs: kwargs)
    pipe = Pipe(m.HELLO + catalogue_frame(plan) + account_frame(c.plan) + frame(c.plan))
    held = []

    def serve(app, settings, stopped):
        assert app["foundry_metadata_credentials"] is None
        assert app["foundry_credentials"] is None
        issuer = app["foundry_admin_credentials"]
        held.append(issuer)
        request = ReadRequest(
            plan.company_id,
            plan.identity_id,
            plan.membership_id,
            plan.settings_id,
            c.profile.profile_id,
            c.profile.configuration_id,
            c.profile.endpoint,
            c.profile.agent_version,
            "LIST_AGENTS",
            None,
            10,
            None,
        )
        access = issuer.resolve(request)
        assert access is not None and access.credential().token == CANARY
        assert issuer.resolve(replace(request, identity_id=uuid4())) is None
        c.snapshot = replace(c.snapshot, digest="d" * 64)
        assert not issuer.ready(request, access)

    m.run_receiver(
        c.plan,
        pipe,
        settings=c.settings,
        snapshot_loader=lambda: c.snapshot,
        serve=serve,
        nonce_factory=lambda: NONCE,
        catalogue_plan=plan,
        catalogue_guard=lambda: True,
    )
    assert pipe.closed and held and b"CATALOGUE_APPROVAL_ACCEPTED" in pipe.output
    assert CANARY.encode() not in pipe.output and capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "fault", ["nonce", "account", "identity", "replay", "duplicate", "settings", "membership"]
)
def test_catalogue_receiver_invalid_or_revoked_approval_never_creates_app(monkeypatch, fault):
    c = catalogue_setup(monkeypatch)
    plan = catalogue_plan(c)
    approved = catalogue_frame(plan)
    if fault == "nonce":
        approved = catalogue_frame(plan, nonce="c" * 64)
    if fault == "account":
        approved = catalogue_frame(plan, account="foreign.account")
    if fault == "identity":
        approved = catalogue_frame(replace(plan, identity_id=uuid4()))
    if fault == "replay":
        approved += approved
    if fault == "duplicate":
        raw = b'{"v":1,"v":1}'
        approved = len(raw).to_bytes(4, "big") + raw
    if fault == "settings":
        plan = replace(plan, settings_id=uuid4())
    called = []
    monkeypatch.setattr(m, "create_app", lambda **kw: called.append(True))
    pipe = Pipe(m.HELLO + approved + account_frame(c.plan) + frame(c.plan))
    with pytest.raises(HandoffError):
        m.run_receiver(
            c.plan,
            pipe,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            nonce_factory=lambda: NONCE,
            catalogue_plan=plan,
            catalogue_guard=lambda: fault != "membership",
        )
    assert not called and pipe.closed and CANARY.encode() not in pipe.output


@pytest.mark.parametrize(
    "changes",
    [
        {"runtime": True},
        {"invocation_gate": lambda: True},
        {"application_factory": lambda **kw: kw},
    ],
)
def test_catalogue_receiver_cannot_enable_runtime_or_custom_app(monkeypatch, changes):
    c = catalogue_setup(monkeypatch)
    plan = catalogue_plan(c)
    pipe = Pipe(b"")
    with pytest.raises(HandoffError):
        m.run_receiver(
            c.plan,
            pipe,
            settings=c.settings,
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            catalogue_plan=plan,
            catalogue_guard=lambda: True,
            **changes,
        )
    assert pipe.closed and not pipe.output


def test_catalogue_receiver_rejects_settings_that_enable_automatic_generation(monkeypatch):
    c = catalogue_setup(monkeypatch)
    pipe = Pipe(b"")
    with pytest.raises(HandoffError):
        m.run_receiver(
            c.plan,
            pipe,
            settings=c.settings.model_copy(update={"automatic_generation_enabled": True}),
            snapshot_loader=lambda: c.snapshot,
            serve=lambda *args: None,
            catalogue_plan=catalogue_plan(c),
            catalogue_guard=lambda: True,
        )
    assert pipe.closed and not pipe.output


# Literal additive inverse: independent review must verify every admitted new byte.
CATALOGUE_RECEIVER_EDITS = [
    (
        (
            '\nif TYPE_CHECKING:\n    from .config import Settings\n    from'
            ' .tenant_settings import TenantSettingsSnapshot\n\n\n'
        ),
        (
            '\nif TYPE_CHECKING:\n    from .config import Settings\n    from'
            ' .foundry_catalogue_lease import CataloguePlan\n    from .ten'
            'ant_settings import TenantSettingsSnapshot\n\n\n'
        ),
    ),
    (
        (
            '    listener: tuple[str, int] | None = None,\n    published_p'
            'ort: int | None = None,\n    application_factory: Callable[..'
            '., Any] | None = None,\n) -> None:\n    """Trusted host entryp'
            'oint. CLI cannot enable invocation or manufacture attestatio'
            'n."""\n    from .config import get_settings\n'
        ),
        (
            '    listener: tuple[str, int] | None = None,\n    published_p'
            'ort: int | None = None,\n    application_factory: Callable[..'
            '., Any] | None = None,\n    catalogue_plan: CataloguePlan | N'
            'one = None,\n    catalogue_guard: Callable[[], bool] | None ='
            ' None,\n) -> None:\n    """Trusted host entrypoint. CLI cannot'
            ' enable invocation or manufacture attestation."""\n    from .'
            'config import get_settings\n'
        ),
    ),
    (
        (
            '    from .tenant_settings import validate_qualified_profile\n'
            '\n    token = None\n    database = None\n    stopped = threadin'
            'g.Event()\n    watcher = None\n'
        ),
        (
            '    from .tenant_settings import validate_qualified_profile\n'
            '\n    token = None\n    admin_credentials = None\n    database '
            '= None\n    stopped = threading.Event()\n    watcher = None\n'
        ),
    ),
    (
        (
            '        with _private_sdk_logging(), redirect_stdout(_Discar'
            'd()), redirect_stderr(_Discard()):\n            plan.validate'
            '()\n            require(type(runtime) is bool)\n            se'
            'ttings = settings or get_settings()\n            settings.val'
            'idate_security_profile()\n            _, public = _local_addr'
            'ess(settings)\n            if serve is None:\n                '
            'require(\n'
        ),
        (
            '        with _private_sdk_logging(), redirect_stdout(_Discar'
            'd()), redirect_stderr(_Discard()):\n            plan.validate'
            '()\n            require(type(runtime) is bool)\n            re'
            'quire(catalogue_plan is not None or catalogue_guard is None)'
            '\n            if catalogue_plan is not None:\n                '
            'from .foundry_catalogue_lease import CataloguePlan\n\n        '
            '        require(type(catalogue_plan) is CataloguePlan)\n     '
            '           catalogue_plan.validate()\n                require'
            '(runtime is False and invocation_gate is None\n              '
            '          and application_factory is None)\n                r'
            'equire((catalogue_plan.company_id, catalogue_plan.tenant_id,'
            '\n                         catalogue_plan.client_id, catalogu'
            'e_plan.authorization_deadline)\n                        == (p'
            'lan.company_id, plan.tenant_id, plan.client_id,\n            '
            '                plan.authorization_deadline))\n              '
            '  require(catalogue_guard is None or callable(catalogue_guar'
            'd))\n            settings = settings or get_settings()\n      '
            '      settings.validate_security_profile()\n            if ca'
            'talogue_plan is not None:\n                require(settings.a'
            'utomatic_generation_enabled is False)\n            _, public '
            '= _local_address(settings)\n            if serve is None:\n   '
            '             require(\n'
        ),
    ),
    (
        (
            '                except Exception:\n                    return'
            ' False\n\n            require(unchanged())\n            require'
            '(exact(channel, len(HELLO), plan.authorization_deadline) == '
            'HELLO)\n            nonce = (nonce_factory or (lambda: secret'
            's.token_hex(32)))()\n            require(type(nonce) is str a'
            'nd re.fullmatch(r"[a-f0-9]{64}", nonce))\n'
        ),
        (
            '                except Exception:\n                    return'
            ' False\n\n            def catalogue_current() -> bool:\n       '
            '         if catalogue_plan is None or not unchanged():\n     '
            '               return False\n                if (initial.id, '
            'initial.digest, profile) != (\n                    catalogue_'
            'plan.settings_id, catalogue_plan.settings_digest,\n          '
            '          catalogue_plan.profile,\n                ):\n       '
            '             return False\n                try:\n             '
            '       if catalogue_guard is not None:\n                     '
            '   return catalogue_guard() is True\n                    if d'
            'atabase is None:\n                        return False\n      '
            '              from .foundry_catalogue_lease import owner_is_'
            'current\n\n                    return owner_is_current(databas'
            'e, catalogue_plan)\n                except Exception:\n       '
            '             return False\n\n            require(unchanged())\n'
            '            if catalogue_plan is not None:\n                r'
            'equire(catalogue_current())\n            require(exact(channe'
            'l, len(HELLO), plan.authorization_deadline) == HELLO)\n      '
            '      nonce = (nonce_factory or (lambda: secrets.token_hex(3'
            '2)))()\n            require(type(nonce) is str and re.fullmat'
            'ch(r"[a-f0-9]{64}", nonce))\n'
        ),
    ),
    (
        (
            '                json.dumps({"v": 1, "nonce": nonce, "pid": 1'
            '}, separators=(",", ":")).encode()\n                + b"\\n"\n '
            '           )\n            confirmed_account = receive_account'
            '(channel, plan, nonce)\n            require(\n                '
            'unchanged() and (binding is None or binding.home_account_id '
            '== confirmed_account)\n            )\n'
        ),
        (
            '                json.dumps({"v": 1, "nonce": nonce, "pid": 1'
            '}, separators=(",", ":")).encode()\n                + b"\\n"\n '
            '           )\n            catalogue_account = None\n          '
            '  if catalogue_plan is not None:\n                from .found'
            'ry_catalogue_lease import validate_approval\n\n               '
            ' size = int.from_bytes(exact(channel, 4, plan.authorization_'
            'deadline), "big")\n                require(0 < size <= MAX_FR'
            'AME)\n                value = json.loads(exact(channel, size,'
            ' plan.authorization_deadline),\n                             '
            '      object_pairs_hook=pairs)\n                catalogue_acc'
            'ount = validate_approval(value, catalogue_plan, nonce)\n     '
            '           del value\n                require(catalogue_curre'
            'nt())\n                channel.write(b"CATALOGUE_APPROVAL_ACC'
            'EPTED\\n")\n            confirmed_account = receive_account(ch'
            'annel, plan, nonce)\n            require(catalogue_plan is No'
            'ne or confirmed_account == catalogue_account)\n            re'
            'quire(\n                unchanged() and (binding is None or b'
            'inding.home_account_id == confirmed_account)\n            )\n'
        ),
    ),
    (
        (
            '                enabled=lambda: not stopped.is_set(),\n      '
            '          binding_digest=digest,\n            )\n            d'
            'el acquired, account\n            credentials = BrowserMetada'
            'taCredential(initial, token, unchanged)\n            runtime_'
            'credentials = None\n            if binding is not None:\n\n'
        ),
        (
            '                enabled=lambda: not stopped.is_set(),\n      '
            '          binding_digest=digest,\n            )\n            i'
            'f catalogue_plan is not None:\n                from .foundry_'
            'catalogue_lease import CatalogueCredentials\n\n               '
            ' require(account == catalogue_account and catalogue_current('
            '))\n                admin_credentials = CatalogueCredentials('
            '\n                    catalogue_plan, account, token, catalog'
            'ue_current\n                )\n            del acquired, accou'
            'nt, catalogue_account\n            credentials = (None if cat'
            'alogue_plan is not None else\n                           Brow'
            'serMetadataCredential(initial, token, unchanged))\n          '
            '  runtime_credentials = None\n            if binding is not N'
            'one:\n\n'
        ),
    ),
    (
        (
            '                    agent_version=binding.agent_version,\n   '
            '                 qualification=binding.qualification,\n      '
            '          )\n            app = (application_factory or create'
            '_app)(\n                settings=settings,\n                fo'
            'undry_metadata_credentials=credentials,\n                foun'
            'dry_credentials=runtime_credentials,\n            )\n\n        '
            '    def monitor() -> None:\n                try:\n'
        ),
        (
            '                    agent_version=binding.agent_version,\n   '
            '                 qualification=binding.qualification,\n      '
            '          )\n            app_kwargs: dict[str, Any] = {\n     '
            '           "settings": settings,\n                "foundry_me'
            'tadata_credentials": credentials,\n                "foundry_c'
            'redentials": runtime_credentials,\n            }\n            '
            'if catalogue_plan is not None:\n                app_kwargs["f'
            'oundry_admin_credentials"] = admin_credentials\n            a'
            'pp = (application_factory or create_app)(**app_kwargs)\n\n    '
            '        def monitor() -> None:\n                try:\n'
        ),
    ),
    (
        (
            '\n            watcher = threading.Thread(target=monitor, daem'
            'on=True)\n            watcher.start()\n            require(not'
            ' stopped.is_set() and credentials.ready(plan.company_id, pro'
            'file))\n            channel.write(b"HANDOFF_READY_INVOCATION_'
            'GATED\\n")\n            if serve is not None:\n                '
            'serve(app, settings, stopped)\n'
        ),
        (
            '\n            watcher = threading.Thread(target=monitor, daem'
            'on=True)\n            watcher.start()\n            require(not'
            ' stopped.is_set() and (\n                catalogue_current() '
            'if catalogue_plan is not None else\n                credentia'
            'ls is not None and credentials.ready(plan.company_id, profil'
            'e)\n            ))\n            channel.write(b"HANDOFF_READY_'
            'INVOCATION_GATED\\n")\n            if serve is not None:\n     '
            '           serve(app, settings, stopped)\n'
        ),
    ),
    (
        (
            '    finally:\n        stopped.set()\n        with _private_sdk'
            '_logging(), redirect_stdout(_Discard()), redirect_stderr(_Di'
            'scard()):\n            for close in (token.close if token is '
            'not None else None, channel.close):\n                if close'
            ' is not None:\n                    try:\n                     '
            '   close()\n'
        ),
        (
            '    finally:\n        stopped.set()\n        with _private_sdk'
            '_logging(), redirect_stdout(_Discard()), redirect_stderr(_Di'
            'scard()):\n            for close in (admin_credentials.close '
            'if admin_credentials is not None else None,\n                '
            '          token.close if token is not None else None, channe'
            'l.close):\n                if close is not None:\n            '
            '        try:\n                        close()\n'
        ),
    ),
]


def without_catalogue_receiver_changes(source):
    return _without_catalogue_stage(without_preview_receiver_changes(source))


def _without_catalogue_stage(source):
    for before, after in reversed(CATALOGUE_RECEIVER_EDITS):
        if source.count(after) != 1:
            raise ValueError("Catalogue receiver inverse differs")
        source = source.replace(after, before, 1)
    return source


def test_catalogue_receiver_expansion_preserves_exact_previous_historical_guard():
    import hashlib
    from pathlib import Path

    current = Path(m.__file__).read_text()
    assert (
        hashlib.sha256(without_catalogue_receiver_changes(current).encode()).hexdigest()
        == "b2ca368368ff858174bb920ced15fee6d9f0b738e4f48fd11c933e37f2298559"
    )
    earlier = without_preview_receiver_changes(current)
    for _before, after in CATALOGUE_RECEIVER_EDITS:
        assert earlier.count(after) == 1
        with pytest.raises(ValueError):
            _without_catalogue_stage(earlier.replace(after, "", 1))
        with pytest.raises(ValueError):
            _without_catalogue_stage(earlier + after)



def preview_exposure() -> m.PreviewExposure:
    return m.PreviewExposure("http://127.0.0.1:8001", "http://127.0.0.1:8012",
                             "http://127.0.0.1:5197", 8000)


@pytest.mark.parametrize("changes", [
    {"api_origin": "http://0.0.0.0:8012"},
    {"api_origin": "https://127.0.0.1:8012"},
    {"api_origin": "http://localhost:8012"},
    {"api_origin": "http://127.0.0.1:08012"},
    {"api_origin": "http://127.0.0.1:8012/"},
    {"api_origin": "http://127.0.0.1:8012?private=value"},
    {"api_origin": "http://user@127.0.0.1:8012"},
    {"api_origin": "http://127.0.0.1:65536"},
    {"api_origin": "http://127.0.0.1:8001"},
    {"web_origin": "http://127.0.0.1:8012"},
    {"web_origin": "https://external.invalid"},
    {"issuer_origin": "http://external.invalid:8001"},
    {"issuer_origin": "http://127.0.0.1:8001/path"},
    {"container_port": True}, {"container_port": 0}, {"container_port": 65536},
])
def test_preview_exposure_rejects_ambiguous_or_external_binding(changes: Any) -> None:
    with pytest.raises(HandoffError, match=m.ERROR):
        replace(preview_exposure(), **changes).wire()


@pytest.mark.parametrize("kind", ["account", "token"])
@pytest.mark.parametrize("digest", [None, "0" * 64, True])
def test_preview_frames_cannot_omit_or_change_exposure(
    monkeypatch: Any, kind: str, digest: Any
) -> None:
    c = setup(monkeypatch)
    changes = {} if digest is None else {"preview_exposure_digest": digest}
    payload = account_frame(c.plan, **changes) if kind == "account" else frame(c.plan, **changes)
    reader = m.receive_account if kind == "account" else m.receive
    with pytest.raises(HandoffError, match=m.ERROR):
        reader(Pipe(payload), c.plan, NONCE, preview_exposure())


def test_preview_binding_is_nonce_challenged_and_never_accepted_by_legacy_frames(
    monkeypatch: Any,
) -> None:
    c = setup(monkeypatch)
    exposure = preview_exposure()
    challenge = m.handoff_challenge(NONCE, exposure)
    assert challenge == {"v": 1, "nonce": NONCE, "pid": 1, "preview_exposure": exposure.wire()}
    digest = exposure.digest()
    assert m.receive_account(Pipe(account_frame(c.plan, preview_exposure_digest=digest)),
                             c.plan, NONCE, exposure) == "synthetic.account"
    token, account = m.receive(Pipe(frame(c.plan, preview_exposure_digest=digest)),
                               c.plan, NONCE, exposure)
    assert account == "synthetic.account" and token.token == CANARY
    pairs = [(m.receive_account, account_frame(c.plan, preview_exposure_digest=digest)),
             (m.receive, frame(c.plan, preview_exposure_digest=digest))]
    for reader, payload in pairs:
        with pytest.raises(HandoffError, match=m.ERROR):
            reader(Pipe(payload), c.plan, NONCE)
    assert m.handoff_challenge(NONCE) == {"v": 1, "nonce": NONCE, "pid": 1}


@pytest.mark.parametrize("fault", ["issuer", "frontend", "bootstrap", "hosted", "port",
                                   "listener", "bool-listener", "serve"])
def test_preview_runtime_binding_rejected_before_any_handoff(
    monkeypatch: Any, fault: str,
) -> None:
    c = setup(monkeypatch)
    exposure = preview_exposure()
    settings = c.settings.model_copy(update={"api_origin": exposure.issuer_origin,
                                             "public_origin": exposure.web_origin,
                                             "bootstrap_enabled": False})
    updates = {"issuer": {"api_origin": "http://127.0.0.1:8002"},
               "frontend": {"public_origin": "http://127.0.0.1:5195"},
               "bootstrap": {"bootstrap_enabled": True}, "hosted": {"profile": "hosted"}}
    settings = settings.model_copy(update=updates.get(fault, {}))
    p = Pipe(m.HELLO)
    with pytest.raises(HandoffError, match=m.ERROR):
        m.run_receiver(c.plan, p, settings=settings, snapshot_loader=lambda: c.snapshot,
                       listener=(m.CONTAINER_LISTEN, True if fault == "bool-listener" else
                                 8002 if fault == "listener" else 8000),
                       published_port=8001 if fault == "port" else 8012,
                       serve=(lambda *args: None) if fault == "serve" else None,
                       preview_exposure=exposure)
    assert p.closed and not p.output


@pytest.mark.parametrize("disconnect", [False, True])
def test_preview_receiver_preserves_issuer_and_revokes_owned_lease(
    monkeypatch: Any, disconnect: bool,
) -> None:
    c = setup(monkeypatch)
    exposure = preview_exposure()
    settings = c.settings.model_copy(update={"api_origin": exposure.issuer_origin,
                                             "public_origin": exposure.web_origin,
                                             "bootstrap_enabled": False})
    digest = exposure.digest()
    p = Pipe(m.HELLO + account_frame(c.plan, preview_exposure_digest=digest)
             + frame(c.plan, preview_exposure_digest=digest))
    monkeypatch.setattr(m, "create_app", lambda **kwargs: kwargs)
    held = []
    def serve(app: Any, listener: Any, stopped: threading.Event) -> None:
        assert listener == (m.CONTAINER_LISTEN, 8000)
        assert app["settings"].api_origin == "http://127.0.0.1:8001"
        credential = app["foundry_metadata_credentials"]
        held.append(credential)
        assert credential.ready(c.plan.company_id, c.profile)
        if disconnect:
            p.alive = False
            assert stopped.wait(1)
            assert not credential.ready(c.plan.company_id, c.profile)
    monkeypatch.setattr(m, "_serve", serve)
    m.run_receiver(c.plan, p, settings=settings, snapshot_loader=lambda: c.snapshot,
                   listener=(m.CONTAINER_LISTEN, 8000), published_port=8012,
                   preview_exposure=exposure, nonce_factory=lambda: NONCE)
    challenge = json.loads(bytes(p.output).splitlines()[0])
    assert challenge["preview_exposure"] == exposure.wire()
    assert p.closed and held and not held[0].ready(c.plan.company_id, c.profile)
    assert CANARY.encode() not in p.output


PREVIEW_RECEIVER_EDITS = [('MODULE = "apbra_api.foundry_memory_handoff"\n'
  'CONTAINER_LISTEN = "0.0.0.0"  # noqa: S104 -- existing container interface; '
  'publication loopback only\n'
  'HELLO = b"APBRA_MEMORY_HANDOFF_1\\n"\n'
  '\n'
  '\n'
  '@dataclass(frozen=True)\n',
  'MODULE = "apbra_api.foundry_memory_handoff"\n'
  'CONTAINER_LISTEN = "0.0.0.0"  # noqa: S104 -- existing container interface; '
  'publication loopback only\n'
  'HELLO = b"APBRA_MEMORY_HANDOFF_1\\n"\n'
  '\n'
  '\n'
  '@dataclass(frozen=True)\n'
  'class PreviewExposure:\n'
  '    """Explicit local test exposure, separate from the preserved identity issuer.\n'
  '\n'
  '    The trusted controller must verify actual owned Docker publication and the\n'
  '    exact new entrypoint before accepting this nonce-bound declaration. This is\n'
  '    not an HTTP setting or authority to change existing services.\n'
  '    """\n'
  '\n'
  '    issuer_origin: str\n'
  '    api_origin: str\n'
  '    web_origin: str\n'
  '    container_port: int\n'
  '\n'
  '    def wire(self) -> dict[str, Any]:\n'
  '        ports = []\n'
  '        for index, value in enumerate((self.issuer_origin, self.api_origin, '
  'self.web_origin)):\n'
  '            require(type(value) is str)\n'
  '            pattern = r"http://(?:127\\.0\\.0\\.1|localhost):([1-9][0-9]{0,4})" if '
  'index == 0 else (\n'
  '                r"http://127\\.0\\.0\\.1:([1-9][0-9]{0,4})"\n'
  '            )\n'
  '            match = re.fullmatch(pattern, value)\n'
  '            require(match is not None)\n'
  '            assert match is not None\n'
  '            port = int(match[1])\n'
  '            require(1 <= port <= 65535)\n'
  '            ports.append(port)\n'
  '        require(len(set(ports)) == 3)\n'
  '        require(type(self.container_port) is int and 1 <= self.container_port <= '
  '65535)\n'
  '        return {"issuer_origin": self.issuer_origin, "api_origin": self.api_origin,\n'
  '                "web_origin": self.web_origin, "container_port": '
  'self.container_port}\n'
  '\n'
  '    def digest(self) -> str:\n'
  '        return hashlib.sha256(json.dumps(self.wire(), sort_keys=True,\n'
  '                                         separators=(",", '
  '":")).encode()).hexdigest()\n'
  '\n'
  '    def validate_runtime(\n'
  '        self, settings: Settings, listener: tuple[str, int] | None, published_port: '
  'int | None\n'
  '    ) -> None:\n'
  '        self.wire()\n'
  '        require(settings.profile in {"development", "test"})\n'
  '        require(settings.bootstrap_enabled is False)\n'
  '        require(settings.api_origin == self.issuer_origin)\n'
  '        require(settings.public_origin == self.web_origin)\n'
  '        require(type(listener) is tuple and len(listener) == 2)\n'
  '        assert listener is not None\n'
  '        require(type(listener[1]) is int)\n'
  '        require(listener == (CONTAINER_LISTEN, self.container_port))\n'
  '        require(type(published_port) is int)\n'
  '        require(self.api_origin == f"http://127.0.0.1:{published_port}")\n'
  '\n'
  '\n'
  'def handoff_challenge(nonce: str, exposure: PreviewExposure | None = None) -> '
  'dict[str, Any]:\n'
  '    require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce))\n'
  '    value: dict[str, Any] = {"v": 1, "nonce": nonce, "pid": 1}\n'
  '    if exposure is not None:\n'
  '        require(type(exposure) is PreviewExposure)\n'
  '        value["preview_exposure"] = exposure.wire()\n'
  '    return value\n'
  '\n'
  '\n'
  'def _frame_fields(\n'
  '    value: Any, expected: set[str], exposure: PreviewExposure | None\n'
  ') -> None:\n'
  '    require(type(value) is dict)\n'
  '    if exposure is None:\n'
  '        require(set(value) == expected)\n'
  '    else:\n'
  '        require(type(exposure) is PreviewExposure)\n'
  '        require(set(value) == expected | {"preview_exposure_digest"})\n'
  '        require(value["preview_exposure_digest"] == exposure.digest())\n'
  '\n'
  '\n'
  '@dataclass(frozen=True)\n'),
 ('    expires_on: int\n'
  '\n'
  '\n'
  'def receive_account(channel: Channel, plan: HandoffPlan, nonce: str) -> str:\n'
  '    value: Any = None\n'
  '    try:\n'
  '        length = int.from_bytes(exact(channel, 4, plan.authorization_deadline), '
  '"big")\n',
  '    expires_on: int\n'
  '\n'
  '\n'
  'def receive_account(\n'
  '    channel: Channel, plan: HandoffPlan, nonce: str,\n'
  '    preview_exposure: PreviewExposure | None = None,\n'
  ') -> str:\n'
  '    value: Any = None\n'
  '    try:\n'
  '        length = int.from_bytes(exact(channel, 4, plan.authorization_deadline), '
  '"big")\n'),
 ('        value = json.loads(\n'
  '            exact(channel, length, plan.authorization_deadline), '
  'object_pairs_hook=pairs\n'
  '        )\n'
  '        require(\n'
  '            type(value) is dict\n'
  '            and set(value) == {"v", "nonce", "company", "tenant", "client", '
  '"deadline", "account"}\n'
  '        )\n'
  '        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == '
  'nonce)\n'
  '        require(all(type(value[k]) is str for k in ("company", "tenant", "client", '
  '"account")))\n'
  '        require(\n',
  '        value = json.loads(\n'
  '            exact(channel, length, plan.authorization_deadline), '
  'object_pairs_hook=pairs\n'
  '        )\n'
  '        _frame_fields(value, {"v", "nonce", "company", "tenant", "client", '
  '"deadline", "account"},\n'
  '                      preview_exposure)\n'
  '        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == '
  'nonce)\n'
  '        require(all(type(value[k]) is str for k in ("company", "tenant", "client", '
  '"account")))\n'
  '        require(\n'),
 ('            value.clear()\n'
  '\n'
  '\n'
  'def receive(channel: Channel, plan: HandoffPlan, nonce: str) -> '
  'tuple[MemoryAccessToken, str]:\n'
  '    raw = b""\n'
  '    value: dict[str, Any] = {}\n'
  '    try:\n',
  '            value.clear()\n'
  '\n'
  '\n'
  'def receive(\n'
  '    channel: Channel, plan: HandoffPlan, nonce: str,\n'
  '    preview_exposure: PreviewExposure | None = None,\n'
  ') -> tuple[MemoryAccessToken, str]:\n'
  '    raw = b""\n'
  '    value: dict[str, Any] = {}\n'
  '    try:\n'),
 ('        require(0 < length <= MAX_FRAME)\n'
  '        raw = exact(channel, length, plan.authorization_deadline)\n'
  '        value = json.loads(raw, object_pairs_hook=pairs)\n'
  '        require(\n'
  '            type(value) is dict\n'
  '            and set(value)\n'
  '            == {\n'
  '                "v",\n'
  '                "nonce",\n'
  '                "company",\n',
  '        require(0 < length <= MAX_FRAME)\n'
  '        raw = exact(channel, length, plan.authorization_deadline)\n'
  '        value = json.loads(raw, object_pairs_hook=pairs)\n'
  '        _frame_fields(\n'
  '            value, {\n'
  '                "v",\n'
  '                "nonce",\n'
  '                "company",\n'),
 ('                "account",\n'
  '                "token",\n'
  '                "expires",\n'
  '            }\n'
  '        )\n'
  '        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == '
  'nonce)\n'
  '        require(\n',
  '                "account",\n'
  '                "token",\n'
  '                "expires",\n'
  '            }, preview_exposure\n'
  '        )\n'
  '        require(type(value["v"]) is int and value["v"] == 1 and value["nonce"] == '
  'nonce)\n'
  '        require(\n'),
 ('    application_factory: Callable[..., Any] | None = None,\n'
  '    catalogue_plan: CataloguePlan | None = None,\n'
  '    catalogue_guard: Callable[[], bool] | None = None,\n'
  ') -> None:\n'
  '    """Trusted host entrypoint. CLI cannot enable invocation or manufacture '
  'attestation."""\n'
  '    from .config import get_settings\n',
  '    application_factory: Callable[..., Any] | None = None,\n'
  '    catalogue_plan: CataloguePlan | None = None,\n'
  '    catalogue_guard: Callable[[], bool] | None = None,\n'
  '    preview_exposure: PreviewExposure | None = None,\n'
  ') -> None:\n'
  '    """Trusted host entrypoint. CLI cannot enable invocation or manufacture '
  'attestation."""\n'
  '    from .config import get_settings\n'),
 ('            if catalogue_plan is not None:\n'
  '                require(settings.automatic_generation_enabled is False)\n'
  '            _, public = _local_address(settings)\n'
  '            if serve is None:\n'
  '                require(\n'
  '                    listener is not None\n'
  '                    and listener[0] == CONTAINER_LISTEN\n',
  '            if catalogue_plan is not None:\n'
  '                require(settings.automatic_generation_enabled is False)\n'
  '            _, public = _local_address(settings)\n'
  '            if preview_exposure is not None:\n'
  '                require(type(preview_exposure) is PreviewExposure and serve is None)\n'
  '                preview_exposure.validate_runtime(settings, listener, '
  'published_port)\n'
  '            elif serve is None:\n'
  '                require(\n'
  '                    listener is not None\n'
  '                    and listener[0] == CONTAINER_LISTEN\n'),
 ('            nonce = (nonce_factory or (lambda: secrets.token_hex(32)))()\n'
  '            require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce))\n'
  '            channel.write(\n'
  '                json.dumps({"v": 1, "nonce": nonce, "pid": 1}, separators=(",", '
  '":")).encode()\n'
  '                + b"\\n"\n'
  '            )\n'
  '            catalogue_account = None\n',
  '            nonce = (nonce_factory or (lambda: secrets.token_hex(32)))()\n'
  '            require(type(nonce) is str and re.fullmatch(r"[a-f0-9]{64}", nonce))\n'
  '            channel.write(\n'
  '                json.dumps(\n'
  '                    handoff_challenge(nonce, preview_exposure), separators=(",", '
  '":")\n'
  '                ).encode()\n'
  '                + b"\\n"\n'
  '            )\n'
  '            catalogue_account = None\n'),
 ('                del value\n'
  '                require(catalogue_current())\n'
  '                channel.write(b"CATALOGUE_APPROVAL_ACCEPTED\\n")\n'
  '            confirmed_account = receive_account(channel, plan, nonce)\n'
  '            require(catalogue_plan is None or confirmed_account == '
  'catalogue_account)\n'
  '            require(\n'
  '                unchanged() and (binding is None or binding.home_account_id == '
  'confirmed_account)\n'
  '            )\n'
  '            channel.write(b"ACCOUNT_ACCEPTED\\n")\n'
  '            acquired, account = receive(channel, plan, nonce)\n'
  '            require(account == confirmed_account)\n'
  '            del confirmed_account\n'
  '            require(unchanged() and (binding is None or binding.home_account_id == '
  'account))\n',
  '                del value\n'
  '                require(catalogue_current())\n'
  '                channel.write(b"CATALOGUE_APPROVAL_ACCEPTED\\n")\n'
  '            confirmed_account = receive_account(channel, plan, nonce, '
  'preview_exposure)\n'
  '            require(catalogue_plan is None or confirmed_account == '
  'catalogue_account)\n'
  '            require(\n'
  '                unchanged() and (binding is None or binding.home_account_id == '
  'confirmed_account)\n'
  '            )\n'
  '            channel.write(b"ACCOUNT_ACCEPTED\\n")\n'
  '            acquired, account = receive(channel, plan, nonce, preview_exposure)\n'
  '            require(account == confirmed_account)\n'
  '            del confirmed_account\n'
  '            require(unchanged() and (binding is None or binding.home_account_id == '
  'account))\n')]


def without_preview_receiver_changes(source):
    for before, after in reversed(PREVIEW_RECEIVER_EDITS):
        if source.count(after) != 1:
            raise ValueError("Preview receiver inverse differs")
        source = source.replace(after, before, 1)
    return source


def test_preview_receiver_preserves_exact_previously_tested_receiver():
    import hashlib
    from pathlib import Path

    current = Path(m.__file__).read_text()
    assert hashlib.sha256(without_preview_receiver_changes(current).encode()).hexdigest() == (
        "c718043e596e154bb4c1e9ffc7b58be660cb376e564b54770fe4ab4c82b0bf60"
    )
    for _before, after in PREVIEW_RECEIVER_EDITS:
        with pytest.raises(ValueError):
            without_preview_receiver_changes(current.replace(after, "", 1))
        with pytest.raises(ValueError):
            without_preview_receiver_changes(current + after)
