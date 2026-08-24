#!/usr/bin/env python3
"""Build and verify the STM32 Toolkit 0.9.0 offline Windows bundle.

This module intentionally uses the Python standard library for the artifact
boundary.  It does not resolve packages, contact an index, execute package
code, or mutate Git.  Product builds are delegated to the existing CPython
build backend through an argument-array subprocess after the closed wheel set
has been selected and verified.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as _datetime
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


VERSION = "0.9.0"
REPOSITORY = "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"
REQUIRED_PYTHON = ">=3.12,<3.13"
MANIFEST_SCHEMA = "stm32-toolkit-release/1"
STATE_SCHEMA = "stm32-toolkit-runtime-state/1"
MAX_MANIFEST_BYTES = 1 << 20
MAX_STATE_BYTES = 64 << 10
SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")
SAFE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
WHEEL_NAME = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^.]+)\.whl$", re.I)
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
HOSTILE_CHARS = set(chr(i) for i in range(32)) | set('"<>|&^%!')


class ReleaseError(Exception):
    """A bounded, caller-safe input/policy/integrity rejection."""

    def __init__(self, public: str):
        super().__init__(public)
        self.public = public


class _DuplicateKey(ValueError):
    pass


def _reject(message: str) -> None:
    raise ReleaseError(message)


def _canonical_json(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReleaseError("canonical JSON value is invalid") from exc
    return (text + "\n").encode("utf-8")


def _strict_json(raw: bytes, *, limit: int) -> Any:
    if len(raw) > limit:
        _reject("JSON document exceeds the permitted size")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _DuplicateKey
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except _DuplicateKey as exc:
        raise ReleaseError("duplicate JSON key") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ReleaseError("invalid JSON document") from exc


def _read_bounded(path: Path, limit: int, *, regular: bool = True) -> bytes:
    _assert_no_redirect(path, leaf=True)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ReleaseError("required artifact is unavailable") from exc
    if size > limit:
        _reject("artifact exceeds the permitted size")
    if regular and not stat.S_ISREG(path.stat().st_mode):
        _reject("artifact is not a regular file")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReleaseError("artifact cannot be read") from exc
    if len(data) != size:
        _reject("artifact changed while being read")
    return data


def _is_reparse(path: Path) -> bool:
    try:
        st = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    # FILE_ATTRIBUTE_REPARSE_POINT.  st_file_attributes exists on Windows and
    # is harmlessly absent on other development hosts.
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _assert_no_redirect(path: Path, *, leaf: bool = False) -> None:
    try:
        if path.exists() and _is_reparse(path):
            _reject("path redirect is not permitted")
        if leaf and path.exists():
            st = path.stat()
            if stat.S_ISDIR(st.st_mode) or stat.S_ISCHR(st.st_mode) or stat.S_ISBLK(st.st_mode):
                _reject("path is not a regular file")
            if getattr(st, "st_nlink", 1) > 1:
                _reject("multi-link artifact is not permitted")
    except OSError as exc:
        raise ReleaseError("path is unavailable") from exc


def _assert_no_redirect_ancestors(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    chain: list[Path] = []
    current = absolute
    while True:
        chain.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for item in reversed(chain):
        if item.exists():
            _assert_no_redirect(item)


def _validate_safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or value != unicodedata.normalize("NFC", value):
        _reject("invalid bundle member name")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value) or "\\" in value or ":" in value:
        _reject("invalid bundle member name")
    if any(ch in HOSTILE_CHARS or ord(ch) == 127 for ch in value) or "${" in value:
        _reject("invalid bundle member name")
    if len(value.encode("utf-8")) > 4096:
        _reject("invalid bundle member name")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _reject("invalid bundle member name")
    for part in parts:
        if len(part.encode("utf-8")) > 255 or part.rstrip(" .") != part:
            _reject("invalid bundle member name")
        if any(ch in HOSTILE_CHARS or ord(ch) < 32 for ch in part):
            _reject("invalid bundle member name")
        if part.split(".", 1)[0].upper() in RESERVED:
            _reject("invalid bundle member name")
    return value


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip("-").lower()


def _safe_join(root: Path, relative: str, *, require_file: bool = True) -> Path:
    clean = _validate_safe_relative(relative)
    candidate = root.joinpath(*clean.split("/"))
    _assert_no_redirect_ancestors(candidate)
    try:
        resolved_root = root.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ReleaseError("bundle member escapes its root") from exc
    if require_file:
        _read_bounded(candidate, 1 << 31)
    return candidate


def _sha256(data_or_path: bytes | Path) -> str:
    h = hashlib.sha256()
    if isinstance(data_or_path, Path):
        with data_or_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
    else:
        h.update(data_or_path)
    return h.hexdigest()


def _safe_hash(value: Any) -> str:
    if not isinstance(value, str) or not SAFE_HASH.fullmatch(value):
        _reject("invalid artifact hash")
    return value


def _safe_commit(value: Any) -> str:
    if not isinstance(value, str) or not SAFE_COMMIT.fullmatch(value):
        _reject("invalid source commit")
    return value


def _load_policy() -> dict[str, Any]:
    path = Path(__file__).with_name("release_0900_policy.json")
    value = _strict_json(_read_bounded(path, MAX_MANIFEST_BYTES), limit=MAX_MANIFEST_BYTES)
    if not isinstance(value, dict):
        _reject("release policy is invalid")
    return value


def _version_key(value: str) -> tuple[Any, ...]:
    if not isinstance(value, str) or not value:
        _reject("invalid package version")
    try:
        from pip._vendor.packaging.version import Version

        parsed = Version(value)
        return (parsed,)
    except Exception:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
            _reject("invalid package version")
        return tuple(int(part) for part in value.split("."))


def _version_equal(left: str, right: str) -> bool:
    try:
        return _version_key(left) == _version_key(right)
    except ReleaseError:
        return False


def _version_lt(left: str, right: str) -> bool:
    try:
        return _version_key(left) < _version_key(right)
    except TypeError:
        return left < right


def _write_fixed_zip(path: Path, files: Mapping[str, bytes], *, timestamp: int = 315532800) -> None:
    """Write sorted, stored, fixed-metadata ZIP bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dt = _datetime.datetime.fromtimestamp(max(315532800, min(int(timestamp), 4354819198)), _datetime.timezone.utc)
    date_time = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second - (dt.second % 2))
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name in sorted(files, key=lambda item: item.encode("utf-8")):
            _validate_safe_relative(name)
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])


def _zip_members(data: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                _reject("archive contains duplicate members")
            result: dict[str, bytes] = {}
            for info in archive.infolist():
                if info.is_dir():
                    continue
                _validate_safe_relative(info.filename)
                result[info.filename] = archive.read(info)
            return result
    except ReleaseError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ReleaseError("invalid ZIP artifact") from exc


def _normalize_zip_bytes(data: bytes, *, timestamp: int) -> bytes:
    with tempfile.TemporaryDirectory(prefix="stm32tk-zip-") as temp:
        path = Path(temp) / "fixed.zip"
        _write_fixed_zip(path, _zip_members(data), timestamp=timestamp)
        return path.read_bytes()


def _process(argv: Sequence[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None, timeout: int = 300, text: bool = False) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(list(argv), cwd=str(cwd) if cwd else None, env=dict(env) if env else None,
                              shell=False, check=False, capture_output=True, timeout=timeout, text=text)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError("required build process failed") from exc


def _git_output(repo: Path, args: Sequence[str], *, binary: bool = False) -> bytes | str:
    result = _process(["git", *args], cwd=repo, timeout=120, text=not binary)
    if result.returncode != 0:
        raise ReleaseError("Git source precondition failed")
    return result.stdout if binary else str(result.stdout).strip()


def _git_epoch(repo: Path, code_head: str) -> int:
    value = _git_output(repo, ["show", "-s", "--format=%ct", code_head])
    try:
        return int(str(value))
    except ValueError as exc:
        raise ReleaseError("Git source precondition failed") from exc


def _assert_source(repo: Path, code_head: str) -> int:
    if not SAFE_COMMIT.fullmatch(code_head):
        _reject("invalid source commit")
    _assert_no_redirect_ancestors(repo)
    if not repo.is_dir():
        _reject("repository root is unavailable")
    head = str(_git_output(repo, ["rev-parse", "HEAD"]))
    if head != code_head:
        _reject("source CodeHead does not match HEAD")
    tracked = _git_output(repo, ["status", "--porcelain", "--untracked-files=no"])
    if tracked:
        _reject("tracked source tree is dirty")
    # Ensure the object exists and is a commit.
    _git_output(repo, ["cat-file", "-e", f"{code_head}^{{commit}}"])
    remote_result = _process(["git", "config", "--get", "remote.origin.url"], cwd=repo, timeout=30, text=True)
    remote = str(remote_result.stdout).strip() if remote_result.returncode == 0 else REPOSITORY
    if remote and "github.com/xiaoyaolinghao/stm32-toolkit" not in remote.lower():
        _reject("source repository identity is not official")
    return _git_epoch(repo, code_head)


def _metadata_from_zip(members: Mapping[str, bytes]) -> tuple[dict[str, str], list[str]]:
    metadata_name = next((name for name in members if name.endswith(".dist-info/METADATA")), None)
    if not metadata_name:
        _reject("wheel metadata is missing")
    fields: dict[str, str] = {}
    requires: list[str] = []
    current: str | None = None
    for raw in members[metadata_name].decode("utf-8", "strict").splitlines():
        if raw.startswith((" ", "\t")) and current:
            fields[current] += raw.strip()
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        current = key
        if key == "requires-dist":
            requires.append(value)
        elif key not in fields:
            fields[key] = value
    return fields, requires


def _record_valid(members: Mapping[str, bytes]) -> None:
    record_name = next((name for name in members if name.endswith(".dist-info/RECORD")), None)
    if not record_name:
        _reject("wheel RECORD is missing")
    try:
        rows = list(csv.reader(members[record_name].decode("utf-8", "strict").splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ReleaseError("wheel RECORD is invalid") from exc
    listed: set[str] = set()
    for row in rows:
        if len(row) != 3 or row[0] in listed:
            _reject("wheel RECORD is invalid")
        listed.add(row[0])
        if row[0] == record_name:
            if row[1] or row[2]:
                _reject("wheel RECORD is invalid")
            continue
        if row[0] not in members or not row[1].startswith("sha256="):
            _reject("wheel RECORD is invalid")
        try:
            digest = base64.urlsafe_b64decode(row[1][7:] + "===")
        except Exception as exc:
            raise ReleaseError("wheel RECORD is invalid") from exc
        if hashlib.sha256(members[row[0]]).digest() != digest or str(len(members[row[0]])) != row[2]:
            _reject("wheel RECORD is invalid")
    if set(members) != listed:
        _reject("wheel RECORD is incomplete")


class WheelInfo:
    __slots__ = ("path", "filename", "name", "normalized", "version", "tags", "metadata", "requires", "members", "license")

    def __init__(self, path: Path, filename: str, name: str, normalized: str, version: str,
                 tags: tuple[str, str, str], metadata: Mapping[str, str], requires: tuple[str, ...],
                 members: Mapping[str, bytes], license: str) -> None:
        self.path = path
        self.filename = filename
        self.name = name
        self.normalized = normalized
        self.version = version
        self.tags = tags
        self.metadata = metadata
        self.requires = requires
        self.members = members
        self.license = license


def _license_value(info_name: str, metadata: Mapping[str, str], policy: Mapping[str, Any]) -> str:
    overrides = policy.get("licenseOverrides", {})
    if info_name in overrides:
        value = overrides[info_name]
    else:
        value = metadata.get("license-expression") or metadata.get("license")
    if not isinstance(value, str) or not value.strip():
        _reject("selected wheel license is not declared")
    # Keep expressions closed: every identifier must be one of the policy's
    # accepted SPDX IDs.  Operators and parentheses are harmless syntax.
    allowed = set(policy.get("allowedLicenses", []))
    identifiers = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", value)
    if not identifiers or any(token not in allowed for token in identifiers if token.upper() not in {"AND", "OR", "WITH"}):
        _reject("selected wheel license is outside policy")
    return value


def _read_wheel(path: Path, policy: Mapping[str, Any], *, strict: bool = True) -> WheelInfo:
    name_match = WHEEL_NAME.fullmatch(path.name)
    if not name_match or path.suffix.lower() != ".whl":
        _reject("wheel filename is invalid")
    filename_dist = name_match.group("name")
    version = name_match.group("version")
    py_tag, abi_tag, platform_tag = name_match.group("py"), name_match.group("abi"), name_match.group("plat")
    py_lower = py_tag.lower()
    py_compatible = "py3" in py_lower.split(".") or py_lower == "cp312" or (py_lower.startswith("cp") and py_lower[2:].isdigit() and int(py_lower[2:]) <= 312)
    if strict and (not py_compatible or abi_tag.lower() not in {"none", "abi3", "cp312"} or platform_tag.lower() not in {"any", "win_amd64"}):
        _reject("wheel is not compatible with Windows CPython 3.12")
    try:
        with zipfile.ZipFile(path) as archive:
            members = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError("wheel archive is invalid") from exc
    if len(members) == 0 or len(members) != len(set(members)):
        _reject("wheel archive is invalid")
    for member in members:
        _validate_safe_relative(member)
    metadata, requires = _metadata_from_zip(members)
    if strict:
        _record_valid(members)
    name = metadata.get("name")
    metadata_version = metadata.get("version")
    if not name or not metadata_version or _normalized_name(name) != _normalized_name(filename_dist) or not _version_equal(metadata_version, version):
        _reject("wheel metadata does not match its filename")
    _version_key(metadata_version)
    license_value = _license_value(_normalized_name(name), metadata, policy) if strict else ""
    return WheelInfo(path, path.name, name, _normalized_name(name), metadata_version,
                     (py_tag, abi_tag, platform_tag), metadata, tuple(requires), members, license_value)


def _marker_applies(requirement: str) -> tuple[str, bool]:
    # Prefer pip's packaging parser, which is already part of the CPython pip
    # installation.  The fallback accepts the simple unmarked/name-only form.
    try:
        from pip._vendor.packaging.requirements import Requirement

        parsed = Requirement(requirement)
        env = {
            "implementation_name": "cpython", "implementation_version": "3.12.10",
            "os_name": "nt", "platform_machine": "AMD64", "platform_release": "",
            "platform_system": "Windows", "platform_version": "", "python_full_version": "3.12.10",
            "python_version": "3.12", "sys_platform": "win32", "extra": "probe",
        }
        return parsed.name, parsed.marker.evaluate(env) if parsed.marker else True
    except Exception:
        match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
        if not match:
            _reject("wheel requirement is invalid")
        return match.group(1), True


def _select_wheels(wheelhouse: Path, policy: Mapping[str, Any]) -> tuple[dict[str, WheelInfo], set[str]]:
    _assert_no_redirect_ancestors(wheelhouse)
    if not wheelhouse.is_dir():
        _reject("wheelhouse is unavailable")
    available: dict[str, list[WheelInfo]] = {}
    for path in sorted(wheelhouse.iterdir(), key=lambda item: item.name.encode("utf-8")):
        if path.is_dir():
            continue
        if path.suffix.lower() == ".whl":
            info = _read_wheel(path, policy, strict=False)
            available.setdefault(info.normalized, []).append(info)
        elif path.name.lower().endswith((".tar.gz", ".zip")):
            # Sdists are never selected.  They are allowed to sit beside an
            # unrelated wheel, but a selected name is rejected below.
            continue
        else:
            _reject("wheelhouse contains an unsupported artifact")

    direct_pin_names = {_normalized_name(name) for name in policy.get("directPins", {}) if _normalized_name(name) not in {"setuptools", "wheel", "stm32-toolkit", "stm32-monitor"}}
    selected_names = set(direct_pin_names)
    # Resolve a closed graph from product and direct pins without invoking a
    # resolver.  Requirement markers are evaluated only for this platform.
    pending = list(selected_names)
    while pending:
        normalized = pending.pop()
        candidates = available.get(normalized, [])
        if not candidates:
            _reject("closed wheelhouse is missing a required distribution")
        compatible = [item for item in candidates if ("py3" in item.tags[0].lower().split(".") or item.tags[0].lower() == "cp312" or (item.tags[0].lower().startswith("cp") and item.tags[0][2:].isdigit() and int(item.tags[0][2:]) <= 312)) and item.tags[2].lower() in {"any", "win_amd64"}]
        if len(compatible) != 1:
            _reject("closed wheelhouse has an ambiguous distribution")
        info = _read_wheel(compatible[0].path, policy, strict=True)
        for requirement in info.requires:
            dep_name, applies = _marker_applies(requirement)
            if not applies:
                continue
            dep_normalized = _normalized_name(dep_name)
            if dep_normalized not in selected_names:
                selected_names.add(dep_normalized)
                pending.append(dep_normalized)

    selected: dict[str, WheelInfo] = {}
    direct: set[str] = set()
    for normalized in sorted(selected_names):
        candidates = available.get(normalized, [])
        if len(candidates) != 1:
            _reject("closed wheelhouse has duplicate normalized distributions")
        selected[normalized] = candidates[0]
        if normalized in direct_pin_names:
            direct.add(normalized)
    # Exact direct versions are checked after graph closure.
    for raw_name, required_version in policy.get("directPins", {}).items():
        normalized = _normalized_name(raw_name)
        if normalized in {"setuptools", "wheel"}:
            continue
        if normalized in selected and not _version_equal(selected[normalized].version, required_version):
            _reject("direct dependency pin is not satisfied")
    return selected, direct


def _extract_zip_to(data: bytes, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in _zip_members(data).items():
        target = root.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _build_wheel(repo_root: Path, package_path: str, wheelhouse: Path, output: Path, epoch: int) -> Path:
    with tempfile.TemporaryDirectory(prefix="stm32tk-build-") as temp:
        work = Path(temp)
        venv_path = work / "venv"
        create = _process([sys.executable, "-m", "venv", str(venv_path)], timeout=180, text=True)
        if create.returncode != 0:
            raise ReleaseError("product build environment could not be created")
        python = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        backend = ["setuptools==84.0.0", "wheel==0.48.0"]
        install = _process([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", "--only-binary=:all:", "--find-links", str(wheelhouse), *backend], timeout=300, text=True)
        if install.returncode != 0:
            raise ReleaseError("closed build backend is unavailable")
        output.mkdir(parents=True, exist_ok=True)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1", "SOURCE_DATE_EPOCH": str(epoch)}
        result = _process([str(python), "-I", "-m", "pip", "wheel", "--disable-pip-version-check", "--no-index", "--no-deps", "--no-build-isolation", "--wheel-dir", str(output), str(repo_root / package_path)], env=env, timeout=600, text=True)
        if result.returncode != 0:
            raise ReleaseError("product wheel build failed")
        wheels = sorted(output.glob("*.whl"), key=lambda item: item.name.encode("utf-8"))
        if len(wheels) != 1:
            raise ReleaseError("product wheel build produced an unexpected result")
        fixed = output / wheels[0].name
        fixed_bytes = _normalize_zip_bytes(fixed.read_bytes(), timestamp=epoch)
        fixed.write_bytes(fixed_bytes)
        return fixed


def _git_archive(repo: Path, code_head: str, epoch: int) -> bytes:
    result = _process(["git", "archive", "--format=zip", "--prefix=stm32-toolkit-0.9.0/", code_head], cwd=repo, timeout=180, text=False)
    if result.returncode != 0:
        raise ReleaseError("source archive could not be created")
    return _normalize_zip_bytes(result.stdout, timestamp=epoch)


def _monitor_asset_inventory(monitor_wheel: bytes) -> dict[str, Any]:
    members = _zip_members(monitor_wheel)
    manifest_name = next((name for name in members if name.endswith("ui_dist/.vite/manifest.json")), None)
    index_name = next((name for name in members if name.endswith("ui_dist/index.html")), None)
    if not manifest_name or not index_name:
        _reject("Monitor asset manifest is missing")
    manifest_bytes = members[manifest_name]
    manifest = _strict_json(manifest_bytes, limit=MAX_MANIFEST_BYTES)
    if not isinstance(manifest, dict):
        _reject("Monitor asset manifest is invalid")
    required = {index_name, manifest_name}
    for record in manifest.values():
        if not isinstance(record, dict):
            _reject("Monitor asset manifest is invalid")
        for field_name in ("file", "css", "assets"):
            value = record.get(field_name)
            values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
            for item in values:
                if not isinstance(item, str):
                    _reject("Monitor asset manifest is invalid")
                clean = _validate_safe_relative(item)
                candidate = next((name for name in members if name.endswith("ui_dist/" + clean)), None)
                if not candidate:
                    _reject("Monitor asset is missing")
                required.add(candidate)
    files = []
    for member in sorted(required, key=lambda item: item.encode("utf-8")):
        rel = member.split("ui_dist/", 1)[-1]
        files.append({"path": rel, "size": len(members[member]), "sha256": _sha256(members[member])})
    metadata, _ = _metadata_from_zip(members)
    return {"version": metadata.get("version", VERSION), "manifestSha256": _sha256(manifest_bytes), "files": files}


def _spdx(selected: Mapping[str, WheelInfo], product_wheels: Mapping[str, bytes], code_head: str, epoch: int, repo_root: Path) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    for index, (normalized, info) in enumerate(sorted(selected.items())):
        packages.append({
            "SPDXID": f"SPDXRef-Package-{normalized}",
            "name": info.name,
            "versionInfo": info.version,
            "downloadLocation": info.metadata.get("home-page", "NOASSERTION"),
            "licenseConcluded": info.license,
            "licenseDeclared": info.license,
            "supplier": info.metadata.get("author", "NOASSERTION"),
            "checksums": [{"algorithm": "SHA256", "checksumValue": _sha256(info.path)}],
        })
    for name, data in sorted(product_wheels.items()):
        normalized = _normalized_name(name)
        packages.append({
            "SPDXID": f"SPDXRef-Product-{normalized}", "name": name, "versionInfo": VERSION,
            "downloadLocation": REPOSITORY, "licenseConcluded": "MIT", "licenseDeclared": "MIT",
            "supplier": "Organization: STM32 Toolkit Team", "checksums": [{"algorithm": "SHA256", "checksumValue": _sha256(data)}],
        })
    lock = repo_root / "tools" / "stm32-monitor" / "ui" / "package-lock.json"
    if lock.is_file():
        try:
            lock_data = _strict_json(_read_bounded(lock, 16 << 20), limit=16 << 20)
            for path, record in sorted((lock_data.get("packages") or {}).items()):
                if not path or not isinstance(record, dict) or not record.get("version"):
                    continue
                name = path.rsplit("/", 1)[-1] or "stm32-monitor-ui"
                packages.append({"SPDXID": "SPDXRef-NPM-" + re.sub(r"[^A-Za-z0-9.-]", "-", path), "name": name, "versionInfo": record["version"], "downloadLocation": record.get("resolved", "NOASSERTION"), "licenseConcluded": record.get("license", "NOASSERTION"), "licenseDeclared": record.get("license", "NOASSERTION")})
        except ReleaseError:
            raise
    packages.sort(key=lambda item: item["SPDXID"])
    relationships = [{"spdxElementId": "SPDXRef-Document", "relationshipType": "DESCRIBES", "relatedSpdxElement": item["SPDXID"]} for item in packages if item["SPDXID"].startswith("SPDXRef-Product-")]
    return {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
        "name": "stm32-toolkit-0.9.0", "documentNamespace": f"https://github.com/XiaoyaoLinghao/stm32-toolkit/spdx/{code_head}",
        "creationInfo": {"created": _datetime.datetime.fromtimestamp(epoch, _datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "creators": ["Tool: stm32-toolkit-release", f"Commit: {code_head}"]},
        "packages": packages, "relationships": relationships,
    }


def _notices(selected: Mapping[str, WheelInfo]) -> bytes:
    lines = ["# Third-party notices", "", "This file is generated from the closed release wheel manifest.", ""]
    for normalized, info in sorted(selected.items()):
        lines.extend([f"## {info.name} {info.version}", "", f"License: {info.license}", ""])
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _compatibility(selected: Mapping[str, WheelInfo]) -> bytes:
    lines = ["# Compatibility", "", "- Windows x86_64.", "- CPython >=3.12,<3.13 (CPython 3.12 only).", "- STM32 Toolkit, Monitor, plugin, and UI 0.9.0.", "- One generic explicit-root CLI/MCP runtime and the retained Claude thin adapter.", "- Project schemas v2/v3 are readable; v1 requires an explicit upgrade. Runtime state schema 1 is supported.", "", "## Selected runtime wheels", ""]
    lines.extend(f"- {info.name}=={info.version}" for _, info in sorted(selected.items()))
    lines.extend(["", "Hardware and other operating systems are not promised by this candidate.", "Remote publication is intentionally not performed.", ""])
    return "\n".join(lines).encode("utf-8")


def _troubleshooting() -> bytes:
    return ("# Troubleshooting\n\n"
            "- Checksum mismatch: discard the extracted copy and obtain a bundle whose external CHECKSUMS.sha256 verifies.\n"
            "- Source commit mismatch: rebuild from the pinned full CodeHead.\n"
            "- Invalid name or redirect path: restore an ordinary file below the Toolkit root.\n"
            "- Missing CPython 3.12: install the supported interpreter; no system-Python fallback is used.\n"
            "- Missing or broken runtime: use Check, then authorize Bootstrap or Repair.\n"
            "- Unsupported state, downgrade refusal, or source conflict: preserve the state and use the matching pinned bundle.\n"
            "- pip-check, Monitor asset, license, SBOM, or doctor mismatch: keep the evidence and obtain a matching candidate.\n").encode("utf-8")


def _manifest_shape(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        _reject("release manifest is invalid")
    expected = {"schema", "productVersion", "requiredPython", "platform", "source", "runtimeStateSchema", "wheels", "artifacts", "publicInventory"}
    if set(manifest) != expected:
        _reject("release manifest has an invalid shape")
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["productVersion"] != VERSION or manifest["requiredPython"] != REQUIRED_PYTHON or manifest["runtimeStateSchema"] != STATE_SCHEMA:
        _reject("release manifest has an invalid identity")
    platform = manifest["platform"]
    if platform != {"os": "windows", "architecture": "x86_64", "python": "cp312"}:
        _reject("release manifest has an invalid platform")
    source = manifest["source"]
    if not isinstance(source, dict) or set(source) != {"repository", "commit", "archive", "sha256"} or source["repository"] != REPOSITORY:
        _reject("release manifest has an invalid source")
    _safe_commit(source["commit"]); _safe_hash(source["sha256"]); _validate_safe_relative(source["archive"])
    if not isinstance(manifest["wheels"], list) or not isinstance(manifest["artifacts"], list):
        _reject("release manifest has an invalid shape")
    inventory = manifest["publicInventory"]
    if inventory != {"mcpTools": 48, "skills": 8}:
        _reject("release manifest has an invalid public inventory")


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = _strict_json(_read_bounded(path, MAX_MANIFEST_BYTES), limit=MAX_MANIFEST_BYTES)
    _manifest_shape(manifest)
    names: set[str] = set()
    distributions: set[str] = set()
    for wheel in manifest["wheels"]:
        if not isinstance(wheel, dict) or set(wheel) != {"name", "version", "file", "sha256", "size", "direct", "license"}:
            _reject("release manifest wheel entry is invalid")
        if not isinstance(wheel["name"], str) or _normalized_name(wheel["name"]) in distributions:
            _reject("release manifest contains duplicate distributions")
        distributions.add(_normalized_name(wheel["name"]))
        file_name = _validate_safe_relative(wheel["file"])
        folded = unicodedata.normalize("NFC", file_name).casefold()
        if folded in names:
            _reject("release manifest contains duplicate files")
        names.add(folded)
        _safe_hash(wheel["sha256"])
        if type(wheel["size"]) is not int or wheel["size"] < 1 or type(wheel["direct"]) is not bool or not isinstance(wheel["version"], str) or not isinstance(wheel["license"], str):
            _reject("release manifest wheel entry is invalid")
    kinds: set[str] = set()
    for artifact in manifest["artifacts"]:
        if not isinstance(artifact, dict) or set(artifact) != {"kind", "file", "sha256", "size"} or artifact["kind"] not in {"monitor-assets", "sbom", "notices", "license", "compatibility", "troubleshooting"}:
            _reject("release manifest artifact entry is invalid")
        file_name = _validate_safe_relative(artifact["file"])
        folded = unicodedata.normalize("NFC", file_name).casefold()
        if folded in names:
            _reject("release manifest contains duplicate files")
        names.add(folded); kinds.add(artifact["kind"]); _safe_hash(artifact["sha256"])
        if type(artifact["size"]) is not int or artifact["size"] < 1:
            _reject("release manifest artifact entry is invalid")
    return manifest


def _verify_bundle(root: Path) -> dict[str, Any]:
    _assert_no_redirect_ancestors(root)
    if not root.is_dir():
        _reject("Toolkit root is unavailable")
    manifest_path = root / "release" / "release-manifest.json"
    if not manifest_path.is_file():
        _reject("release manifest is missing")
    manifest = _load_manifest(manifest_path)
    checks: list[dict[str, Any]] = []
    for entry in [*manifest["wheels"], *manifest["artifacts"]]:
        path = _safe_join(root, entry["file"])
        data = _read_bounded(path, 1 << 31)
        if len(data) != entry["size"] or _sha256(data) != entry["sha256"]:
            _reject("bundle integrity verification failed")
        checks.append({"file": PurePosixPath(entry["file"]).name, "size": len(data)})
    source = manifest["source"]
    source_path: Path | None = None
    for candidate in (root / source["archive"], root / "release" / source["archive"]):
        if candidate.is_file():
            source_path = candidate
            break
    if source_path is None:
        _reject("source archive is missing")
    source_data = _read_bounded(source_path, 1 << 31)
    if _sha256(source_data) != source["sha256"]:
        _reject("source archive integrity verification failed")
    return {
        "status": "ok",
        "schema": MANIFEST_SCHEMA,
        "productVersion": VERSION,
        "wheels": [entry["file"] for entry in manifest["wheels"]],
        "files": sorted(checks, key=lambda item: item["file"].encode("utf-8")),
    }


def _verify_runtime_state(state_path: Path, manifest_path: Path) -> tuple[str, dict[str, Any]]:
    manifest = _load_manifest(manifest_path)
    candidate_hash = _sha256(manifest_path)
    if not state_path.exists():
        return "missing", {"status": "missing", "candidateVersion": VERSION}
    try:
        state = _strict_json(_read_bounded(state_path, MAX_STATE_BYTES), limit=MAX_STATE_BYTES)
    except ReleaseError:
        return "invalid", {"status": "invalid"}
    if not isinstance(state, dict):
        return "invalid", {"status": "invalid"}
    expected = {"schema", "activeVersion", "highestInstalledVersion", "releaseManifestSha256", "sourceCommit", "installGeneration"}
    if set(state) != expected:
        return "invalid", {"status": "invalid"}
    if state["schema"] != STATE_SCHEMA or not all(isinstance(state[key], str) for key in ("activeVersion", "highestInstalledVersion", "releaseManifestSha256", "sourceCommit")) or type(state["installGeneration"]) is not int or state["installGeneration"] < 1:
        return "unsupported" if state.get("schema") != STATE_SCHEMA else "invalid", {"status": "unsupported" if state.get("schema") != STATE_SCHEMA else "invalid"}
    try:
        _safe_hash(state["releaseManifestSha256"]); _safe_commit(state["sourceCommit"]); _version_key(state["activeVersion"]); _version_key(state["highestInstalledVersion"])
    except ReleaseError:
        return "invalid", {"status": "invalid"}
    if _version_lt(VERSION, state["highestInstalledVersion"]):
        return "downgrade-refused", {"status": "downgrade-refused", "highestInstalledVersion": state["highestInstalledVersion"]}
    if _version_equal(VERSION, state["activeVersion"]) and (state["releaseManifestSha256"] != candidate_hash or state["sourceCommit"] != manifest["source"]["commit"]):
        return "source-conflict", {"status": "source-conflict"}
    if state["releaseManifestSha256"] == candidate_hash and state["sourceCommit"] == manifest["source"]["commit"]:
        return "matching", {"status": "matching", "activeVersion": state["activeVersion"], "installGeneration": state["installGeneration"]}
    return "repairable", {"status": "repairable", "activeVersion": state["activeVersion"], "installGeneration": state["installGeneration"]}


def _build_manifest(code_head: str, source_archive: bytes, product_wheels: Mapping[str, bytes], selected: Mapping[str, WheelInfo], artifacts: Mapping[str, bytes], asset_inventory: dict[str, Any]) -> dict[str, Any]:
    wheels = []
    for normalized, info in sorted(selected.items()):
        file_name = f"release/wheels/{info.filename}"
        data = product_wheels.get(normalized, info.path.read_bytes())
        wheels.append({"name": info.name, "version": info.version, "file": file_name, "sha256": _sha256(data), "size": len(data), "direct": normalized in {"stm32-toolkit", "stm32-monitor", "jsonschema", "mcp", "pyelftools", "jinja2", "aiohttp", "pyocd", "pyserial"}, "license": info.license})
    artifact_entries = []
    for kind, (file_name, data) in sorted(artifacts.items()):
        artifact_entries.append({"kind": kind, "file": f"release/{file_name}", "sha256": _sha256(data), "size": len(data)})
    return {"schema": MANIFEST_SCHEMA, "productVersion": VERSION, "requiredPython": REQUIRED_PYTHON, "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"}, "source": {"repository": REPOSITORY, "commit": code_head, "archive": f"stm32-toolkit-{VERSION}-source.zip", "sha256": _sha256(source_archive)}, "runtimeStateSchema": STATE_SCHEMA, "wheels": wheels, "artifacts": artifact_entries, "publicInventory": {"mcpTools": 48, "skills": 8}}


def _build(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root)
    wheelhouse = Path(args.wheelhouse)
    output = Path(args.output_root)
    for path in (repo, wheelhouse):
        if not path.is_absolute():
            _reject("all roots must be absolute")
        _assert_no_redirect_ancestors(path)
    if not output.is_absolute():
        _reject("all roots must be absolute")
    if output.exists():
        _reject("output root must be new")
    try:
        output.resolve().relative_to(repo.resolve())
        _reject("output root overlaps the repository")
    except ValueError:
        pass
    try:
        output.resolve().relative_to(wheelhouse.resolve())
        _reject("output root overlaps the wheelhouse")
    except ValueError:
        pass
    policy = _load_policy()
    epoch = _assert_source(repo, args.code_head)
    selected, direct = _select_wheels(wheelhouse, policy)
    with tempfile.TemporaryDirectory(prefix="stm32tk-release-") as temp:
        temp_root = Path(temp)
        source_archive = _git_archive(repo, args.code_head, epoch)
        product_wheels: dict[str, bytes] = {}
        for package_path, normalized in (("tools/stm32-toolkit", "stm32-toolkit"), ("tools/stm32-monitor", "stm32-monitor")):
            built_dir = temp_root / normalized
            wheel = _build_wheel(repo, package_path, wheelhouse, built_dir, epoch)
            product_wheels[normalized] = wheel.read_bytes()
            selected[normalized] = _read_wheel(wheel, policy)
        monitor_assets = _monitor_asset_inventory(product_wheels["stm32-monitor"])
        licenses_zip = io.BytesIO()
        with tempfile.TemporaryDirectory(prefix="stm32tk-licenses-") as license_temp:
            license_root = Path(license_temp) / "licenses"
            license_root.mkdir()
            license_text = Path(repo / "LICENSE").read_bytes()
            (license_root / "MIT.txt").write_bytes(license_text)
            _write_fixed_zip(Path(license_temp) / "licenses.zip", {"licenses/MIT.txt": license_text}, timestamp=epoch)
            licenses_zip.write_bytes(Path(license_temp, "licenses.zip").read_bytes())
        licenses_data = licenses_zip.getvalue()
        sbom = _canonical_json(_spdx(selected, product_wheels, args.code_head, epoch, repo))
        notices = _notices(selected)
        compatibility = _compatibility(selected)
        troubleshooting = _troubleshooting()
        artifacts = {
            "monitor-assets": ("monitor-assets.json", _canonical_json(monitor_assets)),
            "sbom": ("sbom.spdx.json", sbom),
            "notices": ("THIRD-PARTY-NOTICES.md", notices),
            "license": ("LICENSE", Path(repo / "LICENSE").read_bytes()),
            "compatibility": ("compatibility.md", compatibility),
            "troubleshooting": ("troubleshooting.md", troubleshooting),
        }
        manifest = _build_manifest(args.code_head, source_archive, product_wheels, selected, artifacts, monitor_assets)
        manifest_data = _canonical_json(manifest)
        # Build a release tree used by verify-bundle and by the extracted
        # Windows candidate.  Product wheels are copied into the closed set.
        release_files: dict[str, bytes] = {"release/release-manifest.json": manifest_data}
        for normalized, info in sorted(selected.items()):
            release_files[f"release/wheels/{info.filename}"] = product_wheels.get(normalized, info.path.read_bytes())
        for _, (name, data) in sorted(artifacts.items()):
            release_files[f"release/{name}"] = data
        release_files["release/licenses.zip"] = licenses_data
        source_files = _zip_members(source_archive)
        bundle_files = dict(source_files)
        bundle_files.update(release_files)
        bundle_data = io.BytesIO()
        with tempfile.TemporaryDirectory(prefix="stm32tk-bundle-") as bundle_temp:
            bundle_path = Path(bundle_temp) / "bundle.zip"
            _write_fixed_zip(bundle_path, bundle_files, timestamp=epoch)
            bundle_data = io.BytesIO(bundle_path.read_bytes())
        bundle_bytes = bundle_data.getvalue()
        top_files: dict[str, bytes] = {
            f"stm32_toolkit-{VERSION}-py3-none-any.whl": product_wheels["stm32-toolkit"],
            f"stm32_monitor-{VERSION}-py3-none-any.whl": product_wheels["stm32-monitor"],
            f"stm32-toolkit-{VERSION}-source.zip": source_archive,
            f"stm32-toolkit-{VERSION}-windows-x86_64.zip": bundle_bytes,
            "release-manifest.json": manifest_data,
            "monitor-assets.json": artifacts["monitor-assets"][1],
            "sbom.spdx.json": sbom,
            "THIRD-PARTY-NOTICES.md": notices,
            "LICENSE": artifacts["license"][1],
            "licenses.zip": licenses_data,
            "compatibility.md": compatibility,
            "troubleshooting.md": troubleshooting,
        }
        # Verify the internal release tree before activating the candidate.
        verify_root = temp_root / "verify"
        verify_root.mkdir()
        for name, data in release_files.items():
            target = verify_root / name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        source_target = verify_root / manifest["source"]["archive"]
        source_target.write_bytes(source_archive)
        _verify_bundle(verify_root)
        staging = output.with_name(output.name + ".staging-" + next(tempfile._get_candidate_names()))
        _assert_no_redirect_ancestors(staging.parent)
        staging.mkdir(parents=True)
        try:
            for name, data in top_files.items():
                (staging / name).write_bytes(data)
            checksums = "".join(f"{_sha256(staging / name)}  {name}\n" for name in sorted(top_files, key=lambda item: item.encode("utf-8")))
            (staging / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8", newline="\n")
            # An output is active only after all files are complete.
            os.replace(staging, output)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"status": "ok", "productVersion": VERSION, "codeHead": args.code_head, "files": sorted(top_files)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build_0900_artifacts.py", allow_abbrev=False, exit_on_error=False)
    sub = parser.add_subparsers(dest="mode", required=True)
    build = sub.add_parser("build", allow_abbrev=False)
    build.add_argument("--repo-root", required=True); build.add_argument("--code-head", required=True)
    build.add_argument("--wheelhouse", required=True); build.add_argument("--output-root", required=True)
    verify = sub.add_parser("verify-bundle", allow_abbrev=False)
    verify.add_argument("--toolkit-root", required=True); verify.add_argument("--json", action="store_true")
    state = sub.add_parser("verify-runtime-state", allow_abbrev=False)
    state.add_argument("--state", required=True); state.add_argument("--candidate-manifest", required=True); state.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except (argparse.ArgumentError, SystemExit) as exc:
        if getattr(exc, "code", 2) == 0:
            return 0
        print("release utility: invalid command line", file=sys.stderr)
        return 2
    try:
        if args.mode == "build":
            result = _build(args)
        elif args.mode == "verify-bundle":
            result = _verify_bundle(Path(args.toolkit_root))
        else:
            status, result = _verify_runtime_state(Path(args.state), Path(args.candidate_manifest))
            if status in {"downgrade-refused", "source-conflict", "unsupported", "invalid"}:
                if args.json:
                    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                else:
                    print("release utility: runtime state refused", file=sys.stderr)
                return 2
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except ReleaseError as exc:
        print(f"release utility: {exc.public}", file=sys.stderr)
        return 2
    except Exception:
        print("release utility: unexpected environment or build failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
