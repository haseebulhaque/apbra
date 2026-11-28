"""Loopback capture transport for the disposable browser suite. Never mounted by the runtime."""

import html
import os
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.engine import make_url

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.password_auth import PasswordAuthSettings

LABELS = {"verify": "Verify email", "reset": "Reset password", "invite": "Review invitation"}
PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
}


class BrowserMailbox:
    test_only = True

    def __init__(self) -> None:
        self._lock = Lock()
        self._messages: list[tuple[str, str, str]] = []

    def send(self, recipient: str, purpose: str, proof: str) -> None:
        if purpose not in LABELS:
            raise ValueError("UNSUPPORTED_CAPTURE_PURPOSE")
        with self._lock:
            self._messages.append((recipient, purpose, proof))

    def snapshot(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(reversed(self._messages))


def validate_profile(settings: Settings, feature: PasswordAuthSettings) -> None:
    target = make_url(settings.database_url)
    origins = [urlsplit(settings.public_origin), urlsplit(settings.api_origin)]
    if (
        settings.profile != "test"
        or any(
            os.environ.get(key)
            for key in (
                "PGHOST",
                "PGHOSTADDR",
                "PGPORT",
                "PGDATABASE",
                "PGSERVICE",
                "PGSERVICEFILE",
                "PGSYSCONFDIR",
                "PGOPTIONS",
            )
        )
        or target.drivername != "postgresql+psycopg"
        or target.host not in {"localhost", "127.0.0.1"}
        or not target.port
        or target.database != "apbra_e2e"
        or target.query
        or any(
            o.scheme != "http"
            or o.hostname not in {"127.0.0.1", "localhost"}
            or not o.port
            or o.username
            or o.password
            or o.path
            or o.query
            or o.fragment
            for o in origins
        )
        or any(
            (
                feature.password_smtp_host,
                feature.password_smtp_username,
                feature.password_smtp_password,
                feature.password_mail_from,
            )
        )
        or settings.model_provider_api_key is not None
        or settings.model_provider_profile_json is not None
        or settings.foundry_host_binding_json is not None
        or settings.foundry_qualification_binding_json is not None
        or settings.foundry_host_enabled
        or settings.foundry_qualification_enabled
        or settings.automatic_generation_enabled
        or settings.oidc_issuer
        or settings.oidc_profiles_json
        or settings.oidc_client_secret
        or settings.oidc_token_endpoint
        or any(
            urlsplit(p.endpoint).hostname != "provider.invalid"
            for p in settings.qualified_provider_profiles()
        )
    ):
        raise ValueError("NATIVE_BROWSER_REQUIRES_DISPOSABLE_LOCAL_TEST_PROFILE")


def mount_inbox(app: FastAPI, box: BrowserMailbox, origin: str) -> None:
    @app.get("/__demo/inbox", include_in_schema=False)
    def inbox(request: Request) -> Response:
        if request.headers.get("host") != urlsplit(origin).netloc or request.headers.get(
            "sec-fetch-site"
        ) not in {None, "same-origin", "none"}:
            return Response(status_code=403, headers=PRIVATE_HEADERS)
        items = []
        for recipient, purpose, proof in box.snapshot():
            url = (
                "/invitation#native_invitation=" + proof
                if purpose == "invite"
                else "/account#account_action=" + purpose + "&proof=" + proof
            )
            items.append(
                "<li><span>"
                + html.escape(recipient)
                + '</span> <a href="'
                + html.escape(url, quote=True)
                + '">'
                + LABELS[purpose]
                + "</a></li>"
            )
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Local test inbox · APBRA</title><style>body{font:17px/1.6 system-ui;"
            "max-width:48rem;margin:2rem auto;padding:0 1rem}li{padding:.5rem;"
            "overflow-wrap:anywhere}a:focus-visible{outline:3px solid #126c58}</style></head>"
            "<body><main><h1>Local test inbox</h1><p>This preview captures messages on this "
            "computer. Use synthetic addresses and a password unique to this preview.</p>"
            '<p><a href="/account">Open application</a> · '
            '<a href="/__demo/inbox">Refresh messages</a></p><ol>'
            + ("".join(items) or "<li>No messages yet.</li>")
            + "</ol></main></body></html>",
            headers=PRIVATE_HEADERS,
        )


def create_browser_app() -> FastAPI:
    settings = Settings(_env_file=None)
    feature = PasswordAuthSettings(_env_file=None, password_auth_enabled=True)
    validate_profile(settings, feature)
    box = BrowserMailbox()
    app = create_app(settings, password_settings=feature, password_mailer=box)
    mount_inbox(app, box, settings.public_origin)
    return app
