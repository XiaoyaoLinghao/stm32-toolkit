import hashlib
import json
from pathlib import Path

import pytest

from stm32_monitor.ui_assets import UiAssets


def _write_dist(root: Path) -> Path:
    assets = root / "assets"
    assets.mkdir(parents=True)
    (assets / "index-A1b2C3d4.js").write_bytes(b"console.log(1)")
    (assets / "index-E5f6G7h8.css").write_bytes(b"body{}")
    manifest = {
        "index.html": {
            "file": "assets/index-A1b2C3d4.js",
            "css": ["assets/index-E5f6G7h8.css"],
        }
    }
    (root / ".vite").mkdir()
    (root / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "index.html").write_text(
        '<!doctype html><html><body><div id="app"></div>'
        '<script type="module" src="/assets/index-A1b2C3d4.js"></script></body></html>',
        encoding="utf-8",
    )
    return root


@pytest.fixture
def assets(tmp_path: Path) -> UiAssets:
    return UiAssets.load(_write_dist(tmp_path))


def test_allowlist_never_resolves_or_reflects_request_paths(assets: UiAssets) -> None:
    ok = assets.response("/assets/index-A1b2C3d4.js", 43125)
    assert ok.status == 200
    assert ok.headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert ok.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert ok.headers["ETag"] == '"' + hashlib.sha256(ok.body).hexdigest() + '"'
    assert ok.headers["Referrer-Policy"] == "no-referrer"
    assert ok.headers["X-Content-Type-Options"] == "nosniff"
    assert "connect-src 'self' ws://127.0.0.1:43125" in ok.headers["Content-Security-Policy"]

    denied = assets.response("/assets/../auth.py", 43125)
    assert denied.status == 404 and denied.body == b""
    assert "auth.py" not in str(denied.headers)


def test_index_is_served_with_no_store(assets: UiAssets) -> None:
    index = assets.response("/", 43125)
    assert index.status == 200
    assert index.headers["Content-Type"] == "text/html; charset=utf-8"
    assert index.headers["Cache-Control"] == "no-store"
    assert b'id="app"' in index.body


def test_head_parity(assets: UiAssets) -> None:
    full = assets.response("/assets/index-A1b2C3d4.js", 43125)
    head = assets.response("/assets/index-A1b2C3d4.js", 43125, head=True)
    assert head.status == 200
    assert head.body == b""
    assert head.headers["Content-Length"] == str(len(full.body))
    assert head.headers["ETag"] == full.headers["ETag"]


@pytest.mark.parametrize(
    "route",
    [
        "/assets/../auth.py",
        "/assets/%2e%2e/auth.py",
        "/assets/%2fetc%2fpasswd",
        "/assets/%5cwindows",
        "/assets//double//slash",
        "/assets/unknown-NotAHash.js",
        "/api/v1/status",
        "/assets/index-A1b2C3d4.map",
    ],
)
def test_non_allowlisted_routes_are_denied(assets: UiAssets, route: str) -> None:
    response = assets.response(route, 43125)
    assert response.status == 404
    assert response.body == b""


def test_css_is_served(assets: UiAssets) -> None:
    css = assets.response("/assets/index-E5f6G7h8.css", 43125)
    assert css.status == 200
    assert css.headers["Content-Type"] == "text/css; charset=utf-8"
