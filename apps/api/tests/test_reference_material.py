from __future__ import annotations

from uuid import uuid4

import pytest
from conftest import csrf, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from apbra_api.persistence import Database

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-private-reference"
JPEG = b"\xff\xd8\xff" + b"synthetic-private-reference" + b"\xff\xd9"


def create_case(client: TestClient, session: dict[str, object]) -> dict[str, object]:
    response = client.post(
        "/api/cases",
        json={"request_text": "Compare qualified activity by region."},
        headers={**csrf(session), "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()["case"]


def test_capabilities_and_reference_upload_are_separate_and_truthful(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    capabilities = client.get("/api/cases/capabilities/uploads")
    assert capabilities.status_code == 200
    assert capabilities.json() == {
        "data_extensions": ["CSV", "XLSX"],
        "reference_extensions": ["PNG", "JPG", "JPEG"],
        "max_file_bytes": 5_000_000,
        "max_files_per_selection": 8,
        "max_answer_characters": 2_000,
    }
    case = create_case(client, session)
    added = client.post(
        f"/api/cases/{case['id']}/reference-material",
        params={"filename": "layout.png", "expected_context_version": 1},
        content=PNG,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert added.status_code == 200, added.text
    reference = added.json()["reference_material"]
    assert reference["media_type"] == "image/png"
    assert reference["interpretation_state"] == "NOT_INTERPRETED"
    assert reference["capability_profile_id"] is None
    assert reference["semantic_context_version"] == 2
    listed = client.get(f"/api/cases/{case['id']}/reference-material")
    assert listed.status_code == 200
    assert listed.json()["items"] == [
        {key: value for key, value in reference.items() if key != "semantic_context_version"}
    ]
    assert client.get(f"/api/cases/{case['id']}/evidence").json()["items"] == []


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("wrong.jpg", PNG),
        ("wrong.png", JPEG),
        ("unsupported.gif", b"GIF89a"),
        ("empty.png", b""),
    ],
)
def test_reference_upload_rejects_extension_content_mismatch(
    client: TestClient, filename: str, content: bytes
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    rejected = client.post(
        f"/api/cases/{case['id']}/reference-material",
        params={"filename": filename, "expected_context_version": 1},
        content=content,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert rejected.status_code == 422
    assert client.get(f"/api/cases/{case['id']}/reference-material").json()["items"] == []


def test_reference_upload_is_idempotent_and_revisions_do_not_reclassify_old_bytes(
    client: TestClient,
) -> None:
    session = sign_in(client, "member")
    case = create_case(client, session)
    first = client.post(
        f"/api/cases/{case['id']}/reference-material",
        params={"filename": "sketch.jpeg", "expected_context_version": 1},
        content=JPEG,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert first.status_code == 200
    duplicate = client.post(
        f"/api/cases/{case['id']}/reference-material",
        params={"filename": "same-bytes.jpg", "expected_context_version": 2},
        content=JPEG,
        headers={**csrf(session), "Content-Type": "application/octet-stream"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["reference_material"]["id"] == first.json()["reference_material"]["id"]
    assert duplicate.json()["reference_material"]["semantic_context_version"] == 2
    revised = client.put(
        f"/api/cases/{case['id']}",
        json={
            "request_text": "Compare qualified activity by region and month.",
            "expected_version": 1,
        },
        headers=csrf(session),
    )
    assert revised.status_code == 200
    assert client.get(f"/api/cases/{case['id']}/reference-material").json()["items"] == []


def test_reference_metadata_is_immutable_and_private(
    client: TestClient, database: Database
) -> None:
    owner = sign_in(client, "owner")
    case = create_case(client, owner)
    added = client.post(
        f"/api/cases/{case['id']}/reference-material",
        params={"filename": "private.png", "expected_context_version": 1},
        content=PNG,
        headers={**csrf(owner), "Content-Type": "application/octet-stream"},
    )
    assert added.status_code == 200
    reference_id = added.json()["reference_material"]["id"]
    with database.session() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "UPDATE case_reference_materials "
                    "SET interpretation_state='VISION_AVAILABLE' WHERE id=:id"
                ),
                {"id": reference_id},
            )
        db.rollback()
    with TestClient(client.app) as foreign_client:
        sign_in(foreign_client, "foreign")
        hidden = foreign_client.get(f"/api/cases/{case['id']}/reference-material")
        assert hidden.status_code == 404
        assert "private.png" not in hidden.text
