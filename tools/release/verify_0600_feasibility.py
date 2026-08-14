"""Fail-closed Windows-only software/support-fixture feasibility verifier.

This verifier deliberately has no probe, UART, flash, target-memory, or
semihosting control path.  It verifies only local Windows software identities,
an immutable support fixture, a declared (not executed) transport contract,
and one blank-page launch of the support-owned managed Chromium binary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence


PROFILE_SCHEMA = "stm32tk-0600-feasibility-profile/1"
MANIFEST_SCHEMA = "stm32tk-0600-support-manifest/1"
RESULT_SCHEMA = "stm32tk-0600-feasibility-result/1"
TOOL_RECORD_SCHEMA = "stm32tk-0600-tool-record/1"
REQUIRED_TOOLS = (
    "python310",
    "python312",
    "powershell",
    "cmake",
    "ctest",
    "pyocd",
    "pyserial",
    "node",
    "npm",
    "wheelhouse",
)
PROFILE_KEYS = {
    "schema",
    "windows_owner",
    "host",
    "tools",
    "chromium",
    "firmware_fixture",
    "capabilities",
}
RESULT_KEYS = {
    "schema",
    "owner",
    "profile",
    "support_manifest",
    "run",
    "tools",
    "chromium",
    "firmware_fixture",
    "capabilities",
    "hardware",
    "evidence",
}
FORBIDDEN_EVIDENCE_FIELDS = {
    "evidence_channel",
    "browser_product_flow",
    "package",
    "cross_machine_package",
    "hardware_pass",
    "product_pass",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
VERSION_310 = re.compile(r"^3\.10\.\d+$")
VERSION_312 = re.compile(r"^3\.12\.\d+$")
VERSION_51 = re.compile(r"^5\.1(?:\.\d+){0,2}$")
VERSION_NUMBER = re.compile(r"^\d+(?:\.\d+)+$")


@dataclass(frozen=True)
class VerificationResult:
    code: str
    details: dict[str, object]


def _result(code: str, **details: object) -> VerificationResult:
    return VerificationResult(code=code, details=details)


def _is_mapping(value: object) -> bool:
    return isinstance(value, Mapping)


def _digest(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _relative_file(value: object) -> bool:
    if not _nonempty(value):
        return False
    text = str(value)
    normalized = text.replace("\\", "/")
    if text != normalized or normalized.startswith("/") or ":" in normalized:
        return False
    pieces = normalized.split("/")
    return all(piece not in {"", ".", ".."} for piece in pieces)


def _absolute_windows_path(value: object) -> bool:
    if not _nonempty(value):
        return False
    path = PureWindowsPath(str(value))
    return path.is_absolute() and not any(part in {".", ".."} for part in path.parts)


def _closed(value: object, keys: set[str]) -> bool:
    return _is_mapping(value) and set(value) == keys


def _manifest_entries(manifest: object) -> tuple[VerificationResult | None, dict[str, Mapping[str, object]]]:
    if not _closed(manifest, {"schema", "files"}) or manifest["schema"] != MANIFEST_SCHEMA:
        return _result("FEASIBILITY_MANIFEST_INVALID"), {}
    files = manifest["files"]
    if not isinstance(files, list) or not files:
        return _result("FEASIBILITY_MANIFEST_INVALID"), {}
    entries: dict[str, Mapping[str, object]] = {}
    folded: set[str] = set()
    for item in files:
        if not _closed(item, {"path", "bytes", "sha256"}):
            return _result("FEASIBILITY_MANIFEST_INVALID"), {}
        path = item["path"]
        if (
            not _relative_file(path)
            or not isinstance(item["bytes"], int)
            or isinstance(item["bytes"], bool)
            or item["bytes"] < 0
            or not _digest(item["sha256"])
            or path in entries
            or str(path).casefold() in folded
        ):
            return _result("FEASIBILITY_MANIFEST_INVALID"), {}
        entries[str(path)] = item
        folded.add(str(path).casefold())
    return None, entries


def _profile_manifest_bindings(
    profile: Mapping[str, object], entries: Mapping[str, Mapping[str, object]]
) -> VerificationResult | None:
    tools = profile["tools"]
    chromium = profile["chromium"]
    fixture = profile["firmware_fixture"]
    assert isinstance(tools, Mapping)
    assert isinstance(chromium, Mapping)
    assert isinstance(fixture, Mapping)
    references: list[tuple[object, object | None]] = [
        (chromium["executable"], chromium["executable_sha256"]),
        (chromium["managed_profile"]["seed"], chromium["managed_profile"]["sha256"]),
        (chromium["blank_page"]["path"], chromium["blank_page"]["sha256"]),
        (fixture["path"], fixture["sha256"]),
    ]
    for tool in tools.values():
        assert isinstance(tool, Mapping)
        references.append((tool["record"], None))
    for path, digest in references:
        entry = entries.get(str(path))
        if entry is None or (digest is not None and entry["sha256"] != digest):
            return _result("FEASIBILITY_MANIFEST_BINDING_MISSING", path=path)
    if entries[str(fixture["path"])]["bytes"] != fixture["bytes"]:
        return _result("FEASIBILITY_MANIFEST_BINDING_MISSING", path=fixture["path"])
    return None


def _verify_capabilities(value: object) -> VerificationResult | None:
    if not _closed(value, {"ram", "mailbox", "rtt", "uart", "semihosting"}):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    ram = value["ram"]
    mailbox = value["mailbox"]
    rtt = value["rtt"]
    uart = value["uart"]
    semihosting = value["semihosting"]
    if not isinstance(ram, list) or not ram:
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    ranges: list[tuple[int, int]] = []
    for item in ram:
        if not _closed(item, {"start", "size"}):
            return _result("FEASIBILITY_CAPABILITY_MISSING")
        start, size = item["start"], item["size"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or start < 0
            or size <= 0
        ):
            return _result("FEASIBILITY_CAPABILITY_MISSING")
        ranges.append((start, start + size))
    if not _closed(mailbox, {"address", "size"}):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    address, size = mailbox["address"], mailbox["size"]
    if (
        not isinstance(address, int)
        or isinstance(address, bool)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or not any(start <= address and address + size <= end for start, end in ranges)
    ):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    if not _closed(rtt, {"channel"}) or not isinstance(rtt["channel"], int) or not 0 <= rtt["channel"] <= 15:
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    allowed_baud = {9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600}
    if (
        not _closed(uart, {"port", "baud"})
        or not isinstance(uart["port"], str)
        or re.fullmatch(r"COM[1-9][0-9]*", uart["port"]) is None
        or uart["baud"] not in allowed_baud
    ):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    if not _closed(semihosting, {"declared"}) or semihosting["declared"] is not True:
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    return None


def verify_feasibility(profile: object) -> VerificationResult:
    """Validate the closed, non-hardware Windows support-profile contract."""
    if not _is_mapping(profile):
        return _result("FEASIBILITY_PROFILE_INVALID")
    if FORBIDDEN_EVIDENCE_FIELDS & set(profile):
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    if set(profile) != PROFILE_KEYS or profile.get("schema") != PROFILE_SCHEMA:
        return _result("FEASIBILITY_PROFILE_INVALID")
    if not _nonempty(profile["windows_owner"]):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    host = profile["host"]
    if not _closed(host, {"platform", "architecture"}):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    if host["platform"] != "Windows":
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    if host["architecture"] not in {"AMD64", "ARM64"}:
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    tools = profile["tools"]
    if not _is_mapping(tools) or set(tools) != set(REQUIRED_TOOLS):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    for name in REQUIRED_TOOLS:
        tool = tools[name]
        if not _closed(tool, {"record", "version"}) or not _relative_file(tool["record"]) or not _nonempty(tool["version"]):
            return _result("FEASIBILITY_CAPABILITY_MISSING")
        version = str(tool["version"])
        if (
            (name == "python310" and VERSION_310.fullmatch(version) is None)
            or (name == "python312" and VERSION_312.fullmatch(version) is None)
            or (name == "powershell" and VERSION_51.fullmatch(version) is None)
            or (name not in {"python310", "python312", "powershell", "wheelhouse"} and VERSION_NUMBER.fullmatch(version) is None)
            or (name == "wheelhouse" and not version.startswith("offline-wheelhouse/"))
        ):
            return _result("FEASIBILITY_CAPABILITY_MISSING")
    chromium = profile["chromium"]
    if not _closed(
        chromium,
        {
            "executable",
            "executable_sha256",
            "version",
            "package_root",
            "package_tree_sha256",
            "managed_profile",
            "blank_page",
        },
    ):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    if (
        not _relative_file(chromium["executable"])
        or not _digest(chromium["executable_sha256"])
        or VERSION_NUMBER.fullmatch(str(chromium["version"])) is None
        or not _relative_file(chromium["package_root"])
        or not _digest(chromium["package_tree_sha256"])
        or not _closed(chromium["managed_profile"], {"id", "seed", "sha256"})
        or not _nonempty(chromium["managed_profile"]["id"])
        or not _relative_file(chromium["managed_profile"]["seed"])
        or not _digest(chromium["managed_profile"]["sha256"])
        or not _closed(chromium["blank_page"], {"path", "sha256"})
        or not _relative_file(chromium["blank_page"]["path"])
        or not _digest(chromium["blank_page"]["sha256"])
    ):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    fixture = profile["firmware_fixture"]
    if (
        not _closed(fixture, {"path", "bytes", "sha256"})
        or not _relative_file(fixture["path"])
        or not isinstance(fixture["bytes"], int)
        or isinstance(fixture["bytes"], bool)
        or fixture["bytes"] < 0
        or not _digest(fixture["sha256"])
    ):
        return _result("FEASIBILITY_CAPABILITY_MISSING")
    capability_error = _verify_capabilities(profile["capabilities"])
    if capability_error is not None:
        return capability_error
    return _result("PASS", hardware_status="PENDING")


def expected_chromium_argv(
    chromium: Mapping[str, object], support_root: str, evidence_root: str
) -> list[str]:
    """Return the sole non-product browser invocation accepted by this verifier."""
    blank = str(PureWindowsPath(support_root) / str(chromium["blank_page"]["path"]))
    page_uri = "file:///" + blank.replace("\\", "/")
    profile_dir = str(PureWindowsPath(evidence_root) / "managed-chromium-profile")
    return [
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_dir}",
        "--dump-dom",
        page_uri,
    ]


def verify_result(
    profile: object,
    manifest: object,
    result: object,
    *,
    expected_code_head: str,
    expected_profile_sha256: str,
    expected_manifest_sha256: str,
    support_root: str,
) -> VerificationResult:
    """Validate a result JSON against already-verified local support inputs."""
    profile_result = verify_feasibility(profile)
    if profile_result.code != "PASS":
        return profile_result
    manifest_error, entries = _manifest_entries(manifest)
    if manifest_error is not None:
        return manifest_error
    assert isinstance(profile, Mapping)
    binding_error = _profile_manifest_bindings(profile, entries)
    if binding_error is not None:
        return binding_error
    if not _is_mapping(result):
        return _result("FEASIBILITY_RESULT_INVALID")
    if FORBIDDEN_EVIDENCE_FIELDS & set(result):
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    if set(result) != RESULT_KEYS or result.get("schema") != RESULT_SCHEMA:
        return _result("FEASIBILITY_RESULT_INVALID")
    if result["owner"] != profile["windows_owner"]:
        return _result("FEASIBILITY_RESULT_MISMATCH")
    reference = result["profile"]
    if not _closed(reference, {"path", "sha256"}):
        return _result("FEASIBILITY_RESULT_INVALID")
    if (
        not _relative_file(reference["path"])
        or not _digest(reference["sha256"])
        or reference["sha256"] != expected_profile_sha256
        or entries.get(str(reference["path"]), {}).get("sha256") != reference["sha256"]
    ):
        return _result("FEASIBILITY_PROFILE_MISMATCH")
    support = result["support_manifest"]
    if not _closed(support, {"sha256"}) or support["sha256"] != expected_manifest_sha256:
        return _result("FEASIBILITY_MANIFEST_BINDING_MISSING")
    run = result["run"]
    if not _closed(run, {"kind", "status", "code_head", "machine", "evidence_root"}):
        return _result("FEASIBILITY_RESULT_INVALID")
    if run["kind"] != "windows-software-fixture" or run["status"] != "PASS" or not HEX40.fullmatch(str(run["code_head"])):
        return _result("FEASIBILITY_RESULT_INVALID")
    if run["machine"] != "local":
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    if not _absolute_windows_path(run["evidence_root"]):
        return _result("FEASIBILITY_EVIDENCE_PATH_INVALID")
    tools = result["tools"]
    declared_tools = profile["tools"]
    assert isinstance(declared_tools, Mapping)
    if not _is_mapping(tools) or set(tools) != set(REQUIRED_TOOLS):
        return _result("FEASIBILITY_RESULT_INVALID")
    for name in REQUIRED_TOOLS:
        actual = tools[name]
        declared = declared_tools[name]
        assert isinstance(declared, Mapping)
        if not _closed(actual, {"record", "sha256", "version"}):
            return _result("FEASIBILITY_RESULT_INVALID")
        if (
            actual["record"] != declared["record"]
            or actual["version"] != declared["version"]
            or not _relative_file(actual["record"])
            or not _digest(actual["sha256"])
            or entries.get(str(actual["record"]), {}).get("sha256") != actual["sha256"]
        ):
            return _result("FEASIBILITY_RESULT_MISMATCH")
    chromium = result["chromium"]
    declared_chromium = profile["chromium"]
    assert isinstance(declared_chromium, Mapping)
    chromium_keys = {
        "executable",
        "executable_sha256",
        "version",
        "package_tree_sha256",
        "managed_profile_id",
        "managed_profile_path",
        "blank_page",
        "argv",
        "exit_code",
    }
    if not _is_mapping(chromium):
        return _result("FEASIBILITY_RESULT_INVALID")
    if "platform" in chromium and chromium["platform"] != "Windows":
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    if set(chromium) != chromium_keys:
        return _result("FEASIBILITY_RESULT_INVALID")
    if (
        chromium["executable"] != declared_chromium["executable"]
        or chromium["executable_sha256"] != declared_chromium["executable_sha256"]
        or chromium["version"] != declared_chromium["version"]
        or chromium["package_tree_sha256"] != declared_chromium["package_tree_sha256"]
        or chromium["managed_profile_id"] != declared_chromium["managed_profile"]["id"]
        or chromium["blank_page"] != declared_chromium["blank_page"]["path"]
        or chromium["argv"] != expected_chromium_argv(declared_chromium, support_root, run["evidence_root"])
        or chromium["managed_profile_path"] != str(PureWindowsPath(str(run["evidence_root"])) / "managed-chromium-profile")
        or chromium["exit_code"] != 0
    ):
        return _result("FEASIBILITY_RESULT_MISMATCH")
    if result["firmware_fixture"] != profile["firmware_fixture"] or result["capabilities"] != profile["capabilities"]:
        return _result("FEASIBILITY_RESULT_MISMATCH")
    hardware = result["hardware"]
    if not _closed(hardware, {"status"}):
        return _result("FEASIBILITY_RESULT_INVALID")
    if hardware["status"] != "PENDING":
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE")
    evidence = result["evidence"]
    if not _is_mapping(evidence) or set(evidence) != {"chromium_launch", "chromium_version"}:
        return _result("FEASIBILITY_RESULT_INVALID")
    seen_paths: set[str] = set()
    for item in evidence.values():
        if not _closed(item, {"path", "sha256"}) or not _relative_file(item["path"]) or not _digest(item["sha256"]):
            return _result("FEASIBILITY_EVIDENCE_PATH_INVALID")
        if item["path"] in seen_paths:
            return _result("FEASIBILITY_EVIDENCE_PATH_INVALID")
        seen_paths.add(str(item["path"]))
    if run["code_head"] != expected_code_head:
        return _result("FEASIBILITY_STALE_RESULT")
    return _result("PASS", hardware_status="PENDING")


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _read_json(path: Path) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & 0x400)


def _safe_support_path(root: Path, relative: str) -> Path:
    if not _relative_file(relative):
        raise ValueError("support manifest contains an unsafe path")
    candidate = root.joinpath(*relative.split("/"))
    if candidate.parent != root and any(_is_reparse(parent) for parent in candidate.parents if parent != root):
        raise ValueError("support manifest path traverses a reparse point")
    if not candidate.is_file() or _is_reparse(candidate):
        raise ValueError("support manifest entry is not a regular file")
    return candidate


def _tree_digest(entries: Mapping[str, Mapping[str, object]], package_root: str) -> str:
    prefix = package_root + "/"
    members = [
        {"path": path, "bytes": entry["bytes"], "sha256": entry["sha256"]}
        for path, entry in sorted(entries.items())
        if path.startswith(prefix)
    ]
    if not members:
        raise ValueError("managed Chromium package has no manifest members")
    encoded = json.dumps(members, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_support_root(root: Path, profile_path: Path) -> tuple[Mapping[str, object], Mapping[str, object], dict[str, Mapping[str, object]], str, str]:
    if not root.is_dir() or _is_reparse(root):
        raise ValueError("support root is missing or unsafe")
    manifest_path = root / "support-manifest.json"
    if not manifest_path.is_file() or _is_reparse(manifest_path):
        raise ValueError("support manifest is missing or unsafe")
    manifest = _read_json(manifest_path)
    manifest_error, entries = _manifest_entries(manifest)
    if manifest_error is not None:
        raise ValueError(manifest_error.code)
    actual_files: set[str] = set()
    for current, directories, names in os.walk(root):
        current_path = Path(current)
        if _is_reparse(current_path):
            raise ValueError("support root contains a reparse directory")
        for directory in directories:
            if _is_reparse(current_path / directory):
                raise ValueError("support root contains a reparse directory")
        for name in names:
            file_path = current_path / name
            if _is_reparse(file_path):
                raise ValueError("support root contains a reparse file")
            relative = file_path.relative_to(root).as_posix()
            if relative != "support-manifest.json":
                actual_files.add(relative)
    if actual_files != set(entries):
        raise ValueError("support manifest does not exactly describe the support root")
    for relative, entry in entries.items():
        path = _safe_support_path(root, relative)
        size, digest = _sha256_file(path)
        if size != entry["bytes"] or digest != entry["sha256"]:
            raise ValueError(f"support manifest digest mismatch: {relative}")
    profile_relative = profile_path.relative_to(root).as_posix()
    if profile_relative not in entries:
        raise ValueError("profile is not immutable support input")
    profile = _read_json(profile_path)
    profile_result = verify_feasibility(profile)
    if profile_result.code != "PASS":
        raise ValueError(profile_result.code)
    assert isinstance(profile, Mapping)
    binding_error = _profile_manifest_bindings(profile, entries)
    if binding_error is not None:
        raise ValueError(binding_error.code)
    chromium = profile["chromium"]
    assert isinstance(chromium, Mapping)
    if _tree_digest(entries, str(chromium["package_root"])) != chromium["package_tree_sha256"]:
        raise ValueError("managed Chromium package-tree digest mismatch")
    _, profile_digest = _sha256_file(profile_path)
    _, manifest_digest = _sha256_file(manifest_path)
    return profile, manifest, entries, profile_digest, manifest_digest


def _tool_record(root: Path, profile_tool: Mapping[str, object], name: str) -> Mapping[str, object]:
    record_path = _safe_support_path(root, str(profile_tool["record"]))
    record = _read_json(record_path)
    if not _is_mapping(record) or record.get("schema") != TOOL_RECORD_SCHEMA or record.get("name") != name or record.get("version") != profile_tool["version"]:
        raise ValueError(f"invalid tool record: {name}")
    if name == "wheelhouse":
        if set(record) != {"schema", "name", "version", "path"} or not _relative_file(record.get("path")):
            raise ValueError("invalid wheelhouse record")
        directory = root.joinpath(*str(record["path"]).split("/"))
        if not directory.is_dir() or _is_reparse(directory) or not any(directory.iterdir()):
            raise ValueError("wheelhouse is missing or empty")
    elif name in {"pyocd", "pyserial"}:
        if set(record) != {"schema", "name", "version", "python"} or not _absolute_windows_path(record.get("python")):
            raise ValueError(f"invalid Python package tool record: {name}")
    elif set(record) != {"schema", "name", "version", "executable"} or not _absolute_windows_path(record.get("executable")):
        raise ValueError(f"invalid executable tool record: {name}")
    return record


def _run_tool_version(name: str, record: Mapping[str, object]) -> str:
    if name in {"python310", "python312", "cmake", "ctest", "node", "npm"}:
        executable = str(record["executable"])
        argv = [executable, "--version"]
    elif name == "powershell":
        executable = str(record["executable"])
        argv = [executable, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"]
    elif name == "pyocd":
        argv = [str(record["python"]), "-c", "import pyocd; print(pyocd.__version__)"]
    elif name == "pyserial":
        argv = [str(record["python"]), "-c", "import serial; print(serial.__version__)"]
    else:
        raise ValueError(f"no executable version check for {name}")
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise ValueError(f"tool version command failed: {name}")
    text = (completed.stdout or completed.stderr).strip()
    if name in {"python310", "python312"}:
        text = text.removeprefix("Python ")
    elif name == "cmake":
        text = text.splitlines()[0].removeprefix("cmake version ")
    elif name == "ctest":
        text = text.splitlines()[0].removeprefix("ctest version ")
    elif name == "node":
        text = text.removeprefix("v")
    return text


def _write_json(path: Path, value: object) -> bytes:
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(data)
    return data


def _run(args: argparse.Namespace) -> VerificationResult:
    if os.name != "nt":
        return _result("FEASIBILITY_FORBIDDEN_EVIDENCE", reason="Windows host required")
    repo = Path(args.repo).resolve(strict=True)
    support = Path(args.support).resolve(strict=True)
    profile_path = Path(args.profile).resolve(strict=True)
    evidence = Path(args.evidence).resolve(strict=False)
    if not profile_path.is_relative_to(support):
        return _result("FEASIBILITY_PROFILE_MISMATCH")
    if evidence.exists():
        return _result("FEASIBILITY_EVIDENCE_PATH_INVALID", reason="evidence root must be new")
    if not evidence.parent.is_dir():
        return _result("FEASIBILITY_EVIDENCE_PATH_INVALID", reason="evidence parent is missing")
    try:
        profile, manifest, entries, profile_digest, manifest_digest = _verify_support_root(support, profile_path)
        host = profile["host"]
        assert isinstance(host, Mapping)
        actual_architecture = platform.machine().upper()
        if actual_architecture == "X86_64":
            actual_architecture = "AMD64"
        if host["architecture"] != actual_architecture:
            raise ValueError("support profile host architecture does not match this Windows host")
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30, check=False)
        if head.returncode != 0 or HEX40.fullmatch(head.stdout.strip()) is None:
            raise ValueError("repository CodeHead is unavailable")
        code_head = head.stdout.strip()
        evidence.mkdir()
        declared_tools = profile["tools"]
        assert isinstance(declared_tools, Mapping)
        actual_tools: dict[str, object] = {}
        for name in REQUIRED_TOOLS:
            declared = declared_tools[name]
            assert isinstance(declared, Mapping)
            record = _tool_record(support, declared, name)
            version = declared["version"] if name == "wheelhouse" else _run_tool_version(name, record)
            _, record_digest = _sha256_file(_safe_support_path(support, str(declared["record"])))
            actual_tools[name] = {"record": declared["record"], "sha256": record_digest, "version": version}
        chromium = profile["chromium"]
        assert isinstance(chromium, Mapping)
        executable = _safe_support_path(support, str(chromium["executable"]))
        version_run = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=30, check=False)
        if version_run.returncode != 0:
            raise ValueError("managed Chromium version command failed")
        version_match = re.search(r"\d+(?:\.\d+)+", version_run.stdout + version_run.stderr)
        if version_match is None:
            raise ValueError("managed Chromium did not report a version")
        chromium_version = version_match.group(0)
        launch_argv = expected_chromium_argv(chromium, str(support), str(evidence))
        launch = subprocess.run([str(executable), *launch_argv], capture_output=True, text=True, timeout=30, check=False)
        version_bytes = (version_run.stdout + version_run.stderr).encode("utf-8")
        launch_bytes = _write_json(
            evidence / "chromium-launch.json",
            {
                "argv": launch_argv,
                "exit_code": launch.returncode,
                "stderr": launch.stderr,
                "stdout": launch.stdout,
            },
        )
        (evidence / "chromium-version.txt").write_bytes(version_bytes)
        result_data: dict[str, object] = {
            "schema": RESULT_SCHEMA,
            "owner": profile["windows_owner"],
            "profile": {"path": profile_path.relative_to(support).as_posix(), "sha256": profile_digest},
            "support_manifest": {"sha256": manifest_digest},
            "run": {
                "kind": "windows-software-fixture",
                "status": "PASS",
                "code_head": code_head,
                "machine": "local",
                "evidence_root": str(evidence),
            },
            "tools": actual_tools,
            "chromium": {
                "executable": chromium["executable"],
                "executable_sha256": chromium["executable_sha256"],
                "version": chromium_version,
                "package_tree_sha256": chromium["package_tree_sha256"],
                "managed_profile_id": chromium["managed_profile"]["id"],
                "managed_profile_path": str(evidence / "managed-chromium-profile"),
                "blank_page": chromium["blank_page"]["path"],
                "argv": launch_argv,
                "exit_code": launch.returncode,
            },
            "firmware_fixture": profile["firmware_fixture"],
            "capabilities": profile["capabilities"],
            "hardware": {"status": "PENDING"},
            "evidence": {
                "chromium_launch": {
                    "path": "chromium-launch.json",
                    "sha256": hashlib.sha256(launch_bytes).hexdigest(),
                },
                "chromium_version": {
                    "path": "chromium-version.txt",
                    "sha256": hashlib.sha256(version_bytes).hexdigest(),
                },
            },
        }
        checked = verify_result(
            profile,
            manifest,
            result_data,
            expected_code_head=code_head,
            expected_profile_sha256=profile_digest,
            expected_manifest_sha256=manifest_digest,
            support_root=str(support),
        )
        _, _, _, final_profile_digest, final_manifest_digest = _verify_support_root(support, profile_path)
        if final_profile_digest != profile_digest or final_manifest_digest != manifest_digest:
            raise ValueError("support fixture changed during feasibility collection")
        _write_json(evidence / "result.json", result_data)
        evidence_files = []
        for path in sorted(evidence.iterdir(), key=lambda item: item.name):
            if path.is_file():
                size, digest = _sha256_file(path)
                evidence_files.append({"path": path.name, "bytes": size, "sha256": digest})
        _write_json(evidence / "evidence-manifest.json", {"files": evidence_files, "result": checked.code})
        return checked
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return _result("FEASIBILITY_CAPABILITY_MISSING", reason=str(exc))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_0600_feasibility.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--repo", required=True)
    run.add_argument("--support", required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)
    result = _run(args)
    print(json.dumps({"status": "PASS" if result.code == "PASS" else "BLOCKED", "code": result.code, **result.details}, sort_keys=True))
    return 0 if result.code == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
