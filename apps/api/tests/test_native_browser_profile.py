"""The invitation inbox exists only in the synthetic loopback browser harness."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from native_browser_app import BrowserMailbox, mount_inbox, validate_profile

from apbra_api.password_auth import PasswordAuthSettings


def disposable(settings):
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url).set(database="apbra_e2e")
    return settings.model_copy(update={"database_url": url.render_as_string(hide_password=False)})


@pytest.mark.parametrize(
    "change",
    [
        {"profile": "development"},
        {"profile": "hosted"},
        {"foundry_host_enabled": True},
        {"model_provider_api_key": "synthetic-only"},
        {"model_provider_profile_json": "{}"},
        {"foundry_host_binding_json": "{}"},
        {"foundry_qualification_binding_json": "{}"},
        {"automatic_generation_enabled": True},
        {"oidc_client_secret": "synthetic-only"},
        {"public_origin": "https://example.org"},
        {"api_origin": "http://example.org:8000"},
        {"database_url": "postgresql+psycopg://localhost:5432/apbra"},
        {"database_url": "postgresql+psycopg://db.invalid:5432/apbra_e2e"},
        {"database_url": "postgresql+psycopg://localhost:5432/apbra_e2e?host=db.invalid"},
    ],
)
def test_inbox_guard_rejects_non_disposable_context(settings, change):
    with pytest.raises(ValueError, match="DISPOSABLE"):
        validate_profile(
            disposable(settings).model_copy(update=change), PasswordAuthSettings(_env_file=None)
        )


def test_inbox_guard_requires_capture_only_and_loopback(settings, client):
    cfg = disposable(settings)
    feature = PasswordAuthSettings(_env_file=None, password_auth_enabled=True)
    validate_profile(cfg, feature)
    for field in (
        "password_smtp_host",
        "password_smtp_username",
        "password_smtp_password",
        "password_mail_from",
    ):
        with pytest.raises(ValueError, match="DISPOSABLE"):
            validate_profile(cfg, feature.model_copy(update={field: "synthetic"}))
    assert client.get("/__demo/inbox").status_code == 404
    app = FastAPI()
    box = BrowserMailbox()
    mount_inbox(app, box, cfg.public_origin)
    browser = TestClient(app, base_url=cfg.public_origin)
    assert browser.get("/__demo/inbox").status_code == 200
    assert browser.get("/__demo/inbox", headers={"Host": "other.invalid"}).status_code == 403
    assert browser.get("/__demo/inbox", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    box.send("synthetic@example.org", "invite", "synthetic")
    result = browser.get("/__demo/inbox")
    assert result.headers["cache-control"] == "no-store"
    assert 'href="/invitation#native_invitation=synthetic"' in result.text
