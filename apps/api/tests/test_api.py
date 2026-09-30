from fastapi.testclient import TestClient


def test_health_requires_live_database(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_mutation_requires_csrf(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 401


def test_validation_errors_do_not_echo_invitation_bearer_input(client: TestClient) -> None:
    raw = "sensitive-invitation-bearer"
    response = client.post("/api/invitations/inspect", json={"token": raw})
    assert response.status_code == 422
    assert raw not in response.text
    assert response.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "The request format is invalid.",
        }
    }
