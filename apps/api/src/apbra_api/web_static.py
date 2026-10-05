"""Serve the exact built web asset closure from a private, immutable image directory."""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

_ASSET_NAME = re.compile(r"assets/[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+\Z")
_INDEX_REFERENCE = re.compile(r'(?:src|href)="/(assets/[^"?#]+)"')


def _asset_closure(root: Path) -> frozenset[str]:
    """Validate Vite's entry manifest and every byte the public shell can name."""
    try:
        if (root / "assets").is_symlink() or (root / ".vite").is_symlink():
            raise ValueError("linked asset directory")
        manifest: dict[str, Any] = json.loads((root / ".vite/manifest.json").read_text())
        entry = manifest["index.html"]
        if not isinstance(entry, dict) or entry.get("isEntry") is not True:
            raise ValueError("missing entry")
        pending = ["index.html"]
        seen: set[str] = set()
        files: set[str] = set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            item = manifest[name]
            if not isinstance(item, dict):
                raise ValueError("invalid entry")
            pending.extend(item.get("imports", []))
            pending.extend(item.get("dynamicImports", []))
            files.add(item["file"])
            files.update(item.get("css", []))
            files.update(item.get("assets", []))
        if not files or not all(
            isinstance(name, str) and _ASSET_NAME.fullmatch(name) and not name.endswith(".map")
            for name in files
        ):
            raise ValueError("unsafe asset name")
        if not all((root / name).is_file() and not (root / name).is_symlink() for name in files):
            raise ValueError("missing asset")
        index = (root / "index.html")
        if not index.is_file() or index.is_symlink():
            raise ValueError("missing shell")
        direct = set(_INDEX_REFERENCE.findall(index.read_text()))
        if not direct or not direct.issubset(files):
            raise ValueError("shell references missing asset")
        return frozenset(files)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Built APBRA web assets are invalid or incomplete") from error


def install_web_static(app: FastAPI, root: Path) -> None:
    """Mount only app shell routes and manifest-reachable hashed assets."""
    allowed = _asset_closure(root)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/invite", methods=["GET", "HEAD"], include_in_schema=False)
    def app_shell() -> FileResponse:
        return FileResponse(
            root / "index.html",
            headers={
                "Cache-Control": "no-cache, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.api_route("/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def app_asset(asset_path: str) -> FileResponse:
        name = "assets/" + asset_path
        if name not in allowed:
            raise HTTPException(status_code=404)
        return FileResponse(
            root / name,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )
