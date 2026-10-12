"""Pure submitted-metadata bookkeeping, not provider dispatch or live RAG proof.

A caller must resolve fresh membership/session/CSRF and qualify provider evidence
outside this module. Observations are supplied assertions, not verified indexing,
isolation or physical deletion. No durable storage or operational effects exist.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from uuid import UUID

from apbra_api.domain import Actor, Role


class Action(Enum):
    UPLOAD = "UPLOAD"
    UPDATE = "UPDATE"
    REPLACE = "REPLACE"
    DELETE = "DELETE"


class WriteOutcome(Enum):
    NOT_SENT = "NOT_SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"
    DEFINITIVELY_FAILED = "DEFINITIVELY_FAILED"


class ObservationKind(Enum):
    WRITE_ACKNOWLEDGED = "WRITE_ACKNOWLEDGED"
    WRITE_OUTCOME_UNKNOWN = "WRITE_OUTCOME_UNKNOWN"
    DEFINITIVE_FAILURE = "DEFINITIVE_FAILURE"
    INDEXING_OBSERVED = "INDEXING_OBSERVED"
    REMOVAL_OBSERVED = "REMOVAL_OBSERVED"


class FailureCode(Enum):
    ADMIN_REQUIRED = "ADMIN_REQUIRED"
    KNOWLEDGE_SCOPE_MISMATCH = "KNOWLEDGE_SCOPE_MISMATCH"
    KNOWLEDGE_REVISION_CONFLICT = "KNOWLEDGE_REVISION_CONFLICT"
    KNOWLEDGE_COMMAND_CONFLICT = "KNOWLEDGE_COMMAND_CONFLICT"
    KNOWLEDGE_OBSERVATION_CONFLICT = "KNOWLEDGE_OBSERVATION_CONFLICT"
    KNOWLEDGE_OBSERVATION_INVALID = "KNOWLEDGE_OBSERVATION_INVALID"


class Disposition(Enum):
    APPLIED = "APPLIED"
    REPLAY = "REPLAY"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"


class KnowledgeLifecycleError(ValueError):
    """Only a fixed public category; no opaque input or provider exception."""

    def __init__(self, code: FailureCode) -> None:
        if type(code) is not FailureCode or not any(code is member for member in FailureCode):
            code = FailureCode.KNOWLEDGE_OBSERVATION_INVALID
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class Revision:
    company_id: UUID
    document_id: UUID
    revision_id: UUID
    source_version: str = field(repr=False)
    owner_membership_id: UUID
    predecessor_revision_id: UUID | None


@dataclass(frozen=True, slots=True)
class Command:
    operation_id: UUID
    command_key: str = field(repr=False)
    action: Action
    company_id: UUID
    document_id: UUID
    target_revision_id: UUID
    expected_current_revision_id: UUID | None
    body_fingerprint: str = field(repr=False)
    new_revision: Revision | None


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: UUID
    company_id: UUID
    document_id: UUID
    revision_id: UUID
    operation_id: UUID
    kind: ObservationKind
    failure_code: FailureCode | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    command: Command
    initiator_identity_id: UUID
    initiator_membership_id: UUID
    write_outcome: WriteOutcome = WriteOutcome.NOT_SENT
    observation_history: tuple[Observation, ...] = ()


@dataclass(frozen=True, slots=True)
class Journal:
    company_id: UUID
    document_id: UUID
    revisions: tuple[Revision, ...] = ()
    operations: tuple[Operation, ...] = ()
    current_revision_id: UUID | None = None
    current_operation_id: UUID | None = None
    pending_removal_revision_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class Result:
    journal: Journal
    disposition: Disposition


def _require(valid: bool, code: FailureCode) -> None:
    if not valid:
        raise KnowledgeLifecycleError(code)


def _uuid(value: object, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    _require(type(value) is UUID, FailureCode.KNOWLEDGE_SCOPE_MISMATCH)
    # Exact UUID objects may still be forged using object.__new__/__setattr__.
    # Validate the only value used by UUID equality/hash before either operation.
    try:
        integer = object.__getattribute__(value, "int")
    except AttributeError:
        raise KnowledgeLifecycleError(FailureCode.KNOWLEDGE_SCOPE_MISMATCH) from None
    _require(type(integer) is int, FailureCode.KNOWLEDGE_SCOPE_MISMATCH)
    _require(0 <= integer < 1 << 128, FailureCode.KNOWLEDGE_SCOPE_MISMATCH)


def _revision_shape(value: Revision) -> None:
    _require(type(value) is Revision, FailureCode.KNOWLEDGE_REVISION_CONFLICT)
    for identifier in (
        value.company_id,
        value.document_id,
        value.revision_id,
        value.owner_membership_id,
    ):
        _uuid(identifier)
    _uuid(value.predecessor_revision_id, optional=True)
    _require(type(value.source_version) is str, FailureCode.KNOWLEDGE_REVISION_CONFLICT)


def _command_shape(value: Command) -> None:
    _require(type(value) is Command, FailureCode.KNOWLEDGE_COMMAND_CONFLICT)
    for identifier in (
        value.operation_id,
        value.company_id,
        value.document_id,
        value.target_revision_id,
    ):
        _uuid(identifier)
    _uuid(value.expected_current_revision_id, optional=True)
    _require(
        type(value.command_key) is str and type(value.body_fingerprint) is str,
        FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )
    _require(
        type(value.action) is Action and any(value.action is member for member in Action),
        FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
    )
    if value.new_revision is not None:
        _revision_shape(value.new_revision)


def _observation_shape(value: Observation) -> None:
    _require(type(value) is Observation, FailureCode.KNOWLEDGE_OBSERVATION_INVALID)
    for identifier in (
        value.observation_id,
        value.company_id,
        value.document_id,
        value.revision_id,
        value.operation_id,
    ):
        _uuid(identifier)
    _require(
        type(value.kind) is ObservationKind
        and any(value.kind is member for member in ObservationKind),
        FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
    )
    if value.kind is ObservationKind.DEFINITIVE_FAILURE:
        _require(
            value.failure_code is None
            or (
                type(value.failure_code) is FailureCode
                and any(value.failure_code is member for member in FailureCode)
            ),
            FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
        )
    else:
        _require(value.failure_code is None, FailureCode.KNOWLEDGE_OBSERVATION_INVALID)


def _actor_shape(actor: Actor) -> None:
    _require(type(actor) is Actor, FailureCode.ADMIN_REQUIRED)
    for identifier in (actor.identity_id, actor.membership_id, actor.company_id):
        _uuid(identifier)
    _require(
        type(actor.role) is Role
        and (actor.role is Role.COMPANY_OWNER or actor.role is Role.COMPANY_ADMIN),
        FailureCode.ADMIN_REQUIRED,
    )
    for text in (actor.issuer, actor.subject, actor.display_name, actor.provider_profile_id):
        _require(type(text) is str, FailureCode.KNOWLEDGE_SCOPE_MISMATCH)


def _action_preconditions(
    command: Command, revisions: tuple[Revision, ...], current: UUID | None, owner: UUID
) -> None:
    _require(
        command.expected_current_revision_id == current, FailureCode.KNOWLEDGE_REVISION_CONFLICT
    )
    if command.action is Action.DELETE:
        _require(
            command.new_revision is None
            and any(revision.revision_id == command.target_revision_id for revision in revisions),
            FailureCode.KNOWLEDGE_REVISION_CONFLICT,
        )
        return
    revision = command.new_revision
    _require(revision is not None, FailureCode.KNOWLEDGE_REVISION_CONFLICT)
    if revision is None:  # type narrowing only
        raise KnowledgeLifecycleError(FailureCode.KNOWLEDGE_REVISION_CONFLICT)
    _require(
        revision.company_id == command.company_id and revision.document_id == command.document_id,
        FailureCode.KNOWLEDGE_SCOPE_MISMATCH,
    )
    _require(
        revision.owner_membership_id == owner
        and revision.revision_id == command.target_revision_id
        and revision.predecessor_revision_id == current,
        FailureCode.KNOWLEDGE_REVISION_CONFLICT,
    )
    _require(
        not any(old.revision_id == revision.revision_id for old in revisions),
        FailureCode.KNOWLEDGE_REVISION_CONFLICT,
    )
    if command.action is Action.UPLOAD:
        _require(current is None and not revisions, FailureCode.KNOWLEDGE_REVISION_CONFLICT)
    else:
        _require(current is not None, FailureCode.KNOWLEDGE_REVISION_CONFLICT)


def _observed_outcome(operation: Operation) -> WriteOutcome:
    outcome = WriteOutcome.NOT_SENT
    command = operation.command
    for observation in operation.observation_history:
        _require(
            observation.company_id == command.company_id
            and observation.document_id == command.document_id
            and observation.operation_id == command.operation_id
            and observation.revision_id == command.target_revision_id,
            FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
        )
        if observation.kind is ObservationKind.WRITE_ACKNOWLEDGED:
            outcome = WriteOutcome.ACKNOWLEDGED
        elif observation.kind is ObservationKind.WRITE_OUTCOME_UNKNOWN:
            outcome = WriteOutcome.UNKNOWN
        elif observation.kind is ObservationKind.DEFINITIVE_FAILURE:
            outcome = WriteOutcome.DEFINITIVELY_FAILED
        # Index/removal assertions never synthesize or resolve a write outcome.
        # A lost acknowledgement can coexist with separately observed indexing.
    return outcome


def _validate_journal(journal: Journal) -> None:
    """Validate all shapes before comparing or hashing any supplied field."""
    _require(type(journal) is Journal, FailureCode.KNOWLEDGE_SCOPE_MISMATCH)
    _uuid(journal.company_id)
    _uuid(journal.document_id)
    _uuid(journal.current_revision_id, optional=True)
    _uuid(journal.current_operation_id, optional=True)
    _require(
        type(journal.revisions) is tuple
        and type(journal.operations) is tuple
        and type(journal.pending_removal_revision_ids) is tuple,
        FailureCode.KNOWLEDGE_SCOPE_MISMATCH,
    )
    for revision in journal.revisions:
        _revision_shape(revision)
    for operation in journal.operations:
        _require(type(operation) is Operation, FailureCode.KNOWLEDGE_COMMAND_CONFLICT)
        _command_shape(operation.command)
        _uuid(operation.initiator_identity_id)
        _uuid(operation.initiator_membership_id)
        _require(
            type(operation.write_outcome) is WriteOutcome
            and any(operation.write_outcome is member for member in WriteOutcome),
            FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
        )
        _require(
            type(operation.observation_history) is tuple, FailureCode.KNOWLEDGE_OBSERVATION_INVALID
        )
        for observation in operation.observation_history:
            _observation_shape(observation)
    for identifier in journal.pending_removal_revision_ids:
        _uuid(identifier)
    revisions: tuple[Revision, ...] = ()
    current: UUID | None = None
    current_operation: UUID | None = None
    tombstones: tuple[UUID, ...] = ()
    operation_ids: set[UUID] = set()
    command_keys: set[str] = set()
    observation_ids: set[UUID] = set()
    membership_identities: dict[UUID, UUID] = {}
    for operation in journal.operations:
        command = operation.command
        identity = membership_identities.get(operation.initiator_membership_id)
        _require(
            identity is None or identity == operation.initiator_identity_id,
            FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
        )
        membership_identities[operation.initiator_membership_id] = operation.initiator_identity_id
        _require(
            command.company_id == journal.company_id and command.document_id == journal.document_id,
            FailureCode.KNOWLEDGE_SCOPE_MISMATCH,
        )
        _require(
            command.operation_id not in operation_ids and command.command_key not in command_keys,
            FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
        )
        operation_ids.add(command.operation_id)
        command_keys.add(command.command_key)
        _action_preconditions(command, revisions, current, operation.initiator_membership_id)
        if command.new_revision is not None:
            revisions += (command.new_revision,)
            current, current_operation = command.target_revision_id, command.operation_id
        else:
            if command.target_revision_id not in tombstones:
                tombstones += (command.target_revision_id,)
            if command.target_revision_id == current:
                current_operation = command.operation_id
        for observation in operation.observation_history:
            _require(
                observation.observation_id not in observation_ids,
                FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT,
            )
            observation_ids.add(observation.observation_id)
        _require(
            operation.write_outcome is _observed_outcome(operation),
            FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
        )
    _require(
        journal.revisions == revisions
        and journal.current_revision_id == current
        and journal.current_operation_id == current_operation
        and journal.pending_removal_revision_ids == tombstones,
        FailureCode.KNOWLEDGE_REVISION_CONFLICT,
    )
    # Apply the same admission invariant to stored current history as to a new
    # observation. Older operations keep their legitimate historical assertions.
    if current in tombstones:
        for operation in journal.operations:
            if operation.command.operation_id == current_operation:
                _require(
                    not any(
                        item.kind is ObservationKind.INDEXING_OBSERVED
                        for item in operation.observation_history
                    ),
                    FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
                )


def begin_operation(journal: Journal, actor: Actor, command: Command) -> Result:
    """Append one explicit local intent, or replay its exact immutable identity."""
    try:
        _validate_journal(journal)
        _actor_shape(actor)
        _command_shape(command)
        _require(
            actor.company_id == journal.company_id == command.company_id
            and command.document_id == journal.document_id,
            FailureCode.KNOWLEDGE_SCOPE_MISMATCH,
        )
        for operation in journal.operations:
            if operation.initiator_membership_id == actor.membership_id:
                _require(
                    operation.initiator_identity_id == actor.identity_id,
                    FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
                )
            if (
                operation.command.command_key == command.command_key
                or operation.command.operation_id == command.operation_id
            ):
                _require(
                    operation.command == command
                    and operation.initiator_identity_id == actor.identity_id
                    and operation.initiator_membership_id == actor.membership_id,
                    FailureCode.KNOWLEDGE_COMMAND_CONFLICT,
                )
                return Result(journal, Disposition.REPLAY)
        _action_preconditions(
            command, journal.revisions, journal.current_revision_id, actor.membership_id
        )
        operation = Operation(command, actor.identity_id, actor.membership_id)
        current, current_operation = journal.current_revision_id, journal.current_operation_id
        revisions, tombstones = journal.revisions, journal.pending_removal_revision_ids
        if command.new_revision is not None:
            revisions += (command.new_revision,)
            current, current_operation = command.target_revision_id, command.operation_id
        else:
            if command.target_revision_id not in tombstones:
                tombstones += (command.target_revision_id,)
            if command.target_revision_id == current:
                current_operation = command.operation_id
        return Result(
            replace(
                journal,
                revisions=revisions,
                operations=journal.operations + (operation,),
                current_revision_id=current,
                current_operation_id=current_operation,
                pending_removal_revision_ids=tombstones,
            ),
            Disposition.APPLIED,
        )
    except AttributeError:
        raise KnowledgeLifecycleError(FailureCode.KNOWLEDGE_SCOPE_MISMATCH) from None


def record_observation(journal: Journal, observation: Observation) -> Result:
    """Retain a supplied assertion without dispatch, promotion or deletion proof."""
    try:
        _validate_journal(journal)
        _observation_shape(observation)
        _require(
            observation.company_id == journal.company_id
            and observation.document_id == journal.document_id,
            FailureCode.KNOWLEDGE_SCOPE_MISMATCH,
        )
        target: Operation | None = None
        for operation in journal.operations:
            for old in operation.observation_history:
                if old.observation_id == observation.observation_id:
                    _require(old == observation, FailureCode.KNOWLEDGE_OBSERVATION_CONFLICT)
                    return Result(journal, Disposition.REPLAY)
            if operation.command.operation_id == observation.operation_id:
                target = operation
        _require(target is not None, FailureCode.KNOWLEDGE_OBSERVATION_INVALID)
        if target is None:  # type narrowing only
            raise KnowledgeLifecycleError(FailureCode.KNOWLEDGE_OBSERVATION_INVALID)
        historical = observation.operation_id != journal.current_operation_id
        if observation.kind is ObservationKind.INDEXING_OBSERVED and not historical:
            _require(
                observation.revision_id not in journal.pending_removal_revision_ids,
                FailureCode.KNOWLEDGE_OBSERVATION_INVALID,
            )
        changed = replace(target, observation_history=target.observation_history + (observation,))
        changed = replace(changed, write_outcome=_observed_outcome(changed))
        operations = tuple(
            changed if operation is target else operation for operation in journal.operations
        )
        return Result(
            replace(journal, operations=operations),
            Disposition.HISTORICAL_ONLY if historical else Disposition.APPLIED,
        )
    except AttributeError:
        raise KnowledgeLifecycleError(FailureCode.KNOWLEDGE_OBSERVATION_INVALID) from None
