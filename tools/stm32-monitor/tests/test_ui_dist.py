import json
import re
import zipfile
from pathlib import Path

import pytest

UI_DIST = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stm32_monitor"
    / "ui_dist"
)

_REMOTE_URL = re.compile(r"https?://[^\"'\s)]+")
# XML/SVG namespace URIs are identifier strings, not network fetches.
_NAMESPACE_URIS = {
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xhtml",
    "http://www.w3.org/XML/1998/namespace",
    "http://www.w3.org/1998/Math/MathML",
}


@pytest.fixture(scope="module")
def dist_files() -> list[Path]:
    assert UI_DIST.is_dir(), "ui_dist is absent; run npm run build"
    return sorted(path for path in UI_DIST.rglob("*") if path.is_file())


@pytest.fixture(scope="module")
def manifest() -> dict:
    payload = json.loads((UI_DIST / ".vite" / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_inventory_contains_index_manifest_and_assets(dist_files: list[Path]) -> None:
    names = {path.relative_to(UI_DIST).as_posix() for path in dist_files}
    assert "index.html" in names
    assert ".vite/manifest.json" in names
    assert any(name.startswith("assets/") for name in names)


def test_no_source_maps(dist_files: list[Path]) -> None:
    assert not any(path.name.endswith(".map") for path in dist_files)


def test_no_remote_urls_or_inline_scripts(dist_files: list[Path]) -> None:
    for path in dist_files:
        text = path.read_text(encoding="utf-8")
        for match in _REMOTE_URL.findall(text):
            assert match in _NAMESPACE_URIS, f"remote URL in {path}: {match}"
    html = (UI_DIST / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "<style>" not in html


def test_no_service_worker_or_eval(
    dist_files: list[Path],
) -> None:
    for path in dist_files:
        if path.suffix not in (".js", ".css"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "serviceWorker" not in text
        assert "new Function" not in text
        assert "eval(" not in text


def test_manifest_references_only_present_assets(
    dist_files: list[Path], manifest: dict
) -> None:
    names = {path.relative_to(UI_DIST).as_posix() for path in dist_files}
    for record in manifest.values():
        if not isinstance(record, dict):
            continue
        for field in ("file", "css"):
            value = record.get(field)
            if isinstance(value, str):
                assert value in names, f"manifest references missing {value}"
            elif isinstance(value, list):
                for item in value:
                    assert item in names, f"manifest references missing {item}"


def test_gzip_and_raw_size_budgets(dist_files: list[Path]) -> None:
    import gzip

    js_files = [path for path in dist_files if path.suffix == ".js"]
    gzip_js = sum(len(gzip.compress(path.read_bytes())) for path in js_files)
    assert gzip_js <= 450 * 1024, f"gzip JS {gzip_js} exceeds 450 KiB"
    total_raw = sum(path.stat().st_size for path in dist_files)
    assert total_raw <= 8 * 1024 * 1024, f"total raw {total_raw} exceeds 8 MiB"
    for path in dist_files:
        assert path.stat().st_size <= 4 * 1024 * 1024, f"{path} exceeds 4 MiB"
    index_size = (UI_DIST / "index.html").stat().st_size
    manifest_size = (UI_DIST / ".vite" / "manifest.json").stat().st_size
    assert index_size <= 256 * 1024
    assert manifest_size <= 256 * 1024


def test_no_aggregate_echarts_source_import(dist_files: list[Path]) -> None:
    for path in dist_files:
        if path.suffix != ".js":
            continue
        text = path.read_text(encoding="utf-8")
        assert "echarts/lib/echarts.js" not in text
        assert "echarts.all" not in text


def test_every_asset_is_content_hashed(dist_files: list[Path]) -> None:
    asset_re = re.compile(r"^assets/[A-Za-z0-9_.-]+-[A-Za-z0-9_]{8,}\.(js|css|svg|png|jpe?g|webp|woff2)$")
    for path in dist_files:
        rel = path.relative_to(UI_DIST).as_posix()
        if rel.startswith("assets/"):
            assert asset_re.match(rel), f"{rel} is not content-hashed"
