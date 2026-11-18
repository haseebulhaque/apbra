"""Pure synthetic context projection; no database, auth, browser or provider calls."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apbra_api.domain import SemanticValidationFailed
from apbra_api.native_goal_context import goal_only_context


def fixture():
    case = SimpleNamespace(id=uuid4(), company_id=uuid4(), current_request_version_id=uuid4(),
                           semantic_context_version=4)
    request = SimpleNamespace(id=case.current_request_version_id, request_text="Explain demand.")
    event = SimpleNamespace(id=uuid4(), case_id=case.id, sequence=1, kind="USER_MESSAGE",
                            payload_json=json.dumps({"text": "AI answer: use weekly totals."}))
    store = SimpleNamespace(request_version=lambda _: request, case_versions=lambda _: [request],
                            conversation_events=lambda _: [event])
    return case, request, event, store


def test_goal_and_answer_are_complete_data_not_a_local_questionnaire():
    case, request, event, store = fixture()
    value = goal_only_context(store, case)
    assert value["requestText"] == request.request_text
    assert value["semanticContextVersion"] == 4
    assert value["conversation"][0]["payload"] == json.loads(event.payload_json)
    assert value["evidence"] == value["referenceMaterial"] == []
    assert not {"interpretation", "questions", "confirmation", "dataStructure"} & value.keys()


def test_original_goal_is_retained_with_updated_request_and_all_answers():
    case, request, event, store = fixture()
    store.case_versions = lambda _: [SimpleNamespace(request_text="Original goal"), request]
    second = SimpleNamespace(id=uuid4(), case_id=case.id, sequence=2, kind="USER_MESSAGE",
                             payload_json=json.dumps({"text": "Exact final answer <script>"}))
    store.conversation_events = lambda _: [event, second]
    value = goal_only_context(store, case)
    assert value["originalRequest"] == "Original goal"
    assert value["requestText"] == request.request_text
    assert value["conversation"][-1]["payload"]["text"] == "Exact final answer <script>"


@pytest.mark.parametrize("broken", ["missing", "changed", "foreign_event"])
def test_scope_or_current_request_failure_never_projects_partial_context(broken):
    case, request, event, store = fixture()
    if broken == "missing":
        store.request_version = lambda _: None
    elif broken == "changed":
        request.id = uuid4()
    else:
        event.case_id = uuid4()
    with pytest.raises(SemanticValidationFailed):
        goal_only_context(store, case)


def test_only_assistant_text_enters_dialogue_not_tool_results_or_provider_fields():
    from apbra_api.native_goal_context import assistant_texts

    raw = json.dumps({
        "status": "completed", "privateProviderMetadata": "must not project",
        "output": [
            {"type": "tool_result", "text": "must not project"},
            {"type": "message", "role": "user", "content": [
                {"type": "output_text", "text": "not assistant"}]},
            {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "AI question: café? <script>"},
                {"type": "output_file", "url": "https://private.invalid/do-not-project"},
                {"type": "output_text", "text": "Second AI question"}]},
        ],
    }).encode()
    assert assistant_texts(raw) == ["AI question: café? <script>", "Second AI question"]


@pytest.mark.parametrize("raw", [b"not json", b"null", b"[]", b"{}", b"\xff"])
def test_bad_provider_envelope_does_not_invent_questions(raw):
    from apbra_api.native_goal_context import assistant_texts

    assert assistant_texts(raw) == []


def test_prior_answer_binding_changes_for_late_receipts_and_changed_immutable_digests():
    from apbra_api.native_goal_context import native_context_binding

    row = SimpleNamespace(id=uuid4(), digest="a" * 64, context_version=2)
    initial = native_context_binding("saved goal and answers", [])
    bound = native_context_binding("saved goal and answers", [row])
    assert bound != initial
    assert "assistantTexts" not in bound
    row.digest = "b" * 64
    assert native_context_binding("saved goal and answers", [row]) != bound
    assert native_context_binding("changed requirements", []) != initial
