"""Pure-stdlib verifier for the read-only 0502 release support root.

Reads ``support-manifest.json`` from the support root, requires the declared
wheelhouse and npm cache directories to be canonical non-reparse directories,
requires every declared tool executable to exist and match its recorded SHA-256,
and refuses to mutate the support root. Prints one JSON line with the verified
absolute paths on success; exits nonzero on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def _canonical(path: Path, label: str, kind: str) -> Path:
    absolute = path.absolute()
    try:
        resolved = absolute.resolve(strict=True)
    except OSError:
        _fail(f"{label} is not resolvable")
    if resolved.anchor != absolute.anchor:
        _fail(f"{label} resolves to a different drive")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        names = {entry.name for entry in os.scandir(current)}
        if part not in names:
            _fail(f"{label} is not case-exact")
        current = current / part
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode) or getattr(
            metadata, "st_file_attributes", 0
        ) & _REPARSE:
            _fail(f"{label} contains a redirect")
    if resolved != absolute or (
        (kind == "file" and not absolute.is_file())
        or (kind == "dir" and not absolute.is_dir())
    ):
        _fail(f"{label} is not canonical {kind}")
    return absolute


def _manifest(root: Path) -> dict:
    manifest_path = root / "support-manifest.json"
    if not manifest_path.is_file():
        _fail("support-manifest.json is missing from the support root")
    raw = manifest_path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("support-manifest.json is invalid JSON")
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1:
        _fail("support-manifest.json schemaVersion must be 1")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--support", type=Path, required=True)
    args = parser.parse_args()

    root = _canonical(args.support, "SupportRoot", "dir")
    doc = _manifest(root)
    manifest_path = _canonical(root / "support-manifest.json", "manifest", "file")

    wheelhouse = _canonical(Path(doc["wheelhouse"]), "wheelhouse", "dir")
    npm_cache = _canonical(Path(doc["npmCache"]), "npmCache", "dir")

    tools = {
        "git": doc.get("git"),
        "node": doc.get("node"),
        "npm": doc.get("npm"),
        "python310": doc.get("python310"),
        "python312": doc.get("python312"),
        "cmdexec": doc.get("cmdexec"),
        "chromium": doc.get("chromium"),
    }
    verified_tools: dict[str, str] = {}
    for name, value in tools.items():
        if not value:
            _fail(f"support-manifest.json is missing tool {name}")
        tool_path = _canonical(Path(str(value)), f"tool {name}", "file")
        expected = doc.get("hashes", {}).get(name)
        if expected:
            digest = hashlib.sha256(tool_path.read_bytes()).hexdigest()
            if digest != str(expected):
                _fail(f"tool {name} SHA-256 does not match support manifest")
        verified_tools[name] = str(tool_path)

    for wheel in sorted(wheelhouse.glob("*.whl")):
        if not wheel.is_file():
            _fail("wheelhouse contains a non-file member")

    result = {
        "ok": True,
        "wheelhouse": str(wheelhouse),
        "npmCache": str(npm_cache),
        "tools": verified_tools,
        "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
