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


def test_load_uses_packaged_ui_dist_when_root_is_omitted() -> None:
    assets = UiAssets.load()
    index = assets.response("/", 43125)
    assert index.status == 200
    assert index.headers["Content-Type"] == "text/html; charset=utf-8"


def _write_manifest(root: Path, manifest: object, *, index: bytes | None = None) -> Path:
    (root / ".vite").mkdir(parents=True, exist_ok=True)
    (root / ".vite" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    if index is not None:
        (root / "index.html").write_bytes(index)
    return root


def test_load_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="manifest is absent"):
        UiAssets.load(tmp_path)


def test_load_rejects_non_object_manifest(tmp_path: Path) -> None:
    root = _write_manifest(tmp_path, [])
    with pytest.raises(ValueError, match="manifest is invalid"):
        UiAssets.load(root)


def test_load_rejects_missing_index_html(tmp_path: Path) -> None:
    root = _write_manifest(tmp_path, {"index.html": {"file": "assets/a.js"}})
    with pytest.raises(ValueError, match="index.html is absent"):
        UiAssets.load(root)


def test_load_skips_non_object_records_and_non_string_items(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-A1b2C3d4.js").write_bytes(b"console.log(1)")
    manifest = {
        "broken": [1, 2, 3],
        "entry": {
            "file": "assets/index-A1b2C3d4.js",
            "assets": ["assets/index-A1b2C3d4.js", 42, "assets/other.js"],
        },
    }
    root = _write_manifest(
        tmp_path, manifest, index=b'<!doctype html><div id="app"></div>'
    )
    loaded = UiAssets.load(root)
    assert loaded.response("/assets/index-A1b2C3d4.js", 43125).status == 200
    assert loaded.response("/assets/other.js", 43125).status == 404


def test_register_ignores_non_asset_names(tmp_path: Path) -> None:
    manifest = {"entry": {"file": "index.html"}}
    root = _write_manifest(
        tmp_path, manifest, index=b'<!doctype html><div id="app"></div>'
    )
    loaded = UiAssets.load(root)
    # Only the literal index route is served; the non-assets/ reference is ignored.
    assert loaded.response("/", 43125).status == 200
    assert loaded.response("/index.html", 43125).status == 404


def test_register_ignores_unhashed_unknown_extension_and_missing_files(
    tmp_path: Path,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-A1b2C3d4.js").write_bytes(b"console.log(1)")
    manifest = {
        "entry": {
            "file": "assets/index-A1b2C3d4.js",
            "css": [
                "assets/unhashed.css",
                "assets/index-A1b2C3d4.map",
                "assets/ghost-A1b2C3d4.js",
            ],
        }
    }
    root = _write_manifest(
        tmp_path, manifest, index=b'<!doctype html><div id="app"></div>'
    )
    loaded = UiAssets.load(root)
    assert loaded.response("/assets/index-A1b2C3d4.js", 43125).status == 200
    for route in (
        "/assets/unhashed.css",
        "/assets/index-A1b2C3d4.map",
        "/assets/ghost-A1b2C3d4.js",
    ):
        assert loaded.response(route, 43125).status == 404


def test_read_rejects_invalid_paths_and_missing_files(tmp_path: Path) -> None:
    from stm32_monitor.ui_assets import _read

    assert _read(tmp_path, "assets/\x00file.js") is None
    assert _read(tmp_path, "assets/absent.js") is None
