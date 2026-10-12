"""Synthetic pure bookkeeping proof only; no live provider or request authority."""

import ast
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from apbra_api import knowledge_lifecycle as m
from apbra_api.domain import Actor, Role

CANARY = "synthetic-private-source-and-fingerprint"


def uid(value: int) -> UUID:
    return UUID(int=value)


def actor(role: Role = Role.COMPANY_OWNER) -> Actor:
    return Actor(uid(1), uid(2), uid(3), "synthetic", "subject", "Owner", role, "test")


def empty() -> m.Journal:
    return m.Journal(uid(3), uid(4))


def command(
    action: m.Action = m.Action.UPLOAD,
    revision: int = 10,
    operation: int = 20,
    predecessor: UUID | None = None,
    owner: UUID | None = None,
) -> m.Command:
    owner = uid(2) if owner is None else owner
    new = (
        None
        if action is m.Action.DELETE
        else m.Revision(uid(3), uid(4), uid(revision), CANARY, owner, predecessor)
    )
    return m.Command(
        uid(operation),
        f"command-{operation}",
        action,
        uid(3),
        uid(4),
        uid(revision),
        predecessor,
        CANARY,
        new,
    )


def uploaded() -> m.Journal:
    return m.begin_operation(empty(), actor(), command()).journal


def observation(
    journal: m.Journal,
    kind: m.ObservationKind = m.ObservationKind.WRITE_ACKNOWLEDGED,
    identifier: int = 30,
    operation: int | None = None,
    revision: int | None = None,
) -> m.Observation:
    return m.Observation(
        uid(identifier),
        journal.company_id,
        journal.document_id,
        uid(revision) if revision is not None else journal.current_revision_id,  # type: ignore[arg-type]
        uid(operation) if operation is not None else journal.current_operation_id,  # type: ignore[arg-type]
        kind,
        m.FailureCode.KNOWLEDGE_OBSERVATION_INVALID
        if kind is m.ObservationKind.DEFINITIVE_FAILURE
        else None,
    )


def rejected(call: Any, code: m.FailureCode | None = None) -> None:
    with pytest.raises(m.KnowledgeLifecycleError) as error:
        call()
    assert type(error.value.code) is m.FailureCode
    assert str(error.value) == error.value.code.value
    assert CANARY not in str(error.value) + repr(error.value)
    if code is not None:
        assert error.value.code is code


@pytest.mark.parametrize("role", list(Role))
def test_role_matrix_and_replay_rechecks_current_role(role: Role) -> None:
    caller = actor(role)
    if role is Role.COMPANY_OWNER or role is Role.COMPANY_ADMIN:
        result = m.begin_operation(empty(), caller, command())
        assert result.disposition is m.Disposition.APPLIED
        replay = m.begin_operation(result.journal, caller, command())
        assert replay.disposition is m.Disposition.REPLAY and replay.journal is result.journal
    else:
        rejected(
            lambda: m.begin_operation(empty(), caller, command()), m.FailureCode.ADMIN_REQUIRED
        )
        rejected(
            lambda: m.begin_operation(uploaded(), caller, command()), m.FailureCode.ADMIN_REQUIRED
        )


def test_immutable_history_source_owner_and_update_replace_action_are_preserved() -> None:
    initial = empty()
    first = m.begin_operation(initial, actor(), command()).journal
    other = replace(actor(Role.COMPANY_ADMIN), identity_id=uid(5), membership_id=uid(6))
    second_command = command(m.Action.UPDATE, 11, 21, uid(10), other.membership_id)
    second = m.begin_operation(first, other, second_command).journal
    third = m.begin_operation(second, actor(), command(m.Action.REPLACE, 12, 22, uid(11))).journal
    assert initial.revisions == () and initial.operations == ()
    assert first.revisions == third.revisions[:1]
    assert first.operations == third.operations[:1]
    assert [revision.owner_membership_id for revision in third.revisions] == [
        uid(2),
        uid(6),
        uid(2),
    ]
    assert third.operations[1].command.action is m.Action.UPDATE
    assert third.operations[2].command.action is m.Action.REPLACE
    assert all(revision.source_version == CANARY for revision in third.revisions)
    assert third.current_revision_id == uid(12) and third.current_operation_id == uid(22)
    for value, name in [
        (third, "current_revision_id"),
        (third.revisions[0], "source_version"),
        (third.operations[0], "write_outcome"),
        (command(), "body_fingerprint"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, "changed")
    assert CANARY not in repr(third)


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", uid(99)),
        ("command_key", "changed"),
        ("action", m.Action.REPLACE),
        ("body_fingerprint", "changed"),
        ("expected_current_revision_id", uid(99)),
        ("target_revision_id", uid(99)),
        ("new_revision", replace(command().new_revision, source_version="changed")),
    ],
)
def test_replay_conflicts_on_complete_command_not_fingerprint_alone(field: str, value: Any) -> None:
    journal = uploaded()
    changed = replace(command(), **{field: value})
    rejected(lambda: m.begin_operation(journal, actor(), changed))
    assert journal == uploaded()


@pytest.mark.parametrize("field", ["identity_id", "membership_id"])
def test_replay_binds_both_actor_identities(field: str) -> None:
    rejected(
        lambda: m.begin_operation(uploaded(), replace(actor(), **{field: uid(99)}), command()),
        m.FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )


def test_exact_replay_precedes_new_command_expected_revision_guard() -> None:
    first = uploaded()
    second = m.begin_operation(first, actor(), command(m.Action.UPDATE, 11, 21, uid(10))).journal
    result = m.begin_operation(second, actor(), command())
    assert result.disposition is m.Disposition.REPLAY and result.journal is second
    rejected(
        lambda: m.begin_operation(second, actor(), command(m.Action.UPDATE, 12, 22, uid(10))),
        m.FailureCode.KNOWLEDGE_REVISION_CONFLICT,
    )


@pytest.mark.parametrize(
    "target",
    [
        "actor-company",
        "command-company",
        "command-document",
        "revision-company",
        "revision-document",
        "owner",
    ],
)
def test_foreign_scope_and_revision_owner_reject_before_append(target: str) -> None:
    caller, request = actor(), command()
    if target == "actor-company":
        caller = replace(caller, company_id=uid(99))
    elif target.startswith("command-"):
        request = replace(request, **{target.removeprefix("command-") + "_id": uid(99)})
    else:
        field = (
            "owner_membership_id" if target == "owner" else target.removeprefix("revision-") + "_id"
        )
        request = replace(request, new_revision=replace(request.new_revision, **{field: uid(99)}))
    journal = empty()
    rejected(lambda: m.begin_operation(journal, caller, request))
    assert journal == empty()


@pytest.mark.parametrize(
    "intent",
    [
        command(m.Action.UPDATE),
        command(m.Action.REPLACE),
        command(m.Action.DELETE),
        replace(command(), new_revision=None),
        replace(
            command(), new_revision=replace(command().new_revision, predecessor_revision_id=uid(99))
        ),
        replace(command(), target_revision_id=uid(99)),
    ],
)
def test_action_preconditions_reject_invalid_first_intents(intent: m.Command) -> None:
    rejected(lambda: m.begin_operation(empty(), actor(), intent))


def test_upload_reuse_predecessor_mismatch_and_delete_payload_reject() -> None:
    journal = uploaded()
    for request in [
        command(m.Action.UPLOAD, 11, 21, uid(10)),
        command(m.Action.UPDATE, 10, 21, uid(10)),
        command(m.Action.UPDATE, 11, 21, uid(99)),
        replace(command(m.Action.DELETE, 10, 21, uid(10)), new_revision=command().new_revision),
    ]:
        rejected(lambda request=request: m.begin_operation(journal, actor(), request))


@pytest.mark.parametrize(
    "kind,outcome",
    [
        (m.ObservationKind.WRITE_ACKNOWLEDGED, m.WriteOutcome.ACKNOWLEDGED),
        (m.ObservationKind.WRITE_OUTCOME_UNKNOWN, m.WriteOutcome.UNKNOWN),
        (m.ObservationKind.DEFINITIVE_FAILURE, m.WriteOutcome.DEFINITIVELY_FAILED),
    ],
)
def test_write_fact_only_changes_explicit_local_outcome_not_indexing(
    kind: Any, outcome: Any
) -> None:
    journal = uploaded()
    fact = observation(journal, kind)
    result = m.record_observation(journal, fact)
    assert result.journal.operations[0].write_outcome is outcome
    assert result.journal.operations[0].observation_history == (fact,)
    assert journal.operations[0].write_outcome is m.WriteOutcome.NOT_SENT
    assert result.journal.current_revision_id == journal.current_revision_id
    assert not any(
        item.kind is m.ObservationKind.INDEXING_OBSERVED
        for item in result.journal.operations[0].observation_history
    )


@pytest.mark.parametrize(
    "write_kind",
    [None, m.ObservationKind.WRITE_OUTCOME_UNKNOWN, m.ObservationKind.DEFINITIVE_FAILURE],
)
def test_explicit_index_fact_can_coexist_without_synthesizing_ack(write_kind: Any) -> None:
    journal = uploaded()
    if write_kind is not None:
        journal = m.record_observation(journal, observation(journal, write_kind)).journal
    previous_outcome = journal.operations[0].write_outcome
    indexed = observation(journal, m.ObservationKind.INDEXING_OBSERVED, 31)
    result = m.record_observation(journal, indexed)
    assert result.disposition is m.Disposition.APPLIED
    assert result.journal.operations[0].write_outcome is previous_outcome
    assert result.journal.operations[0].observation_history[-1] is indexed
    # Another reducer operation validates the mixed facts without remote-order assumptions.
    assert m.begin_operation(result.journal, actor(), command()).disposition is m.Disposition.REPLAY


def test_current_delete_tombstone_and_late_index_are_history_not_reactivation() -> None:
    first = uploaded()
    deletion = command(m.Action.DELETE, 10, 21, uid(10))
    deleted = m.begin_operation(first, actor(), deletion).journal
    assert deleted.current_revision_id == uid(10) and deleted.current_operation_id == uid(21)
    assert deleted.pending_removal_revision_ids == (uid(10),)
    rejected(
        lambda: m.record_observation(
            deleted, observation(deleted, m.ObservationKind.INDEXING_OBSERVED)
        )
    )
    old_index = observation(deleted, m.ObservationKind.INDEXING_OBSERVED, operation=20)
    result = m.record_observation(deleted, old_index)
    assert result.disposition is m.Disposition.HISTORICAL_ONLY
    assert result.journal.pending_removal_revision_ids == (uid(10),)
    assert result.journal.current_operation_id == uid(21)
    removal = observation(deleted, m.ObservationKind.REMOVAL_OBSERVED, 31)
    observed = m.record_observation(result.journal, removal).journal
    assert observed.pending_removal_revision_ids == (uid(10),)
    assert observed.operations[-1].write_outcome is m.WriteOutcome.NOT_SENT
    newer = m.begin_operation(observed, actor(), command(m.Action.REPLACE, 11, 22, uid(10))).journal
    assert newer.current_revision_id == uid(11) and newer.pending_removal_revision_ids == (uid(10),)


def test_historical_delete_preserves_latest_revision_and_its_operation_outcome() -> None:
    first = uploaded()
    second = m.begin_operation(first, actor(), command(m.Action.UPDATE, 11, 21, uid(10))).journal
    second = m.record_observation(
        second, observation(second, m.ObservationKind.WRITE_ACKNOWLEDGED)
    ).journal
    delete_a = command(m.Action.DELETE, 10, 22, uid(11))
    result = m.begin_operation(second, actor(), delete_a)
    journal = result.journal
    assert journal.current_revision_id == uid(11) and journal.current_operation_id == uid(21)
    assert journal.operations[1] is second.operations[1]
    assert journal.operations[1].write_outcome is m.WriteOutcome.ACKNOWLEDGED
    late = observation(journal, m.ObservationKind.REMOVAL_OBSERVED, 31, operation=22, revision=10)
    retained = m.record_observation(journal, late)
    assert retained.disposition is m.Disposition.HISTORICAL_ONLY
    assert retained.journal.current_operation_id == uid(21)
    assert retained.journal.pending_removal_revision_ids == (uid(10),)
    assert (
        m.begin_operation(retained.journal, actor(), delete_a).disposition is m.Disposition.REPLAY
    )


def test_superseded_index_and_write_facts_cannot_change_current_metadata() -> None:
    second = m.begin_operation(
        uploaded(), actor(), command(m.Action.REPLACE, 11, 21, uid(10))
    ).journal
    for index, kind in enumerate(m.ObservationKind):
        fact = observation(second, kind, 30 + index, operation=20, revision=10)
        before = second
        result = m.record_observation(second, fact)
        assert result.disposition is m.Disposition.HISTORICAL_ONLY
        second = result.journal
        assert (second.current_revision_id, second.current_operation_id) == (uid(11), uid(21))
        assert second.operations[1] is before.operations[1]
        assert second.operations[0].observation_history[-1] is fact


def test_observation_exact_replay_and_conflicting_global_id_reuse() -> None:
    initial = uploaded()
    fact = observation(initial)
    journal = m.record_observation(initial, fact).journal
    result = m.record_observation(journal, fact)
    assert result.disposition is m.Disposition.REPLAY and result.journal is journal
    rejected(
        lambda: m.record_observation(
            journal, replace(fact, kind=m.ObservationKind.WRITE_OUTCOME_UNKNOWN)
        ),
        m.FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT,
    )
    second = m.begin_operation(journal, actor(), command(m.Action.UPDATE, 11, 21, uid(10))).journal
    rejected(
        lambda: m.record_observation(second, observation(second)),
        m.FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT,
    )


@pytest.mark.parametrize("field", ["company_id", "document_id", "revision_id", "operation_id"])
def test_observation_reference_binding_rejects_foreign_unknown_fields(field: str) -> None:
    journal = uploaded()
    rejected(
        lambda: m.record_observation(journal, replace(observation(journal), **{field: uid(99)}))
    )


def test_id_uniqueness_is_per_entity_namespace_not_cross_kind() -> None:
    request = command(operation=10)  # same numeric UUID as revision is permitted
    journal = m.begin_operation(empty(), actor(), request).journal
    fact = observation(journal, identifier=10)
    result = m.record_observation(journal, fact)
    assert result.disposition is m.Disposition.APPLIED
    assert m.begin_operation(result.journal, actor(), request).disposition is m.Disposition.REPLAY


@pytest.mark.parametrize(
    "malformation",
    [
        "current-revision",
        "current-operation",
        "extra-revision",
        "duplicate-revision",
        "duplicate-operation",
        "owner",
        "predecessor",
        "operation-identity",
        "outcome",
        "unknown-tombstone",
        "duplicate-tombstone",
        "foreign-company",
        "foreign-document",
        "mutable-revisions",
        "mutable-operations",
        "mutable-history",
        "mutable-tombstones",
        "duplicate-observation",
        "foreign-observation",
    ],
)
def test_complete_journal_graph_is_checked_before_new_work(malformation: str) -> None:
    journal = uploaded()
    op = journal.operations[0]
    rev = journal.revisions[0]
    if malformation == "current-revision":
        journal = replace(journal, current_revision_id=uid(99))
    elif malformation == "current-operation":
        journal = replace(journal, current_operation_id=uid(99))
    elif malformation == "extra-revision":
        journal = replace(journal, revisions=(rev, replace(rev, revision_id=uid(99))))
    elif malformation == "duplicate-revision":
        journal = replace(journal, revisions=(rev, rev))
    elif malformation == "duplicate-operation":
        journal = replace(journal, operations=(op, op))
    elif malformation == "owner":
        journal = replace(journal, operations=(replace(op, initiator_membership_id=uid(99)),))
    elif malformation == "predecessor":
        journal = replace(
            journal,
            operations=(
                replace(
                    op,
                    command=replace(
                        op.command, new_revision=replace(rev, predecessor_revision_id=uid(99))
                    ),
                ),
            ),
        )
    elif malformation == "operation-identity":
        journal = replace(journal, operations=(replace(op, initiator_identity_id="private"),))
    elif malformation == "outcome":
        journal = replace(
            journal, operations=(replace(op, write_outcome=m.WriteOutcome.ACKNOWLEDGED),)
        )
    elif malformation == "unknown-tombstone":
        journal = replace(journal, pending_removal_revision_ids=(uid(99),))
    elif malformation == "duplicate-tombstone":
        journal = replace(journal, pending_removal_revision_ids=(uid(10), uid(10)))
    elif malformation == "foreign-company":
        journal = replace(journal, company_id=uid(99))
    elif malformation == "foreign-document":
        journal = replace(journal, document_id=uid(99))
    elif malformation == "mutable-revisions":
        journal = replace(journal, revisions=[rev])
    elif malformation == "mutable-operations":
        journal = replace(journal, operations=[op])
    elif malformation == "mutable-history":
        journal = replace(journal, operations=(replace(op, observation_history=[]),))
    elif malformation == "mutable-tombstones":
        journal = replace(journal, pending_removal_revision_ids=[])
    elif malformation == "duplicate-observation":
        fact = observation(journal)
        journal = replace(
            journal,
            operations=(
                replace(
                    op, write_outcome=m.WriteOutcome.ACKNOWLEDGED, observation_history=(fact, fact)
                ),
            ),
        )
    else:
        fact = replace(observation(journal), revision_id=uid(99))
        journal = replace(
            journal,
            operations=(
                replace(op, write_outcome=m.WriteOutcome.ACKNOWLEDGED, observation_history=(fact,)),
            ),
        )
    rejected(lambda: m.begin_operation(journal, actor(), command()))
    rejected(lambda: m.record_observation(journal, observation(uploaded())))


def test_opaque_hostile_instance_class_metaclass_and_string_hooks_never_run(capsys: Any) -> None:
    hooks: list[str] = []

    class PrivateMeta(type):
        def __hash__(cls) -> int:
            hooks.append("hash")
            print(CANARY)
            return 0

        def __eq__(cls, other: object) -> bool:
            hooks.append("eq")
            print(CANARY)
            return False

    class Private(metaclass=PrivateMeta):
        @property
        def __class__(self) -> type[object]:
            hooks.append("class")
            print(CANARY)
            return object

        def __getattr__(self, name: str) -> Any:
            hooks.append("attribute")
            print(CANARY)
            return self

        def __hash__(self) -> int:
            hooks.append("hash-instance")
            print(CANARY)
            return 0

        def __eq__(self, other: object) -> bool:
            hooks.append("eq-instance")
            print(CANARY)
            return False

        def __str__(self) -> str:
            hooks.append("str")
            print(CANARY)
            return CANARY

        def __repr__(self) -> str:
            hooks.append("repr")
            print(CANARY)
            return CANARY

    private = Private()
    for field in [
        "operation_id",
        "command_key",
        "action",
        "company_id",
        "document_id",
        "target_revision_id",
        "expected_current_revision_id",
        "body_fingerprint",
        "new_revision",
    ]:
        rejected(
            lambda field=field: m.begin_operation(
                empty(), actor(), replace(command(), **{field: private})
            )
        )
    for field in [
        "company_id",
        "document_id",
        "revisions",
        "operations",
        "current_revision_id",
        "current_operation_id",
        "pending_removal_revision_ids",
    ]:
        rejected(
            lambda field=field: m.begin_operation(
                replace(empty(), **{field: private}), actor(), command()
            )
        )
    rejected(lambda: m.begin_operation(private, actor(), command()))
    rejected(lambda: m.begin_operation(empty(), private, command()))
    rejected(lambda: m.record_observation(uploaded(), private))
    for field in ["kind", "failure_code", "revision_id", "observation_id"]:
        rejected(
            lambda field=field: m.record_observation(
                uploaded(), replace(observation(uploaded()), **{field: private})
            )
        )
    assert hooks == []
    output = capsys.readouterr()
    assert output.out == "" and output.err == ""


@pytest.mark.parametrize("integer", [None, True, -1, 1 << 128, CANARY])
def test_malformed_exact_uuid_internals_reject_before_hash_or_equality(integer: Any) -> None:
    forged = object.__new__(UUID)
    if integer is not None:
        object.__setattr__(forged, "int", integer)
    rejected(lambda: m.begin_operation(empty(), actor(), replace(command(), operation_id=forged)))


def test_uninitialized_exact_dtos_and_str_subclasses_are_safe(capsys: Any) -> None:
    class PrivateString(str):
        def __eq__(self, other: object) -> bool:
            print(CANARY)
            return True

        def __hash__(self) -> int:
            print(CANARY)
            return 0

    for cls in [m.Journal, m.Command, m.Revision, m.Operation, m.Observation]:
        forged = object.__new__(cls)
        if cls is m.Journal:
            rejected(lambda forged=forged: m.begin_operation(forged, actor(), command()))
        elif cls is m.Command:
            rejected(lambda forged=forged: m.begin_operation(empty(), actor(), forged))
        elif cls is m.Revision:
            rejected(
                lambda forged=forged: m.begin_operation(
                    replace(empty(), revisions=(forged,)), actor(), command()
                )
            )
        elif cls is m.Operation:
            rejected(
                lambda forged=forged: m.begin_operation(
                    replace(empty(), operations=(forged,)), actor(), command()
                )
            )
        else:
            rejected(lambda forged=forged: m.record_observation(uploaded(), forged))
    for field in ["command_key", "body_fingerprint"]:
        rejected(
            lambda field=field: m.begin_operation(
                empty(), actor(), replace(command(), **{field: PrivateString(CANARY)})
            )
        )
    assert capsys.readouterr().out == ""


def test_import_closure_and_code_have_no_operational_side_effects() -> None:
    source = Path(m.__file__).resolve()
    tree = ast.parse(source.read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"dataclasses", "enum", "uuid", "apbra_api.domain"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    code = """import dataclasses,enum,uuid,typing,sys,importlib.abc,socket,os,logging
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  forbidden=('azure','httpx','sqlalchemy','apbra_api.api','apbra_api.main',
   'apbra_api.config','apbra_api.persistence','apbra_api.tenant_settings')
  if fullname.startswith(forbidden):raise RuntimeError('Forbidden import')
sys.meta_path.insert(0,Block())
def deny(*a,**k):raise RuntimeError('Forbidden effect')
socket.create_connection=deny;socket.socket.connect=deny;os.getenv=deny;logging.getLogger=deny
class NoEnvironment(dict):
 def __getitem__(self,k):raise RuntimeError('Environment access')
 def get(self,*a):raise RuntimeError('Environment access')
os.environ=NoEnvironment()
sys.path.insert(0,SOURCE)
import apbra_api.knowledge_lifecycle as module
assert Path(module.__file__).resolve()==EXPECTED
print('PURE_IMPORT_NO_PROVIDER_CONFIG_ENV_NETWORK_PASS')
"""
    code = code.replace("SOURCE", repr(str(source.parents[1]))).replace("EXPECTED", repr(source))
    # EXPECTED must be a path literal rather than repr(PosixPath(...)).
    code = code.replace(repr(source), "Path(" + repr(str(source)) + ")")
    # Controlled synthetic code and the running test interpreter; no untrusted command.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-S", "-B", "-c", code],
        env={},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout == "PURE_IMPORT_NO_PROVIDER_CONFIG_ENV_NETWORK_PASS\n"


def test_definitive_failure_with_unknown_cause_needs_no_invented_code() -> None:
    journal = uploaded()
    fact = replace(observation(journal, m.ObservationKind.DEFINITIVE_FAILURE), failure_code=None)
    result = m.record_observation(journal, fact)
    assert result.journal.operations[0].write_outcome is m.WriteOutcome.DEFINITIVELY_FAILED
    assert result.journal.operations[0].observation_history[-1].failure_code is None
    assert m.begin_operation(result.journal, actor(), command()).disposition is m.Disposition.REPLAY


def test_actor_and_revision_private_fields_reject_without_input_hooks(capsys: Any) -> None:
    hooks: list[str] = []

    class Private:
        def __getattr__(self, name: str) -> Any:
            hooks.append("attribute")
            print(CANARY)
            return self

        def __str__(self) -> str:
            hooks.append("str")
            print(CANARY)
            return CANARY

        def __eq__(self, other: object) -> bool:
            hooks.append("equality")
            print(CANARY)
            return True

    private = Private()
    for field in [
        "identity_id",
        "membership_id",
        "company_id",
        "role",
        "issuer",
        "subject",
        "display_name",
        "provider_profile_id",
    ]:
        rejected(
            lambda field=field: m.begin_operation(
                empty(), replace(actor(), **{field: private}), command()
            )
        )
    for field in [
        "company_id",
        "document_id",
        "revision_id",
        "source_version",
        "owner_membership_id",
        "predecessor_revision_id",
    ]:
        intent = replace(
            command(), new_revision=replace(command().new_revision, **{field: private})
        )
        rejected(lambda intent=intent: m.begin_operation(empty(), actor(), intent))
    assert hooks == [] and capsys.readouterr().out == ""


def test_uuid_integer_and_tuple_subclasses_never_execute_hooks(capsys: Any) -> None:
    hooks: list[str] = []

    class PrivateInt(int):
        def __lt__(self, other: object) -> bool:
            hooks.append("compare")
            print(CANARY)
            return True

        def __hash__(self) -> int:
            hooks.append("hash")
            print(CANARY)
            return 0

    class PrivateTuple(tuple):
        def __iter__(self) -> Any:
            hooks.append("iterate")
            print(CANARY)
            return iter(())

    forged = object.__new__(UUID)
    object.__setattr__(forged, "int", PrivateInt(1))
    rejected(lambda: m.begin_operation(empty(), actor(), replace(command(), operation_id=forged)))
    for field in ["revisions", "operations", "pending_removal_revision_ids"]:
        rejected(
            lambda field=field: m.begin_operation(
                replace(empty(), **{field: PrivateTuple()}), actor(), command()
            )
        )
    assert hooks == [] and capsys.readouterr().out == ""


def test_forged_exact_enum_members_are_not_admitted_as_closed_labels() -> None:
    action = object.__new__(m.Action)
    object.__setattr__(action, "_value_", "UPLOAD")
    object.__setattr__(action, "_name_", "UPLOAD")
    rejected(lambda: m.begin_operation(empty(), actor(), replace(command(), action=action)))
    kind = object.__new__(m.ObservationKind)
    object.__setattr__(kind, "_value_", "WRITE_ACKNOWLEDGED")
    object.__setattr__(kind, "_name_", "WRITE_ACKNOWLEDGED")
    rejected(lambda: m.record_observation(uploaded(), replace(observation(uploaded()), kind=kind)))


def test_duplicate_observation_ids_across_operation_histories_reject_before_replay() -> None:
    first = m.record_observation(uploaded(), observation(uploaded())).journal
    second = m.begin_operation(first, actor(), command(m.Action.UPDATE, 11, 21, uid(10))).journal
    forged_op = replace(
        second.operations[1],
        write_outcome=m.WriteOutcome.ACKNOWLEDGED,
        observation_history=(observation(second),),
    )
    forged = replace(second, operations=(second.operations[0], forged_op))
    rejected(
        lambda: m.begin_operation(forged, actor(), command()),
        m.FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT,
    )
    rejected(
        lambda: m.record_observation(forged, observation(second)),
        m.FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT,
    )


def test_membership_identity_cannot_change_for_new_command() -> None:
    journal = uploaded()
    changed_actor = replace(actor(), identity_id=uid(99))
    rejected(
        lambda: m.begin_operation(
            journal, changed_actor, command(m.Action.UPDATE, 11, 21, uid(10))
        ),
        m.FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )


def test_malformed_membership_identity_history_rejects_before_any_processing() -> None:
    second = m.begin_operation(
        uploaded(), actor(), command(m.Action.UPDATE, 11, 21, uid(10))
    ).journal
    forged = replace(
        second,
        operations=(
            second.operations[0],
            replace(second.operations[1], initiator_identity_id=uid(99)),
        ),
    )
    rejected(
        lambda: m.begin_operation(forged, actor(), command()),
        m.FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )
    rejected(
        lambda: m.record_observation(forged, observation(second)),
        m.FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )


@pytest.mark.parametrize("next_action", ["exact-observation-replay", "acknowledgement", "update"])
def test_stored_current_tombstone_index_rejects_before_any_further_processing(
    next_action: str,
) -> None:
    deleted = m.begin_operation(
        uploaded(), actor(), command(m.Action.DELETE, 10, 21, uid(10))
    ).journal
    index = observation(deleted, m.ObservationKind.INDEXING_OBSERVED)
    forged = replace(
        deleted,
        operations=(
            deleted.operations[0],
            replace(deleted.operations[1], observation_history=(index,)),
        ),
    )

    def run() -> m.Result:
        if next_action == "exact-observation-replay":
            return m.record_observation(forged, index)
        if next_action == "acknowledgement":
            return m.record_observation(forged, observation(forged, identifier=31))
        return m.begin_operation(forged, actor(), command(m.Action.UPDATE, 11, 22, uid(10)))

    rejected(run, m.FailureCode.KNOWLEDGE_OBSERVATION_INVALID)


def test_index_fact_recorded_before_delete_remains_valid_historical_history() -> None:
    first = uploaded()
    indexed = m.record_observation(
        first, observation(first, m.ObservationKind.INDEXING_OBSERVED)
    ).journal
    deleted = m.begin_operation(indexed, actor(), command(m.Action.DELETE, 10, 21, uid(10))).journal
    assert deleted.operations[0].observation_history == indexed.operations[0].observation_history
    assert m.begin_operation(deleted, actor(), command()).disposition is m.Disposition.REPLAY
