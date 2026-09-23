from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from typing import cast
from urllib.parse import urlsplit

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from apbra_api.api import create_app
from apbra_api.bootstrap import bootstrap
from apbra_api.config import Settings
from apbra_api.persistence import Database


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get(
        "APBRA_TEST_DATABASE_URL",
        "postgresql+psycopg://apbra:apbra@127.0.0.1:54321/apbra_test",
    )


@pytest.fixture(scope="session")
def settings(database_url: str) -> Settings:
    return Settings(
        profile="test",
        database_url=database_url,
        public_origin="http://127.0.0.1:5173",
        api_origin="http://127.0.0.1:8000",
        session_secret=secrets.token_urlsafe(48),
        bootstrap_enabled=True,
    )


@pytest.fixture(autouse=True)
def migrated_database(settings: Settings) -> Iterator[Database]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url)
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
