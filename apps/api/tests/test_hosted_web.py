"""Same-origin hosted shell serves only its exact immutable Vite asset closure."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apbra_api.api import create_app
from apbra_api.config import Settings
from apbra_api.persistence import Database


def built_shell(root: Path) -> None:
    (root / ".vite").mkdir()
    (root / "assets").mkdir()
    (root / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/index-AbCd1234.js"></script>'
    )
    (root / "assets/index-AbCd1234.js").write_text("console.log('synthetic')")
    (root / ".vite/manifest.json").write_text(json.dumps({
        "index.html": {
            "file": "assets/index-AbCd1234.js", "isEntry": True, "src": "index.html"
        }
    }))


def test_hosted_shell_asset_cache_and_api_boundaries(
    settings: Settings, database: Database, tmp_path: Path
) -> None:
    built_shell(tmp_path)
    (tmp_path / "private-secret.txt").write_text("not public")
    client = TestClient(create_app(settings=settings, database=database, web_static_root=tmp_path))
    for route in ("/", "/invite"):
        for method in ("GET", "HEAD"):
            response = client.request(method, route)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-cache, must-revalidate"
            assert response.headers["x-content-type-options"] == "nosniff"
    asset = client.get("/assets/index-AbCd1234.js")
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/api/health").status_code == 200
    unknown_api = client.get("/api/not-a-route")
    assert unknown_api.status_code == 404
    assert "text/html" not in unknown_api.headers.get("content-type", "")
    assert client.post("/api/health").status_code == 405
    for route in (
        "/not-an-app-route", "/assets/unknown-AbCd1234.js", "/private-secret.txt",
        "/assets/../private-secret.txt",
    ):
        assert client.get(route).status_code == 404


def test_hosted_assets_fail_closed_on_missing_or_unsafe_manifest(
    settings: Settings, database: Database, tmp_path: Path
) -> None:
    built_shell(tmp_path)
    (tmp_path / "assets/index-AbCd1234.js").unlink()
    with pytest.raises(RuntimeError, match="invalid or incomplete"):
        create_app(settings=settings, database=database, web_static_root=tmp_path)
    (tmp_path / "assets/index-AbCd1234.js").write_text("synthetic")
    (tmp_path / "index.html").write_text(
        '<script type="module" src="/assets/stale-AbCd1234.js"></script>'
    )
    with pytest.raises(RuntimeError, match="invalid or incomplete"):
        create_app(settings=settings, database=database, web_static_root=tmp_path)
    (tmp_path / "index.html").write_text(
        '<script type="module" src="/assets/index-AbCd1234.js"></script>'
    )
    manifest = tmp_path / ".vite/manifest.json"
    manifest.write_text(json.dumps({
        "index.html": {"file": "../private-secret.txt", "isEntry": True}
    }))
    with pytest.raises(RuntimeError, match="invalid or incomplete"):
        create_app(settings=settings, database=database, web_static_root=tmp_path)
