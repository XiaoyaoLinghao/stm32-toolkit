"""Bundled UI resource allowlist serving for the Monitor service.

``UiAssets`` reads the committed Vite ``ui_dist`` package resources exactly
once, validates every referenced file into an immutable allowlist, and
answers only the exact ``/`` and ``/assets/<content-hashed filename>``
routes.  No request path is ever joined to a filesystem path, no directory
listing is produced, and ``/api/*`` never falls back to ``index.html``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Mapping

try:  # Python 3.11+
    from importlib.resources.abc import Traversable
except ImportError:  # pragma: no cover - Python 3.9/3.10 path
    from importlib.abc import Traversable  # type: ignore[no-redef]

from aiohttp import web

_INDEX_ROUTE = "/"
_ASSETS_PREFIX = "/assets/"
_MANIFEST = ".vite/manifest.json"
_HASH_RE = re.compile(r"^assets/[A-Za-z0-9_.-]+-[A-Za-z0-9_]{8,}\.([a-z0-9]+)$")

_MIME = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}
_ALLOWED_EXTENSIONS = frozenset(_MIME)

_CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
    "form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; connect-src 'self' ws://127.0.0.1:{port}; worker-src 'none'; "
    "child-src 'none'; media-src 'none'"
)
_COMMON = {
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()"
    ),
}
_INDEX_CACHE = "no-store"
_ASSET_CACHE = "public, max-age=31536000, immutable"


@dataclass(frozen=True)
class UiAssetEntry:
    route: str
    name: str
    body: bytes
    mime: str
    etag: str
    cache_control: str


class UiAssets:
    """Immutable allowlist of committed UI package resources."""

    def __init__(self, entries: Mapping[str, UiAssetEntry]) -> None:
        self._entries = dict(entries)

    @classmethod
    def load(cls, root: Traversable | None = None) -> "UiAssets":
        if root is None:
            root = resources.files("stm32_monitor") / "ui_dist"
        entries: dict[str, UiAssetEntry] = {}
        manifest = _read(root, _MANIFEST)
        if manifest is None:
            raise ValueError("ui_dist manifest is absent")
        records = json.loads(manifest.decode("utf-8"))
        if not isinstance(records, dict):
            raise ValueError("ui_dist manifest is invalid")

        index_body = _read(root, "index.html")
        if index_body is None:
            raise ValueError("ui_dist index.html is absent")
        entries[_INDEX_ROUTE] = UiAssetEntry(
            route=_INDEX_ROUTE,
            name="index.html",
            body=index_body,
            mime="text/html; charset=utf-8",
            etag=_quote_sha256(index_body),
            cache_control=_INDEX_CACHE,
        )

        seen: set[str] = set()
        for record in records.values():
            if not isinstance(record, dict):
                continue
            for field in ("file", "css", "assets"):
                value = record.get(field)
                if isinstance(value, str):
                    _register(root, entries, value, seen)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            _register(root, entries, item, seen)
        return cls(entries)

    def response(self, route: str, port: int, *, head: bool = False) -> web.Response:
        entry = self._entries.get(route)
        if entry is None:
            return web.Response(status=404, body=b"")
        headers = dict(_COMMON)
        headers.update(
            {
                "Content-Security-Policy": _CSP.format(port=port),
                "Content-Type": entry.mime,
                "ETag": entry.etag,
                "Cache-Control": entry.cache_control,
                "Content-Length": str(len(entry.body)),
            }
        )
        return web.Response(status=200, body=b"" if head else entry.body, headers=headers)


def _register(
    root: Traversable, entries: dict[str, UiAssetEntry], name: str, seen: set[str]
) -> None:
    if name in seen or not name.startswith("assets/"):
        return
    seen.add(name)
    match = _HASH_RE.fullmatch(name)
    if match is None:
        return
    extension = match.group(1)
    mime = _MIME.get(f".{extension}")
    if mime is None:
        return
    body = _read(root, name)
    if body is None:
        return
    entries[f"{_ASSETS_PREFIX}{name[len('assets/'):]}"] = UiAssetEntry(
        route=f"{_ASSETS_PREFIX}{name[len('assets/'):]}",
        name=name,
        body=body,
        mime=mime,
        etag=_quote_sha256(body),
        cache_control=_ASSET_CACHE,
    )


def _quote_sha256(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _read(root: Traversable, relative: str) -> bytes | None:
    try:
        parts = tuple(part for part in relative.split("/") if part)
        current: Traversable = root
        for part in parts:
            current = current.joinpath(part)
        if not current.is_file():
            return None
        return current.read_bytes()
    except (OSError, ValueError):
        return None
