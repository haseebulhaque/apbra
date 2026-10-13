"""Synthetic owner flow only; run with --noconftest, never an owner auth session."""

from __future__ import annotations

import ast
import io
import json
import logging
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from apbra_api import foundry_metadata_projection as projection
from apbra_api import foundry_owner_metadata as module
from apbra_api.model_provider import ProviderConfigurationError

ROOT = Path(__file__).resolve().parents[3]
BASE = "ad236e098199bfd1500f1010535e4f5a2317fc38"
CANARY = "synthetic-private-canary"


@pytest.fixture
def flow(monkeypatch: pytest.MonkeyPatch) -> Any:
    events: list[str] = []
    memories: list[Any] = []
    plan = module._PLAN
    tty = io.StringIO()
    properties = {
        "object": "agent",
        "name": plan.agent_name,
        "agent_endpoint": {
            "version_selector": {
                "version_selection_rules": [
                    {"type": "FixedRatio", "agent_version": "6", "traffic_percentage": 100}
                ]
            }
        },
    }
    version = {
        "object": "agent.version",
        "name": plan.agent_name,
        "version": "6",
        "definition": {
            "kind": "prompt",
            "model": "synthetic-model",
            "instructions": CANARY,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "standards",
                    "server_url": "https://synthetic.search.windows.net/knowledgebases/s08-knowledge-base/mcp",
                    "allowed_tools": ["knowledge_base_retrieve"],
                    "headers": {"Authorization": CANARY},
                }
            ],
        },
    }
    knowledge = {
        "name": plan.knowledge_base,
        "outputMode": "answerSynthesis",
        "models": [
            {
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "modelName": "synthetic-model",
                    "deploymentId": "synthetic-deployment",
                    "apiKey": CANARY,
                },
            }
        ],
        "knowledgeSources": [{"name": CANARY}],
        "retrievalReasoningEffort": {"kind": "low"},
        "retrievalInstructions": CANARY,
    }
    state = SimpleNamespace(
        events=events,
        memories=memories,
        properties=properties,
        version=version,
        knowledge=knowledge,
        denied=None,
        response=None,
        fail=None,
        clock=1000.0,
        expiry=1600.0,
        options={},
    )
    monkeypatch.setattr(module.time, "time", lambda: state.clock)

    @contextmanager
    def terminal(binding: Any) -> Any:
        events.append("TTY")
        yield tty

    monkeypatch.setattr(module, "_qualification_terminal", terminal)

    def confirm(terminal: Any, binding: Any, message: str, reply: str) -> None:
        events.append(reply)
        if state.denied == reply:
            raise ValueError(CANARY)

    monkeypatch.setattr(module, "_confirm_private", confirm)
    original = module._OwnerMemory

    class Memory(original):
        def __init__(self, binding: Any) -> None:
            super().__init__(binding)
            memories.append(self)

    monkeypatch.setattr(module, "_OwnerMemory", Memory)

    class SDK:
        record = SimpleNamespace(
            tenant_id=plan.tenant_id,
            client_id=plan.client_id,
            home_account_id="synthetic-account",
            username="owner@example.invalid",
        )

        def authenticate(self, *, scopes: list[str]) -> Any:
            events.append("AUTH")
            assert scopes == [module._SCOPE]
            if state.fail == "auth":
                logging.error(CANARY)
                raise ValueError(CANARY)
            return self.record

        def get_token(self, *scopes: str) -> Any:
            events.append("TOKEN:" + scopes[0])
            return SimpleNamespace(token=CANARY, expires_on=state.expiry)

        def close(self) -> None:
            events.append("SDK_CLOSE")
            if state.fail == "close":
                raise ValueError(CANARY)

    state.sdk = SDK()

    def factory(**kwargs: Any) -> Any:
        events.append("SDK")
        state.options = kwargs
        return state.sdk

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer " + CANARY
        events.append("GET:" + request.url.path)
        if state.response:
            return state.response(request)
        value = (
            knowledge
            if "knowledgebases" in request.url.path
            else version
            if "/versions/" in request.url.path
            else properties
        )
        return httpx.Response(200, json=value)

    def client(**kwargs: Any) -> httpx.Client:
        assert (
            kwargs["trust_env"] is False
            and kwargs["follow_redirects"] is False
            and kwargs["verify"] is True
        )
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    state.factory, state.client = factory, client

    def inline_get(
        url: str, token: str, timeout: float, cap: int, factory: Any, memory: Any, buffer: bytearray
    ) -> None:
        # These legacy semantic fakes are NOT process/deadline qualification.
        started = module.time.monotonic()
        raw = module._read_http_metadata(url, token, timeout, cap, factory)
        try:
            if module.time.monotonic() - started >= timeout:
                raise ProviderConfigurationError("FOUNDRY_QUALIFICATION_UNAVAILABLE")
            memory.append_private(buffer, bytes(raw))
        finally:
            raw.clear()

    monkeypatch.setattr(module, "_run_owned_get", inline_get)
    return state


def run(state: Any) -> dict[str, Any]:
    return module.run_owner_metadata(credential_factory=state.factory, client_factory=state.client)


def cleanup(state: Any) -> None:
    for memory in state.memories:
        assert (
            memory._closed and not memory._tokens and not memory._documents and not memory._buffers
        )
        assert memory._sdk is None and memory._client is None and memory._record is None


def test_canonical_order_and_safe_unknown_cost(flow: Any) -> None:
    result = run(flow)
    assert flow.events == [
        "TTY",
        "CONFIRM PRIVATE TERMINAL",
        "SDK",
        "AUTH",
        "CONFIRM ACCOUNT",
        "TOKEN:" + module._SCOPE,
        "GET:/api/projects/s08-cloud-ai-agent/agents/s08-document-grounded-agent",
        "GET:/api/projects/s08-cloud-ai-agent/agents/s08-document-grounded-agent/versions/6",
        "CONFIRM SEARCH",
        "TOKEN:" + module._SEARCH_SCOPE,
        "GET:/knowledgebases('s08-knowledge-base')",
        "SDK_CLOSE",
    ]
    assert result["allInCostBound"] == "UNKNOWN" and result["runtimeActivated"] is False
    assert CANARY not in json.dumps(result)
    assert "searchOrigin" not in result
    assert "synthetic.search.windows.net" not in json.dumps(result)
    assert (
        flow.options["cache_persistence_options"] is None
        and flow.options["disable_automatic_authentication"] is True
        and flow.options["retry_total"] == 0
    )
    assert flow.options["timeout"] == 300
    cleanup(flow)


@pytest.mark.parametrize("reply", ["CONFIRM PRIVATE TERMINAL", "CONFIRM ACCOUNT", "CONFIRM SEARCH"])
def test_decline_stops_next_boundary(flow: Any, reply: str) -> None:
    flow.denied = reply
    with pytest.raises(ProviderConfigurationError, match="FOUNDRY_QUALIFICATION_UNAVAILABLE"):
        run(flow)
    if reply == "CONFIRM PRIVATE TERMINAL":
        assert "SDK" not in flow.events
    if reply == "CONFIRM ACCOUNT":
        assert not any(x.startswith("GET") for x in flow.events)
    if reply == "CONFIRM SEARCH":
        assert "TOKEN:" + module._SEARCH_SCOPE not in flow.events
    cleanup(flow)


@pytest.mark.parametrize("field", ["tenant_id", "client_id", "home_account_id", "username"])
def test_wrong_account_before_token(flow: Any, field: str) -> None:
    setattr(flow.sdk.record, field, "" if field in {"home_account_id", "username"} else "wrong")
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert not any(x.startswith("TOKEN") for x in flow.events)
    cleanup(flow)


@pytest.mark.parametrize("mode", ["expired", "account-change", "auth", "close"])
def test_expiry_account_change_and_private_failures(
    flow: Any, mode: str, capsys: Any, caplog: Any
) -> None:
    if mode == "expired":
        flow.expiry = 999
    elif mode == "account-change":
        original = flow.sdk.get_token

        def token(*args: str) -> Any:
            flow.sdk.record.home_account_id = "changed"
            return original(*args)

        flow.sdk.get_token = token
    else:
        flow.fail = mode
    with pytest.raises(ProviderConfigurationError) as error:
        run(flow)
    assert CANARY not in str(error.value) + capsys.readouterr().out + caplog.text
    cleanup(flow)


@pytest.mark.parametrize(
    "kind", ["redirect", "status", "type", "encoding", "duplicate", "nonfinite", "list", "oversize"]
)
def test_untrusted_http_no_followup(flow: Any, kind: str) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.invalid"})
        if kind == "status":
            return httpx.Response(403, text=CANARY)
        if kind == "type":
            return httpx.Response(200, text=CANARY)
        if kind == "encoding":
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "content-encoding": "unknown"},
                content=b"{}",
            )
        value = {
            "duplicate": b'{"x":1,"x":2}',
            "nonfinite": b'{"x":NaN}',
            "list": b"[]",
            "oversize": b" " * 4000001,
        }[kind]
        return httpx.Response(200, headers={"content-type": "application/json"}, content=value)

    flow.response = response
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert sum(x.startswith("GET") for x in flow.events) == 1
    cleanup(flow)


@pytest.mark.parametrize("target", ["agent", "version", "tool", "kb"])
def test_resource_mismatch_stops(flow: Any, target: str) -> None:
    if target == "agent":
        flow.properties["name"] = "other"
    if target == "version":
        flow.version["version"] = "other"
    if target == "tool":
        flow.version["definition"]["tools"][0]["server_url"] = "https://evil.invalid/mcp"
    if target == "kb":
        flow.knowledge["name"] = "other"
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    cleanup(flow)


def test_projector_body_and_old_guard_ast_preserved() -> None:
    before = ast.parse(
        subprocess.check_output(  # noqa: S603 - fixed public git source inspection
            ["/usr/bin/git", "show", BASE + ":apps/api/src/apbra_api/main.py"], cwd=ROOT, text=True
        )
    )
    after = ast.parse((ROOT / "apps/api/src/apbra_api/main.py").read_text())
    pure = ast.parse((ROOT / "apps/api/src/apbra_api/foundry_metadata_projection.py").read_text())
    old = {n.name: n for n in before.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    new = {n.name: n for n in after.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    moved = {n.name: n for n in pure.body if isinstance(n, ast.FunctionDef)}
    for name, node in old.items():
        if name in {
            "_public_identifier",
            "_instruction_bytes",
            "_agent_observation",
            "_knowledge_observation",
        }:
            assert ast.dump(ast.Module(body=node.body, type_ignores=[])) == ast.dump(
                ast.Module(body=moved[name].body, type_ignores=[])
            )
        else:
            assert ast.dump(node) == ast.dump(new[name]), name
    assert ast.dump(before.body[-1]) == ast.dump(after.body[-1])
    assert projection.ProviderConfigurationError is ProviderConfigurationError


def test_fixed_plan_public_literal_provenance() -> None:
    tree = ast.parse((ROOT / "apps/api/src/apbra_api/config.py").read_text())
    binding = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "FoundryQualificationBinding"
    )
    literals = {
        n.target.id: ast.literal_eval(n.annotation.slice)
        for n in binding.body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.annotation, ast.Subscript)
        and isinstance(n.annotation.value, ast.Name)
        and n.annotation.value.id == "Literal"
    }
    for key, value in literals.items():
        assert getattr(module._PLAN, key) == value
    assert not hasattr(module._PLAN, "authorization_deadline")


def test_import_does_not_touch_startup_or_sdk() -> None:
    script = """import sys,importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'apbra_api.main','apbra_api.config','apbra_api.api'}:
   raise AssertionError(fullname)
  if fullname.startswith('azure'):raise AssertionError(fullname)
sys.meta_path.insert(0,Deny())
import apbra_api.foundry_owner_metadata
assert 'apbra_api.main' not in sys.modules
assert 'apbra_api.config' not in sys.modules
assert 'apbra_api.api' not in sys.modules
"""
    result = subprocess.run(  # noqa: S603 - own interpreter and fixed synthetic import script
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_wrong_plan_rejected_before_tty(flow: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    monkeypatch.setattr(module, "_PLAN", replace(module._PLAN, agent_version="99"))
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert not flow.events


@pytest.mark.parametrize("stage", ["factory", "auth", "token", "close"])
def test_sdk_direct_output_and_logs_never_escape(
    flow: Any, stage: str, capsys: Any, caplog: Any
) -> None:
    original = (
        flow.factory
        if stage == "factory"
        else getattr(
            flow.sdk, {"auth": "authenticate", "token": "get_token", "close": "close"}[stage]
        )
    )

    def noisy(*args: Any, **kwargs: Any) -> Any:
        print(CANARY)
        print(CANARY, file=sys.stderr)
        logging.error(CANARY)
        logging.log(100, CANARY)
        return original(*args, **kwargs)

    if stage == "factory":
        flow.factory = noisy
    else:
        setattr(
            flow.sdk, {"auth": "authenticate", "token": "get_token", "close": "close"}[stage], noisy
        )
    run(flow)
    capture = capsys.readouterr()
    assert CANARY not in capture.out + capture.err + caplog.text
    cleanup(flow)


@pytest.mark.parametrize("stage", ["auth", "token"])
def test_keyboard_interrupt_cleans_memory(flow: Any, stage: str) -> None:
    def interrupted(*args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt

    setattr(flow.sdk, "authenticate" if stage == "auth" else "get_token", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(flow)
    cleanup(flow)


@pytest.mark.parametrize("bad", ["uri", "code", "expired", "duplicate", "nonfinite", "valid"])
def test_private_challenge_is_bounded_and_naturally_expires(flow: Any, bad: str) -> None:
    class TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    @contextmanager
    def terminal(binding: Any) -> Any:
        yield TTY()

    original_terminal = module._qualification_terminal
    module._qualification_terminal = terminal
    original = flow.sdk.authenticate

    def authenticate(**kwargs: Any) -> Any:
        callback = flow.options["prompt_callback"]
        from datetime import UTC, datetime

        uri = "https://evil.invalid" if bad == "uri" else "https://microsoft.com/devicelogin"
        code = "bad\ncode" if bad == "code" else "ABC-123"
        expiry = datetime.fromtimestamp(999 if bad == "expired" else 1600, UTC)
        if bad == "nonfinite":

            class InvalidExpiry(datetime):
                def timestamp(self) -> float:
                    return float("nan")

            expiry = InvalidExpiry(2026, 1, 1, tzinfo=UTC)
        callback(uri, code, expiry)
        if bad == "duplicate":
            callback(uri, code, expiry)
        return original(**kwargs)

    flow.sdk.authenticate = authenticate
    try:
        if bad == "valid":
            assert run(flow)["status"] == "METADATA_OBSERVED_ONLY"
        else:
            with pytest.raises(ProviderConfigurationError):
                run(flow)
            assert not any(x.startswith("GET") for x in flow.events)
        cleanup(flow)
    finally:
        module._qualification_terminal = original_terminal


@pytest.mark.parametrize("marker", module._CAPTURED_TERMINAL_MARKERS)
def test_captured_markers_fail_before_process_probe(
    marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(marker, "present")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: pytest.fail("probed"))
    with pytest.raises(ProviderConfigurationError):
        module._owner_terminal_provenance(module._PLAN)


@pytest.mark.parametrize(
    "names",
    [
        ["python", "zsh", "Terminal"],
        ["python", "zsh", "iTerm2"],
        ["python", "codex", "Terminal"],
        ["python", "zsh", "unknown"],
    ],
)
def test_only_bounded_owner_terminal_ancestry(
    names: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for marker in module._CAPTURED_TERMINAL_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.os, "getpid", lambda: 99)
    calls = []

    def ps(args: list[str], **kwargs: Any) -> Any:
        assert args[0] == "/bin/ps" and args[2] == "ppid=,comm="
        assert kwargs["timeout"] == 300
        index = len(calls)
        calls.append(args)
        name = names[min(index, len(names) - 1)]
        parent = 1 if index >= len(names) - 1 else 98 - index
        return SimpleNamespace(stdout=f"{parent} /Applications/{name}\n")

    monkeypatch.setattr(module.subprocess, "run", ps)
    if names[-1] in {"Terminal", "iTerm2"} and "codex" not in names:
        module._owner_terminal_provenance(module._PLAN)
    else:
        with pytest.raises(ProviderConfigurationError):
            module._owner_terminal_provenance(module._PLAN)
    assert len(calls) <= 16


def test_stdio_redirection_fails_before_devtty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_owner_terminal_provenance", lambda plan: None)
    monkeypatch.setattr(module.sys, "stdin", io.StringIO())
    with pytest.raises(ProviderConfigurationError):
        with module._qualification_terminal(module._PLAN):
            pytest.fail("entered")


@pytest.mark.parametrize(
    "which",
    ["unknown-url", "wrong-scope", "duplicate", "search-before-confirm", "expired-after-get"],
)
def test_transport_whitelist_and_expiry_boundaries(flow: Any, which: str) -> None:
    memory = module._OwnerMemory(module._PLAN)
    try:
        memory._private_approved = True
        memory.install_sdk(flow.sdk)
        memory.authenticate()
        memory.confirm_account()
        memory.acquire(module._SCOPE)
        url = (
            module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"
        )
        if which == "unknown-url":
            url = "https://evil.invalid"
        if which == "duplicate":
            memory.get(url, module._SCOPE, flow.client)
        if which == "expired-after-get":

            def late(request: httpx.Request) -> httpx.Response:
                flow.clock = 1601
                return httpx.Response(200, json=flow.properties)

            flow.response = late
        with pytest.raises(ProviderConfigurationError):
            if which == "search-before-confirm":
                memory.acquire(module._SEARCH_SCOPE)
            else:
                memory.get(
                    url,
                    module._SEARCH_SCOPE if which == "wrong-scope" else module._SCOPE,
                    flow.client,
                )
    finally:
        memory.close()


def test_natural_idle_token_expiry_cleanup(flow: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    timers = []

    class Timer:
        def __init__(self, seconds: float, callback: Any) -> None:
            self.seconds, self.callback = seconds, callback
            self.daemon = False
            timers.append(self)

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

    monkeypatch.setattr(module, "Timer", Timer)
    memory = module._OwnerMemory(module._PLAN)
    memory._private_approved = True
    memory.install_sdk(flow.sdk)
    memory.authenticate()
    memory.confirm_account()
    memory.acquire(module._SCOPE)
    assert timers[0].seconds == 600
    timers[0].callback()
    assert memory._closed and memory._tokens == {} and memory._record is None


def test_logging_helper_exact_original_ast() -> None:
    before = ast.parse(
        subprocess.check_output(  # noqa: S603 - fixed public git source inspection
            ["/usr/bin/git", "show", BASE + ":apps/api/src/apbra_api/main.py"], cwd=ROOT, text=True
        )
    )
    after = ast.parse((ROOT / "apps/api/src/apbra_api/foundry_owner_metadata.py").read_text())
    for name in [
        "_private_sdk_logging",
        "_device_credential",
        "_AuthenticationRecord",
        "_DeviceCredential",
    ]:
        left = next(
            n
            for n in before.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name
        )
        right = next(
            n
            for n in after.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name
        )
        assert ast.dump(left) == ast.dump(right)


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "agent-name",
        "object",
        "rules",
        "traffic",
        "prompt",
        "model",
        "tools",
        "url",
        "allowlist",
        "kb",
        "output",
        "effort",
        "models",
        "source-cap",
        "numeric-cap",
    ],
)
def test_original_projector_success_error_and_redaction_parity(flow: Any, mutation: str) -> None:
    import copy
    import math
    import re
    from urllib.parse import urlparse

    original = ast.parse(
        subprocess.check_output(  # noqa: S603 - fixed public original source
            ["/usr/bin/git", "show", BASE + ":apps/api/src/apbra_api/main.py"], cwd=ROOT, text=True
        )
    )
    names = {
        "_public_identifier",
        "_instruction_bytes",
        "_agent_observation",
        "_knowledge_observation",
    }
    definitions = [
        node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    code = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            *definitions,
        ],
        type_ignores=[],
    )
    ns = {
        "json": json,
        "re": re,
        "math": math,
        "urlparse": urlparse,
        "_qualification_error": module._qualification_error,
    }
    exec(compile(ast.fix_missing_locations(code), "frozen-original-projectors", "exec"), ns)  # noqa: S102 - exact frozen public pure AST
    props, version, kb = (
        copy.deepcopy(flow.properties),
        copy.deepcopy(flow.version),
        copy.deepcopy(flow.knowledge),
    )
    definition = version["definition"]
    tool = definition["tools"][0]
    if mutation == "agent-name":
        props["name"] = "wrong"
    if mutation == "object":
        version["object"] = "wrong"
    if mutation == "rules":
        props["agent_endpoint"]["version_selector"]["version_selection_rules"] = []
    if mutation == "traffic":
        props["agent_endpoint"]["version_selector"]["version_selection_rules"][0][
            "traffic_percentage"
        ] = 99
    if mutation == "prompt":
        definition["kind"] = "unknown"
    if mutation == "model":
        definition["model"] = CANARY + "\n"
    if mutation == "tools":
        definition["tools"] = []
    if mutation == "url":
        tool["server_url"] = "https://evil.invalid"
    if mutation == "allowlist":
        tool["allowed_tools"] = ["mutate"]
    if mutation == "kb":
        kb["name"] = "wrong"
    if mutation == "output":
        kb["outputMode"] = "unknown"
    if mutation == "effort":
        kb["retrievalReasoningEffort"] = {"kind": "unknown"}
    if mutation == "models":
        kb["models"] = [{"kind": "wrong"}]
    if mutation == "source-cap":
        kb["knowledgeSources"][0]["maxSubQueries"] = -1
    if mutation == "numeric-cap":
        kb["retrieveDefaults"] = {"maxRuntimeInSeconds": float("inf")}

    def outcome(functions: Any) -> Any:
        try:
            return functions["_agent_observation"](props, version, module._PLAN), functions[
                "_knowledge_observation"
            ](kb, module._PLAN)
        except Exception as error:
            return type(error), str(error)

    assert outcome(ns) == outcome(vars(projection))


@pytest.mark.parametrize("value", [0, -1, True, float("inf"), float("nan"), "1600"])
def test_invalid_token_expiry_cleans(flow: Any, value: Any) -> None:
    flow.expiry = value
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert not any(event.startswith("GET") for event in flow.events)
    cleanup(flow)


def test_private_consent_revocation_stops_next_sdk_boundary(flow: Any) -> None:
    original = flow.sdk.authenticate

    def revoked(**kwargs: Any) -> Any:
        record = original(**kwargs)
        flow.memories[0]._private_approved = False
        return record

    flow.sdk.authenticate = revoked
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert not any(event.startswith("TOKEN") for event in flow.events)
    cleanup(flow)


@pytest.mark.parametrize("reply", ["CONFIRM ACCOUNT\n", "NO\n", "", "CONFIRM ACCOUNT EXTRA\n"])
def test_confirmation_reads_only_bounded_explicit_reply(
    reply: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 99

    data = iter(reply.encode())
    monkeypatch.setattr(module.select, "select", lambda *args: ([99], [], []))
    # Avoid any real descriptor read; consume exactly one synthetic byte per call.
    data = iter(reply.encode())

    def read(fd: int, n: int) -> bytes:
        assert fd == 99 and n == 1
        item = next(data, None)
        return b"" if item is None else bytes([item])

    monkeypatch.setattr(module.os, "read", read)
    if reply == "CONFIRM ACCOUNT\n":
        module._confirm_private(TTY(), module._PLAN, "safe", "CONFIRM ACCOUNT")
    else:
        with pytest.raises(ProviderConfigurationError):
            module._confirm_private(TTY(), module._PLAN, "safe", "CONFIRM ACCOUNT")


def test_metadata_operation_elapsed_bound_rejects_late_stream(
    flow: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = [0.0, 301.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: ticks.pop(0) if ticks else 301.0)
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    cleanup(flow)


@pytest.mark.parametrize("argument", ["--target", "--foundry-device-code", "--report", "secret"])
def test_cli_rejects_all_operational_override_arguments(
    argument: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.sys, "argv", ["owner-metadata", argument])
    monkeypatch.setattr(module, "run_owner_metadata", lambda: pytest.fail("executed"))
    with pytest.raises(SystemExit, match="Foundry owner metadata is unavailable"):
        module.main()


def test_cli_has_only_safe_status_on_private_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(module.sys, "argv", ["owner-metadata"])

    def failed() -> Any:
        raise ValueError(CANARY)

    monkeypatch.setattr(module, "run_owner_metadata", failed)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert str(error.value) == "Foundry owner metadata is unavailable."
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err


def test_account_must_exist_before_confirmation_and_tokens(flow: Any) -> None:
    memory = module._OwnerMemory(module._PLAN)
    memory._private_approved = True
    memory.install_sdk(flow.sdk)
    try:
        with pytest.raises(ProviderConfigurationError):
            memory.confirm_account()
        with pytest.raises(ProviderConfigurationError):
            memory.acquire(module._SCOPE)
        assert not any(event.startswith("TOKEN") for event in flow.events)
    finally:
        memory.close()


def test_sdk_factory_failure_has_no_private_output(flow: Any, capsys: Any) -> None:
    def factory(**kwargs: Any) -> Any:
        print(CANARY)
        raise ValueError(CANARY)

    flow.factory = factory
    with pytest.raises(ProviderConfigurationError) as error:
        run(flow)
    assert CANARY not in str(error.value) + capsys.readouterr().out
    cleanup(flow)


@pytest.mark.parametrize("token", ["", b"bytes", None, 1])
def test_invalid_token_type_or_empty_rejected_before_metadata(flow: Any, token: Any) -> None:
    def bad(*scopes: str) -> Any:
        return SimpleNamespace(token=token, expires_on=1600)

    flow.sdk.get_token = bad
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    assert not any(event.startswith("GET") for event in flow.events)
    cleanup(flow)


def test_sdk_close_interrupt_is_sanitized_and_state_released(flow: Any) -> None:
    def interrupted() -> None:
        raise KeyboardInterrupt

    flow.sdk.close = interrupted
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    cleanup(flow)


@pytest.mark.parametrize("error_type", [SystemExit, KeyboardInterrupt])
def test_cli_sanitizes_sdk_process_interrupts(
    error_type: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(module.sys, "argv", ["owner-metadata"])

    def failed() -> Any:
        raise error_type(CANARY)

    monkeypatch.setattr(module, "run_owner_metadata", failed)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert str(error.value) == "Foundry owner metadata is unavailable."
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err


def test_sdk_system_exit_is_fixed_error_and_cleans(flow: Any) -> None:
    def stopped(**kwargs: Any) -> Any:
        raise SystemExit(CANARY)

    flow.sdk.authenticate = stopped
    with pytest.raises(ProviderConfigurationError) as error:
        run(flow)
    assert CANARY not in str(error.value)
    cleanup(flow)


class SpawnFakeFactory:
    """Only imported by synthetic child commands; never performs a socket request."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def __call__(self, **kwargs: Any) -> httpx.Client:
        import time

        assert sys.flags.isolated and sys.dont_write_bytecode
        assert "apbra_api.main" not in sys.modules and "azure.identity" not in sys.modules
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        mode = self.mode

        class Trickle(httpx.SyncByteStream):
            def __iter__(self) -> Any:
                for chunk in [b"{", b'"ok":', b"true", b"}"]:
                    time.sleep(0.22)
                    print(CANARY)
                    print(CANARY, file=sys.stderr)
                    logging.error(CANARY)
                    yield chunk

        def response(request: httpx.Request) -> httpx.Response:
            print(CANARY)
            print(CANARY, file=sys.stderr)
            logging.error(CANARY)
            assert (
                request.method == "GET" and request.headers["Authorization"] == "Bearer " + CANARY
            )
            if mode == "block":
                time.sleep(10)
            if mode == "ignore-term":
                import signal

                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep(10)
            if mode == "trickle":
                return httpx.Response(
                    200, headers={"content-type": "application/json"}, stream=Trickle()
                )
            if mode == "failure":
                return httpx.Response(403, text=CANARY)
            if mode == "duplicate":
                return httpx.Response(
                    200, headers={"content-type": "application/json"}, content=b'{"x":1,"x":2}'
                )
            return httpx.Response(200, json={"synthetic": True})

        return httpx.Client(transport=httpx.MockTransport(response), **kwargs)


def spawn_test_setup(monkeypatch: pytest.MonkeyPatch, mode: str) -> tuple[Any, list[Any]]:
    import time

    def command() -> list[str]:
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);"
            "from test_foundry_owner_metadata import SpawnFakeFactory;"
            "from apbra_api.foundry_owner_metadata import _metadata_worker;"
            "_metadata_worker(SpawnFakeFactory(sys.argv[3]))"
        )
        return [
            sys.executable,
            "-I",
            "-B",
            "-c",
            code,
            str(ROOT / "apps/api/src"),
            str(Path(__file__).parent),
            mode,
        ]

    monkeypatch.setattr(module, "_worker_command", command)
    operations = []
    original = module._GetOperation

    class Operation(original):
        def __init__(self, timeout: float) -> None:
            super().__init__(timeout)
            operations.append(self)

    monkeypatch.setattr(module, "_GetOperation", Operation)
    memory = module._OwnerMemory(module._PLAN)
    memory._record = SimpleNamespace(
        tenant_id=module._PLAN.tenant_id,
        client_id=module._PLAN.client_id,
        home_account_id="synthetic",
    )
    memory._account = (module._PLAN.tenant_id, module._PLAN.client_id, "synthetic")
    memory._confirmed = True
    memory._private_approved = True
    memory._tokens[module._SCOPE] = (CANARY, time.time() + 60)
    return memory, operations


@pytest.mark.parametrize("mode", ["block", "ignore-term", "trickle"])
def test_real_spawn_absolute_wall_deadline_kills_and_reaps(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import time

    memory, operations = spawn_test_setup(monkeypatch, mode)
    buffer = bytearray()
    memory.register_buffer(buffer)
    url = module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"
    start = time.monotonic()
    try:
        with pytest.raises(ProviderConfigurationError):
            module._run_owned_get(url, CANARY, 0.65, 4000000, None, memory, buffer)
        assert time.monotonic() - start < 1.5
        assert operations[0].death_verified and operations[0].process.poll() is not None
        assert operations[0].process.returncode < 0
    finally:
        memory.close()
    assert buffer == b"" and memory._cleanup_done.is_set()
    assert CANARY not in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["success", "failure"])
def test_real_spawn_success_or_safe_failure_no_raw_process_output(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    memory, operations = spawn_test_setup(monkeypatch, mode)
    buffer = bytearray()
    memory.register_buffer(buffer)
    url = module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"
    try:
        if mode == "success":
            module._run_owned_get(url, CANARY, 3.0, 4000000, None, memory, buffer)
            assert json.loads(buffer) == {"synthetic": True}
        else:
            with pytest.raises(ProviderConfigurationError):
                module._run_owned_get(url, CANARY, 3.0, 4000000, None, memory, buffer)
        assert operations[0].death_verified and operations[0].process.poll() is not None
    finally:
        memory.close()
    capture = capsys.readouterr()
    assert CANARY not in capture.out + capture.err


def test_buffer_append_after_revocation_is_rejected_and_no_orphan(flow: Any) -> None:
    memory = module._OwnerMemory(module._PLAN)
    memory._private_approved = True
    memory.install_sdk(flow.sdk)
    memory.authenticate()
    memory.confirm_account()
    buffer = bytearray()
    memory.register_buffer(buffer)
    memory.append_private(buffer, b"private-before-close")
    memory.close()
    with pytest.raises(ProviderConfigurationError):
        memory.append_private(buffer, CANARY.encode())
    assert buffer == b"" and memory._buffers == [] and memory._cleanup_done.is_set()


def test_overlapping_sdk_operation_close_is_serialized_without_stdout_leak(
    flow: Any, capsys: Any
) -> None:
    from threading import Event, Thread

    entered = Event()
    release = Event()
    closing = Event()
    release_close = Event()
    done = Event()
    memory = module._OwnerMemory(module._PLAN)
    memory._private_approved = True
    memory.install_sdk(flow.sdk)
    memory.authenticate()
    memory.confirm_account()

    def token(*scopes: str) -> Any:
        entered.set()
        assert release.wait(2)
        return SimpleNamespace(token=CANARY, expires_on=1600)

    def close() -> None:
        closing.set()
        assert release_close.wait(2)
        print(CANARY)
        print(CANARY, file=sys.stderr)
        logging.log(100, CANARY)

    flow.sdk.get_token = token
    flow.sdk.close = close
    failures = []

    def acquire() -> None:
        try:
            memory.acquire(module._SCOPE)
        except ProviderConfigurationError:
            failures.append("revoked")

    actor = Thread(target=acquire)
    actor.start()
    assert entered.wait(2)
    closer = Thread(target=lambda: (memory.close(), done.set()))
    closer.start()
    assert not done.wait(0.02)
    assert memory._closed and memory._cleanup_pending and memory._closing_resources
    release.set()
    assert closing.wait(2)
    assert not done.is_set()
    release_close.set()
    actor.join(2)
    closer.join(2)
    assert not actor.is_alive() and not closer.is_alive() and done.is_set()
    assert failures == ["revoked"] and memory._cleanup_done.is_set()
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err


def test_real_spawn_cancel_kills_worker_and_prevents_next_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time
    from threading import Thread

    memory, operations = spawn_test_setup(monkeypatch, "block")
    failures = []
    url = module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"

    def get() -> None:
        try:
            memory.get(url, module._SCOPE, None)
        except Exception:
            failures.append("cancelled")

    actor = Thread(target=get)
    actor.start()
    until = time.monotonic() + 2
    while (not operations or operations[0].process is None) and time.monotonic() < until:
        time.sleep(0.005)
    assert operations and operations[0].process is not None
    memory.close()
    actor.join(1)
    assert not actor.is_alive() and failures == ["cancelled"]
    assert operations[0].death_verified and operations[0].process.poll() is not None
    with pytest.raises(ProviderConfigurationError):
        memory.get(url + "/versions/6", module._SCOPE, None)
    assert len(operations) == 1 and memory._cleanup_done.is_set()


def test_real_spawn_natural_token_expiry_clips_wall_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    memory, operations = spawn_test_setup(monkeypatch, "block")
    memory._tokens[module._SCOPE] = (CANARY, time.time() + 0.35)
    url = module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"
    started = time.monotonic()
    try:
        with pytest.raises(ProviderConfigurationError):
            memory.get(url, module._SCOPE, None)
        assert time.monotonic() - started < 1.2
        assert operations[0].death_verified and operations[0].process.poll() is not None
    finally:
        memory.close()


def test_owned_worker_command_has_no_token_url_or_ambient_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = module._worker_command()
    assert original[1:4] == ["-I", "-B", "-c"]
    assert CANARY not in repr(original) and "https://" not in repr(original)
    captured = {}

    class Process:
        stdin = None
        stdout = None

    def popen(args: list[str], **kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["args"] = args
        raise OSError("synthetic")

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    operation = module._GetOperation(1)
    with pytest.raises(ProviderConfigurationError):
        operation.start()
    operation.cancel()
    assert captured["env"] == {} and captured["cwd"] == "/" and captured["close_fds"] is True
    assert captured["stderr"] == module.subprocess.DEVNULL


def test_sdk_reentrant_callback_observes_closed_without_memory_lock_inversion(flow: Any) -> None:
    from threading import Event, Thread

    entered = Event()
    release = Event()
    memory = module._OwnerMemory(module._PLAN)
    memory._private_approved = True
    memory.install_sdk(flow.sdk)
    memory.authenticate()
    memory.confirm_account()

    def token(*scopes: str) -> Any:
        entered.set()
        assert release.wait(2)
        memory.guard()
        return SimpleNamespace(token=CANARY, expires_on=1600)

    flow.sdk.get_token = token
    errors = []

    def acquire() -> None:
        try:
            memory.acquire(module._SCOPE)
        except ProviderConfigurationError:
            errors.append("revoked")

    caller = Thread(target=acquire)
    caller.start()
    assert entered.wait(2)
    closer = Thread(target=memory.close)
    closer.start()
    assert not memory._cleanup_done.wait(0.02)
    release.set()
    caller.join(2)
    closer.join(2)
    assert not caller.is_alive() and not closer.is_alive() and errors == ["revoked"]
    assert memory._cleanup_done.is_set() and memory._closing_resources == []


def test_cleanup_failure_keeps_owned_resource_and_never_claims_verified(flow: Any) -> None:
    flow.fail = "close"
    with pytest.raises(ProviderConfigurationError):
        run(flow)
    memory = flow.memories[0]
    assert memory._cleanup_done.is_set() and not memory._cleanup_verified
    assert memory._cleanup_failed and flow.sdk in memory._closing_resources


def test_real_get_failure_closes_before_any_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    memory, operations = spawn_test_setup(monkeypatch, "failure")
    url = module._PLAN.project_endpoint + "/agents/" + module._PLAN.agent_name + "?api-version=v1"
    with pytest.raises(ProviderConfigurationError):
        memory.get(url, module._SCOPE, None)
    assert memory._closed and memory._cleanup_verified and operations[0].death_verified
    with pytest.raises(ProviderConfigurationError):
        memory.get(url + "/versions/6", module._SCOPE, None)
    assert len(operations) == 1


def test_late_public_spawn_remains_owned_and_never_receives_private_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time
    from threading import Event

    entered = Event()
    release = Event()
    original = module.subprocess.Popen
    processes = []

    def delayed(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(3)
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", delayed)
    operation = module._GetOperation(0.1)
    started = time.monotonic()
    try:
        with pytest.raises(ProviderConfigurationError):
            operation.start()
        assert entered.is_set() and time.monotonic() - started < 0.5
        with pytest.raises(ProviderConfigurationError):
            operation.cancel()
        assert not operation.death_verified and operation.process is None
        release.set()
        assert operation._startup_done.wait(2)
        assert operation.death_verified and len(processes) == 1
        assert processes[0].poll() is not None
        assert processes[0].stdin.closed and processes[0].stdout.closed
    finally:
        release.set()
        operation._startup_done.wait(2)
        operation.cancel()


def test_owned_process_failed_reap_is_fixed_and_never_claims_death() -> None:
    class Process:
        stdin = None
        stdout = None
        killed = False

        def poll(self) -> Any:
            return None

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float) -> None:
            assert timeout == 1.0
            raise module.subprocess.TimeoutExpired("public-synthetic", timeout)

    operation = module._GetOperation(0.1)
    process = Process()
    operation.process = process
    with pytest.raises(ProviderConfigurationError):
        operation.cancel()
    assert process.killed and not operation.death_verified


def test_ipc_write_revocation_never_exports_registered_bytearray(
    flow: Any, monkeypatch: Any
) -> None:
    import os

    memory = module._OwnerMemory(module._PLAN)
    memory._record = flow.sdk.record
    memory._account = (
        module._PLAN.tenant_id, module._PLAN.client_id, flow.sdk.record.home_account_id
    )
    memory._confirmed = True
    private = bytearray(b"synthetic-private-fixture")
    memory.register_buffer(private)
    read_fd, write_fd = os.pipe()
    operation = module._GetOperation(2)

    def concurrent_close(fd: int, copy: bytes) -> int:
        assert type(copy) is bytes
        memory.close()
        assert private == b"" and memory._cleanup_done.is_set()
        return len(copy)

    monkeypatch.setattr(module.os, "write", concurrent_close)
    try:
        with pytest.raises(ProviderConfigurationError):
            operation.transfer(write_fd, private, len(private), memory, bytearray())
        assert memory._closed and not memory._cleanup_pending and memory._cleanup_verified
        memory.close()
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_close_clear_failure_still_closes_resources_and_completes(flow: Any) -> None:
    memory = module._OwnerMemory(module._PLAN)
    memory._sdk = flow.sdk
    private = bytearray(b"synthetic-private-fixture")
    memory._buffers.append(private)
    exported = memoryview(private)
    try:
        memory.close()
        assert memory._closed and memory._cleanup_done.is_set() and not memory._cleanup_pending
        assert not memory._cleanup_verified and memory._cleanup_failed
        assert memory._sdk is None and "SDK_CLOSE" in flow.events
        assert len(memory._failed_buffers) == 1 and memory._failed_buffers[0] is private
        memory.close()
    finally:
        exported.release()
        private.clear()


@pytest.fixture
def owned_nonseekable_tty(monkeypatch: pytest.MonkeyPatch) -> Any:
    import builtins
    import os
    import pty
    from contextlib import ExitStack

    master, slave = pty.openpty()
    original_open = builtins.open
    opened = []

    @contextmanager
    def activate() -> Any:
        # Patch inside the test call phase, after pytest's capture setup. All
        # actual stream and open mode behavior still uses this owned PTY.
        with ExitStack() as stack, monkeypatch.context() as patch:
            for name, mode in (("stdin", "rb"), ("stdout", "wb"), ("stderr", "wb")):
                stream = stack.enter_context(original_open(os.dup(slave), mode, buffering=0))
                patch.setattr(module.sys, name, stream)
            patch.setattr(module.os, "environ", {})
            patch.setattr(module.sys, "platform", "darwin")

            def ps(args: list[str], **kwargs: Any) -> Any:
                assert args == ["/bin/ps", "-o", "ppid=,comm=", "-p", str(os.getpid())]
                return SimpleNamespace(stdout="1 /Applications/Utilities/Terminal.app/Terminal")

            patch.setattr(module.subprocess, "run", ps)

            def own_open(file: Any, *args: Any, **kwargs: Any) -> Any:
                assert file == "/dev/tty"
                opened.append((args, kwargs))
                return original_open(os.dup(slave), *args, **kwargs)

            patch.setattr(builtins, "open", own_open)
            yield

    try:
        yield SimpleNamespace(master=master, slave=slave, opened=opened, activate=activate)
    finally:
        os.close(master)
        os.close(slave)


def test_private_terminal_real_nonseekable_pty_opens_writes_and_exact_confirmation(
    owned_nonseekable_tty: Any,
) -> None:
    import os

    fixture = owned_nonseekable_tty
    with fixture.activate():
        with module._qualification_terminal(module._PLAN) as terminal:
            assert terminal.isatty() and not terminal.seekable()
            os.write(fixture.master, b"CONFIRM SYNTHETIC\n")
            module._confirm_private(
                terminal, module._PLAN, "Synthetic private prompt", "CONFIRM SYNTHETIC"
            )
            assert module.select.select([fixture.master], [], [], 1)[0]
            output = os.read(fixture.master, 4096)
            assert b"Synthetic private prompt" in output and b"Type CONFIRM SYNTHETIC" in output
    assert terminal.closed and os.isatty(fixture.slave)
    assert fixture.opened == [(("r+b",), {"buffering": 0})]
    with pytest.raises(ValueError):
        terminal.write("closed")


@pytest.mark.parametrize("reply", [b"NO\n", b"CONFIRM SYNTHETIC EXTRA\n", b"\x04"])
def test_private_terminal_real_pty_cancel_extra_and_eof_reject_and_close(
    owned_nonseekable_tty: Any, reply: bytes
) -> None:
    import os

    with owned_nonseekable_tty.activate(), pytest.raises(ProviderConfigurationError):
        with module._qualification_terminal(module._PLAN) as terminal:
            os.write(owned_nonseekable_tty.master, reply)
            module._confirm_private(terminal, module._PLAN, "Synthetic prompt", "CONFIRM SYNTHETIC")
    assert terminal.closed


def test_private_terminal_captured_context_rejects_before_opening_owned_pty(
    owned_nonseekable_tty: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_nonseekable_tty.activate():
        with monkeypatch.context() as capture:
            capture.setattr(module.os, "environ", {"CODEX_SESSION_ID": "synthetic-capture"})
            with pytest.raises(ProviderConfigurationError):
                with module._qualification_terminal(module._PLAN):
                    pytest.fail("captured terminal accepted")
    assert owned_nonseekable_tty.opened == []


def test_private_terminal_unsupported_platform_rejects_before_opening_owned_pty(
    owned_nonseekable_tty: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_nonseekable_tty.activate(), monkeypatch.context() as platform:
        platform.setattr(module.sys, "platform", "linux")
        with pytest.raises(ProviderConfigurationError):
            with module._qualification_terminal(module._PLAN):
                pytest.fail("unsupported platform accepted")
    assert owned_nonseekable_tty.opened == []


def diagnostic_cli(flow: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> dict[str, str]:
    original = module.run_owner_metadata
    monkeypatch.setattr(module.sys, "argv", ["owner-metadata"])
    monkeypatch.setattr(
        module,
        "run_owner_metadata",
        lambda: original(credential_factory=flow.factory, client_factory=flow.client),
    )
    with pytest.raises(SystemExit, match="Foundry owner metadata is unavailable"):
        module.main()
    output = capsys.readouterr()
    assert output.out == "" and CANARY not in output.err
    result = json.loads(output.err)
    assert set(result) == {"status", "stage", "category"}
    assert result["status"] == "METADATA_UNAVAILABLE"
    assert type(result["stage"]) is str and result["stage"] in module._FAILURE_STAGES
    assert type(result["category"]) is str and result["category"] in module._FAILURE_CATEGORIES
    return result


@pytest.mark.parametrize(
    "operation,stage",
    [
        ("private", "PRIVATE_CONFIRMATION"),
        ("construct", "SDK_CONSTRUCTION"),
        ("import", "SDK_CONSTRUCTION"),
        ("install", "SDK_INSTALLATION"),
        ("auth", "AUTHENTICATION_BEFORE_CALLBACK"),
        ("account", "ACCOUNT_VALIDATION"),
        ("account-confirm", "ACCOUNT_CONFIRMATION"),
        ("ai-token", "AI_TOKEN"),
        ("properties", "AGENT_PROPERTIES_GET"),
        ("version", "AGENT_VERSION_GET"),
        ("agent-project", "AGENT_PROJECTION"),
        ("search-confirm", "SEARCH_CONFIRMATION"),
        ("search-bind", "SEARCH_BINDING"),
        ("search-token", "SEARCH_TOKEN"),
        ("knowledge", "KNOWLEDGE_GET"),
        ("knowledge-project", "KNOWLEDGE_PROJECTION"),
    ],
)
def test_diagnostic_actual_boundaries_are_fixed_and_private(
    flow: Any, operation: str, stage: str, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    def private_failure(*args: Any, **kwargs: Any) -> Any:
        print(CANARY)
        logging.error(CANARY)
        raise ValueError(CANARY)

    # SDK output is discarded by the existing quiet boundary. Non-SDK helpers
    # throw a private exception only; they never normally emit raw public output.
    def failure(*args: Any, **kwargs: Any) -> Any:
        raise ValueError(CANARY)

    if operation == "private":
        flow.denied = "CONFIRM PRIVATE TERMINAL"
    elif operation == "construct":
        flow.factory = private_failure
    elif operation == "import":

        def missing(**kwargs: Any) -> Any:
            raise ImportError(CANARY)

        flow.factory = missing
    elif operation == "install":
        monkeypatch.setattr(module._OwnerMemory, "install_sdk", failure)
    elif operation == "auth":
        flow.sdk.authenticate = private_failure
    elif operation == "account":
        flow.sdk.record.tenant_id = CANARY
    elif operation == "account-confirm":
        flow.denied = "CONFIRM ACCOUNT"
    elif operation in {"ai-token", "search-token"}:
        original = flow.sdk.get_token
        scope = module._SCOPE if operation == "ai-token" else module._SEARCH_SCOPE

        def token(*scopes: str) -> Any:
            if scopes == (scope,):
                return private_failure()
            return original(*scopes)

        flow.sdk.get_token = token
    elif operation in {"properties", "version", "knowledge"}:
        original_get = module._OwnerMemory.get

        def get(self: Any, url: str, scope: str, factory: Any) -> Any:
            matched = (
                "knowledgebases" in url
                if operation == "knowledge"
                else "/versions/" in url
                if operation == "version"
                else "/versions/" not in url and "knowledgebases" not in url
            )
            if matched:
                return failure()
            return original_get(self, url, scope, factory)

        monkeypatch.setattr(module._OwnerMemory, "get", get)
    elif operation == "agent-project":
        monkeypatch.setattr(module, "_agent_observation", failure)
    elif operation == "search-confirm":
        flow.denied = "CONFIRM SEARCH"
    elif operation == "search-bind":
        monkeypatch.setattr(module._OwnerMemory, "confirm_search", failure)
    elif operation == "knowledge-project":
        monkeypatch.setattr(module, "_knowledge_observation", failure)
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == stage
    if operation == "import":
        assert result["category"] == "SDK_IMPORT_FAILED"
    cleanup(flow)
    assert len([e for e in flow.events if e.startswith("GET:")]) <= 3


@pytest.mark.parametrize(
    "mode,stage,category",
    [
        ("before", "AUTHENTICATION_BEFORE_CALLBACK", "AUTHENTICATION_FAILED"),
        ("invalid", "CALLBACK_URI", "QUALIFICATION_REJECTED"),
        ("write", "CALLBACK_OUTPUT", "TERMINAL_IO_FAILED"),
        ("after", "AUTHENTICATION_AFTER_CALLBACK", "AUTHENTICATION_FAILED"),
    ],
)
def test_auth_callback_diagnostics_report_actual_entry_validation_and_completion(
    flow: Any,
    mode: str,
    stage: str,
    category: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    from datetime import UTC, datetime

    class PrivateTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, value: str) -> int:
            if mode == "write":
                raise ValueError(CANARY)
            return super().write(value)

    private = PrivateTTY()

    @contextmanager
    def terminal(binding: Any) -> Any:
        yield private

    monkeypatch.setattr(module, "_qualification_terminal", terminal)

    def auth(**kwargs: Any) -> Any:
        if mode != "before":
            flow.options["prompt_callback"](
                CANARY if mode == "invalid" else "https://microsoft.com/devicelogin",
                "SYNTHETIC-CODE",
                datetime.fromtimestamp(1200, UTC),
            )
        raise ValueError(CANARY)

    flow.sdk.authenticate = auth
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert (result["stage"], result["category"]) == (stage, category)
    cleanup(flow)
    assert not any(e.startswith("TOKEN:") or e.startswith("GET:") for e in flow.events)


@pytest.mark.parametrize("mode", ["exception", "unverified", "flag"])
def test_cleanup_failure_overrides_primary_without_private_output(
    flow: Any,
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    flow.fail = "auth"
    original = module._OwnerMemory.close

    def close(self: Any) -> None:
        original(self)
        if mode == "exception":
            raise ValueError(CANARY)
        if mode == "unverified":
            self._cleanup_verified = False
        if mode == "flag":
            self._cleanup_failed = True

    monkeypatch.setattr(module._OwnerMemory, "close", close)
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == "CLEANUP" and result["category"] == "CLEANUP_FAILED"
    cleanup(flow)


@pytest.mark.parametrize(
    "error,category",
    [
        (KeyboardInterrupt(CANARY), "CANCELLED"),
        (SystemExit(CANARY), "OPERATION_STOPPED"),
        (TimeoutError(CANARY), "TIMEOUT"),
    ],
)
def test_diagnostic_interrupt_timeout_exit_are_safe_and_cleanup(
    flow: Any,
    error: BaseException,
    category: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    def failed(**kwargs: Any) -> Any:
        raise error

    flow.sdk.authenticate = failed
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == "AUTHENTICATION_BEFORE_CALLBACK" and result["category"] == category
    cleanup(flow)


def test_forged_sdk_failure_cannot_supply_stage_facts(
    flow: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    def failed(**kwargs: Any) -> Any:
        raise module._SafeMetadataFailure("KNOWLEDGE_GET", "METADATA_GET_FAILED")

    flow.sdk.authenticate = failed
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == "AUTHENTICATION_BEFORE_CALLBACK"
    assert result["category"] == "QUALIFICATION_REJECTED"
    cleanup(flow)


@pytest.mark.parametrize(
    "stage,category",
    [
        (CANARY, "UNAVAILABLE"),
        ("SDK_CONSTRUCTION", CANARY),
        (None, "UNAVAILABLE"),
        ("UNKNOWN", None),
    ],
)
def test_unknown_failure_labels_fail_closed(stage: Any, category: Any) -> None:
    failure = module._SafeMetadataFailure(stage, category)
    assert module._failure_output(failure) == {
        "status": "METADATA_UNAVAILABLE",
        "stage": "UNKNOWN",
        "category": "UNAVAILABLE",
    }


def test_string_subclass_failure_fields_never_execute_private_hooks() -> None:
    class PrivateString(str):
        def __hash__(self) -> int:
            raise RuntimeError(CANARY)

        def __eq__(self, value: object) -> bool:
            raise RuntimeError(CANARY)

    failure = module._SafeMetadataFailure("UNKNOWN", "UNAVAILABLE")
    failure.stage = PrivateString("SDK_CONSTRUCTION")
    failure.category = PrivateString("SDK_IMPORT_FAILED")
    assert module._failure_output(failure)["stage"] == "UNKNOWN"
    assert module._failure_output(failure)["category"] == "UNAVAILABLE"



@pytest.mark.parametrize("boundary", ["binding", "terminal"])
def test_preconsent_guard_diagnostics_stop_before_sdk_and_do_not_disclose(
    flow: Any, boundary: str, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    if boundary == "binding":
        from dataclasses import replace
        monkeypatch.setattr(module, "_PLAN", replace(module._PLAN, client_id=CANARY))
    else:
        @contextmanager
        def rejected(binding: Any) -> Any:
            raise ValueError(CANARY)
            yield
        monkeypatch.setattr(module, "_qualification_terminal", rejected)
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == ("BINDING" if boundary == "binding" else "TERMINAL_OPEN")
    assert "SDK" not in flow.events and not flow.memories


def test_opaque_sdk_exception_never_stringified_or_represented(
    flow: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    class PrivateError(Exception):
        def __str__(self) -> str: raise RuntimeError(CANARY)
        def __repr__(self) -> str: raise RuntimeError(CANARY)
    def failed(**kwargs: Any) -> Any: raise PrivateError(CANARY)
    flow.factory = failed
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == "SDK_CONSTRUCTION" and result["category"] == "SDK_CONSTRUCTION_FAILED"
    cleanup(flow)



def test_cleanup_keyboard_interrupt_preserves_subtype_and_only_fixed_failure_codes(
    flow: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    original = module._OwnerMemory.close
    def interrupted(self: Any) -> None:
        original(self)
        raise KeyboardInterrupt(CANARY)
    monkeypatch.setattr(module._OwnerMemory, "close", interrupted)
    with pytest.raises(KeyboardInterrupt) as error:
        run(flow)
    assert str(error.value) == "FOUNDRY_QUALIFICATION_UNAVAILABLE"
    assert module._failure_output(error.value) == {
        "status": "METADATA_UNAVAILABLE", "stage": "CLEANUP", "category": "CLEANUP_FAILED"
    }
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err
    cleanup(flow)


@pytest.mark.parametrize("boundary", ["construct", "cleanup", "output"])
def test_cli_opaque_exception_class_hooks_never_execute_or_leak(
    flow: Any, boundary: str, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    hooks: list[str] = []
    terminal_output = io.StringIO()

    @contextmanager
    def terminal(binding: Any) -> Any:
        yield terminal_output

    monkeypatch.setattr(module, "_qualification_terminal", terminal)

    class PrivateMeta(type):
        def __hash__(cls) -> int:
            hooks.append("hash")
            print(CANARY)
            return 0

        def __eq__(cls, other: object) -> bool:
            hooks.append("eq")
            print(CANARY)
            return False

    class PrivateError(Exception, metaclass=PrivateMeta):
        @property
        def __class__(self) -> type[Exception]:
            hooks.append("class")
            print(CANARY)
            return Exception

        def __str__(self) -> str:
            hooks.append("str")
            print(CANARY)
            return CANARY

        def __repr__(self) -> str:
            hooks.append("repr")
            print(CANARY)
            return CANARY

    def failed(*args: Any, **kwargs: Any) -> Any:
        raise PrivateError(CANARY)

    if boundary == "construct":
        flow.factory = failed
    elif boundary == "cleanup":
        original = module._OwnerMemory.close

        def close(self: Any) -> None:
            original(self)
            failed()

        monkeypatch.setattr(module._OwnerMemory, "close", close)
    else:
        monkeypatch.setattr(module, "run_owner_metadata", failed)
        monkeypatch.setattr(module.sys, "argv", ["owner-metadata"])
        with pytest.raises(SystemExit, match="Foundry owner metadata is unavailable"):
            module.main()
        output = capsys.readouterr()
        assert output.out == "" and CANARY not in output.err
        assert json.loads(output.err) == {
            "status": "METADATA_UNAVAILABLE", "stage": "UNKNOWN", "category": "UNAVAILABLE"
        }
        assert hooks == []
        return

    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == ("SDK_CONSTRUCTION" if boundary == "construct" else "CLEANUP")
    assert result["category"] == (
        "SDK_CONSTRUCTION_FAILED" if boundary == "construct" else "CLEANUP_FAILED"
    )
    assert hooks == []
    assert CANARY not in terminal_output.getvalue()
    cleanup(flow)


@pytest.fixture
def installed_device_code_request_token() -> Any:
    """Exact installed 1.26 method/decorator, fake self only; no identity import."""
    import functools
    import hashlib
    import importlib.metadata
    import sysconfig
    from datetime import datetime, timezone

    from azure.core.exceptions import ClientAuthenticationError

    assert importlib.metadata.version("azure-identity") == "1.26.0"
    purelib = Path(sysconfig.get_path("purelib"))
    source = purelib / "azure/identity/_credentials/device_code.py"
    wrapper = purelib / "azure/identity/_internal/decorators.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "0d75bdf62e8588a27511e4dba8ca8b6d1656f33a47a4992ec9444749ee7a8bc1"
    )
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == (
        "b8cf9a3f816c5584f6691d415f8d6476f1c7b3cdd7c41f8ed2f63346add8530e"
    )
    decorator = next(
        node
        for node in ast.walk(ast.parse(wrapper.read_bytes()))
        if isinstance(node, ast.FunctionDef) and node.name == "wrap_exceptions"
    )
    credential = next(
        node
        for node in ast.parse(source.read_bytes()).body
        if isinstance(node, ast.ClassDef) and node.name == "DeviceCodeCredential"
    )
    method = next(
        node
        for node in credential.body
        if isinstance(node, ast.FunctionDef) and node.name == "_request_token"
    )
    namespace = {
        "functools": functools,
        "ClientAuthenticationError": ClientAuthenticationError,
        "datetime": datetime,
        "timezone": timezone,
        "time": module.time,
        "Dict": dict,
        "Any": Any,
    }
    # Only SHA-pinned installed SDK AST bodies, never arbitrary input or credential startup.
    exec(  # noqa: S102 - Execute only pinned trusted SDK AST, never input or startup.
        compile(ast.Module(body=[decorator], type_ignores=[]), str(wrapper), "exec"),
        namespace,
    )
    exec(  # noqa: S102 - Execute only pinned trusted SDK AST, never input or startup.
        compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    return namespace["_request_token"]


@pytest.mark.parametrize(
    "case,stage",
    [
        ("standard", "AUTHENTICATION_AFTER_CALLBACK"),
        ("www", "AUTHENTICATION_AFTER_CALLBACK"),
        ("state", "CALLBACK_STATE"),
        ("expiry-conversion", "CALLBACK_EXPIRY_CONVERSION"),
        ("terminal", "CALLBACK_TERMINAL"),
        ("expired", "CALLBACK_EXPIRY_VALUE"),
        ("nonfinite", "CALLBACK_EXPIRY_VALUE"),
        ("uri", "CALLBACK_URI"),
        ("code", "CALLBACK_CODE"),
        ("code-type", "CALLBACK_CODE"),
        ("reentry", "CALLBACK_REENTRY"),
        ("missing-uri", "AUTHENTICATION_BEFORE_CALLBACK"),
        ("sdk-expiry-type", "AUTHENTICATION_BEFORE_CALLBACK"),
    ],
)
def test_installed_sdk_ast_wrapper_preserves_guards_and_distinguishes_callback_checks(
    flow: Any,
    case: str,
    stage: str,
    installed_device_code_request_token: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    import socket
    from datetime import UTC

    denied: list[str] = []

    def no_network(*args: Any, **kwargs: Any) -> Any:
        denied.append("network")
        raise AssertionError("Synthetic network denied")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)

    class PrivateTTY(io.StringIO):
        def isatty(self) -> bool:
            return case != "terminal"

    private = PrivateTTY()

    @contextmanager
    def terminal(binding: Any) -> Any:
        yield private

    monkeypatch.setattr(module, "_qualification_terminal", terminal)
    fake_flow = {
        "verification_uri": "https://microsoft.com/devicelogin",
        "user_code": "SYNTH1234",
        "expires_at": 1200,
        "expires_in": 200,
    }
    if case == "uri":
        fake_flow["verification_uri"] = "https://microsoft.com/devicelogin/"
    if case == "www":
        fake_flow["verification_uri"] = "https://www.microsoft.com/devicelogin"
    if case == "code":
        fake_flow["user_code"] = CANARY + "_"
    if case == "code-type":
        fake_flow["user_code"] = 123
    if case == "expired":
        fake_flow["expires_at"] = 999
    if case == "missing-uri":
        del fake_flow["verification_uri"]
    if case == "sdk-expiry-type":
        fake_flow["expires_at"] = CANARY
    calls: list[str] = []
    sdk_shapes: list[tuple[type[Any], type[Any], bool]] = []

    class Expiry:
        def timestamp(self) -> float:
            if case == "expiry-conversion":
                print(CANARY)
                raise ValueError(CANARY)
            return float("nan")

    class FakeMSAL:
        def initiate_device_flow(self, scopes: list[str]) -> Any:
            assert scopes == [module._SCOPE]
            calls.append("flow")
            return fake_flow

        def acquire_token_by_device_flow(self, payload: Any, **kwargs: Any) -> Any:
            assert payload is fake_flow
            calls.append("poll")
            raise ValueError(
                CANARY
            )  # Deliberate offline stop after the accepted challenge.

    fake_msal = FakeMSAL()

    def callback(uri: str, code: str, expires: Any) -> None:
        sdk_shapes.append((type(uri), type(code), expires.tzinfo is UTC))
        # Explicit fault injection AFTER proving the SDK's canonical datetime shape.
        # These expiry faults do not assert the real SDK normally emits another type.
        if case in {"expiry-conversion", "nonfinite"}:
            expires = Expiry()
        memory = flow.memories[0]
        if case == "state":
            memory._private_approved = False
        if case == "reentry":
            memory._device_expiry = 1200
        flow.options["prompt_callback"](uri, code, expires)

    fake_self = SimpleNamespace(
        _get_app=lambda **kwargs: fake_msal, _prompt_callback=callback, _timeout=60
    )

    def auth(**kwargs: Any) -> Any:
        return installed_device_code_request_token(fake_self, module._SCOPE)

    flow.sdk.authenticate = auth
    result = diagnostic_cli(flow, monkeypatch, capsys)
    assert result["stage"] == stage
    assert result["category"] == (
        "AUTHENTICATION_FAILED"
        if case in {"standard", "www", "missing-uri", "sdk-expiry-type"}
        else "CALLBACK_REJECTED"
    )
    assert calls == (["flow", "poll"] if case in {"standard", "www"} else ["flow"])
    if case not in {"missing-uri", "sdk-expiry-type"}:
        assert sdk_shapes[0][0] is str and sdk_shapes[0][2] is True
    if case in {"standard", "www"}:
        assert "SYNTH1234" in private.getvalue()
        assert str(fake_flow["verification_uri"]) in private.getvalue()
    else:
        assert private.getvalue() == ""
    assert denied == []
    cleanup(flow)
    assert not any(
        event.startswith("TOKEN:") or event.startswith("GET:") for event in flow.events
    )


def test_callback_guard_order_and_original_predicates_are_exactly_preserved() -> None:
    old = ast.parse(
        subprocess.check_output(
            [  # noqa: S607 - Fixed immutable public source comparison; no arbitrary command.
                "git",
                "show",
                "1b792aa5f7e28b1e341961758fd8f5bb53fef760:apps/api/src/apbra_api/foundry_owner_metadata.py",
            ],
            cwd=ROOT,
            text=True,
        )
    )
    current = ast.parse(Path(module.__file__).read_text())
    original = next(
        node
        for node in ast.walk(old)
        if isinstance(node, ast.FunctionDef) and node.name == "prompt"
    )
    updated = next(
        node
        for node in ast.walk(current)
        if isinstance(node, ast.FunctionDef) and node.name == "prompt"
    )
    old_predicates = next(
        node.test.values
        for node in original.body
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp)
    )
    checks = [node for node in updated.body if isinstance(node, ast.If)]
    # PLAN10817 changes only this predicate: two exact Microsoft HTTPS literals,
    # builtin str first, no normalization or subclass equality/hash hooks.
    expected_uri = ast.parse(
        'type(uri) is not str or uri not in ('
        '"https://microsoft.com/devicelogin", "https://www.microsoft.com/devicelogin")',
        mode="eval",
    ).body
    uri_check = checks[2]
    assert ast.dump(uri_check.test) == ast.dump(expected_uri)
    uri_check.test = old_predicates[3]
    self_contained = [
        value
        for node in checks
        for value in (
            node.test.values if isinstance(node.test, ast.BoolOp) else [node.test]
        )
    ]
    assert [ast.dump(value) for value in self_contained] == [
        ast.dump(value) for value in old_predicates
    ]
    assert all(
        ast.dump(ast.Module(body=node.body, type_ignores=[]))
        == ast.dump(ast.Module(body=checks[0].body, type_ignores=[]))
        for node in checks
    )
    # Restore the single original OR statement and original stage marker, then
    # compare the entire callback AST, including conversion BEFORE terminal check.
    updated.body = [
        node
        for node in updated.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "mark"
            and node.value.args[0].value
            in {
                "CALLBACK_STATE",
                "CALLBACK_EXPIRY_CONVERSION",
                "CALLBACK_TERMINAL",
                "CALLBACK_EXPIRY_VALUE",
                "CALLBACK_URI",
                "CALLBACK_CODE",
                "CALLBACK_REENTRY",
            }
        )
    ]
    first = next(i for i, node in enumerate(updated.body) if isinstance(node, ast.If))
    updated.body[first : first + len(checks)] = [
        next(node for node in original.body if isinstance(node, ast.If))
    ]
    updated.body.insert(0, original.body[0])
    assert ast.dump(updated) == ast.dump(original)


@pytest.mark.parametrize("uri", [
    "http://microsoft.com/devicelogin", "http://www.microsoft.com/devicelogin",
    "https://microsoft.com/devicelogin/", "https://www.microsoft.com/devicelogin/",
    "https://microsoft.com/link", "https://www.microsoft.com/link",
    "https://microsoft.com:443/devicelogin", "https://www.microsoft.com:443/devicelogin",
    "https://microsoft.com/devicelogin?code=synthetic", "https://www.microsoft.com/devicelogin#code",
    "https://owner@microsoft.com/devicelogin", "https://www.microsoft.com@evil.invalid/devicelogin",
    "https://microsoft.com.evil.invalid/devicelogin", "https://evil.microsoft.com/devicelogin",
    "https://www.microsoft.com.evil.invalid/devicelogin", "https://www.microsoft.com/DeviceLogin",
    "https://WWW.microsoft.com/devicelogin", "HTTPS://www.microsoft.com/devicelogin",
    " https://www.microsoft.com/devicelogin", "https://www.microsoft.com/devicelogin ",
    "https://www.microsoft.com/devicelogin\n", "https://www.microsoft.com/devicelogin\r",
    "https://www.microsoft.com/\tdevicelogin", "https://www.microsoft.com/devicelogin\x00",
    "https://www.microsoft.com/%64evicelogin", "https://www.microsoft.com/devicelogin;param",
    "https://www.microsoft.com\\devicelogin", "https://www.microsoft.com/other",
    None, 123, b"https://www.microsoft.com/devicelogin",
])
def test_sdk_forwarded_uri_spoofs_and_nonstring_values_reject_without_challenge(
    flow: Any, uri: Any, installed_device_code_request_token: Any,
    monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    calls: list[str] = []

    class TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    private = TTY()

    @contextmanager
    def terminal(binding: Any) -> Any:
        yield private

    monkeypatch.setattr(module, "_qualification_terminal", terminal)

    class FakeMSAL:
        def initiate_device_flow(self, scopes: list[str]) -> dict[str, Any]:
            calls.append("flow")
            return {"verification_uri": uri, "user_code": "SYNTH1234",
                    "expires_at": 1200, "expires_in": 200}

        def acquire_token_by_device_flow(self, *args: Any, **kwargs: Any) -> Any:
            calls.append("poll")
            raise AssertionError("Rejected URI reached synthetic polling")

    fake = SimpleNamespace(_get_app=lambda **kwargs: FakeMSAL(),
                           _prompt_callback=lambda *args: flow.options["prompt_callback"](*args),
                           _timeout=60)

    def auth(**kwargs: Any) -> Any:
        return installed_device_code_request_token(fake, module._SCOPE)

    flow.sdk.authenticate = auth
    assert diagnostic_cli(flow, monkeypatch, capsys) == {
        "status": "METADATA_UNAVAILABLE", "stage": "CALLBACK_URI", "category": "CALLBACK_REJECTED"
    }
    assert calls == ["flow"] and private.getvalue() == ""
    cleanup(flow)
    assert not any(event.startswith("TOKEN:") or event.startswith("GET:") for event in flow.events)


@pytest.mark.parametrize("kind", ["str-subclass-canonical", "str-subclass-www", "opaque"])
def test_uri_exact_type_guard_never_executes_private_instance_or_metaclass_hooks(
    flow: Any, kind: str, installed_device_code_request_token: Any,
    monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    hooks: list[str] = []

    class PrivateMeta(type):
        def __hash__(cls) -> int:
            hooks.append("metaclass-hash")
            print(CANARY)
            return 0

        def __eq__(cls, other: object) -> bool:
            hooks.append("metaclass-equality")
            print(CANARY)
            return True

    class Hooks:
        @property
        def __class__(self) -> type[object]:
            hooks.append("class")
            print(CANARY)
            return str

        def __str__(self) -> str:
            hooks.append("str")
            print(CANARY)
            return CANARY

        def __repr__(self) -> str:
            hooks.append("repr")
            print(CANARY)
            return CANARY

        def __eq__(self, other: object) -> bool:
            hooks.append("equality")
            print(CANARY)
            return True

        def __ne__(self, other: object) -> bool:
            hooks.append("inequality")
            print(CANARY)
            return False

        def __hash__(self) -> int:
            hooks.append("hash")
            print(CANARY)
            return 0

    class PrivateString(Hooks, str, metaclass=PrivateMeta):
        pass

    class Opaque(Hooks, metaclass=PrivateMeta):
        pass

    uri = Opaque() if kind == "opaque" else PrivateString(
        "https://microsoft.com/devicelogin" if kind == "str-subclass-canonical"
        else "https://www.microsoft.com/devicelogin"
    )
    # Reuse the exact SDK-adapter rejection path and assert real, nonthrowing
    # hooks never ran (an assertion inside a swallowed SDK hook is insufficient).
    test_sdk_forwarded_uri_spoofs_and_nonstring_values_reject_without_challenge(
        flow, uri, installed_device_code_request_token, monkeypatch, capsys
    )
    assert hooks == []
