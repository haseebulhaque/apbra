from __future__ import annotations

import os
import secrets
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL, make_url

from alembic import command
from apbra_api.api import create_app
from apbra_api.bootstrap import bootstrap
from apbra_api.config import Settings
from apbra_api.persistence import Database

_TARGET_CHANGING_LIBPQ_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
)


def _database_target(url: URL) -> tuple[str, int, str]:
    assert url.host is not None and url.port is not None and url.database is not None
    host = "127.0.0.1" if url.host == "localhost" else url.host
    return (host, url.port, url.database)


def validate_disposable_database_url(raw_url: str) -> str:
    """Fail closed before a backend test can connect to or reset PostgreSQL."""

    try:
        url = make_url(raw_url)
    except Exception as error:
        raise pytest.UsageError(
            "APBRA_TEST_DATABASE_URL must be a valid PostgreSQL URL."
        ) from error
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port is None
        or url.database != "apbra_test"
        or url.query
    ):
        raise pytest.UsageError(
            "Backend tests may reset only an explicit loopback PostgreSQL database named "
            "apbra_test, without connection query options."
        )
    inherited = [name for name in _TARGET_CHANGING_LIBPQ_ENV if os.environ.get(name)]
    if inherited:
        raise pytest.UsageError(
            "Backend tests reject inherited libpq target settings: " + ", ".join(inherited)
        )
    test_target = _database_target(url)
    for name in ("APBRA_DATABASE_URL", "APBRA_E2E_DATABASE_URL"):
        candidate = os.environ.get(name)
        if not candidate:
            continue
        try:
            candidate_url = make_url(candidate)
            if candidate_url.query:
                raise ValueError("connection query options are ambiguous")
            candidate_target = _database_target(candidate_url)
        except Exception as error:
            raise pytest.UsageError(
                f"{name} must expose an unambiguous host, port, and database "
                "while destructive backend tests run."
            ) from error
        if candidate_url.database == "apbra_test" or candidate_target == test_target:
            raise pytest.UsageError(f"APBRA_TEST_DATABASE_URL must be distinct from {name}.")
    return raw_url


def disposable_alembic_config(database_url: str) -> Config:
    validated_url = validate_disposable_database_url(database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", validated_url)
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    raw_url = os.environ.get("APBRA_TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError("APBRA_TEST_DATABASE_URL must explicitly name apbra_test.")
    return validate_disposable_database_url(raw_url)


@pytest.fixture(scope="session")
def settings(database_url: str, tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("apbra-api")
    return Settings(
        profile="test",
        database_url=database_url,
        public_origin="http://127.0.0.1:5173",
        api_origin="http://127.0.0.1:8000",
        session_secret=secrets.token_urlsafe(48),
        bootstrap_enabled=True,
        evidence_root=root / "evidence",
        semantic_bridge_path=Path(
            os.environ.get("APBRA_TEST_SEMANTIC_BRIDGE", "/nonexistent/bridge.mjs")
        ),
        semantic_node_path=Path(shutil.which("node") or "/nonexistent/node"),
    )


@pytest.fixture(autouse=True)
def migrated_database(settings: Settings) -> Iterator[Database]:
    config = disposable_alembic_config(settings.database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    database = Database(settings.database_url)
    bootstrap(settings, database)
    yield database
    database.engine.dispose()


@pytest.fixture
def database(migrated_database: Database) -> Database:
    return migrated_database


@pytest.fixture
def client(settings: Settings, database: Database) -> TestClient:
    return TestClient(create_app(settings=settings, database=database))


def sign_in(client: TestClient, selector: str = "owner") -> dict[str, object]:
    start = client.get(
        "/api/auth/login", params={"identity": selector, "return_to": "/"}, follow_redirects=False
    )
    assert start.status_code == 302
    authorize_url = urlsplit(start.headers["location"])
    authorize = client.get(f"{authorize_url.path}?{authorize_url.query}", follow_redirects=False)
    assert authorize.status_code == 302
    callback_url = urlsplit(authorize.headers["location"])
    callback = client.get(f"{callback_url.path}?{callback_url.query}", follow_redirects=False)
    assert callback.status_code == 302
    session = client.get("/api/auth/session")
    assert session.status_code == 200
    return cast(dict[str, object], session.json())


def csrf(session: dict[str, object]) -> dict[str, str]:
    token = session.get("csrf_token")
    assert isinstance(token, str)
    return {"X-CSRF-Token": token}
