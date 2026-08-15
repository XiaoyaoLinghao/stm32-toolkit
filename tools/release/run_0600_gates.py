"""Offline gate runners and controller state machines for STM32 Toolkit 0.6."""

from __future__ import annotations

import argparse
import builtins
import ctypes
import hashlib
import importlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import xml.etree.ElementTree as ElementTree
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, IO, Mapping, Protocol, Sequence

KNOWN_MODULES = {"STM32TK-0601", "STM32TK-0602", "STM32TK-0603"}
COVERAGE_TASK_ID = re.compile(r"(?P<module>STM32TK-[0-9]{4})-T(?:0[1-9]|[1-9][0-9])")
COVERAGE_META_KEYS = {"format", "version", "timestamp", "branch_coverage", "show_contexts"}
COVERAGE_ROW_KEYS = {
    "executed_lines", "summary", "missing_lines", "excluded_lines",
    "executed_branches", "missing_branches", "functions", "classes",
}
COVERAGE_SUMMARY_BASE_KEYS = {
    "covered_lines", "num_statements", "percent_covered", "percent_covered_display",
    "missing_lines", "excluded_lines", "num_branches", "num_partial_branches",
    "covered_branches", "missing_branches",
}
COVERAGE_SUMMARY_EXTENDED_KEYS = COVERAGE_SUMMARY_BASE_KEYS | {
    "percent_statements_covered", "percent_statements_covered_display",
    "percent_branches_covered", "percent_branches_covered_display",
}
FROZEN_T12_BASETEMP_TOKEN = r"C:\tmp\stm32tk-0603-package-312"
_NATIVE_PIPE_ENV = "STM32TK_CONTROLLER_NATIVE_PIPE"
_ORIGINAL_OPEN = builtins.open
_TRUSTED_PYTEST_BOOTSTRAP = (
    "import sys;"
    "sys.path.insert(0,sys.argv.pop(1));"
    "import run_0600_gates as plugin;"
    "import pytest;"
    "raise SystemExit(pytest.main(sys.argv[1:],plugins=[plugin]))"
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
UTC = "%Y-%m-%dT%H:%M:%S.%fZ"
RECOVERY_EVENTS = {
    "HOST_POWER_OR_REBOOT",
    "RUNNER_LOSS_BEFORE_CHILD_RESULT",
    "PHYSICAL_USB_OR_PROBE_REMOVAL",
    "TARGET_POWER_LOSS",
}
RECOVERY_KEYS = {
    "classification",
    "event",
    "reviewer",
    "recorded_at_utc",
    "run_kind",
    "run_id",
    "code_head",
    "checkpoint",
    "interrupted_attempt_digest",
}
FROZEN_TOOL_VERSIONS = {
    "cmake": "4.3.1",
    "ctest": "4.3.1",
    "node": "24.18.0",
    "npm": "11.16.0",
    "powershell": "5.1.26100.9168",
    "pyocd": "0.45.1",
    "pyserial": "3.5",
    "python310": "3.10.11",
    "python312": "3.12.10",
    "wheelhouse": "offline-wheelhouse/1",
}
FROZEN_CAPABILITIES = {
    "mailbox": {"address": 536870912, "size": 4096},
    "ram": [{"size": 32768, "start": 536870912}],
    "rtt": {"channel": 0},
    "semihosting": {"declared": True},
    "uart": {"baud": 115200, "port": "COM7"},
}


class ControllerError(ValueError):
    """A controller input or retained state failed closed."""


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("last_access_time", wintypes.FILETIME),
        ("last_write_time", wintypes.FILETIME),
        ("volume_serial", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("number_of_links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


class _LockedWindowsDirectory:
    def __init__(self, path: Path, handle: int, volume_serial: int, file_index: int) -> None:
        self.path = path
        self.handle = handle
        self.volume_serial = volume_serial
        self.file_index = file_index

    def __enter__(self) -> _LockedWindowsDirectory:
        return self

    def __exit__(self, *_args: object) -> None:
        if self.handle:
            _close_windows_handle(self.handle)
            self.handle = 0


class _LockedWindowsFile:
    def __init__(
        self,
        path: Path,
        handle: int,
        volume_serial: int,
        file_index: int,
        *,
        cleanup: bool = False,
    ) -> None:
        self.path = path
        self.handle = handle
        self.volume_serial = volume_serial
        self.file_index = file_index
        self.cleanup = cleanup

    def __enter__(self) -> _LockedWindowsFile:
        return self

    def __exit__(self, *_args: object) -> None:
        cleanup_safe = False
        if self.handle:
            try:
                _validate_locked_coverage_file(self)
                cleanup_safe = True
            finally:
                _close_windows_handle(self.handle)
                self.handle = 0
        if self.cleanup:
            if not cleanup_safe or _is_reparse(self.path) or not self.path.is_file():
                raise ControllerError("coverage lock sentinel cleanup identity is unsafe")
            try:
                self.path.unlink()
            except OSError as exc:
                raise ControllerError("coverage lock sentinel cleanup failed") from exc


class CatalogError(ValueError):
    """A lazily loaded catalog failed the controller boundary."""


class VerificationError(ValueError):
    """A lazily loaded release input failed the controller boundary."""


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


_RELEASE_MODULE: object | None = None


def _release_module() -> object:
    """Load release-verifier code only after the calling path established its blob trust."""
    global _RELEASE_MODULE
    if _RELEASE_MODULE is None:
        _RELEASE_MODULE = importlib.import_module("verify_0600_release")
    return _RELEASE_MODULE


def _release_call(name: str, *args: object, **kwargs: object) -> object:
    function = getattr(_release_module(), name)
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        error = CatalogError if exc.__class__.__name__ == "CatalogError" else VerificationError
        raise error(str(exc)) from exc


def load_catalog(path: Path) -> object:
    return _release_call("load_catalog", path)


def load_performance_catalog(path: Path) -> object:
    return _release_call("load_performance_catalog", path)


def validate_performance_run(value: object) -> object:
    return _release_call("validate_performance_run", value)


def create_candidate_ledger(**kwargs: object) -> dict[str, object]:
    return _release_call("create_candidate_ledger", **kwargs)  # type: ignore[return-value]


def write_candidate_ledger(*args: object, **kwargs: object) -> None:
    _release_call("write_candidate_ledger", *args, **kwargs)


def reconcile_candidate(*args: object, **kwargs: object) -> Path:
    return _release_call("reconcile_candidate", *args, **kwargs)  # type: ignore[return-value]


def validate_candidate_ledger(value: object) -> dict[str, object]:
    return _release_call("validate_candidate_ledger", value)  # type: ignore[return-value]


def validate_recovery_record(*args: object, **kwargs: object) -> dict[str, object]:
    return _release_call("validate_recovery_record", *args, **kwargs)  # type: ignore[return-value]


def create_shard_package(*args: object, **kwargs: object) -> dict[str, object]:
    return _release_call("create_shard_package", *args, **kwargs)  # type: ignore[return-value]


def verify_shard_package(*args: object, **kwargs: object) -> None:
    _release_call("verify_shard_package", *args, **kwargs)


VERIFIER_RELATIVE_PATH = "tools/release/verify_0600_release.py"
FEASIBILITY_RELATIVE_PATH = "tools/release/verify_0600_feasibility.py"
RUNNER_RELATIVE_PATH = "tools/release/run_0600_gates.py"
HARDWARE_CALLER_RELATIVE_PATHS = (
    RUNNER_RELATIVE_PATH,
    FEASIBILITY_RELATIVE_PATH,
    VERIFIER_RELATIVE_PATH,
)
CANONICAL_ORIGIN = "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"
FEASIBILITY_REQUIRED_TOOLS = (
    "python310", "python312", "powershell", "cmake", "ctest", "pyocd",
    "pyserial", "node", "npm", "wheelhouse",
)
_FEASIBILITY_MODULE: object | None = None
VerifiedModuleSources = dict[str, tuple[Path, bytes, str]]


def _feasibility_module() -> object:
    global _FEASIBILITY_MODULE
    if _FEASIBILITY_MODULE is None:
        _FEASIBILITY_MODULE = importlib.import_module("verify_0600_feasibility")
    return _FEASIBILITY_MODULE


def _git_text(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ControllerError("Git verifier binding check failed")
    return completed.stdout.strip()


def _git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _verify_hardware_caller_trust(
    repo: Path,
    expected_code_head: str,
    *,
    git_runner: Callable[[list[str]], str] | None = None,
    capture_modules: bool = False,
) -> VerifiedModuleSources:
    """Bind the loaded public hardware caller before any release-verifier load."""
    if HEX40.fullmatch(expected_code_head) is None:
        raise ControllerError("hardware caller CodeHead is invalid")
    try:
        repository = repo.resolve(strict=True)
    except OSError as exc:
        raise ControllerError("hardware caller repository is invalid") from exc
    if repo != repository or Path(__file__).resolve() != repository.joinpath(
        *RUNNER_RELATIVE_PATH.split("/")
    ):
        raise ControllerError("hardware caller runner path is not exact")
    selected_git_runner = git_runner or (lambda args: _git_text(repository, args))
    if selected_git_runner(["rev-parse", "HEAD"]).strip() != expected_code_head:
        raise ControllerError("hardware caller HEAD changed")
    if (
        selected_git_runner(["config", "--get", "remote.origin.url"]).strip()
        != CANONICAL_ORIGIN
    ):
        raise ControllerError("hardware caller origin changed")
    captured: VerifiedModuleSources = {}
    for relative in HARDWARE_CALLER_RELATIVE_PATHS:
        working = selected_git_runner(["hash-object", "--", relative]).strip()
        committed = selected_git_runner(
            ["rev-parse", f"{expected_code_head}:{relative}"]
        ).strip()
        if HEX40.fullmatch(working) is None or working != committed:
            raise ControllerError(f"hardware caller blob changed: {relative}")
        if capture_modules and relative != RUNNER_RELATIVE_PATH:
            path = repository.joinpath(*relative.split("/"))
            source = path.read_bytes()
            if _git_blob_id(source) != working:
                raise ControllerError(f"hardware caller blob changed: {relative}")
            captured[relative] = (path, source, working)
    return captured


def _exec_verified_module(
    relative: str,
    source: tuple[Path, bytes, str],
) -> tuple[object, str, object | None]:
    path, data, expected_blob = source
    if _git_blob_id(data) != expected_blob:
        raise ControllerError(f"hardware caller blob changed: {relative}")
    module_name = f"_stm32tk_verified_{path.stem}_{expected_blob}"
    previous = sys.modules.get(module_name)
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except Exception as exc:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise ControllerError(f"trusted hardware verifier failed to load: {relative}") from exc
    return module, module_name, previous


def _load_verified_hardware_verifiers(
    repo: Path,
    expected_code_head: str,
    sources: VerifiedModuleSources,
    *,
    git_runner: Callable[[list[str]], str] | None = None,
) -> None:
    """Execute captured verifier bytes, then close the disk-race window."""
    global _RELEASE_MODULE, _FEASIBILITY_MODULE
    required = {VERIFIER_RELATIVE_PATH, FEASIBILITY_RELATIVE_PATH}
    if set(sources) != required:
        raise ControllerError("hardware caller verifier capture is incomplete")
    previous_globals = (_RELEASE_MODULE, _FEASIBILITY_MODULE)
    loaded: list[tuple[str, object | None]] = []
    try:
        release, name, previous = _exec_verified_module(
            VERIFIER_RELATIVE_PATH, sources[VERIFIER_RELATIVE_PATH]
        )
        loaded.append((name, previous))
        feasibility, name, previous = _exec_verified_module(
            FEASIBILITY_RELATIVE_PATH, sources[FEASIBILITY_RELATIVE_PATH]
        )
        loaded.append((name, previous))
        _verify_hardware_caller_trust(
            repo, expected_code_head, git_runner=git_runner
        )
    except Exception:
        _RELEASE_MODULE, _FEASIBILITY_MODULE = previous_globals
        for module_name, previous in reversed(loaded):
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
        raise
    _RELEASE_MODULE = release
    _FEASIBILITY_MODULE = feasibility


def _verify_relative_blob(repo: Path, expected_code_head: str, relative: str) -> Path:
    if HEX40.fullmatch(expected_code_head) is None:
        raise ControllerError("expected CodeHead is invalid")
    try:
        repository = repo.resolve(strict=True)
        script = repository.joinpath(*relative.split("/"))
        if not script.is_file() or script.is_symlink():
            raise ControllerError("re-derived verifier is missing or linked")
    except OSError as exc:
        raise ControllerError("repository/verifier path is invalid") from exc
    if _git_text(repository, ["rev-parse", "HEAD"]) != expected_code_head:
        raise ControllerError("worktree HEAD does not match expected CodeHead")
    committed = _git_text(repository, ["rev-parse", f"{expected_code_head}:{relative}"])
    working = _git_text(repository, ["hash-object", "--", str(script)])
    if HEX40.fullmatch(committed) is None or committed != working:
        raise ControllerError("release verifier working blob does not match CodeHead")
    return script


def _verify_verifier_blob(repo: Path, expected_code_head: str) -> Path:
    return _verify_relative_blob(repo, expected_code_head, VERIFIER_RELATIVE_PATH)


def invoke_trusted_verifier(
    *,
    repo: Path,
    expected_code_head: str,
    verifier_args: Sequence[str],
    after_first_check: Callable[[], object] | None = None,
    process_factory: Callable[[list[str]], object] | None = None,
) -> object:
    """Perform both caller-owned checks and create exactly one interpreter process."""
    _verify_verifier_blob(repo, expected_code_head)
    if after_first_check is not None:
        after_first_check()
    script = _verify_verifier_blob(repo, expected_code_head)
    argv = [sys.executable, str(script), *verifier_args]
    if any(not isinstance(token, str) or not token for token in argv):
        raise ControllerError("verifier argv token is invalid")
    factory = process_factory or (lambda command: subprocess.Popen(command, env=_safe_controller_env()))
    return factory(argv)


@dataclass(frozen=True)
class GateRequest:
    gate_id: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    expected_nodes: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
    resource_locks: dict[str, str] | None = None


@dataclass(frozen=True)
class GateRunOutput:
    exit_code: int
    stdout: bytes
    stderr: bytes
    selected_nodes: tuple[str, ...]
    node_outcomes: tuple[tuple[str, str], ...]
    duration_ms: int = 0
    timed_out: bool = False
    retained_evidence: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: str
    reason: str
    metadata: dict[str, object]


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ControllerError("UTC value is naive")
    return value.astimezone(timezone.utc).strftime(UTC)


def _safe_controller_env() -> dict[str, str]:
    allowed = {
        "COMSPEC", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "PATH", "PATHEXT",
        "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "WINDIR",
    }
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.update({"PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return result


def _metadata(
    gate: GateRequest,
    output: GateRunOutput,
    *,
    run_id: str,
    code_head: str,
    started: datetime,
    decision: Mapping[str, object] | None = None,
) -> dict[str, object]:
    executable_version = "reserved"
    if gate.argv:
        if os.path.normcase(gate.argv[0]) == os.path.normcase(sys.executable):
            executable_version = platform.python_version()
        else:
            executable_path = Path(gate.argv[0])
            if not executable_path.is_absolute():
                located = shutil.which(gate.argv[0], path=_safe_controller_env().get("PATH"))
                if located is None:
                    raise ControllerError("gate executable identity cannot be resolved")
                executable_path = Path(located)
            try:
                resolved_executable = executable_path.resolve(strict=True)
                if not resolved_executable.is_file() or resolved_executable.is_symlink():
                    raise ControllerError("gate executable identity is not a regular file")
                executable_version = f"sha256:{hashlib.sha256(resolved_executable.read_bytes()).hexdigest()}"
            except OSError as exc:
                raise ControllerError("gate executable identity cannot be read") from exc
    return {
        "architecture": platform.machine(),
        "argv": list(gate.argv),
        "code_head": code_head,
        "cwd": ".",
        "decision": dict(decision or {
            "postcheck": "NOT_RUN", "precheck": "NOT_RUN", "prerequisites": []
        }),
        "duration_ms": output.duration_ms,
        "executable": gate.argv[0] if gate.argv else "reserved",
        "executable_version": executable_version,
        "exit_code": output.exit_code,
        "gate_id": gate.gate_id,
        "node_outcomes": [
            {"node_id": node_id, "outcome": outcome}
            for node_id, outcome in output.node_outcomes
        ],
        "os": platform.system(),
        "retained_evidence": list(output.retained_evidence),
        "run_id": run_id,
        "seed": f"stm32tk-0600:{run_id}:{gate.gate_id}",
        "selected_nodes": list(output.selected_nodes),
        "started_at_utc": _utc(started),
        "stderr": {"bytes": len(output.stderr), "sha256": hashlib.sha256(output.stderr).hexdigest()},
        "stdout": {"bytes": len(output.stdout), "sha256": hashlib.sha256(output.stdout).hexdigest()},
        "timed_out": output.timed_out,
    }


def _decision_facts(
    gate: GateRequest,
    statuses: Mapping[str, str],
    *,
    precheck: str,
    postcheck: str,
) -> dict[str, object]:
    return {
        "postcheck": postcheck,
        "precheck": precheck,
        "prerequisites": [
            {"gate_id": gate_id, "status": statuses[gate_id]}
            for gate_id in gate.prerequisites
        ],
    }


def _node_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ControllerError(f"native node {field} is invalid")
    return value


_NATIVE_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9_.-])[A-Za-z]:[\\/]")
_NATIVE_UNC_PATH = re.compile(r"(?<![A-Za-z0-9_.-])[\\/]{2}[^\\/\s]")
_NATIVE_UNIX_PATH = re.compile(r"(?<![A-Za-z0-9_.*?-])/(?!/)(?=[^/\s])")
_NATIVE_FILE_URI = re.compile(r"\bfile:[\\/]+", re.IGNORECASE)
_NATIVE_CREDENTIAL = re.compile(
    r"(?i)(?:authorization\s*[:=]\s*(?:bearer|basic)\s+\S+|"
    r"(?:password|passwd|secret|token|api[-_]?key)\s*[:=]\s*\S+)"
)


def _native_portable_string(value: str) -> None:
    inspected = value.replace("<REPOSITORY_ROOT>/", "repo/").replace(
        "<EVIDENCE_ROOT>/", "evidence/"
    )
    if (
        _NATIVE_WINDOWS_PATH.search(inspected)
        or _NATIVE_UNC_PATH.search(inspected)
        or _NATIVE_UNIX_PATH.search(inspected)
        or _NATIVE_FILE_URI.search(inspected)
    ):
        raise ControllerError("native artifact contains an unrecognized absolute path")
    if _NATIVE_CREDENTIAL.search(inspected):
        raise ControllerError("native artifact contains a credential")


def _replace_verified_root(value: str, root: Path, token: str) -> tuple[str, bool]:
    canonical = str(root.resolve(strict=True))
    variants = {canonical, canonical.replace("\\", "/"), canonical.replace("/", "\\")}
    changed = False
    for variant in sorted(variants, key=len, reverse=True):
        pattern = re.compile(re.escape(variant) + r"(?=$|[\\/])", re.IGNORECASE)
        value, count = pattern.subn(token, value)
        changed = changed or count > 0
    return value, changed


def _normalize_known_path(value: str, repository_root: Path, evidence_root: Path) -> str:
    value, _ = _replace_verified_root(value, repository_root, "<REPOSITORY_ROOT>")
    value, _ = _replace_verified_root(value, evidence_root, "<EVIDENCE_ROOT>")
    value = value.replace("<REPOSITORY_ROOT>\\", "<REPOSITORY_ROOT>/").replace(
        "<EVIDENCE_ROOT>\\", "<EVIDENCE_ROOT>/"
    )
    _native_portable_string(value)
    return value


def _documented_native_json_path(framework: str, path: tuple[object, ...]) -> bool:
    if framework == "vitest-json":
        return (
            len(path) == 3 and path[0] == "testResults"
            and isinstance(path[1], int) and path[2] == "name"
        )
    if path in {("config", "configFile"), ("config", "rootDir")}:
        return True
    if (
        len(path) == 4 and path[:2] == ("config", "projects")
        and isinstance(path[2], int) and path[3] in {"outputDir", "testDir"}
    ):
        return True
    return bool(path and path[-1] == "file" and any(item in {"suites", "specs"} for item in path[:-1]))


def normalize_native_artifact(
    framework: str,
    raw: bytes,
    *,
    repository_root: Path,
    evidence_root: Path,
) -> bytes:
    """Normalize only documented native fields below the two verified local roots."""
    try:
        repository_root = repository_root.resolve(strict=True)
        evidence_root = evidence_root.resolve(strict=True)
    except OSError as exc:
        raise ControllerError("native artifact roots are unavailable") from exc
    if not repository_root.is_dir() or not evidence_root.is_dir():
        raise ControllerError("native artifact roots are not directories")
    if framework in {"vitest-json", "playwright-json"}:
        report = _native_json(raw, framework)

        def walk(member: object, path: tuple[object, ...] = ()) -> object:
            if isinstance(member, dict):
                result: dict[str, object] = {}
                for key, item in member.items():
                    if not isinstance(key, str):
                        raise ControllerError("native artifact JSON key is invalid")
                    result[key] = walk(item, (*path, key))
                return result
            if isinstance(member, list):
                return [walk(item, (*path, index)) for index, item in enumerate(member)]
            if isinstance(member, str):
                if _documented_native_json_path(framework, path):
                    normalized = _normalize_known_path(
                        member, repository_root, evidence_root
                    )
                    if normalized.startswith(("<REPOSITORY_ROOT>/", "<EVIDENCE_ROOT>/")):
                        normalized = normalized.replace("\\", "/")
                    return normalized
                _native_portable_string(member)
            return member

        return canonical_json_bytes(walk(report))
    if framework == "ctest-text":
        try:
            value = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ControllerError("CTest native text is invalid UTF-8") from exc
        return _normalize_known_path(value, repository_root, evidence_root).encode("utf-8")
    if framework not in {"pytest-junit", "ctest-junit"}:
        raise ControllerError("native artifact normalization framework is unsupported")
    try:
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, UnicodeError) as exc:
        raise ControllerError("native XML artifact is invalid") from exc
    text_tags = {"failure", "error", "skipped", "system-out", "system-err"}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        for key, value in tuple(element.attrib.items()):
            if (tag == "testcase" and key == "file") or tag in text_tags:
                element.attrib[key] = _normalize_known_path(
                    value, repository_root, evidence_root
                )
            else:
                _native_portable_string(value)
        for member_name in ("text", "tail"):
            value = getattr(element, member_name)
            if not value:
                continue
            if tag in text_tags:
                setattr(
                    element, member_name,
                    _normalize_known_path(value, repository_root, evidence_root),
                )
            else:
                _native_portable_string(value)
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _unique_native_outcomes(outcomes: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    if not outcomes or len({node_id for node_id, _ in outcomes}) != len(outcomes):
        raise ControllerError("native node inventory is empty or duplicated")
    return tuple(outcomes)


def _native_count(value: object, field: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ControllerError(f"native summary {field} count is invalid") from exc
    if isinstance(value, bool) or result < 0 or str(result) != str(value):
        raise ControllerError(f"native summary {field} count is invalid")
    return result


def _validate_native_exit(
    framework: str,
    outcomes: tuple[tuple[str, str], ...],
    exit_code: int | None,
    *,
    global_error: bool = False,
) -> None:
    if exit_code is None:
        return
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise ControllerError(f"{framework} native exit code is invalid")
    native_failure = global_error or any(outcome == "failed" for _, outcome in outcomes)
    if (exit_code == 0) == native_failure:
        raise ControllerError(f"{framework} native summary and exit code are inconsistent")


def _parse_junit_node_outcomes(raw: bytes, framework: str) -> tuple[tuple[str, str], ...]:
    try:
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, UnicodeError) as exc:
        raise ControllerError(f"{framework} native report is invalid XML") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise ControllerError(f"{framework} native report root is invalid")
    outcomes: list[tuple[str, str]] = []
    testcases = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "testcase"]
    for testcase in testcases:
        name = _node_text(testcase.get("name"), "name")
        classname = testcase.get("classname")
        node_id = name if framework == "ctest-junit" else f"{_node_text(classname, 'classname')}::{name}"
        children = {child.tag.rsplit("}", 1)[-1] for child in testcase}
        status = testcase.get("status")
        if "failure" in children or "error" in children or status == "fail":
            outcome = "failed"
        elif "skipped" in children or status in {"skip", "notrun"}:
            outcome = "skipped"
        elif status in {None, "run"}:
            outcome = "passed"
        else:
            raise ControllerError(f"{framework} native testcase status is invalid")
        outcomes.append((node_id, outcome))
    result = _unique_native_outcomes(outcomes)
    suites = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "testsuite"]
    if not suites:
        raise ControllerError(f"{framework} native summary is missing")
    for suite in suites:
        suite_cases = [
            item for item in suite.iter()
            if item.tag.rsplit("}", 1)[-1] == "testcase"
        ]
        suite_outcomes = []
        for item in suite_cases:
            index = testcases.index(item)
            suite_outcomes.append(outcomes[index][1])
        tests = _native_count(suite.get("tests"), "tests")
        failures = _native_count(suite.get("failures"), "failures", default=0)
        errors = _native_count(suite.get("errors"), "errors", default=0)
        skipped = _native_count(suite.get("skipped"), "skipped", default=0)
        disabled = _native_count(suite.get("disabled"), "disabled", default=0)
        if (
            tests != len(suite_cases)
            or failures + errors != suite_outcomes.count("failed")
            or skipped + disabled != suite_outcomes.count("skipped")
        ):
            raise ControllerError(f"{framework} native summary counts contradict nodes")
    return result


def _parse_ctest_text_node_outcomes(raw: bytes) -> tuple[tuple[str, str], ...]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ControllerError("ctest-text native report is invalid UTF-8") from exc
    row = re.compile(
        r"^\s*(?P<ordinal>[1-9][0-9]*)/(?P<total>[1-9][0-9]*) Test\s+#(?P<number>[1-9][0-9]*): "
        r"(?P<name>.+?) \.{3,}\s*(?P<status>Passed|Not Run|Skipped|\*\*\*Failed)\s+"
        r"(?P<seconds>[0-9]+(?:\.[0-9]+)?) sec$"
    )
    outcomes: list[tuple[str, str]] = []
    totals: set[int] = set()
    ordinals: list[int] = []
    for line in lines:
        match = row.fullmatch(line)
        if match is None:
            continue
        ordinals.append(int(match.group("ordinal")))
        totals.add(int(match.group("total")))
        status = match.group("status")
        outcomes.append((
            _node_text(match.group("name"), "name"),
            "failed" if status == "***Failed" else "skipped" if status in {"Not Run", "Skipped"} else "passed",
        ))
    result = _unique_native_outcomes(outcomes)
    if totals != {len(result)} or ordinals != list(range(1, len(result) + 1)):
        raise ControllerError("ctest-text native rows contradict inventory")
    summaries = [
        re.fullmatch(r"(?P<percent>[0-9]+)% tests passed, (?P<failed>[0-9]+) tests failed out of (?P<total>[0-9]+)", line)
        for line in lines
    ]
    summaries = [item for item in summaries if item is not None]
    if len(summaries) != 1:
        raise ControllerError("ctest-text native summary is missing or duplicated")
    summary = summaries[0]
    failed = sum(outcome == "failed" for _, outcome in result)
    total = len(result)
    percent_numerator = (total - failed) * 100
    expected_percents = {
        percent_numerator // total,
        math.ceil(percent_numerator / total),
    }
    if (
        int(summary.group("failed")) != failed
        or int(summary.group("total")) != total
        or int(summary.group("percent")) not in expected_percents
    ):
        raise ControllerError("ctest-text native summary counts contradict nodes")
    return result


def _native_json(raw: bytes, framework: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError(f"{framework} native report is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ControllerError(f"{framework} native report must be an object")
    return value


def _parse_vitest_node_outcomes(raw: bytes) -> tuple[tuple[str, str], ...]:
    report = _native_json(raw, "vitest-json")
    tests = report.get("testResults")
    if not isinstance(tests, list):
        raise ControllerError("vitest native report testResults is invalid")
    outcomes: list[tuple[str, str]] = []
    for suite in tests:
        if not isinstance(suite, dict) or not isinstance(suite.get("assertionResults"), list):
            raise ControllerError("vitest native report suite is invalid")
        for assertion in suite["assertionResults"]:
            if not isinstance(assertion, dict):
                raise ControllerError("vitest native assertion is invalid")
            node_id = _node_text(assertion.get("fullName"), "fullName")
            status = assertion.get("status")
            if status not in {"passed", "failed", "skipped", "pending", "todo"}:
                raise ControllerError("vitest native assertion status is invalid")
            outcomes.append((node_id, "skipped" if status in {"pending", "todo"} else status))
    result = _unique_native_outcomes(outcomes)
    statuses = [outcome for _, outcome in result]
    expected_counts = {
        "numTotalTests": len(result),
        "numPassedTests": statuses.count("passed"),
        "numFailedTests": statuses.count("failed"),
        "numPendingTests": statuses.count("skipped"),
    }
    for field, expected in expected_counts.items():
        if _native_count(report.get(field), field) != expected:
            raise ControllerError("vitest native summary counts contradict nodes")
    todo = _native_count(report.get("numTodoTests"), "numTodoTests", default=0)
    if todo > expected_counts["numPendingTests"]:
        raise ControllerError("vitest native summary todo count contradicts nodes")
    suite_statuses = [suite.get("status") for suite in tests if isinstance(suite, dict)]
    suite_total = _native_count(report.get("numTotalTestSuites"), "numTotalTestSuites")
    suite_passed = _native_count(report.get("numPassedTestSuites"), "numPassedTestSuites")
    suite_failed = _native_count(report.get("numFailedTestSuites"), "numFailedTestSuites")
    suite_pending = _native_count(report.get("numPendingTestSuites"), "numPendingTestSuites")
    if (
        suite_passed + suite_failed + suite_pending != suite_total
        or (bool(suite_statuses.count("failed")) != bool(suite_failed))
    ):
        raise ControllerError("vitest native summary suite counts contradict nodes")
    success = report.get("success")
    expected_success = not statuses.count("failed") and not suite_failed
    if type(success) is not bool or success is not expected_success:
        raise ControllerError("vitest native success contradicts node summary")
    return result


def _parse_playwright_node_outcomes(raw: bytes) -> tuple[tuple[str, str], ...]:
    report = _native_json(raw, "playwright-json")
    suites = report.get("suites")
    if not isinstance(suites, list):
        raise ControllerError("playwright native report suites is invalid")
    outcomes: list[tuple[str, str]] = []

    def walk(suite: object) -> None:
        if not isinstance(suite, dict):
            raise ControllerError("playwright native suite is invalid")
        file_name = _node_text(suite.get("file"), "file")
        specs = suite.get("specs", [])
        children = suite.get("suites", [])
        if not isinstance(specs, list) or not isinstance(children, list):
            raise ControllerError("playwright native suite children are invalid")
        for spec in specs:
            if not isinstance(spec, dict) or not isinstance(spec.get("tests"), list):
                raise ControllerError("playwright native spec is invalid")
            title = _node_text(spec.get("title"), "title")
            for test in spec["tests"]:
                if not isinstance(test, dict):
                    raise ControllerError("playwright native test is invalid")
                project = _node_text(test.get("projectName"), "projectName")
                status = test.get("status")
                results = test.get("results")
                if not isinstance(results, list) or status not in {"expected", "unexpected", "skipped"}:
                    raise ControllerError("playwright native test status is invalid")
                if status == "skipped":
                    outcome = "skipped"
                elif len(results) == 1 and isinstance(results[0], dict) and results[0].get("status") in {"passed", "failed", "timedOut", "skipped"}:
                    native = results[0]["status"]
                    outcome = "failed" if native in {"failed", "timedOut"} else native
                else:
                    raise ControllerError("playwright native test result is invalid")
                outcomes.append((f"{project}::{file_name}::{title}", outcome))
        for child in children:
            walk(child)

    for suite in suites:
        walk(suite)
    result = _unique_native_outcomes(outcomes)
    stats = report.get("stats")
    errors = report.get("errors")
    if not isinstance(stats, dict) or not isinstance(errors, list):
        raise ControllerError("playwright native summary is invalid")
    native_statuses: list[str] = []

    def collect(suite: object) -> None:
        assert isinstance(suite, dict)
        for spec in suite.get("specs", []):
            assert isinstance(spec, dict)
            for test in spec.get("tests", []):
                assert isinstance(test, dict)
                native_statuses.append(str(test.get("status")))
        for child in suite.get("suites", []):
            collect(child)

    for suite in suites:
        collect(suite)
    for field in ("expected", "unexpected", "skipped", "flaky"):
        if _native_count(stats.get(field), field) != native_statuses.count(field):
            raise ControllerError("playwright native summary counts contradict nodes")
    return result


def parse_native_node_outcomes(
    framework: str, raw: bytes, *, exit_code: int | None = None,
) -> tuple[tuple[str, str], ...]:
    """Map one strictly validated native runner report to the catalog's node inventory."""
    if framework in {"pytest-junit", "ctest-junit"}:
        outcomes = _parse_junit_node_outcomes(raw, framework)
        _validate_native_exit(framework, outcomes, exit_code)
        return outcomes
    if framework == "ctest-text":
        outcomes = _parse_ctest_text_node_outcomes(raw)
        _validate_native_exit(framework, outcomes, exit_code)
        return outcomes
    if framework == "vitest-json":
        outcomes = _parse_vitest_node_outcomes(raw)
        _validate_native_exit(framework, outcomes, exit_code)
        return outcomes
    if framework == "playwright-json":
        outcomes = _parse_playwright_node_outcomes(raw)
        report = _native_json(raw, framework)
        errors = report.get("errors")
        _validate_native_exit(
            framework, outcomes, exit_code,
            global_error=isinstance(errors, list) and bool(errors),
        )
        return outcomes
    raise ControllerError("native node framework is unsupported")


def native_node_framework(argv: Sequence[str]) -> str:
    """Identify the only accepted native outcome format for a frozen runner argv."""
    lowered = tuple(token.casefold() for token in argv)
    if any(lowered[index:index + 2] == ("-m", "pytest") for index in range(len(lowered) - 1)):
        if any(token.startswith("--junitxml") for token in argv):
            raise ControllerError("pytest native JUnit sink must be controller-owned")
        return "pytest-junit"
    executable = Path(argv[0]).name.casefold()
    if executable in {"ctest", "ctest.exe"}:
        if "--output-junit" in lowered:
            raise ControllerError("CTest native JUnit sink must be controller-owned")
        return "ctest-text"
    if any("vitest" in token for token in lowered):
        if any(token.startswith("--reporter") for token in lowered):
            raise ControllerError("Vitest native JSON reporter must be controller-owned")
        return "vitest-json"
    if any("playwright" in token for token in lowered):
        if any(token.startswith("--reporter") for token in lowered):
            raise ControllerError("Playwright native JSON reporter must be controller-owned")
        projects = tuple(token.split("=", 1)[1] for token in argv if token.startswith("--project="))
        if projects != ("chromium-1280", "chromium-1024"):
            raise ControllerError("Windows Playwright adapter requires only frozen Chromium projects")
        return "playwright-json"
    raise ControllerError("gate executable has no supported native node outcome adapter")


class _WindowsNativePipeSink:
    """One inbound byte stream with no linkable NTFS directory entry."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise ControllerError("native report pipe requires Windows")
        self.name = rf"\\.\pipe\stm32tk-0600-{secrets.token_hex(16)}"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        handle = kernel32.CreateNamedPipeW(
            self.name,
            0x00000001,  # PIPE_ACCESS_INBOUND
            0x00000000,  # byte mode, blocking
            1, 0, 65536, 0, None,
        )
        invalid = ctypes.c_void_p(-1).value
        handle_value = handle if isinstance(handle, int) else handle.value
        if handle_value in (None, invalid):
            raise ControllerError("native report pipe create failed") from ctypes.WinError(ctypes.get_last_error())
        self._handle = handle_value
        self._data = bytearray()
        self._error: BaseException | None = None
        self._finishing = threading.Event()
        self._thread = threading.Thread(target=self._read, name="stm32tk-native-pipe", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        kernel32.ConnectNamedPipe.restype = wintypes.BOOL
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
        ]
        kernel32.ReadFile.restype = wintypes.BOOL
        kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
        kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
        try:
            while True:
                if not kernel32.ConnectNamedPipe(wintypes.HANDLE(self._handle), None):
                    error = ctypes.get_last_error()
                    if error != 535:  # ERROR_PIPE_CONNECTED
                        raise ctypes.WinError(error)
                connection = bytearray()
                while True:
                    buffer = ctypes.create_string_buffer(65536)
                    read = wintypes.DWORD()
                    if not kernel32.ReadFile(
                        wintypes.HANDLE(self._handle), buffer, len(buffer), ctypes.byref(read), None,
                    ):
                        error = ctypes.get_last_error()
                        if error in {109, 232}:  # broken/no data after writer closes
                            break
                        raise ctypes.WinError(error)
                    if read.value == 0:
                        break
                    connection.extend(buffer.raw[:read.value])
                    if len(connection) > 64 * 1024 * 1024:
                        raise ControllerError("native report pipe exceeded size limit")
                if connection:
                    self._data.extend(connection)
                    break
                if self._finishing.is_set():
                    break
                kernel32.DisconnectNamedPipe(wintypes.HANDLE(self._handle))
        except BaseException as exc:
            self._error = exc

    def finish(self) -> bytes:
        self._finishing.set()
        self._thread.join(timeout=0.25)
        if self._thread.is_alive():
            # If the child never connected, connect and immediately close a writer so
            # ConnectNamedPipe cannot strand the controller.
            try:
                writer = _open_windows_native_pipe_writer(self.name, "wb")
                writer.close()
            except (OSError, ControllerError):
                pass
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            self.close()
            raise ControllerError("native report pipe did not finish")
        if self._error is not None:
            raise ControllerError("native report pipe read failed") from self._error
        return bytes(self._data)

    def close(self) -> None:
        if self._handle is not None:
            handle, self._handle = self._handle, None
            _close_windows_handle(handle)

    def __enter__(self) -> "_WindowsNativePipeSink":
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._thread.is_alive():
            try:
                self.finish()
            except ControllerError:
                pass
        self.close()


def _open_windows_native_pipe_writer(
    name: str, mode: str = "w", *, encoding: str | None = None,
    errors: str | None = None, newline: str | None = None,
) -> IO[object]:
    """Open only a controller namespace pipe as a Python file object."""
    prefix = r"\\.\pipe\stm32tk-0600-"
    if not name.startswith(prefix) or re.fullmatch(r"[0-9a-f]{32}", name[len(prefix):]) is None:
        raise ControllerError("native report pipe name is invalid")
    if mode not in {"w", "wb", "wt"}:
        raise ControllerError("native report pipe mode is invalid")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(name, 0x40000000, 0, None, 3, 0, None)
    invalid = ctypes.c_void_p(-1).value
    handle_value = handle if isinstance(handle, int) else handle.value
    if handle_value in (None, invalid) and ctypes.get_last_error() == 231:
        kernel32.WaitNamedPipeW(name, 5000)
        handle = kernel32.CreateFileW(name, 0x40000000, 0, None, 3, 0, None)
        handle_value = handle if isinstance(handle, int) else handle.value
    if handle_value in (None, invalid):
        raise ControllerError("native report pipe writer open failed") from ctypes.WinError(ctypes.get_last_error())
    import msvcrt
    try:
        fd = msvcrt.open_osfhandle(handle_value, os.O_WRONLY | (os.O_BINARY if "b" in mode else os.O_TEXT))
    except BaseException:
        _close_windows_handle(handle_value)
        raise
    try:
        if "b" in mode:
            return _ORIGINAL_OPEN(fd, mode, closefd=True)
        return _ORIGINAL_OPEN(fd, mode, encoding=encoding or "utf-8", errors=errors, newline=newline, closefd=True)
    except BaseException:
        os.close(fd)
        raise


def pytest_configure(config: object) -> None:
    """Trusted child adapter: route the exact controller sink through Win32."""
    sink = os.environ.get(_NATIVE_PIPE_ENV)
    if sink is None:
        return
    original = builtins.open

    def pipe_open(file: object, mode: str = "r", buffering: int = -1,
                  encoding: str | None = None, errors: str | None = None,
                  newline: str | None = None, closefd: bool = True,
                  opener: object | None = None) -> IO[object]:
        try:
            value = os.fspath(file)
        except TypeError:
            value = None
        if value == sink:
            if buffering != -1 or not closefd or opener is not None:
                raise ControllerError("native report pipe open options are invalid")
            return _open_windows_native_pipe_writer(
                sink, mode, encoding=encoding, errors=errors, newline=newline,
            )
        return original(file, mode, buffering, encoding, errors, newline, closefd, opener)

    setattr(config, "_stm32tk_original_open", original)
    builtins.open = pipe_open


def pytest_unconfigure(config: object) -> None:
    original = getattr(config, "_stm32tk_original_open", None)
    if original is not None:
        builtins.open = original


def _native_report_argv(argv: Sequence[str], sink: str) -> tuple[str, tuple[str, ...], str | None]:
    """Append the single native result sink without changing the frozen product argv."""
    framework = native_node_framework(argv)
    if framework == "pytest-junit":
        return framework, (f"--junitxml={sink}",), sink
    if framework == "ctest-text":
        return framework, (), None
    return framework, ("--reporter=json",), None


def _trusted_pytest_argv(argv: Sequence[str]) -> list[str]:
    lowered = tuple(token.casefold() for token in argv)
    positions = [
        index for index in range(len(lowered) - 1)
        if lowered[index:index + 2] == ("-m", "pytest")
    ]
    if len(positions) != 1:
        raise ControllerError("trusted pytest adapter requires one -m pytest invocation")
    index = positions[0]
    return [
        *argv[:index], "-I", "-c", _TRUSTED_PYTEST_BOOTSTRAP,
        str(Path(__file__).resolve().parent), *argv[index + 2:],
    ]


def _portable_native_stdout(stdout: bytes, native_report: str) -> bytes:
    """Redact exactly the controller-created native report pathname from runner chatter."""
    prefix = r"\\.\pipe\stm32tk-0600-"
    if not native_report.startswith(prefix) or re.fullmatch(r"[0-9a-f]{32}", native_report[len(prefix):]) is None:
        raise ControllerError("native report path is not controller-owned")
    try:
        needle = native_report.encode("utf-8")
    except UnicodeError as exc:
        raise ControllerError("native report path cannot be encoded") from exc
    return stdout.replace(needle, b"<EVIDENCE_ROOT>/native-results.xml")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.kill()


def execute_gate_process(
    gate: GateRequest,
    environment: dict[str, str],
    *,
    evidence_root: Path,
    after_gate_root_create: Callable[[Path], object] | None = None,
) -> GateRunOutput:
    """Execute one catalog argv without a shell and retain one immutable stream/result snapshot."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", gate.gate_id):
        raise ControllerError("gate id cannot name an evidence directory")
    if not gate.argv or any(not token or any(character in token for character in "\r\n") for token in gate.argv):
        raise ControllerError("gate argv is invalid")
    if os.name != "nt" or not evidence_root.is_absolute() or not evidence_root.is_dir():
        raise ControllerError("executor evidence root is invalid")
    gate_root = evidence_root / gate.gate_id
    try:
        framework = native_node_framework(gate.argv)
    except ControllerError:
        if gate.expected_nodes:
            raise
        framework = "opaque"
    native_name = (
        None if framework == "opaque" else
        "native-results.xml" if framework == "pytest-junit" else
        "native-results.txt" if framework == "ctest-text"
        else "native-results.json"
    )
    with ExitStack() as stack:
        evidence_lock = stack.enter_context(_open_locked_windows_directory(evidence_root))
        stack.enter_context(_create_coverage_lock_sentinel(evidence_root))
        _validate_locked_coverage_directory(evidence_lock)
        report_pipe = stack.enter_context(_WindowsNativePipeSink()) if framework == "pytest-junit" else None
        if report_pipe is not None:
            framework, native_tokens, native_report_path = _native_report_argv(gate.argv, report_pipe.name)
        elif framework == "opaque":
            native_tokens, native_report_path = (), None
        else:
            framework, native_tokens, native_report_path = _native_report_argv(gate.argv, "")
        base_environment = _safe_controller_env()
        child_env = {
            key: value
            for key, value in environment.items()
            if key.upper() in {member.upper() for member in base_environment}
        }
        for key, value in base_environment.items():
            child_env.setdefault(key, value)
        child_env["STM32TK_TEST_SEED"] = f"stm32tk-0600:{gate.gate_id}"
        if report_pipe is not None and framework == "pytest-junit":
            child_env[_NATIVE_PIPE_ENV] = report_pipe.name
        process_argv = [*gate.argv, *native_tokens]
        if framework == "pytest-junit":
            process_argv = _trusted_pytest_argv(process_argv)
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        started = time.monotonic_ns()
        process = subprocess.Popen(
            process_argv,
            cwd=gate.cwd,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            shell=False,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=gate.timeout_seconds)
            exit_code = int(process.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            stdout, stderr = process.communicate(timeout=10)
            exit_code = -1
        duration_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
        _validate_locked_coverage_directory(evidence_lock)
        if framework == "opaque":
            native_report = b""
            outcomes = ()
        elif report_pipe is None:
            native_report = stdout
        else:
            native_report = report_pipe.finish()
            if not native_report:
                raise ControllerError("native runner report was not created")
            stdout = _portable_native_stdout(stdout, report_pipe.name)
        if framework != "opaque":
            native_report = normalize_native_artifact(
                framework,
                native_report,
                repository_root=Path(__file__).resolve().parents[2],
                evidence_root=evidence_root,
            )
            if framework in {"vitest-json", "playwright-json"}:
                stdout = native_report
            outcomes = parse_native_node_outcomes(
                framework, native_report, exit_code=exit_code,
            )
        result_value = {
            "schema": "stm32-gate-process-result/1",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "selected_nodes": [node_id for node_id, _ in outcomes],
            "node_outcomes": [
                {"node_id": node_id, "outcome": outcome}
                for node_id, outcome in outcomes
            ],
        }
        payloads = {
            "result.json": canonical_json_bytes(result_value),
            "stderr.log": stderr,
            "stdout.log": stdout,
        }
        if native_name is not None:
            payloads[native_name] = native_report
        try:
            gate_root.mkdir()
        except OSError as exc:
            raise ControllerError("gate evidence directory must be a new path") from exc
        if after_gate_root_create is not None:
            after_gate_root_create(gate_root)
        try:
            gate_lock = stack.enter_context(_open_locked_windows_directory(gate_root))
            stack.enter_context(_create_coverage_lock_sentinel(gate_root))
        except (OSError, ControllerError) as exc:
            raise ControllerError("gate evidence directory is a reparse point or changed identity") from exc
        artifacts: dict[str, _LockedWindowsFile] = {}
        for name in payloads:
            try:
                artifacts[name] = stack.enter_context(_open_locked_windows_file(
                    gate_root / name, create_new=True, write=True,
                ))
            except (OSError, ControllerError) as exc:
                raise ControllerError("gate evidence artifact create-new failed") from exc
        retained: list[dict[str, object]] = []
        for name in sorted(payloads, key=lambda item: item.encode("utf-8")):
            data = payloads[name]
            _windows_write_locked_file(artifacts[name], data)
            if _windows_read_locked_file(artifacts[name]) != data:
                raise ControllerError("gate evidence artifact differs after locked write")
            retained.append({
                "path": f"{gate.gate_id}/{name}",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        _validate_locked_coverage_directory(evidence_lock)
        _validate_locked_coverage_directory(gate_lock)
        return GateRunOutput(
            exit_code,
            stdout,
            stderr,
            tuple(node_id for node_id, _ in outcomes),
            outcomes,
            duration_ms=duration_ms,
            timed_out=timed_out,
            retained_evidence=tuple(retained),
        )


def validate_resource_locks(gates: Sequence[GateRequest]) -> None:
    claims: dict[tuple[str, str], str] = {}
    for gate in gates:
        for kind, identity in (gate.resource_locks or {}).items():
            if not kind or not identity:
                raise ControllerError("resource lock is empty")
            key = (kind, identity)
            if key in claims:
                raise ControllerError(
                    f"resource lock conflict: {kind}:{identity} ({claims[key]}, {gate.gate_id})"
                )
            claims[key] = gate.gate_id


def run_gate_matrix(
    matrix: str,
    gates: Sequence[GateRequest],
    *,
    execute: Callable[[GateRequest, dict[str, str]], GateRunOutput],
    precheck: Callable[[GateRequest], None] | None = None,
    postcheck: Callable[[GateRequest], None] | None = None,
    prerequisite_statuses: Mapping[str, str] | None = None,
    run_id: str = "00000000-0000-4000-8000-000000000000",
    code_head: str = "0" * 40,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[GateResult]:
    if matrix not in {"quick", "candidate", "final-readiness", "final"}:
        raise ControllerError("unknown matrix")
    ids = [gate.gate_id for gate in gates]
    if len(ids) != len(set(ids)):
        raise ControllerError("duplicate gate id")
    initial_statuses = dict(prerequisite_statuses or {})
    if any(
        not isinstance(name, str) or not name or status not in {"PASS", "FAIL", "BLOCKED"}
        for name, status in initial_statuses.items()
    ):
        raise ControllerError("external prerequisite status is invalid")
    known = set(ids) | set(initial_statuses)
    for gate in gates:
        if not set(gate.prerequisites) <= known:
            raise ControllerError("unknown prerequisite")
    validate_resource_locks(gates)
    results: list[GateResult] = []
    statuses: dict[str, str] = initial_statuses
    environment = _safe_controller_env()
    for gate in gates:
        if any(statuses[item] != "PASS" for item in gate.prerequisites):
            output = GateRunOutput(-1, b"", b"", (), ())
            result = GateResult(
                gate.gate_id,
                "BLOCKED",
                "PREREQUISITE_NOT_PASS",
                _metadata(
                    gate, output, run_id=run_id, code_head=code_head, started=now(),
                    decision=_decision_facts(
                        gate, statuses, precheck="NOT_RUN", postcheck="NOT_RUN"
                    ),
                ),
            )
            results.append(result)
            statuses[gate.gate_id] = result.status
            continue
        precheck_state = "NOT_REQUIRED"
        if precheck is not None:
            try:
                precheck(gate)
                precheck_state = "PASS"
            except Exception as exc:  # external/precondition boundary, converted to evidence
                output = GateRunOutput(-1, b"", str(exc).encode("utf-8"), (), ())
                result = GateResult(
                    gate.gate_id,
                    "FAIL",
                    "PRECHECK_FAILED",
                    _metadata(
                        gate, output, run_id=run_id, code_head=code_head, started=now(),
                        decision=_decision_facts(
                            gate, statuses, precheck="FAIL", postcheck="NOT_RUN"
                        ),
                    ),
                )
                results.append(result)
                statuses[gate.gate_id] = result.status
                if matrix == "final":
                    break
                continue
        elif matrix in {"candidate", "final-readiness", "final"}:
            raise ControllerError("matrix precheck is required")
        if matrix == "final-readiness":
            output = GateRunOutput(0, b"", b"", (), ())
            postcheck_state = "NOT_RUN"
        else:
            output = execute(gate, dict(environment))
            if not isinstance(output, GateRunOutput):
                raise ControllerError("executor returned an invalid result")
            postcheck_state = "NOT_REQUIRED"
            if postcheck is not None:
                try:
                    postcheck(gate)
                    postcheck_state = "PASS"
                except Exception:
                    result = GateResult(
                        gate.gate_id,
                        "FAIL",
                        "POSTCHECK_FAILED",
                        _metadata(
                            gate, output, run_id=run_id, code_head=code_head, started=now(),
                            decision=_decision_facts(
                                gate, statuses,
                                precheck=precheck_state, postcheck="FAIL",
                            ),
                        ),
                    )
                    results.append(result)
                    statuses[gate.gate_id] = result.status
                    if matrix == "final":
                        break
                    continue
        node_mismatch = len(output.selected_nodes) != len(set(output.selected_nodes)) or output.selected_nodes != gate.expected_nodes
        outcome_mismatch = (
            tuple(node_id for node_id, _ in output.node_outcomes) != gate.expected_nodes
            or any(outcome not in {"passed", "failed"} for _, outcome in output.node_outcomes)
        )
        if matrix == "final-readiness":
            node_mismatch = False
            outcome_mismatch = False
        failed_node = any(outcome == "failed" for _, outcome in output.node_outcomes)
        status = "PASS" if output.exit_code == 0 and not node_mismatch and not failed_node else "FAIL"
        if outcome_mismatch:
            status = "FAIL"
        reason = "NODE_INVENTORY_MISMATCH" if node_mismatch else "NODE_OUTCOME_MISMATCH" if outcome_mismatch else "PASS" if status == "PASS" else "TIMEOUT" if output.timed_out else "PRODUCT_FAILURE"
        result = GateResult(
            gate.gate_id,
            status,
            reason,
            _metadata(
                gate, output, run_id=run_id, code_head=code_head, started=now(),
                decision=_decision_facts(
                    gate, statuses,
                    precheck=precheck_state, postcheck=postcheck_state,
                ),
            ),
        )
        results.append(result)
        statuses[gate.gate_id] = result.status
        if matrix == "final" and result.status != "PASS":
            break
    return results


def _bind_platform_shards(shards: Sequence[Sequence[GateResult]]) -> list[GateResult]:
    flattened = [result for shard in shards for result in shard]
    run_ids = {str(result.metadata.get("run_id")) for result in flattened}
    if len(run_ids) != 1:
        raise ControllerError("platform shards have mismatched final run id")
    return flattened


run_gate_matrix.bind_platform_shards = _bind_platform_shards  # type: ignore[attr-defined]


def _coverage_configured(environment: Mapping[str, str]) -> bool:
    for key, value in environment.items():
        upper = key.upper()
        if upper.startswith(("COVERAGE_", "COV_CORE_")):
            return True
        if upper == "PYTEST_ADDOPTS" and "cov" in value.casefold():
            return True
    return False


def _within_repo_file(repo: Path, path: Path) -> Path:
    if not repo.is_absolute() or not repo.is_dir() or not path.is_absolute():
        raise ControllerError("repository path must be absolute")
    if any(character in str(path) for character in ";|&><"):
        raise ControllerError("shell token in path")
    try:
        resolved_repo = repo.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_repo)
    except (OSError, ValueError) as exc:
        raise ControllerError("path is outside the repository") from exc
    info = resolved.lstat()
    if resolved.is_symlink() or not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ControllerError("repository path is not a regular committed candidate")
    return resolved


def _default_runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
    return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode


def _load_json(path: Path) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ControllerError("JSON object contains a duplicate key")
            value[key] = item
        return value

    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError("JSON input is unreadable") from exc


def run_performance(
    repo: Path,
    module: str,
    test_file: Path,
    mode: str,
    output: Path,
    performance_config: Path | None,
    runner: Callable[..., int] = _default_runner,
) -> dict[str, object]:
    if module not in KNOWN_MODULES or mode not in {"calibrate", "verify"}:
        raise ControllerError("unknown performance module or mode")
    test = _within_repo_file(repo, test_file)
    if re.fullmatch(r"test_[A-Za-z0-9_]+_performance\.py", test.name) is None:
        raise ControllerError("performance test must be an entire test_*_performance.py file")
    if not output.is_absolute() or output.exists() or not output.parent.is_dir():
        raise ControllerError("performance output must be a new absolute file")
    if _coverage_configured(os.environ):
        raise ControllerError("performance rejects coverage variables")
    test_digest = hashlib.sha256(test.read_bytes()).hexdigest()
    profile_digest = ""
    if mode == "calibrate":
        if performance_config is not None:
            raise ControllerError("calibration does not accept a performance config")
    else:
        if performance_config is None:
            raise ControllerError("verify requires the fixed performance config")
        resolved_config = performance_config.resolve() if performance_config.is_absolute() else (repo / performance_config).resolve()
        fixed_config = repo / "tools/release/performance_0600.json"
        if resolved_config != fixed_config.resolve() or not resolved_config.is_file():
            raise ControllerError("verify requires the fixed performance config")
        try:
            value = load_performance_catalog(resolved_config)
        except (ValueError, OSError) as exc:
            raise ControllerError("performance config is not closed") from exc
        assert isinstance(value, dict)
        matching = [item for item in value["profiles"] if isinstance(item, dict) and item.get("module") == module]
        if len(matching) != 1:
            raise ControllerError("performance profile is missing or duplicated")
        profile = matching[0]
        producers = [item for item in profile["producers"] if item["producer"] == "python"]
        if len(producers) != 1 or producers[0]["test_file"] != test.relative_to(repo.resolve()).as_posix() or producers[0]["test_file_sha256"] != test_digest:
            raise ControllerError("performance workload/config digest mismatch")
        profile_digest = str(profile["profile_sha256"])
    environment = _safe_controller_env()
    environment.update(
        {
            "STM32TK_PERFORMANCE_MODE": mode,
            "STM32TK_PERFORMANCE_MODULE": module,
            "STM32TK_PERFORMANCE_OUTPUT": str(output),
            "STM32TK_PERFORMANCE_TEST_SHA256": test_digest,
            "STM32TK_PERFORMANCE_PROFILE_SHA256": profile_digest,
        }
    )
    return_code = runner([sys.executable, "-m", "pytest", str(test)], cwd=repo, env=environment)
    if return_code != 0 or not output.is_file():
        raise ControllerError("performance test did not produce a successful output")
    retained = output.read_bytes()
    result = _load_json(output)
    if (
        not isinstance(result, dict)
        or result["mode"] != mode
        or result["module"] != module
        or result["producer"] != "python"
        or result["profile_sha256"] != (profile_digest or None)
        or result["test_file"] != test.relative_to(repo.resolve()).as_posix()
        or result["test_file_sha256"] != test_digest
    ):
        raise ControllerError("performance output is stale or malformed")
    try:
        validated = validate_performance_run(result)
    except ValueError as exc:
        raise ControllerError("performance output is stale or malformed") from exc
    if output.read_bytes() != retained:
        raise ControllerError("performance output changed during validation")
    assert isinstance(validated, dict)
    if mode == "verify":
        runtime_version = validated["environment"]["python_version"]
        catalog_workloads = {item["id"]: item for item in producers[0]["workloads"]}
        for workload in validated["workloads"]:
            accepted = catalog_workloads.get(workload["id"])
            if accepted is None or accepted["workload_sha256"] != workload["workload_sha256"]:
                raise ControllerError("performance output workload differs from the accepted profile")
            calibrations = [
                item for item in accepted["calibrations"]
                if item["runtime"] == {"kind": "cpython", "version": runtime_version}
            ]
            if (
                len(calibrations) != 1
                or workload["accepted_baseline"] != calibrations[0]["baseline"]
                or workload["absolute_threshold"] != calibrations[0]["absolute_threshold"]
                or validated["environment_sha256"] != calibrations[0]["environment_sha256"]
            ):
                raise ControllerError("performance output thresholds differ from the accepted runtime calibration")
    return validated


def _changed_product_files(repo: Path, git_runner: Callable[[list[str]], list[str]]) -> list[str]:
    candidates = git_runner(["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"]) + git_runner(["ls-files", "--others", "--exclude-standard"])
    product_prefixes = (
        "tools/stm32-toolkit/src/stm32_toolkit/",
        "tools/stm32-monitor/src/stm32_monitor/",
    )
    normalized = [item.replace("\\", "/") for item in candidates]
    paths = [
        item for item in normalized
        if item.startswith(product_prefixes) and item.casefold().endswith(".py")
    ]
    if not paths:
        raise ControllerError("no changed product Python file")
    if len(paths) != len(set(paths)) or len(paths) != len({item.casefold() for item in paths}):
        raise ControllerError("changed product file duplicate")
    for relative in paths:
        _within_repo_file(repo, repo.joinpath(*relative.split("/")))
    return sorted(paths, key=lambda item: item.encode("utf-8"))


def _coverage_module_for_product_file(relative: str) -> str:
    roots = (
        ("tools/stm32-toolkit/src/", "stm32_toolkit"),
        ("tools/stm32-monitor/src/", "stm32_monitor"),
    )
    matching = [(prefix, package) for prefix, package in roots if relative.startswith(prefix)]
    if len(matching) != 1 or not relative.endswith(".py"):
        raise ControllerError("changed product module path is invalid")
    prefix, package = matching[0]
    parts = relative[len(prefix):-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    if not parts or parts[0] != package or any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) is None for part in parts):
        raise ControllerError("changed product module path is invalid")
    return ".".join(parts)


def _validate_coverage_basetemp(repo: Path, task_id: str, value: str) -> Path:
    if task_id != "STM32TK-0603-T12":
        raise ControllerError("coverage basetemp is not allowed for this task")
    if (
        not value
        or any(character in value for character in ";|&><\r\n")
        or any(character.isspace() for character in value)
        or "/" in value
        or re.search(r"(?:^|\\)\.\.?(?:\\|$)", value) is not None
    ):
        raise ControllerError("coverage basetemp is invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or value != str(path)
        or value != os.path.abspath(value)
        or value != FROZEN_T12_BASETEMP_TOKEN
    ):
        raise ControllerError("coverage basetemp is not the frozen canonical token")
    return path


def _coverage_windows_available() -> bool:
    return os.name == "nt"


def _validate_coverage_attempt_location(repo: Path, evidence_root: Path) -> None:
    """Validate the frozen direct-child create-new location before claiming it."""
    if not _coverage_windows_available():
        raise ControllerError("development coverage requires Windows directory locking")
    temporary_root = Path(r"C:\tmp")
    if (
        not evidence_root.is_absolute()
        or str(evidence_root) != os.path.abspath(evidence_root)
        or evidence_root.parent != temporary_root
        or not evidence_root.name
    ):
        raise ControllerError("coverage evidence root must be a canonical direct child of C:\\tmp")
    if not temporary_root.is_dir() or _is_reparse(temporary_root):
        raise ControllerError("coverage temporary root is a reparse point or unavailable")
    try:
        evidence_root.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ControllerError("coverage evidence target state is unreadable") from exc
    else:
        if _is_reparse(evidence_root):
            raise ControllerError("coverage evidence target is a reparse point")
        raise ControllerError("coverage evidence root must be a new path")
    try:
        evidence_root.relative_to(repo.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ControllerError("coverage evidence root must resolve outside the repository")


def _windows_final_path(kernel32: object, handle: int) -> Path:
    kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    ]
    kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    required = kernel32.GetFinalPathNameByHandleW(wintypes.HANDLE(handle), None, 0, 0)
    if required == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = kernel32.GetFinalPathNameByHandleW(wintypes.HANDLE(handle), buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _windows_directory_information(kernel32: object, handle: int) -> _ByHandleFileInformation:
    kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    information = _ByHandleFileInformation()
    if not kernel32.GetFileInformationByHandle(wintypes.HANDLE(handle), ctypes.byref(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    return information


def _close_windows_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    if not kernel32.CloseHandle(wintypes.HANDLE(handle)):
        raise ctypes.WinError(ctypes.get_last_error())


def _open_locked_windows_file(
    path: Path,
    *,
    create_new: bool,
    write: bool,
    cleanup: bool = False,
    share_write: bool = True,
) -> _LockedWindowsFile:
    if not _coverage_windows_available():
        raise ControllerError("development coverage requires Windows file locking")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    desired_access = 0x80000000 | (0x40000000 if write else 0)
    handle = kernel32.CreateFileW(
        str(path),
        desired_access,
        0x00000001 | (0x00000002 if share_write else 0),
        None,
        1 if create_new else 3,
        0x00200000,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    handle_value = handle if isinstance(handle, int) else handle.value
    if handle_value in (None, invalid):
        error = ctypes.WinError(ctypes.get_last_error())
        raise ControllerError("coverage file handle open/create failed") from error
    try:
        information = _windows_directory_information(kernel32, handle_value)
        if information.file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
            raise ControllerError("coverage locked file is a directory")
        if information.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ControllerError("coverage locked file is a reparse point")
        if information.number_of_links != 1:
            raise ControllerError("coverage locked file has multiple hard links")
        final_path = _windows_final_path(kernel32, handle_value)
        if os.path.normcase(str(final_path)) != os.path.normcase(os.path.abspath(path)):
            raise ControllerError("coverage locked file resolves to another path")
        return _LockedWindowsFile(
            path, handle_value, information.volume_serial,
            (information.file_index_high << 32) | information.file_index_low,
            cleanup=cleanup,
        )
    except BaseException:
        kernel32.CloseHandle(wintypes.HANDLE(handle_value))
        raise


def _validate_locked_coverage_file(locked: _LockedWindowsFile) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        information = _windows_directory_information(kernel32, locked.handle)
        final_path = _windows_final_path(kernel32, locked.handle)
    except OSError as exc:
        raise ControllerError("coverage locked file became unreadable") from exc
    identity = (
        information.volume_serial,
        (information.file_index_high << 32) | information.file_index_low,
    )
    if identity != (locked.volume_serial, locked.file_index):
        raise ControllerError("coverage locked file identity changed")
    if (
        information.file_attributes & (stat.FILE_ATTRIBUTE_DIRECTORY | stat.FILE_ATTRIBUTE_REPARSE_POINT)
        or information.number_of_links != 1
        or os.path.normcase(str(final_path)) != os.path.normcase(os.path.abspath(locked.path))
    ):
        raise ControllerError("coverage locked file path changed")


def _validate_locked_coverage_file_path(locked: _LockedWindowsFile) -> None:
    _validate_locked_coverage_file(locked)
    with _open_locked_windows_file(locked.path, create_new=False, write=False) as current:
        if (current.volume_serial, current.file_index) != (locked.volume_serial, locked.file_index):
            raise ControllerError("coverage locked file path identity changed")


def _create_coverage_lock_sentinel(root: Path) -> _LockedWindowsFile:
    # This closes accidental/injected replacement windows; deliberate ACL changes by the
    # same SID and higher-privilege processes are outside the controller threat model.
    path = root / f".stm32tk-coverage-lock-{secrets.token_hex(16)}"
    return _open_locked_windows_file(path, create_new=True, write=True, cleanup=True)


def _windows_read_locked_file(locked: _LockedWindowsFile) -> bytes:
    _validate_locked_coverage_file_path(locked)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD,
    ]
    kernel32.SetFilePointerEx.restype = wintypes.BOOL
    new_position = ctypes.c_longlong()
    if not kernel32.SetFilePointerEx(
        wintypes.HANDLE(locked.handle), 0, ctypes.byref(new_position), 0
    ) or new_position.value != 0:
        raise ControllerError("coverage locked file rewind failed") from ctypes.WinError(ctypes.get_last_error())
    kernel32.GetFileSizeEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong)]
    kernel32.GetFileSizeEx.restype = wintypes.BOOL
    size = ctypes.c_longlong()
    if not kernel32.GetFileSizeEx(wintypes.HANDLE(locked.handle), ctypes.byref(size)):
        raise ControllerError("coverage locked file size is unreadable") from ctypes.WinError(ctypes.get_last_error())
    if size.value < 0 or size.value > 64 * 1024 * 1024:
        raise ControllerError("coverage locked file size is outside bounds")
    buffer = ctypes.create_string_buffer(size.value or 1)
    read = wintypes.DWORD()
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    if not kernel32.ReadFile(
        wintypes.HANDLE(locked.handle), buffer, size.value, ctypes.byref(read), None
    ):
        raise ControllerError("coverage locked file read failed") from ctypes.WinError(ctypes.get_last_error())
    if read.value != size.value:
        raise ControllerError("coverage locked file read was incomplete")
    _validate_locked_coverage_file_path(locked)
    return bytes(buffer.raw[:read.value])


def _windows_write_locked_file(locked: _LockedWindowsFile, data: bytes) -> None:
    _validate_locked_coverage_file_path(locked)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD,
    ]
    kernel32.SetFilePointerEx.restype = wintypes.BOOL
    new_position = ctypes.c_longlong()
    if not kernel32.SetFilePointerEx(
        wintypes.HANDLE(locked.handle), 0, ctypes.byref(new_position), 0
    ) or new_position.value != 0:
        raise ControllerError("coverage locked result rewind failed") from ctypes.WinError(ctypes.get_last_error())
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel32.FlushFileBuffers.restype = wintypes.BOOL
    written = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(data)
    if not kernel32.WriteFile(
        wintypes.HANDLE(locked.handle), buffer, len(data), ctypes.byref(written), None
    ):
        raise ControllerError("coverage locked result write failed") from ctypes.WinError(ctypes.get_last_error())
    if written.value != len(data):
        raise ControllerError("coverage locked result write was incomplete")
    kernel32.SetEndOfFile.argtypes = [wintypes.HANDLE]
    kernel32.SetEndOfFile.restype = wintypes.BOOL
    if not kernel32.SetEndOfFile(wintypes.HANDLE(locked.handle)):
        raise ControllerError("coverage locked result truncate failed") from ctypes.WinError(ctypes.get_last_error())
    if not kernel32.FlushFileBuffers(wintypes.HANDLE(locked.handle)):
        raise ControllerError("coverage locked result flush failed") from ctypes.WinError(ctypes.get_last_error())
    _validate_locked_coverage_file_path(locked)


def _load_locked_coverage_json(locked: _LockedWindowsFile) -> object:
    return _load_coverage_json_bytes(_windows_read_locked_file(locked))


def _load_coverage_json_bytes(raw: bytes) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ControllerError("JSON object contains a duplicate key")
            value[key] = item
        return value

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError("coverage JSON input is unreadable") from exc


def _open_locked_windows_directory(path: Path) -> _LockedWindowsDirectory:
    """Lock/recheck accidental or injected races; not a same-SID hostile-process boundary."""
    if not _coverage_windows_available():
        raise ControllerError("development coverage requires Windows directory locking")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(path),
        0x0080,
        0x00000001 | 0x00000002,
        None,
        3,
        0x00200000 | 0x02000000,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    handle_value = handle if isinstance(handle, int) else handle.value
    if handle_value in (None, invalid):
        error = ctypes.WinError(ctypes.get_last_error())
        raise ControllerError("coverage directory handle open failed") from error
    try:
        information = _windows_directory_information(kernel32, handle_value)
        if not information.file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
            raise ControllerError("coverage locked path is not a directory")
        if information.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ControllerError("coverage locked directory is a reparse point")
        final_path = _windows_final_path(kernel32, handle_value)
        if os.path.normcase(str(final_path)) != os.path.normcase(os.path.abspath(path)):
            raise ControllerError("coverage locked directory resolves to another path")
        return _LockedWindowsDirectory(
            path, handle_value, information.volume_serial,
            (information.file_index_high << 32) | information.file_index_low,
        )
    except BaseException:
        kernel32.CloseHandle(wintypes.HANDLE(handle_value))
        raise


def _validate_locked_coverage_directory(locked: _LockedWindowsDirectory) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        information = _windows_directory_information(kernel32, locked.handle)
        final_path = _windows_final_path(kernel32, locked.handle)
    except OSError as exc:
        raise ControllerError("coverage locked directory became unreadable") from exc
    identity = (
        information.volume_serial,
        (information.file_index_high << 32) | information.file_index_low,
    )
    if identity != (locked.volume_serial, locked.file_index):
        raise ControllerError("coverage locked directory identity changed")
    if (
        not information.file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY
        or information.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or os.path.normcase(str(final_path)) != os.path.normcase(os.path.abspath(locked.path))
        or not locked.path.is_dir()
        or _is_reparse(locked.path)
    ):
        raise ControllerError("coverage locked directory path changed")
    with _open_locked_windows_directory(locked.path) as current:
        if (current.volume_serial, current.file_index) != (locked.volume_serial, locked.file_index):
            raise ControllerError("coverage locked directory path identity changed")


def _verify_coverage_attempt_basetemp(evidence_root: Path, basetemp: Path, *, created: bool) -> None:
    """Keep high-entropy pytest scratch lexically bound and reject reparse state."""
    if (
        basetemp.parent != evidence_root
        or re.fullmatch(r"pytest-basetemp-[0-9a-f]{32}", basetemp.name) is None
        or str(basetemp) != os.path.abspath(basetemp)
    ):
        raise ControllerError("coverage basetemp is not bound to the evidence attempt")
    try:
        basetemp.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ControllerError("coverage basetemp state is unreadable") from exc
    else:
        if not created:
            raise ControllerError("coverage basetemp must remain absent before pytest")
        if not basetemp.is_dir() or _is_reparse(basetemp) or basetemp.resolve().parent != evidence_root:
            raise ControllerError("coverage basetemp result is not a retained private directory")
        return
    if created:
        raise ControllerError("coverage basetemp result is missing")


def _validate_coverage_regular_child(evidence_root: Path, path: Path, name: str) -> None:
    if path != evidence_root / name:
        raise ControllerError("coverage retained path is not bound to the evidence attempt")
    try:
        information = path.lstat()
    except OSError as exc:
        raise ControllerError("coverage retained file is missing or unreadable") from exc
    if not stat.S_ISREG(information.st_mode) or _is_reparse(path) or path.resolve().parent != evidence_root:
        raise ControllerError("coverage retained output is not a regular bound file")


def _validate_coverage_raw_path(evidence_root: Path, raw_path: Path) -> None:
    _validate_coverage_regular_child(evidence_root, raw_path, "coverage-raw.json")


def _validate_coverage_pytest_tokens(
    repo: Path, task_id: str, pytest_tokens: Sequence[str]
) -> list[str]:
    if not pytest_tokens:
        raise ControllerError("coverage pytest tokens are missing")
    validated: list[str] = []
    seen_quiet = False
    seen_plugin = False
    seen_basetemp = False
    seen_coverage: set[str] = set()
    index = 0
    while index < len(pytest_tokens):
        token = pytest_tokens[index]
        if not isinstance(token, str) or not token or any(character in token for character in ";|&><\r\n") or any(char.isspace() for char in token):
            raise ControllerError("coverage shell token is forbidden")
        if token == "-q":
            if seen_quiet:
                raise ControllerError("coverage quiet option is duplicated")
            seen_quiet = True
        elif token == "-p":
            if seen_plugin or index + 1 >= len(pytest_tokens) or pytest_tokens[index + 1] != "no:cacheprovider":
                raise ControllerError("coverage plugin option is invalid")
            seen_plugin = True
            validated.extend((token, "no:cacheprovider"))
            index += 2
            continue
        elif token == "no:cacheprovider":
            raise ControllerError("coverage plugin value is unpaired")
        elif token == "--basetemp":
            if seen_basetemp or index + 1 >= len(pytest_tokens):
                raise ControllerError("coverage basetemp option is invalid")
            value = pytest_tokens[index + 1]
            if not isinstance(value, str):
                raise ControllerError("coverage basetemp option is invalid")
            basetemp = _validate_coverage_basetemp(repo, task_id, value)
            seen_basetemp = True
            validated.extend((token, str(basetemp)))
            index += 2
            continue
        elif token.startswith("--cov="):
            module = token.removeprefix("--cov=")
            if re.fullmatch(r"(?:stm32_toolkit|stm32_monitor)(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module) is None:
                raise ControllerError("coverage module is invalid")
            if module in seen_coverage:
                index += 1
                continue
            seen_coverage.add(module)
        elif token.startswith("-"):
            raise ControllerError("coverage option is not allowed")
        else:
            path = Path(token)
            if not path.is_absolute():
                path = repo / path
            test = _within_repo_file(repo, path)
            relative = test.relative_to(repo.resolve()).as_posix()
            test_prefixes = (
                "tools/stm32-toolkit/tests/",
                "tools/stm32-monitor/tests/",
            )
            if not relative.startswith(test_prefixes) or not test.name.startswith("test_") or test.suffix != ".py":
                raise ControllerError("coverage test path is invalid")
            token = str(test)
        validated.append(token)
        index += 1
    return validated


def _default_git_runner(repo: Path) -> Callable[[list[str]], list[str]]:
    def run(args: list[str]) -> list[str]:
        completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ControllerError("git discovery failed")
        return [line for line in completed.stdout.splitlines() if line]

    return run


def _coverage_percent(covered_lines: int, statements: int, covered_branches: int, branches: int) -> float:
    denominator = statements + branches
    return 100.0 if denominator == 0 else (covered_lines + covered_branches) * 100.0 / denominator


def _validate_coverage_percent(value: object, expected: float, *, display: bool = False) -> None:
    if display:
        if 0 < expected < 1:
            expected_display = "1"
        elif 99 < expected < 100:
            expected_display = "99"
        else:
            expected_display = f"{expected:.0f}"
        if not isinstance(value, str) or value != expected_display:
            raise ControllerError("coverage summary display percent is invalid")
        return
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not math.isclose(float(value), expected, rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise ControllerError("coverage summary percent is invalid")


def _validate_coverage_summary(value: object, *, extended: bool) -> dict[str, object]:
    expected_keys = COVERAGE_SUMMARY_EXTENDED_KEYS if extended else COVERAGE_SUMMARY_BASE_KEYS
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ControllerError("coverage summary is not closed")
    integer_fields = {
        "covered_lines", "num_statements", "missing_lines", "excluded_lines", "num_branches",
        "num_partial_branches", "covered_branches", "missing_branches",
    }
    for field in integer_fields:
        item = value[field]
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ControllerError("coverage summary counter is invalid")
    if value["covered_lines"] + value["missing_lines"] != value["num_statements"]:
        raise ControllerError("coverage line counters are inconsistent")
    if value["covered_branches"] + value["missing_branches"] != value["num_branches"]:
        raise ControllerError("coverage branch counters are inconsistent")
    if value["num_partial_branches"] > value["num_branches"]:
        raise ControllerError("coverage partial branch count is invalid")
    combined = _coverage_percent(
        value["covered_lines"], value["num_statements"], value["covered_branches"], value["num_branches"]
    )
    _validate_coverage_percent(value["percent_covered"], combined)
    _validate_coverage_percent(value["percent_covered_display"], combined, display=True)
    if extended:
        statements = 100.0 if value["num_statements"] == 0 else value["covered_lines"] * 100.0 / value["num_statements"]
        branches = 100.0 if value["num_branches"] == 0 else value["covered_branches"] * 100.0 / value["num_branches"]
        _validate_coverage_percent(value["percent_statements_covered"], statements)
        _validate_coverage_percent(value["percent_statements_covered_display"], statements, display=True)
        _validate_coverage_percent(value["percent_branches_covered"], branches)
        _validate_coverage_percent(value["percent_branches_covered_display"], branches, display=True)
    return value


def _validate_coverage_v7(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"meta", "files", "totals"}:
        raise ControllerError("coverage JSON root is invalid")
    meta = value["meta"]
    if not isinstance(meta, dict) or set(meta) != COVERAGE_META_KEYS:
        raise ControllerError("coverage metadata is not closed")
    if (
        not isinstance(meta["format"], int)
        or isinstance(meta["format"], bool)
        or meta["format"] != 3
        or not isinstance(meta["version"], str)
        or re.fullmatch(r"7\.[0-9]+\.[0-9]+", meta["version"]) is None
        or not isinstance(meta["timestamp"], str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?", meta["timestamp"]) is None
        or meta["branch_coverage"] is not True
        or meta["show_contexts"] is not False
    ):
        raise ControllerError("coverage metadata is invalid")
    files = value["files"]
    if not isinstance(files, dict):
        raise ControllerError("coverage files are invalid")
    version = tuple(int(part) for part in meta["version"].split("."))
    extended = version >= (7, 15, 0)
    summaries: list[dict[str, object]] = []
    for details in files.values():
        if not isinstance(details, dict) or set(details) != COVERAGE_ROW_KEYS:
            raise ControllerError("coverage row is invalid")
        for field in ("executed_lines", "missing_lines", "excluded_lines", "executed_branches", "missing_branches"):
            if not isinstance(details[field], list):
                raise ControllerError("coverage row list is invalid")
        if not isinstance(details["functions"], dict) or not isinstance(details["classes"], dict):
            raise ControllerError("coverage row detail map is invalid")
        summaries.append(_validate_coverage_summary(details["summary"], extended=extended))
    totals = _validate_coverage_summary(value["totals"], extended=extended)
    for field in (
        "covered_lines", "num_statements", "missing_lines", "excluded_lines", "num_branches",
        "num_partial_branches", "covered_branches", "missing_branches",
    ):
        if totals[field] != sum(summary[field] for summary in summaries):
            raise ControllerError("coverage totals do not match file summaries")
    return value


def run_dev_coverage(
    repo: Path,
    task_id: str,
    evidence_root: Path,
    pytest_tokens: Sequence[str],
    git_runner: Callable[[list[str]], list[str]] | None = None,
    runner: Callable[..., int] = _default_runner,
) -> dict[str, object]:
    scoped_task = COVERAGE_TASK_ID.fullmatch(task_id)
    if task_id not in KNOWN_MODULES and (
        scoped_task is None or scoped_task.group("module") not in KNOWN_MODULES
    ):
        raise ControllerError("unknown coverage task")
    validated = _validate_coverage_pytest_tokens(repo, task_id, pytest_tokens)
    changed = _changed_product_files(repo, git_runner or _default_git_runner(repo))
    requested_coverage = {token.removeprefix("--cov=") for token in validated if token.startswith("--cov=")}
    for module in sorted({_coverage_module_for_product_file(path) for path in changed} - requested_coverage):
        validated.append(f"--cov={module}")
    if _coverage_configured(os.environ):
        raise ControllerError("dev coverage rejects inherited coverage variables")
    basetemp_index = validated.index("--basetemp") if "--basetemp" in validated else None
    _validate_coverage_attempt_location(repo, evidence_root)
    with _open_locked_windows_directory(Path(r"C:\tmp")) as temporary_lock:
        with _create_coverage_lock_sentinel(temporary_lock.path) as temporary_sentinel:
            _validate_locked_coverage_file(temporary_sentinel)
            _validate_locked_coverage_directory(temporary_lock)
            _validate_coverage_attempt_location(repo, evidence_root)
            evidence = prepare_evidence_root(evidence_root)
            with _open_locked_windows_directory(evidence) as evidence_lock:
                with _create_coverage_lock_sentinel(evidence) as evidence_sentinel:
                    _validate_locked_coverage_file(evidence_sentinel)
                    return _run_locked_dev_coverage(
                        repo, task_id, evidence, validated, changed, basetemp_index,
                        temporary_lock, evidence_lock, runner,
                    )


def _run_locked_dev_coverage(
    repo: Path,
    task_id: str,
    evidence: Path,
    validated: list[str],
    changed: list[str],
    basetemp_index: int | None,
    temporary_lock: _LockedWindowsDirectory,
    evidence_lock: _LockedWindowsDirectory,
    runner: Callable[..., int],
) -> dict[str, object]:
    _validate_locked_coverage_directory(temporary_lock)
    _validate_locked_coverage_directory(evidence_lock)
    basetemp: Path | None = None
    if basetemp_index is not None:
        basetemp = evidence / f"pytest-basetemp-{secrets.token_hex(16)}"
        validated[basetemp_index + 1] = str(basetemp)
        _verify_coverage_attempt_basetemp(evidence, basetemp, created=False)
    with _WindowsNativePipeSink() as raw_pipe:
        return _complete_locked_dev_coverage(
            repo, task_id, evidence, validated, changed, basetemp,
            raw_pipe, temporary_lock, evidence_lock, runner,
        )


def _complete_locked_dev_coverage(
    repo: Path,
    task_id: str,
    evidence: Path,
    validated: list[str],
    changed: list[str],
    basetemp: Path | None,
    raw_pipe: _WindowsNativePipeSink,
    temporary_lock: _LockedWindowsDirectory,
    evidence_lock: _LockedWindowsDirectory,
    runner: Callable[..., int],
) -> dict[str, object]:
    argv = [
        sys.executable, "-m", "pytest", *validated,
        "-p", "pytest_cov", "--cov-branch",
        f"--cov-report=json:{raw_pipe.name}",
    ]
    if basetemp is not None:
        _verify_coverage_attempt_basetemp(evidence, basetemp, created=False)
    _validate_locked_coverage_directory(temporary_lock)
    _validate_locked_coverage_directory(evidence_lock)
    child_env = _safe_controller_env()
    child_env[_NATIVE_PIPE_ENV] = raw_pipe.name
    return_code = runner(_trusted_pytest_argv(argv), cwd=repo, env=child_env)
    raw_bytes = raw_pipe.finish()
    _validate_locked_coverage_directory(temporary_lock)
    _validate_locked_coverage_directory(evidence_lock)
    if basetemp is not None:
        _verify_coverage_attempt_basetemp(evidence, basetemp, created=True)
    raw_path = evidence / "coverage-raw.json"
    try:
        with _open_locked_windows_file(raw_path, create_new=True, write=True) as raw_lock:
            _windows_write_locked_file(raw_lock, raw_bytes)
            _validate_locked_coverage_file_path(raw_lock)
    except ControllerError as exc:
        raise ControllerError("coverage raw result create-new write failed") from exc
    if return_code != 0:
        raise ControllerError("coverage subprocess failed")
    _validate_locked_coverage_directory(temporary_lock)
    _validate_locked_coverage_directory(evidence_lock)
    raw = _load_coverage_json_bytes(raw_bytes)
    _validate_locked_coverage_directory(temporary_lock)
    _validate_locked_coverage_directory(evidence_lock)
    _validate_coverage_raw_path(evidence, raw_path)
    parsed = _validate_coverage_v7(raw)
    rows: dict[str, tuple[int, int]] = {}
    folded: set[str] = set()
    for raw_path_name, details in parsed["files"].items():
        if not isinstance(raw_path_name, str) or not isinstance(details, dict):
            raise ControllerError("coverage row is invalid")
        path = Path(raw_path_name)
        if path.is_absolute():
            try:
                name = path.resolve().relative_to(repo.resolve()).as_posix()
            except ValueError as exc:
                raise ControllerError("coverage row escapes repository") from exc
        else:
            name = raw_path_name.replace("\\", "/")
        if name.casefold() in folded:
            raise ControllerError("coverage row case-fold duplicate")
        summary = details["summary"]
        covered, total = summary["covered_branches"], summary["num_branches"]
        if not isinstance(covered, int) or isinstance(covered, bool) or not isinstance(total, int) or isinstance(total, bool) or covered < 0 or total < 0 or covered > total:
            raise ControllerError("coverage branch counts are invalid")
        rows[name] = (covered, total)
        folded.add(name.casefold())
    normalized: list[dict[str, object]] = []
    for path in changed:
        matching = [name for name in rows if name.casefold() == path.casefold()]
        if matching != [path]:
            raise ControllerError("changed product file is missing from coverage output")
        covered, total = rows[path]
        percent = 100 if total == 0 else covered * 100 // total
        if percent < 90:
            raise ControllerError("changed product file is below 90% branch coverage")
        normalized.append({"covered_branches": covered, "num_branches": total, "path": path, "percent": percent})
    result = {"schema": "stm32-dev-branch-coverage/1", "task_id": task_id, "files": normalized}
    result_path = evidence / "branch-coverage.json"
    _validate_locked_coverage_directory(evidence_lock)
    try:
        with _open_locked_windows_file(result_path, create_new=True, write=True) as locked_result:
            _windows_write_locked_file(locked_result, canonical_json_bytes(result))
            _validate_locked_coverage_file_path(locked_result)
            _validate_locked_coverage_directory(evidence_lock)
            return result
    except ControllerError as exc:
        raise ControllerError("coverage normalized result create-new write failed") from exc


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _support_files(root: Path) -> dict[str, Path]:
    members: dict[str, Path] = {}
    folded: set[str] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ControllerError("support root is unreadable") from exc
        for entry in entries:
            path = Path(entry.path)
            if _is_reparse(path):
                raise ControllerError("support root contains a link/reparse entry")
            relative = path.relative_to(root).as_posix()
            if relative.casefold() in folded:
                raise ControllerError("support root contains a case-fold duplicate")
            folded.add(relative.casefold())
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
            elif entry.is_file(follow_symlinks=False):
                members[relative] = path
            else:
                raise ControllerError("support root contains a special file")
    return members


def verify_support_root(
    support_profile: Path, *, before_reread: Callable[[], object] | None = None
) -> dict[str, object]:
    if not support_profile.is_absolute():
        raise ControllerError("support profile must be absolute")
    try:
        profile = support_profile.resolve(strict=True)
        root = profile.parents[1]
        if profile.relative_to(root).as_posix() != "feasibility/profile.json":
            raise ControllerError("support profile path is not frozen")
    except (OSError, ValueError) as exc:
        raise ControllerError("support profile is unavailable") from exc
    manifest_path = root / "support-manifest.json"
    members = _support_files(root)
    manifest_bytes = manifest_path.read_bytes()
    value = _load_json(manifest_path)
    if not isinstance(value, dict) or set(value) != {"schema", "files"} or value["schema"] != "stm32tk-0600-support-manifest/1" or not isinstance(value["files"], list):
        raise ControllerError("support manifest is not closed")
    expected_paths: list[str] = []
    first_reads: dict[str, bytes] = {}
    declared_entries: dict[str, Mapping[str, object]] = {}
    folded: set[str] = set()
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise ControllerError("support manifest entry is not closed")
        relative = item["path"]
        if not isinstance(relative, str) or not relative or "\\" in relative or relative.startswith("/") or any(part in {"", ".", ".."} for part in relative.split("/")) or relative.casefold() in folded:
            raise ControllerError("support manifest path is invalid or duplicated")
        if relative not in members or relative == "support-manifest.json":
            raise ControllerError("support manifest member is missing")
        data = members[relative].read_bytes()
        if not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or item["bytes"] != len(data) or item["sha256"] != hashlib.sha256(data).hexdigest():
            raise ControllerError("support manifest bytes/digest mismatch")
        expected_paths.append(relative)
        folded.add(relative.casefold())
        first_reads[relative] = data
        declared_entries[relative] = item
    if set(members) != set(expected_paths) | {"support-manifest.json"}:
        raise ControllerError("support root has missing or extra entries")
    profile_value = _load_json(profile)
    feasibility = _feasibility_module()
    feasibility_result = feasibility.verify_feasibility(profile_value)
    if feasibility_result.code != "PASS" or not isinstance(profile_value, Mapping):
        raise ControllerError("support profile is not the Task 1 feasibility contract")
    if (
        profile_value["windows_owner"] != "Codex"
        or profile_value["capabilities"] != FROZEN_CAPABILITIES
        or not isinstance(profile_value["tools"], Mapping)
        or {
            name: profile_value["tools"][name]["version"]
            for name in FEASIBILITY_REQUIRED_TOOLS
        } != FROZEN_TOOL_VERSIONS
    ):
        raise ControllerError("support owner/capability/tool versions are not frozen")
    binding_error = feasibility._profile_manifest_bindings(profile_value, declared_entries)
    if binding_error is not None:
        raise ControllerError("support profile references are not manifest-bound")
    for name in FEASIBILITY_REQUIRED_TOOLS:
        try:
            feasibility._tool_record(root, profile_value["tools"][name], name)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ControllerError("support tool record is not frozen") from exc
    chromium = profile_value["chromium"]
    assert isinstance(chromium, Mapping)
    if (
        chromium["version"] != "141.0.7390.37"
        or feasibility._tree_digest(declared_entries, str(chromium["package_root"]))
        != chromium["package_tree_sha256"]
    ):
        raise ControllerError("managed Chromium package/version proof is invalid")
    version_path = root.joinpath(*str(chromium["version_evidence"]["path"]).split("/"))
    try:
        if feasibility.managed_chromium_version(version_path.read_bytes()) != chromium["version"]:
            raise ControllerError("managed Chromium version evidence mismatches")
        feasibility._load_managed_profile_seed(root, chromium)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ControllerError("managed Chromium launch/profile proof is invalid") from exc
    if before_reread is not None:
        before_reread()
    if manifest_path.read_bytes() != manifest_bytes:
        raise ControllerError("support manifest changed during verification")
    for relative, first in first_reads.items():
        if members[relative].read_bytes() != first:
            raise ControllerError("support cache changed during verification")
    profile_data = first_reads["feasibility/profile.json"]
    return {
        "profile": {"path": "feasibility/profile.json", "bytes": len(profile_data), "sha256": hashlib.sha256(profile_data).hexdigest()},
        "manifest": {"path": "support-manifest.json", "bytes": len(manifest_bytes), "sha256": hashlib.sha256(manifest_bytes).hexdigest()},
    }


def load_hardware_campaign_input(
    path: Path,
    *,
    expected_generator_code_head: str,
    expected_evidence_owner: str = "user",
) -> tuple[Path, dict[str, str], dict[str, object]]:
    """Validate the closed 0603 campaign and return its support/identity bindings."""
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or str(path) != os.path.abspath(path)
    ):
        raise ControllerError("hardware campaign input path is not a canonical regular file")
    campaign_bytes = path.read_bytes()
    campaign = _load_json(path)
    if (
        not isinstance(campaign, dict)
        or campaign_bytes != canonical_json_bytes(campaign)
        or campaign.get("generator_code_head") != expected_generator_code_head
        or campaign.get("evidence_owner") != expected_evidence_owner
    ):
        raise ControllerError("hardware campaign input is not canonical/closed")
    try:
        retained = _release_call(
            "_validate_hardware",
            campaign,
            product_0603=expected_generator_code_head,
            owner=expected_evidence_owner,
        )
    except VerificationError as exc:
        raise ControllerError(str(exc)) from exc
    if not isinstance(retained, dict):
        raise ControllerError("hardware campaign retained file snapshot is invalid")
    support_reference = campaign.get("support_profile")
    if not isinstance(support_reference, dict) or not isinstance(support_reference.get("path"), str):
        raise ControllerError("hardware campaign support profile is invalid")
    support_profile = Path(str(support_reference["path"]))
    support_binding = verify_support_root(support_profile)
    manifest_reference = campaign.get("support_manifest")
    if (
        not isinstance(manifest_reference, dict)
        or support_binding["profile"] != {
            "path": "feasibility/profile.json",
            "bytes": support_reference.get("bytes"),
            "sha256": support_reference.get("sha256"),
        }
        or support_binding["manifest"] != {
            "path": "support-manifest.json",
            "bytes": manifest_reference.get("bytes"),
            "sha256": manifest_reference.get("sha256"),
        }
        or Path(str(manifest_reference.get("path"))) != support_profile.parents[1] / "support-manifest.json"
    ):
        raise ControllerError("hardware campaign support references differ from the full support root")
    if path.read_bytes() != campaign_bytes or any(Path(name).read_bytes() != data for name, data in retained.items()):
        raise ControllerError("hardware campaign input changed during validation")
    identity = {
        name: str(campaign[name])
        for name in ("board_id", "probe_serial_hash", "uart_serial_hash", "power_identity")
    }
    campaign_binding = {
        "schema": "stm32-hardware-campaign-binding/1",
        "campaign_id": campaign["campaign_id"],
        "sha256": hashlib.sha256(campaign_bytes).hexdigest(),
        "generator_code_head": campaign["generator_code_head"],
        "evidence_owner": campaign["evidence_owner"],
        "board_revision": campaign["board_revision"],
        "mcu_part": campaign["mcu_part"],
        "mcu_uid_hash": campaign["mcu_uid_hash"],
        "probe_model": campaign["probe_model"],
        "uart_adapter_model": campaign["uart_adapter_model"],
        "firmware_0400_sha256": campaign["firmware_0400"]["sha256"],
        "firmware_0400_build_id": campaign["firmware_0400"]["build_id"],
        "firmware_0600_sha256": campaign["firmware_0600"]["sha256"],
        "firmware_0600_build_id": campaign["firmware_0600"]["build_id"],
    }
    return support_profile, identity, campaign_binding


def prepare_evidence_root(path: Path) -> Path:
    if not path.is_absolute() or path.exists() or not path.parent.is_dir():
        raise ControllerError("evidence root must be a new canonical absolute path")
    if str(path) != os.path.abspath(path):
        raise ControllerError("evidence root is not canonical")
    path.mkdir()
    return path


class HardwareBackend(Protocol):
    def prepare(self, action_id: str) -> dict[str, object]: ...
    def observe(self, action_id: str) -> dict[str, str]: ...
    def execute(self, action_id: str) -> dict[str, object]: ...


class HardwareContractController:
    """One-action-per-process authorization state machine; backend is injected."""

    def __init__(
        self,
        *,
        contract: str,
        repo: Path,
        catalog: Path,
        expected_code_head: str,
        controller_code_head: str,
        final_run_id: str,
        evidence_root: Path,
        backend: HardwareBackend,
        support_profile: Path,
        hardware_identity: Mapping[str, str],
        hardware_campaign: Mapping[str, object],
        git_runner: Callable[[list[str]], str] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        if contract not in {"0400", "0600"}:
            raise ControllerError("unknown hardware contract")
        if HEX40.fullmatch(expected_code_head) is None or HEX40.fullmatch(controller_code_head) is None:
            raise ControllerError("hardware CodeHead is invalid")
        if contract == "0400" and expected_code_head == controller_code_head:
            raise ControllerError("0400 requires a distinct tested product CodeHead")
        if UUID.fullmatch(final_run_id) is None or not evidence_root.is_absolute():
            raise ControllerError("hardware run/root identity is invalid")
        fixed_catalog = (repo / "tools/release/gates_0600.json").resolve()
        if catalog.resolve() != fixed_catalog:
            raise ControllerError("hardware controller requires the fixed catalog")
        selected_git_runner = git_runner or (lambda args: _git_text(repo, args))
        _verify_hardware_caller_trust(
            repo, controller_code_head, git_runner=selected_git_runner
        )
        if set(hardware_identity) != {
            "board_id", "probe_serial_hash", "uart_serial_hash", "power_identity"
        }:
            raise ControllerError("hardware identity is not closed")
        identity = dict(hardware_identity)
        if (
            not bool(_release_call("_bounded_identity", identity["board_id"]))
            or not bool(_release_call("_bounded_identity", identity["power_identity"]))
            or HEX64.fullmatch(identity["probe_serial_hash"]) is None
            or HEX64.fullmatch(identity["uart_serial_hash"]) is None
            or identity["probe_serial_hash"] in {"0" * 64, "1" * 64}
            or identity["uart_serial_hash"] in {"0" * 64, "1" * 64}
        ):
            raise ControllerError("hardware identity is invalid or placeholder")
        campaign = dict(hardware_campaign)
        campaign_keys = {
            "schema", "campaign_id", "sha256", "generator_code_head", "evidence_owner",
            "board_revision", "mcu_part", "mcu_uid_hash", "probe_model",
            "uart_adapter_model", "firmware_0400_sha256", "firmware_0400_build_id",
            "firmware_0600_sha256", "firmware_0600_build_id",
        }
        if (
            set(campaign) != campaign_keys
            or campaign["schema"] != "stm32-hardware-campaign-binding/1"
            or not isinstance(campaign["campaign_id"], str)
            or UUID.fullmatch(campaign["campaign_id"]) is None
            or campaign["generator_code_head"] != controller_code_head
            or campaign["evidence_owner"] != "user"
            or any(
                not bool(_release_call("_bounded_identity", campaign[name]))
                for name in (
                    "evidence_owner",
                    "board_revision", "mcu_part", "probe_model", "uart_adapter_model",
                    "firmware_0400_build_id", "firmware_0600_build_id",
                )
            )
            or any(
                not isinstance(campaign[name], str) or HEX64.fullmatch(campaign[name]) is None
                for name in (
                    "sha256", "mcu_uid_hash", "firmware_0400_sha256",
                    "firmware_0600_sha256",
                )
            )
            or campaign["firmware_0400_build_id"] == campaign["firmware_0600_build_id"]
        ):
            raise ControllerError("hardware campaign binding is invalid")
        try:
            loaded = load_catalog(catalog)
        except CatalogError as exc:
            raise ControllerError(str(exc)) from exc
        self.contract = contract
        self.repo = repo
        self.catalog = catalog
        self.expected_code_head = expected_code_head
        self.controller_code_head = controller_code_head
        self.final_run_id = final_run_id
        self.evidence_root = evidence_root
        self.backend = backend
        self.support_profile = support_profile
        self.hardware_identity = identity
        self.hardware_campaign = campaign
        self.git_runner = selected_git_runner
        self.now = now
        self.random_bytes = random_bytes
        self.action_ids = loaded.hardware_gate_ids(contract)
        self.actions_reserved = all(
            not gate.command_argv for gate in loaded.gates if gate.contract == contract
        )
        self.checkpoint_path = evidence_root / "checkpoint.json"
        self.catalog_sha256 = hashlib.sha256(catalog.read_bytes()).hexdigest()
        self.support_binding = verify_support_root(support_profile)
        self.resource_locks = {
            "board": identity["board_id"],
            "evidence-root": str(evidence_root),
            "probe": identity["probe_serial_hash"],
            "uart": identity["uart_serial_hash"],
        }

    def prepare_reserved(self) -> dict[str, object]:
        """Validate the public path but never synthesize authorization for reserved actions."""
        self._verify_preconditions()
        if not self.actions_reserved:
            raise ControllerError("executable hardware actions require a bound product backend")
        if self.evidence_root.exists():
            self._load()
        elif not self.evidence_root.parent.is_dir():
            raise ControllerError("hardware evidence parent is unavailable")
        return {
            "status": "BLOCKED",
            "reason": "CATALOG_ACTION_RESERVED",
            "contract": self.contract,
            "next_action": self.action_ids[0],
            "hardware_access": 0,
        }

    def _verify_preconditions(self) -> None:
        """Re-establish every immutable input immediately before a backend boundary."""
        if self.git_runner(["rev-parse", "HEAD"]).strip() != self.controller_code_head:
            raise ControllerError("hardware controller worktree HEAD changed")
        origin = self.git_runner(["config", "--get", "remote.origin.url"]).strip()
        if origin != "https://github.com/XiaoyaoLinghao/stm32-toolkit.git":
            raise ControllerError("hardware controller origin changed")
        if self.git_runner(["status", "--porcelain=v1", "--untracked-files=all"]):
            raise ControllerError("hardware controller worktree is not clean")
        for relative in (
            "tools/release/gates_0600.json",
            "tools/release/path_contract_0600.ps1",
            "tools/release/run_0600_gates.py",
            "tools/release/run_0600_hardware.ps1",
            "tools/release/verify_0600_feasibility.py",
            "tools/release/verify_0600_release.py",
        ):
            working = self.git_runner(["hash-object", "--", relative]).strip()
            committed = self.git_runner(["rev-parse", f"HEAD:{relative}"]).strip()
            if HEX40.fullmatch(working) is None or working != committed:
                raise ControllerError("hardware controller blob changed")
        if hashlib.sha256(self.catalog.read_bytes()).hexdigest() != self.catalog_sha256:
            raise ControllerError("hardware catalog changed")
        if verify_support_root(self.support_profile) != self.support_binding:
            raise ControllerError("hardware support proof changed")

    def _initial(self) -> dict[str, object]:
        return {
            "schema": "stm32-hardware-checkpoint/1",
            "contract": self.contract,
            "final_run_id": self.final_run_id,
            "evidence_root": str(self.evidence_root),
            "controller_code_head": self.controller_code_head,
            "tested_code_head": self.expected_code_head,
            "catalog_sha256": self.catalog_sha256,
            "support": self.support_binding,
            "hardware_identity": self.hardware_identity,
            "hardware_campaign": self.hardware_campaign,
            "resource_locks": self.resource_locks,
            "action_inventory": list(self.action_ids),
            "actions": [{"id": item, "state": "pending", "result": None} for item in self.action_ids],
            "prepared": None,
            "used_nonces": [],
            "recovery_history": [],
            "contract_complete": False,
        }

    def _write(self, value: dict[str, object]) -> None:
        if not self.evidence_root.exists():
            self.evidence_root.mkdir(parents=False)
        elif not self.evidence_root.is_dir():
            raise ControllerError("hardware evidence root is invalid")
        temporary = self.checkpoint_path.with_name("checkpoint.json.tmp")
        temporary.write_bytes(canonical_json_bytes(value))
        os.replace(temporary, self.checkpoint_path)

    def _load(self) -> dict[str, object]:
        if not self.checkpoint_path.is_file():
            if self.evidence_root.exists():
                raise ControllerError("hardware evidence root exists without a checkpoint")
            return self._initial()
        data = self.checkpoint_path.read_bytes()
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ControllerError("hardware checkpoint is unreadable") from exc
        if data != canonical_json_bytes(value) or not isinstance(value, dict):
            raise ControllerError("hardware checkpoint is not canonical")
        expected = self._initial()
        bound = (
            "schema", "contract", "final_run_id", "evidence_root", "controller_code_head",
            "tested_code_head", "catalog_sha256", "support", "hardware_identity",
            "hardware_campaign",
            "resource_locks", "action_inventory",
        )
        if set(value) != set(expected) or any(value[key] != expected[key] for key in bound):
            raise ControllerError("hardware checkpoint binding mismatch")
        actions = value["actions"]
        if not isinstance(actions, list) or len(actions) != len(self.action_ids):
            raise ControllerError("hardware checkpoint actions are invalid")
        expected_ids = list(self.action_ids)
        for index, action in enumerate(actions):
            if (
                not isinstance(action, dict)
                or set(action) != {"id", "state", "result"}
                or action["id"] != expected_ids[index]
                or action["state"] not in {"pending", "passed", "failed"}
                or (action["state"] == "pending" and action["result"] is not None)
                or (action["state"] != "pending" and not isinstance(action["result"], str))
            ):
                raise ControllerError("hardware checkpoint action is not closed")
            if action["state"] != "pending":
                if action["result"] != f"{action['id']}.result.json":
                    raise ControllerError("hardware checkpoint result path is not exact")
                self._validate_hardware_result_file(
                    self.evidence_root / str(action["result"]),
                    str(action["id"]),
                    str(action["state"]),
                )
        states = [str(action["state"]) for action in actions]
        terminal_seen = False
        for state in states:
            if terminal_seen and state != "pending":
                raise ControllerError("hardware checkpoint action order is invalid")
            terminal_seen = terminal_seen or state in {"pending", "failed"}
        used = value["used_nonces"]
        if (
            not isinstance(used, list)
            or any(not isinstance(item, str) or HEX64.fullmatch(item) is None for item in used)
            or len(set(used)) != len(used)
        ):
            raise ControllerError("hardware checkpoint nonces are invalid")
        history = value["recovery_history"]
        if not isinstance(history, list) or len(history) > 1:
            raise ControllerError("hardware checkpoint recovery history is invalid")
        for item in history:
            if (
                not isinstance(item, dict)
                or set(item) != {"record_sha256", "event", "action"}
                or HEX64.fullmatch(str(item["record_sha256"])) is None
                or item["event"] not in RECOVERY_EVENTS
                or item["action"] not in {"", *self.action_ids}
            ):
                raise ControllerError("hardware checkpoint recovery entry is invalid")
        prepared = value["prepared"]
        if prepared is not None:
            self._validate_prepared(prepared, used, actions)
        complete = value["contract_complete"]
        if type(complete) is not bool or complete != all(state == "passed" for state in states):
            raise ControllerError("hardware checkpoint completion is invalid")
        return value

    def _validate_hardware_result_file(
        self, path: Path, action_id: str, action_state: str
    ) -> None:
        try:
            data = path.read_bytes()
            value = json.loads(data.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ControllerError("hardware result is unreadable") from exc
        if (
            data != canonical_json_bytes(value)
            or not isinstance(value, dict)
            or set(value) != {"schema", "action", "status", "artifacts", "controller_code_head", "tested_code_head", "campaign_sha256"}
            or value["schema"] != "stm32-hardware-action-result/1"
            or value["action"] != action_id
            or value["status"] != ("PASS" if action_state == "passed" else "FAIL")
            or value["controller_code_head"] != self.controller_code_head
            or value["tested_code_head"] != self.expected_code_head
            or value["campaign_sha256"] != self.hardware_campaign["sha256"]
            or not isinstance(value["artifacts"], list)
        ):
            raise ControllerError("hardware result is not closed/dual-CodeHead bound")
        for artifact in value["artifacts"]:
            if (
                not isinstance(artifact, dict)
                or set(artifact) != {"path", "bytes", "sha256", "controller_code_head", "tested_code_head", "campaign_sha256"}
                or artifact["controller_code_head"] != self.controller_code_head
                or artifact["tested_code_head"] != self.expected_code_head
                or artifact["campaign_sha256"] != self.hardware_campaign["sha256"]
                or not isinstance(artifact.get("path"), str)
                or not artifact["path"]
                or "\\" in artifact["path"]
                or any(part in {"", ".", ".."} for part in artifact["path"].split("/"))
            ):
                raise ControllerError("retained hardware artifact is not dual-CodeHead bound")
            artifact_path = self.evidence_root.joinpath(*str(artifact["path"]).split("/"))
            try:
                artifact_bytes = artifact_path.read_bytes()
            except OSError as exc:
                raise ControllerError("retained hardware artifact is missing") from exc
            if (
                not _exact_integer(artifact.get("bytes"))
                or artifact["bytes"] != len(artifact_bytes)
                or artifact.get("sha256") != hashlib.sha256(artifact_bytes).hexdigest()
            ):
                raise ControllerError("retained hardware artifact bytes/digest mismatch")

    def _digest_for_prepared(self, prepared: Mapping[str, object]) -> str:
        summary = {"snapshot": prepared["summary"], "counters": prepared["counters"]}
        digest_input = {
            "action": prepared["action"],
            "contract": self.contract,
            "controller_code_head": self.controller_code_head,
            "final_run_id": self.final_run_id,
            "nonce": prepared["nonce"],
            "expires_at_utc": prepared["expires_at_utc"],
            "prepare_summary": summary,
            "tested_code_head": self.expected_code_head,
            "campaign_sha256": self.hardware_campaign["sha256"],
        }
        return hashlib.sha256(canonical_json_bytes(digest_input)).hexdigest()

    def _validate_prepared(
        self, prepared: object, used: object, actions: object
    ) -> None:
        if not isinstance(prepared, dict) or set(prepared) != {
            "action", "nonce", "action_digest", "expires_at_utc", "summary", "counters", "consumed"
        }:
            raise ControllerError("hardware prepared checkpoint is not closed")
        expected_counters = {
            "identity_state_read": 1, "control": 0, "modify": 0,
            "reset": 0, "halt": 0, "write": 0, "flash": 0,
        }
        counters = prepared.get("counters") if isinstance(prepared, dict) else None
        if (
            prepared["action"] not in self.action_ids
            or not isinstance(prepared["nonce"], str)
            or HEX64.fullmatch(prepared["nonce"]) is None
            or prepared["nonce"] not in used
            or not isinstance(prepared["action_digest"], str)
            or HEX64.fullmatch(prepared["action_digest"]) is None
            or type(prepared["consumed"]) is not bool
            or not isinstance(prepared["summary"], dict)
            or set(prepared["summary"]) != {"board_id", "probe_serial_hash", "uart_serial_hash", "power_identity", "state"}
            or any(prepared["summary"][key] != value for key, value in self.hardware_identity.items())
            or not isinstance(prepared["summary"]["state"], str)
            or not prepared["summary"]["state"]
            or not isinstance(counters, dict)
            or set(counters) != set(expected_counters)
            or any(
                not _exact_integer(counters[name]) or counters[name] != expected
                for name, expected in expected_counters.items()
            )
        ):
            raise ControllerError("hardware prepared checkpoint is invalid")
        try:
            datetime.strptime(str(prepared["expires_at_utc"]), UTC)
        except ValueError as exc:
            raise ControllerError("hardware prepared expiry is invalid") from exc
        if prepared["action_digest"] != self._digest_for_prepared(prepared):
            raise ControllerError("hardware prepared action digest mismatch")
        matching = [item for item in actions if item["id"] == prepared["action"]]
        if len(matching) != 1 or matching[0]["state"] != "pending":
            raise ControllerError("hardware prepared action state is invalid")

    def _next_pending(self, checkpoint: dict[str, object]) -> dict[str, object] | None:
        actions = checkpoint["actions"]
        assert isinstance(actions, list)
        for item in actions:
            assert isinstance(item, dict)
            if item["state"] == "failed":
                raise ControllerError("hardware contract has a terminal failure")
            if item["state"] == "pending":
                return item
        return None

    def prepare(self) -> dict[str, str]:
        self._verify_preconditions()
        checkpoint = self._load()
        if checkpoint["prepared"] is not None:
            raise ControllerError("an action is already prepared")
        action = self._next_pending(checkpoint)
        if action is None:
            raise ControllerError("hardware contract is complete")
        summary = self.backend.prepare(str(action["id"]))
        expected_counters = {"identity_state_read": 1, "control": 0, "modify": 0, "reset": 0, "halt": 0, "write": 0, "flash": 0}
        if (
            not isinstance(summary, dict)
            or set(summary) != {"snapshot", "counters"}
            or not isinstance(summary["counters"], dict)
            or set(summary["counters"]) != set(expected_counters)
            or any(
                not _exact_integer(summary["counters"][name])
                or summary["counters"][name] != expected
                for name, expected in expected_counters.items()
            )
            or not isinstance(summary["snapshot"], dict)
        ):
            raise ControllerError("prepare did not perform exactly one OBSERVE-only snapshot")
        snapshot = summary["snapshot"]
        if (
            set(snapshot) != {"board_id", "probe_serial_hash", "uart_serial_hash", "power_identity", "state"}
            or any(snapshot.get(key) != value for key, value in self.hardware_identity.items())
            or not isinstance(snapshot.get("state"), str)
            or not snapshot["state"]
        ):
            raise ControllerError("prepare hardware identity mismatches the frozen binding")
        self._verify_preconditions()
        nonce_bytes = self.random_bytes(32)
        if not isinstance(nonce_bytes, bytes) or len(nonce_bytes) != 32:
            raise ControllerError("CSPRNG did not return 32 bytes")
        nonce = nonce_bytes.hex()
        if nonce in checkpoint["used_nonces"]:
            raise ControllerError("authorization nonce was reused")
        prepared_at = self.now()
        expires = prepared_at + timedelta(minutes=15)
        digest_input = {
            "action": action["id"],
            "contract": self.contract,
            "controller_code_head": self.controller_code_head,
            "final_run_id": self.final_run_id,
            "nonce": nonce,
            "expires_at_utc": _utc(expires),
            "prepare_summary": summary,
            "tested_code_head": self.expected_code_head,
            "campaign_sha256": self.hardware_campaign["sha256"],
        }
        digest = hashlib.sha256(canonical_json_bytes(digest_input)).hexdigest()
        checkpoint["prepared"] = {
            "action": action["id"],
            "nonce": nonce,
            "action_digest": digest,
            "expires_at_utc": _utc(expires),
            "summary": summary["snapshot"],
            "counters": summary["counters"],
            "consumed": False,
        }
        checkpoint["used_nonces"].append(nonce)
        self._write(checkpoint)
        return {"nonce": nonce, "action_digest": digest, "expires_at_utc": _utc(expires), "checkpoint": str(self.checkpoint_path)}

    def execute(self, nonce: str, action_digest: str, *, authorized: bool) -> dict[str, object]:
        self._verify_preconditions()
        checkpoint = self._load()
        prepared = checkpoint["prepared"]
        if not authorized or not isinstance(prepared, dict) or prepared.get("consumed") is not False or nonce != prepared.get("nonce") or action_digest != prepared.get("action_digest"):
            raise ControllerError("hardware authorization is missing, consumed, or mismatched")
        try:
            expiry = datetime.strptime(str(prepared["expires_at_utc"]), UTC).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ControllerError("hardware authorization expiry is invalid") from exc
        if self.now() >= expiry:
            raise ControllerError("hardware authorization expired")
        if prepared["action_digest"] != self._digest_for_prepared(prepared):
            raise ControllerError("hardware authorization digest changed")
        prepared["consumed"] = True
        self._write(checkpoint)
        action_id = str(prepared["action"])
        observed = self.backend.observe(action_id)
        if observed != prepared["summary"]:
            checkpoint["prepared"] = None
            self._write(checkpoint)
            raise ControllerError("identity/state changed before CONTROL/MODIFY")
        self._verify_preconditions()
        body = self.backend.execute(action_id)
        if not isinstance(body, dict) or set(body) != {"status", "artifacts"} or body["status"] not in {"PASS", "FAIL"} or not isinstance(body["artifacts"], list):
            raise ControllerError("hardware backend result is invalid")
        for artifact in body["artifacts"]:
            if (
                not isinstance(artifact, dict)
                or set(artifact) != {"path", "bytes", "sha256", "controller_code_head", "tested_code_head", "campaign_sha256"}
                or artifact["controller_code_head"] != self.controller_code_head
                or artifact["tested_code_head"] != self.expected_code_head
                or artifact["campaign_sha256"] != self.hardware_campaign["sha256"]
                or not isinstance(artifact["path"], str)
                or not artifact["path"]
                or "\\" in artifact["path"]
                or any(part in {"", ".", ".."} for part in artifact["path"].split("/"))
                or not isinstance(artifact["bytes"], int)
                or isinstance(artifact["bytes"], bool)
                or artifact["bytes"] < 0
                or HEX64.fullmatch(str(artifact["sha256"])) is None
            ):
                raise ControllerError("hardware artifact is not closed and dual-CodeHead bound")
            artifact_path = self.evidence_root.joinpath(*str(artifact["path"]).split("/"))
            if not artifact_path.is_file() or artifact_path.is_symlink():
                raise ControllerError("hardware artifact is missing or linked")
            artifact_bytes = artifact_path.read_bytes()
            if artifact["bytes"] != len(artifact_bytes) or artifact["sha256"] != hashlib.sha256(artifact_bytes).hexdigest():
                raise ControllerError("hardware artifact bytes/digest mismatch")
        self._verify_preconditions()
        result = {
            "schema": "stm32-hardware-action-result/1",
            "action": action_id,
            "status": body["status"],
            "artifacts": body["artifacts"],
            "controller_code_head": self.controller_code_head,
            "tested_code_head": self.expected_code_head,
            "campaign_sha256": self.hardware_campaign["sha256"],
        }
        result_path = self.evidence_root / f"{action_id}.result.json"
        result_path.write_bytes(canonical_json_bytes(result))
        actions = checkpoint["actions"]
        assert isinstance(actions, list)
        for action in actions:
            assert isinstance(action, dict)
            if action["id"] == action_id:
                action["state"] = "passed" if body["status"] == "PASS" else "failed"
                action["result"] = result_path.name
                break
        checkpoint["prepared"] = None
        checkpoint["contract_complete"] = all(isinstance(item, dict) and item["state"] == "passed" for item in actions)
        self._write(checkpoint)
        return result

    def resume(self, checkpoint_path: Path, recovery_record: Path) -> dict[str, str]:
        self._verify_preconditions()
        if checkpoint_path != self.checkpoint_path or not checkpoint_path.is_absolute() or recovery_record.parent == self.evidence_root:
            raise ControllerError("recovery files must be separate and checkpoint-bound")
        checkpoint_bytes = checkpoint_path.read_bytes()
        checkpoint = self._load()
        history = checkpoint["recovery_history"]
        assert isinstance(history, list)
        if history:
            raise ControllerError("hardware single-resume limit reached")
        record_bytes = recovery_record.read_bytes()
        try:
            record = json.loads(record_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ControllerError("recovery record is unreadable") from exc
        if record_bytes != canonical_json_bytes(record) or not isinstance(record, dict) or set(record) != RECOVERY_KEYS:
            raise ControllerError("recovery record is not canonical/closed")
        if (
            record["classification"] != "RECOVERABLE_INFRA_ERROR"
            or record["event"] not in RECOVERY_EVENTS
            or not isinstance(record["reviewer"], str)
            or not record["reviewer"]
            or record["run_kind"] != f"hardware-{self.contract}"
            or record["run_id"] != self.final_run_id
            or record["code_head"] != self.expected_code_head
            or record["checkpoint"] != str(self.checkpoint_path)
            or record["interrupted_attempt_digest"] != hashlib.sha256(checkpoint_bytes).hexdigest()
        ):
            raise ControllerError("recovery record binding mismatch")
        try:
            datetime.strptime(str(record["recorded_at_utc"]), UTC)
        except ValueError as exc:
            raise ControllerError("recovery record UTC is invalid") from exc
        prepared = checkpoint["prepared"]
        action_id = str(prepared["action"]) if isinstance(prepared, dict) else ""
        if isinstance(prepared, dict):
            checkpoint["prepared"] = None
        history.append({"record_sha256": hashlib.sha256(record_bytes).hexdigest(), "event": record["event"], "action": action_id})
        self._verify_preconditions()
        if checkpoint_path.read_bytes() != checkpoint_bytes or recovery_record.read_bytes() != record_bytes:
            raise ControllerError("hardware retained recovery state changed")
        self._write(checkpoint)
        return {"action": action_id, "status": "FRESH_PREPARE_REQUIRED"}


def _run_wrapper_contract_body(
    *,
    kind: str,
    matrix: str,
    module: str,
    shard: str,
    run_id: str,
    evidence_root: Path,
    expected_code_head: str,
    gate_catalog: Path,
    performance_catalog: Path,
    support_profile: Path,
    controller_path: Path,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    catalog_loader: Callable[[Path], object] = load_catalog,
    performance_loader: Callable[[Path], object] = load_performance_catalog,
    verifier_blob_checker: Callable[[Path, str], Path] = _verify_verifier_blob,
    verifier_invoker: Callable[[Path, str, list[str]], object] | None = None,
    after_first_verifier_check: Callable[[], object] | None = None,
    gate_precheck: Callable[[GateRequest], None] | None = None,
    _candidate_lock_ready: Callable[[Path], None] | None = None,
    _before_candidate_root_create: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    """Schedule the catalog matrix, retain all evidence, package it, and verify terminal state."""
    if kind not in {"quick", "candidate", "final"} or matrix != kind:
        raise ControllerError("wrapper kind/matrix mismatch")
    if module not in KNOWN_MODULES or not shard or UUID.fullmatch(run_id) is None or HEX40.fullmatch(expected_code_head) is None:
        raise ControllerError("wrapper run identity is invalid")
    for name, path in (
        ("gate catalog", gate_catalog),
        ("performance catalog", performance_catalog),
        ("support profile", support_profile),
        ("controller", controller_path),
    ):
        if not path.is_absolute() or not path.is_file() or path.is_symlink() or str(path) != os.path.abspath(path):
            raise ControllerError(f"{name} path is not a canonical regular file")
    repo = controller_path.resolve().parents[2]
    expected_controller_name = f"run_0600_{kind}.ps1"
    if (
        controller_path.resolve() != repo / "tools/release" / expected_controller_name
        or gate_catalog.resolve() != repo / "tools/release/gates_0600.json"
        or performance_catalog.resolve() != repo / "tools/release/performance_0600.json"
    ):
        raise ControllerError("wrapper controller/catalog/performance paths are not fixed")
    verifier_blob_checker(repo, expected_code_head)
    if verifier_blob_checker is _verify_verifier_blob:
        _verify_relative_blob(repo, expected_code_head, FEASIBILITY_RELATIVE_PATH)
    if after_first_verifier_check is not None:
        after_first_verifier_check()
    verifier_blob_checker(repo, expected_code_head)
    if verifier_blob_checker is _verify_verifier_blob:
        _verify_relative_blob(repo, expected_code_head, FEASIBILITY_RELATIVE_PATH)
    catalog_bytes = gate_catalog.read_bytes()
    performance_bytes = performance_catalog.read_bytes()
    support_bytes = support_profile.read_bytes()
    try:
        catalog = catalog_loader(gate_catalog)
        performance_loader(performance_catalog)
    except ValueError as exc:
        raise ControllerError(str(exc)) from exc
    support = verify_support_root(support_profile)
    if (
        gate_catalog.read_bytes() != catalog_bytes
        or performance_catalog.read_bytes() != performance_bytes
        or support_profile.read_bytes() != support_bytes
    ):
        raise ControllerError("wrapper immutable input changed during first-use validation")
    catalog_digest = hashlib.sha256(catalog_bytes).hexdigest()
    performance_digest = hashlib.sha256(performance_bytes).hexdigest()
    support_digest = hashlib.sha256(support_bytes).hexdigest()
    candidate_ledger_path: Path | None = None
    candidate_ledger: dict[str, object] | None = None
    if kind == "candidate":
        candidate_root = evidence_root.parent
        if _before_candidate_root_create is not None:
            _before_candidate_root_create(candidate_root)
        try:
            candidate_root.mkdir()
        except FileExistsError as exc:
            raise ControllerError("candidate root must be absent for a new attempt") from exc
        except OSError as exc:
            raise ControllerError("candidate root create-new failed") from exc
        if _candidate_lock_ready is not None:
            _candidate_lock_ready(candidate_root)
        candidate_ledger_path = candidate_root / "candidate-ledger.json"
        if candidate_ledger_path.exists():
            raise ControllerError("candidate ledger already exists; use the closed resume mode")
        candidate_ledger = create_candidate_ledger(
            module=module,
            controller_path=controller_path,
            candidate_root=candidate_root,
            evidence_root=evidence_root,
            run_id=run_id,
            expected_code_head=expected_code_head,
            catalog_sha256=catalog_digest,
            performance_sha256=performance_digest,
            support_profile_sha256=support_digest,
            now=now(),
        )
        write_candidate_ledger(candidate_ledger_path, candidate_ledger)
    evidence = prepare_evidence_root(evidence_root)
    module_suffix = module.rsplit("-", 1)[-1]
    catalog_matrix = "final-windows" if kind == "final" else f"{kind}-{module_suffix}"
    families = tuple(
        family for family in catalog.families
        if family.module == module and catalog_matrix in family.matrices
    )
    executable = tuple(family for family in families if not family.reserved)
    scheduled_executable = executable
    if kind == "final":
        first_reserved = next(
            (index for index, family in enumerate(families) if family.reserved),
            len(families),
        )
        scheduled_executable = tuple(
            family for family in families[:first_reserved] if not family.reserved
        )
    requests = [
        GateRequest(
            family.family_id,
            family.command_argv,
            repo,
            900,
            family.node_ids,
            prerequisites=tuple(
                family.prerequisites
            ),
        )
        for family in scheduled_executable
    ]
    requested_ids = {family.family_id for family in scheduled_executable}
    complete_catalog_statuses = {
        family.family_id: "BLOCKED"
        for family in catalog.families
        if family.family_id not in requested_ids
    }
    gate_root = evidence / "gates"
    if requests:
        gate_root.mkdir()

    def immutable_precheck(_gate: GateRequest) -> None:
        if gate_precheck is not None:
            gate_precheck(_gate)
            return
        if kind == "candidate" and candidate_ledger is not None:
            reconcile_candidate(candidate_ledger)
        else:
            if _git_text(repo, ["rev-parse", "HEAD"]) != expected_code_head:
                raise ControllerError("wrapper worktree HEAD changed")
            if _git_text(repo, ["config", "--get", "remote.origin.url"]).rstrip("/").removesuffix(".git") != "https://github.com/XiaoyaoLinghao/stm32-toolkit":
                raise ControllerError("wrapper origin changed")
            if _git_text(repo, ["status", "--porcelain=v1", "--untracked-files=all"]):
                raise ControllerError("wrapper worktree is dirty")
            for relative in (
                f"tools/release/{expected_controller_name}",
                "tools/release/gates_0600.json",
                "tools/release/performance_0600.json",
                "tools/release/run_0600_gates.py",
                "tools/release/verify_0600_feasibility.py",
                "tools/release/verify_0600_release.py",
            ):
                if _git_text(repo, ["hash-object", "--", relative]) != _git_text(repo, ["rev-parse", f"{expected_code_head}:{relative}"]):
                    raise ControllerError("wrapper committed blob changed")
        if (
            gate_catalog.read_bytes() != catalog_bytes
            or performance_catalog.read_bytes() != performance_bytes
            or support_profile.read_bytes() != support_bytes
            or verify_support_root(support_profile) != support
        ):
            raise ControllerError("wrapper readiness input changed")

    matrix_results = run_gate_matrix(
        matrix,
        requests,
        execute=lambda gate, environment: execute_gate_process(
            gate, environment, evidence_root=gate_root
        ),
        precheck=immutable_precheck,
        postcheck=immutable_precheck,
        prerequisite_statuses=complete_catalog_statuses,
        run_id=run_id,
        code_head=expected_code_head,
        now=now,
    ) if requests else []
    matrix_by_id = {result.gate_id: result for result in matrix_results}
    status_inventory = dict(complete_catalog_statuses)
    gate_results: list[dict[str, object]] = []
    for family in families:
        matrix_result = matrix_by_id.get(family.family_id)
        if matrix_result is not None:
            row = {
                "gate_id": matrix_result.gate_id,
                "status": matrix_result.status,
                "reason": matrix_result.reason,
                "metadata": matrix_result.metadata,
            }
        elif family.reserved:
            blocked_request = GateRequest(
                family.family_id, (), repo, 900, (), prerequisites=family.prerequisites
            )
            row = {
                "gate_id": family.family_id,
                "status": "BLOCKED",
                "reason": "RESERVED_CATALOG_FAMILY",
                "metadata": _metadata(
                    blocked_request,
                    GateRunOutput(-1, b"", b"", (), ()),
                    run_id=run_id,
                    code_head=expected_code_head,
                    started=now(),
                    decision=_decision_facts(
                        blocked_request,
                        status_inventory,
                        precheck="NOT_RUN",
                        postcheck="NOT_RUN",
                    ),
                ),
            }
        else:
            stopped = GateRequest(
                family.family_id, family.command_argv, repo, 900, family.node_ids,
                prerequisites=family.prerequisites,
            )
            prerequisite_blocked = any(
                status_inventory[item] != "PASS" for item in family.prerequisites
            )
            row = {
                "gate_id": family.family_id,
                "status": "BLOCKED",
                "reason": (
                    "PREREQUISITE_NOT_PASS" if prerequisite_blocked
                    else "FINAL_FAIL_FAST"
                ),
                "metadata": _metadata(
                    stopped, GateRunOutput(-1, b"", b"", (), ()),
                    run_id=run_id, code_head=expected_code_head, started=now(),
                    decision=_decision_facts(
                        stopped,
                        status_inventory,
                        precheck="NOT_RUN",
                        postcheck="NOT_RUN",
                    ),
                ),
            }
        gate_results.append(row)
        status_inventory[family.family_id] = str(row["status"])
    inventory = [family.family_id for family in families]
    statuses = [str(item["status"]) for item in gate_results]
    if not families:
        status, reason = "BLOCKED", "MODULE_FAMILY_MISSING"
    elif "FAIL" in statuses:
        status, reason = "FAIL", "GATE_FAILURE"
    elif "BLOCKED" in statuses:
        status, reason = "BLOCKED", "CATALOG_FAMILIES_RESERVED"
    else:
        status, reason = "PASS", "PASS"
    product_bodies = sum(
        bool(item["metadata"]["retained_evidence"])
        for item in gate_results
        if isinstance(item.get("metadata"), dict)
    )
    prerequisite_inventory = [
        {"gate_id": family.family_id, "requires": list(family.prerequisites)}
        for family in families
    ]
    lock_inventory = sorted(
        {
            f"{kind}:{identity}"
            for request in requests
            for kind, identity in (request.resource_locks or {}).items()
        },
        key=lambda item: item.encode("utf-8"),
    )
    binding = {
        "owner": "Codex",
        "platform": f"windows-{platform.machine().casefold()}",
        "run_id": run_id,
        "code_head": expected_code_head,
        "catalog_sha256": catalog_digest,
        "locks": lock_inventory,
        "support_sha256": str(support["manifest"]["sha256"]),
        "status": status,
    }
    evidence_inventory = ["controller-result.json"]
    for row in gate_results:
        metadata = row["metadata"]
        for reference in metadata["retained_evidence"]:
            evidence_inventory.append(f"gates/{reference['path']}")
    evidence_inventory.sort(key=lambda item: item.encode("utf-8"))
    controller_result = {
        "schema": "stm32-gate-controller-result/1",
        "matrix": matrix,
        "module": module,
        "shard": shard,
        "run_id": run_id,
        "code_head": expected_code_head,
        "status": status,
        "reason": reason,
        "product_bodies": product_bodies,
        "network_access": 0,
        "remote_git_actions": 0,
        "resume_count": 0,
        "catalog_sha256": catalog_digest,
        "performance_sha256": performance_digest,
        "support": support,
        "audit": {
            "schema": "stm32-terminal-audit/1",
            "status": "BLOCKED",
            "reason": "AUDIT_GATE_RESERVED",
            "evidence": None,
        },
        "gate_inventory": inventory,
        "prerequisites": prerequisite_inventory,
        "gate_results": gate_results,
        "evidence_inventory": evidence_inventory,
        "binding": binding,
    }
    checkpoint = evidence / "controller-result.json"
    checkpoint.write_bytes(canonical_json_bytes(controller_result))
    if kind == "final":
        (evidence / "checkpoint.json").write_bytes(
            canonical_json_bytes(
                {
                    "schema": "stm32-final-checkpoint/1",
                    "run_id": run_id,
                    "code_head": expected_code_head,
                    "controller_path": str(controller_path),
                    "evidence_root": str(evidence),
                    "state": status.casefold(),
                    "resume_count": 0,
                    "interruption_event": None,
                }
            )
        )
    if candidate_ledger is not None and candidate_ledger_path is not None:
        previous = dict(candidate_ledger)
        updated = dict(candidate_ledger)
        updated["checkpoint"] = str(checkpoint)
        updated["state"] = status.casefold()
        updated["updated_at_utc"] = _utc(now())
        write_candidate_ledger(candidate_ledger_path, updated, previous=previous)
    package_path = evidence.parent / f"{evidence.name}.shard.zip"
    package = create_shard_package(
        evidence, package_path, binding, member_paths=evidence_inventory
    )
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(package)
    )
    verify_shard_package(
        package_path,
        package,
        binding,
        evidence_root=evidence,
        expected_paths=evidence_inventory,
        allowed_external_paths=sorted(
            evidence_inventory + (["checkpoint.json"] if kind == "final" else []),
            key=lambda item: item.encode("utf-8"),
        ),
    )
    if kind in {"candidate", "final"}:
        arguments = (
            [
                "candidate-evidence", "--module", module,
                "--candidate-run-id", run_id, "--evidence", str(evidence.parent),
                "--expected-code-head", expected_code_head,
                "--catalog", str(gate_catalog), "--performance", str(performance_catalog),
                "--support-profile", str(support_profile),
            ]
            if kind == "candidate"
            else ["final-evidence", "--input", str(evidence / "checkpoint.json")]
        )
        invoke = verifier_invoker or (
            lambda selected_repo, head, argv: invoke_trusted_verifier(
                repo=selected_repo,
                expected_code_head=head,
                verifier_args=argv,
                process_factory=lambda command: subprocess.run(
                    command,
                    cwd=selected_repo,
                    env=_safe_controller_env(),
                    capture_output=True,
                    check=False,
                ),
            )
        )
        child = invoke(repo, expected_code_head, arguments)
        if getattr(child, "returncode", None) != 0:
            raise ControllerError("release verifier child failed")
    return {"status": status, "reason": reason, "binding": binding, "package": package}


def _validate_candidate_attempt_location(evidence_root: Path, temporary: Path) -> Path:
    candidate_root = evidence_root.parent
    if (
        not evidence_root.is_absolute()
        or str(evidence_root) != os.path.abspath(evidence_root)
        or candidate_root.parent != temporary
        or not candidate_root.name
    ):
        raise ControllerError("candidate root must be a canonical direct child of C:\\tmp")
    if not temporary.is_dir() or _is_reparse(temporary):
        raise ControllerError("candidate temporary root is a reparse point or unavailable")
    try:
        candidate_root.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ControllerError("candidate root state is unreadable") from exc
    else:
        raise ControllerError("candidate root must be absent for a new attempt")
    return candidate_root


def run_wrapper_contract(
    *, after_candidate_location_check: Callable[[], object] | None = None,
    before_candidate_root_create: Callable[[Path], None] | None = None,
    _candidate_temporary_root: Path = Path(r"C:\tmp"),
    **kwargs: object,
) -> dict[str, object]:
    """Lock candidate create-new roots; ordinary quick/final calls use the common body."""
    if kwargs.get("kind") != "candidate":
        return _run_wrapper_contract_body(**kwargs)  # type: ignore[arg-type]
    evidence_root = kwargs.get("evidence_root")
    if not isinstance(evidence_root, Path):
        raise ControllerError("candidate evidence root is invalid")
    if _candidate_temporary_root != Path(r"C:\tmp") and "PYTEST_CURRENT_TEST" not in os.environ:
        raise ControllerError("candidate temporary root override is test-only")
    _validate_candidate_attempt_location(evidence_root, _candidate_temporary_root)
    with ExitStack() as locks:
        temporary_lock = locks.enter_context(_open_locked_windows_directory(_candidate_temporary_root))
        temporary_sentinel = locks.enter_context(_create_coverage_lock_sentinel(_candidate_temporary_root))
        _validate_locked_coverage_directory(temporary_lock)
        _validate_locked_coverage_file_path(temporary_sentinel)
        if after_candidate_location_check is not None:
            after_candidate_location_check()
        _validate_candidate_attempt_location(evidence_root, _candidate_temporary_root)
        _validate_locked_coverage_directory(temporary_lock)

        def lock_candidate(root: Path) -> None:
            root_lock = locks.enter_context(_open_locked_windows_directory(root))
            root_sentinel = locks.enter_context(_create_coverage_lock_sentinel(root))
            _validate_locked_coverage_directory(root_lock)
            _validate_locked_coverage_file_path(root_sentinel)

        return _run_wrapper_contract_body(
            _candidate_lock_ready=lock_candidate,
            _before_candidate_root_create=before_candidate_root_create,
            **kwargs,  # type: ignore[arg-type]
        )


CONTROLLER_RESULT_KEYS = {
    "schema",
    "matrix",
    "module",
    "shard",
    "run_id",
    "code_head",
    "status",
    "reason",
    "product_bodies",
    "network_access",
    "remote_git_actions",
    "resume_count",
    "catalog_sha256",
    "performance_sha256",
    "support",
    "audit",
    "gate_inventory",
    "prerequisites",
    "gate_results",
    "evidence_inventory",
    "binding",
}


def _validate_controller_checkpoint(value: dict[str, object]) -> None:
    if set(value) != CONTROLLER_RESULT_KEYS:
        raise ControllerError("candidate checkpoint is not closed")
    if (
        value.get("schema") != "stm32-gate-controller-result/1"
        or value.get("status") not in {"PASS", "FAIL", "BLOCKED"}
        or not isinstance(value.get("reason"), str)
        or any(not _exact_integer(value.get(name)) or int(value[name]) < 0 for name in (
            "product_bodies", "network_access", "remote_git_actions", "resume_count"
        ))
        or any(HEX64.fullmatch(str(value.get(name))) is None for name in (
            "catalog_sha256", "performance_sha256"
        ))
        or not isinstance(value.get("gate_inventory"), list)
        or not isinstance(value.get("prerequisites"), list)
        or not isinstance(value.get("gate_results"), list)
        or not isinstance(value.get("evidence_inventory"), list)
    ):
        raise ControllerError("candidate checkpoint recursive identity/type (including resume_count) is invalid")
    inventory = value["gate_inventory"]
    if (
        any(not isinstance(item, str) or not item for item in inventory)
        or len(set(inventory)) != len(inventory)
    ):
        raise ControllerError("candidate checkpoint gate inventory is invalid")
    prerequisites = value["prerequisites"]
    if any(
        not isinstance(item, dict)
        or set(item) != {"gate_id", "requires"}
        or item["gate_id"] not in inventory
        or not isinstance(item["requires"], list)
        or any(member not in inventory for member in item["requires"])
        for item in prerequisites
    ):
        raise ControllerError("candidate checkpoint prerequisites are invalid")
    rows = value["gate_results"]
    if (
        len(rows) != len(inventory)
        or any(
            not isinstance(item, dict)
            or set(item) != {"gate_id", "status", "reason", "metadata"}
            or item["gate_id"] != inventory[index]
            or item["status"] not in {"PASS", "FAIL", "BLOCKED"}
            or not isinstance(item["reason"], str)
            or not isinstance(item["metadata"], dict)
            for index, item in enumerate(rows)
        )
    ):
        raise ControllerError("candidate checkpoint gate results are invalid")
    support = value["support"]
    if not isinstance(support, dict) or set(support) != {"profile", "manifest"}:
        raise ControllerError("candidate checkpoint support binding is invalid")
    for reference in support.values():
        if (
            not isinstance(reference, dict)
            or set(reference) != {"path", "bytes", "sha256"}
            or not isinstance(reference["path"], str)
            or not _exact_integer(reference["bytes"])
            or reference["bytes"] < 0
            or HEX64.fullmatch(str(reference["sha256"])) is None
        ):
            raise ControllerError("candidate checkpoint support reference is invalid")
    audit = value["audit"]
    if (
        not isinstance(audit, dict)
        or set(audit) != {"schema", "status", "reason", "evidence"}
        or audit != {
            "schema": "stm32-terminal-audit/1",
            "status": "BLOCKED",
            "reason": "AUDIT_GATE_RESERVED",
            "evidence": None,
        }
    ):
        raise ControllerError("candidate checkpoint audit evidence is invalid")
    binding = value["binding"]
    if (
        not isinstance(binding, dict)
        or set(binding) != {"owner", "platform", "run_id", "code_head", "catalog_sha256", "locks", "support_sha256", "status"}
        or binding["run_id"] != value["run_id"]
        or binding["code_head"] != value["code_head"]
        or binding["catalog_sha256"] != value["catalog_sha256"]
        or binding["support_sha256"] != support["manifest"]["sha256"]
        or binding["status"] != value["status"]
        or not isinstance(binding["locks"], list)
    ):
        raise ControllerError("candidate checkpoint shard binding is invalid")


def _canonical_object_file(path: Path) -> tuple[bytes, dict[str, object]]:
    if not path.is_absolute() or not path.is_file():
        raise ControllerError("retained JSON path must be absolute and existing")
    data = path.read_bytes()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControllerError("retained JSON is unreadable") from exc
    if not isinstance(value, dict) or data != canonical_json_bytes(value):
        raise ControllerError("retained JSON is not a canonical object")
    return data, value


def _exact_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _successful_child(result: object) -> bool:
    return _exact_integer(getattr(result, "returncode", None)) and result.returncode == 0


def _atomic_json_write(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(value))
    os.replace(temporary, path)


def run_wrapper_resume(
    *,
    kind: str,
    candidate_ledger_path: Path | None = None,
    recovery_record_path: Path,
    git_runner: Callable[[list[str]], str] | None = None,
    verifier_invoker: Callable[[Path, str, list[str]], object] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, object]:
    if kind != "candidate" or candidate_ledger_path is None:
        raise ControllerError("only the closed candidate resume form is available here")
    ledger_bytes, raw_ledger = _canonical_object_file(candidate_ledger_path)
    if verifier_invoker is None:
        raw_controller = raw_ledger.get("controller_path")
        raw_head = raw_ledger.get("expected_code_head")
        if not isinstance(raw_controller, str) or not isinstance(raw_head, str):
            raise ControllerError("candidate ledger caller identity is invalid")
        _verify_verifier_blob(Path(raw_controller).parents[2], raw_head)
    try:
        ledger = validate_candidate_ledger(raw_ledger)
    except VerificationError as exc:
        raise ControllerError(str(exc)) from exc
    if candidate_ledger_path != Path(str(ledger["candidate_root"])) / "candidate-ledger.json":
        raise ControllerError("candidate ledger path is not wrapper-owned")
    checkpoint_value = ledger["checkpoint"]
    if not isinstance(checkpoint_value, str):
        raise ControllerError("candidate state is not resume-eligible")
    checkpoint_path = Path(checkpoint_value)
    checkpoint_bytes, checkpoint = _canonical_object_file(checkpoint_path)
    _validate_controller_checkpoint(checkpoint)
    if not _exact_integer(checkpoint.get("resume_count")) or checkpoint.get("resume_count") != 0:
        raise ControllerError("candidate single-resume limit reached")
    if ledger["state"] not in {"blocked", "failed"}:
        raise ControllerError("candidate state is not resume-eligible")
    if (
        checkpoint.get("matrix") != "candidate"
        or checkpoint.get("module") != ledger["module"]
        or checkpoint.get("run_id") != ledger["candidate_run_id"]
        or checkpoint.get("code_head") != ledger["expected_code_head"]
        or checkpoint.get("status") not in {"FAIL", "BLOCKED"}
        or not all(_exact_integer(checkpoint.get(name)) for name in ("product_bodies", "network_access", "remote_git_actions"))
    ):
        raise ControllerError("candidate checkpoint identity/state mismatch")
    recovery_bytes, recovery = _canonical_object_file(recovery_record_path)
    try:
        validate_recovery_record(
            recovery,
            expected_run_kind=f"candidate-{str(ledger['module']).rsplit('-', 1)[-1]}",
            expected_run_id=str(ledger["candidate_run_id"]),
            expected_code_head=str(ledger["expected_code_head"]),
            expected_checkpoint=checkpoint_path,
            expected_attempt_digest=hashlib.sha256(checkpoint_bytes).hexdigest(),
        )
        if checkpoint.get("reason") != recovery.get("event"):
            raise ControllerError(
                "candidate checkpoint is not bound to the claimed recoverable event"
            )
        verifier_path = reconcile_candidate(ledger, git_runner=git_runner)
    except VerificationError as exc:
        raise ControllerError(str(exc)) from exc
    worktree = Path(str(ledger["controller_path"])).parents[2]
    verifier_args = ["candidate-evidence", "--candidate-ledger", str(candidate_ledger_path)]
    invoker = verifier_invoker or (
        lambda repo, head, argv: invoke_trusted_verifier(
            repo=repo,
            expected_code_head=head,
            verifier_args=argv,
            process_factory=lambda command: subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=_safe_controller_env(),
            ),
        )
    )
    if verifier_path != worktree.joinpath(*VERIFIER_RELATIVE_PATH.split("/")):
        raise ControllerError("candidate reconciliation returned a non-fixed verifier")
    if (
        candidate_ledger_path.read_bytes() != ledger_bytes
        or checkpoint_path.read_bytes() != checkpoint_bytes
        or recovery_record_path.read_bytes() != recovery_bytes
    ):
        raise ControllerError("candidate retained state changed before verifier spawn")
    invocation_result = invoker(worktree, str(ledger["expected_code_head"]), verifier_args)
    if not _successful_child(invocation_result):
        raise ControllerError("candidate verifier child failed")
    if (
        candidate_ledger_path.read_bytes() != ledger_bytes
        or checkpoint_path.read_bytes() != checkpoint_bytes
        or recovery_record_path.read_bytes() != recovery_bytes
    ):
        raise ControllerError("candidate retained state changed during verifier execution")
    previous = dict(ledger)
    updated_checkpoint = dict(checkpoint)
    updated_checkpoint["resume_count"] = 1
    updated_ledger = dict(ledger)
    updated_ledger["state"] = "running"
    updated_ledger["updated_at_utc"] = _utc(now())
    try:
        _atomic_json_write(checkpoint_path, updated_checkpoint)
        write_candidate_ledger(candidate_ledger_path, updated_ledger, previous=previous)
    except VerificationError as exc:
        raise ControllerError(str(exc)) from exc
    return {
        "status": "RESUMED",
        "checkpoint": str(checkpoint_path),
        "recovery_record_sha256": hashlib.sha256(recovery_bytes).hexdigest(),
        "verifier_result": None if invocation_result is None else str(invocation_result),
    }


FINAL_CHECKPOINT_KEYS = {
    "schema",
    "run_id",
    "code_head",
    "controller_path",
    "evidence_root",
    "state",
    "resume_count",
    "interruption_event",
}


def run_final_resume(
    *,
    checkpoint_path: Path,
    recovery_record_path: Path,
    verifier_invoker: Callable[[Path, str, list[str]], object] | None = None,
) -> dict[str, object]:
    checkpoint_bytes, checkpoint = _canonical_object_file(checkpoint_path)
    if set(checkpoint) != FINAL_CHECKPOINT_KEYS or checkpoint.get("schema") != "stm32-final-checkpoint/1":
        raise ControllerError("final checkpoint is not closed")
    if not _exact_integer(checkpoint.get("resume_count")) or checkpoint.get("resume_count") != 0:
        raise ControllerError("final single-resume limit reached")
    if (
        checkpoint.get("state") not in {"blocked", "failed"}
        or not isinstance(checkpoint.get("run_id"), str)
        or UUID.fullmatch(str(checkpoint["run_id"])) is None
        or not isinstance(checkpoint.get("code_head"), str)
        or HEX40.fullmatch(str(checkpoint["code_head"])) is None
    ):
        raise ControllerError("final checkpoint state/identity is not resume-eligible")
    controller = Path(str(checkpoint.get("controller_path")))
    evidence = Path(str(checkpoint.get("evidence_root")))
    if (
        not controller.is_absolute()
        or not evidence.is_absolute()
        or checkpoint_path != evidence / "checkpoint.json"
        or controller.name != "run_0600_final.ps1"
        or controller.parent.name != "release"
        or controller.parent.parent.name != "tools"
    ):
        raise ControllerError("final checkpoint paths are not fixed/root-bound")
    if verifier_invoker is None:
        _verify_verifier_blob(controller.parents[2], str(checkpoint["code_head"]))
    recovery_bytes, recovery = _canonical_object_file(recovery_record_path)
    try:
        validate_recovery_record(
            recovery,
            expected_run_kind="final-windows",
            expected_run_id=str(checkpoint["run_id"]),
            expected_code_head=str(checkpoint["code_head"]),
            expected_checkpoint=checkpoint_path,
            expected_attempt_digest=hashlib.sha256(checkpoint_bytes).hexdigest(),
        )
    except VerificationError as exc:
        raise ControllerError(str(exc)) from exc
    if checkpoint.get("interruption_event") != recovery.get("event"):
        raise ControllerError("final checkpoint is not bound to the recoverable event")
    worktree = controller.parents[2]
    verifier_args = ["final-evidence", "--input", str(checkpoint_path)]
    invoker = verifier_invoker or (
        lambda repo, head, argv: invoke_trusted_verifier(
            repo=repo,
            expected_code_head=head,
            verifier_args=argv,
            process_factory=lambda command: subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=_safe_controller_env(),
            ),
        )
    )
    if checkpoint_path.read_bytes() != checkpoint_bytes or recovery_record_path.read_bytes() != recovery_bytes:
        raise ControllerError("final retained state changed before verifier spawn")
    invocation_result = invoker(worktree, str(checkpoint["code_head"]), verifier_args)
    if not _successful_child(invocation_result):
        raise ControllerError("final verifier child failed")
    if checkpoint_path.read_bytes() != checkpoint_bytes or recovery_record_path.read_bytes() != recovery_bytes:
        raise ControllerError("final retained state changed during verifier execution")
    updated_checkpoint = dict(checkpoint)
    updated_checkpoint["resume_count"] = 1
    updated_checkpoint["state"] = "running"
    _atomic_json_write(checkpoint_path, updated_checkpoint)
    return {
        "status": "RESUMED",
        "checkpoint": str(checkpoint_path),
        "recovery_record_sha256": hashlib.sha256(recovery_bytes).hexdigest(),
        "verifier_result": None if invocation_result is None else str(invocation_result),
    }


def _contract_self_test(kind: str) -> dict[str, object]:
    if kind not in {"quick", "candidate", "final", "hardware"}:
        raise ControllerError("unknown self-test kind")
    if kind != "hardware":
        fake_calls: list[str] = []

        def fake_execute(gate: GateRequest, _environment: dict[str, str]) -> GateRunOutput:
            fake_calls.append(gate.gate_id)
            code = 1 if gate.gate_id == "FAIL" else 0
            outcome = "failed" if code else "passed"
            return GateRunOutput(
                code,
                b"fake",
                b"",
                gate.expected_nodes,
                tuple((node, outcome) for node in gate.expected_nodes),
            )

        fixture = [
            GateRequest("PASS", (sys.executable, "fake"), Path.cwd(), 1, ("fake::pass",)),
            GateRequest("FAIL", (sys.executable, "fake"), Path.cwd(), 1, ("fake::fail",)),
            GateRequest("BLOCKED", (sys.executable, "fake"), Path.cwd(), 1, ("fake::blocked",), prerequisites=("FAIL",)),
        ]
        states = [
            item.status for item in run_gate_matrix(
                kind,
                fixture,
                execute=fake_execute,
                precheck=(lambda _gate: None) if kind in {"candidate", "final"} else None,
            )
        ]
        expected_states = ["PASS", "FAIL"] if kind == "final" else ["PASS", "FAIL", "BLOCKED"]
        if states != expected_states or fake_calls != ["PASS", "FAIL"]:
            raise ControllerError(f"{kind} self-test transitions failed")
    else:
        class FakeBackend:
            def __init__(self) -> None:
                self.snapshot = {
                    "board_id": "NUCLEO-F446RE",
                    "probe_serial_hash": "c" * 64,
                    "uart_serial_hash": "d" * 64,
                    "power_identity": "bench-supply-A",
                    "state": "running",
                }
                self.executed: list[str] = []

            def prepare(self, action_id: str) -> dict[str, object]:
                return {
                    "snapshot": dict(self.snapshot),
                    "counters": {"identity_state_read": 1, "control": 0, "modify": 0, "reset": 0, "halt": 0, "write": 0, "flash": 0},
                }

            def observe(self, action_id: str) -> dict[str, str]:
                return dict(self.snapshot)

            def execute(self, action_id: str) -> dict[str, object]:
                self.executed.append(action_id)
                return {"status": "PASS", "artifacts": []}

        root = Path(tempfile.mkdtemp(prefix="stm32tk-0600-hardware-selftest-", dir=r"C:\tmp"))
        try:
            catalog_path = Path(__file__).with_name("gates_0600.json")
            support_profile = Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json")
            if not support_profile.is_file():
                raise ControllerError("hardware self-test support fixture is unavailable")
            class FakeGit:
                def __call__(self, args: list[str]) -> str:
                    if args == ["rev-parse", "HEAD"]:
                        return "b" * 40 + "\n"
                    if args == ["config", "--get", "remote.origin.url"]:
                        return "https://github.com/XiaoyaoLinghao/stm32-toolkit.git\n"
                    if args == ["status", "--porcelain=v1", "--untracked-files=all"]:
                        return ""
                    if args[:2] == ["hash-object", "--"] or (args[0] == "rev-parse" and ":" in args[1]):
                        return "e" * 40 + "\n"
                    raise ControllerError("hardware self-test received unexpected Git request")
            for contract in ("0400", "0600"):
                backend = FakeBackend()
                nonce_counter = 0

                def fake_random(count: int) -> bytes:
                    nonlocal nonce_counter
                    result = bytes((index + nonce_counter) % 256 for index in range(count))
                    nonce_counter += 1
                    return result

                controller = HardwareContractController(
                    contract=contract,
                    repo=Path(__file__).resolve().parents[2],
                    catalog=catalog_path,
                    expected_code_head="a" * 40,
                    controller_code_head="b" * 40,
                    final_run_id="123e4567-e89b-42d3-a456-426614174000",
                    evidence_root=root / contract,
                    backend=backend,
                    support_profile=support_profile,
                    hardware_identity={
                        "board_id": "NUCLEO-F446RE",
                        "probe_serial_hash": "c" * 64,
                        "uart_serial_hash": "d" * 64,
                        "power_identity": "bench-supply-A",
                    },
                    hardware_campaign={
                        "schema": "stm32-hardware-campaign-binding/1",
                        "campaign_id": "223e4567-e89b-42d3-a456-426614174000",
                        "sha256": "e" * 64,
                        "generator_code_head": "b" * 40,
                        "evidence_owner": "user",
                        "board_revision": "rev-A", "mcu_part": "STM32F446RE",
                        "mcu_uid_hash": "4" * 64, "probe_model": "ST-LINK/V3",
                        "uart_adapter_model": "FT232R",
                        "firmware_0400_sha256": "5" * 64,
                        "firmware_0400_build_id": "firmware-0400-A",
                        "firmware_0600_sha256": "6" * 64,
                        "firmware_0600_build_id": "firmware-0600-A",
                    },
                    git_runner=FakeGit(),
                    now=lambda: datetime(2026, 8, 15, tzinfo=timezone.utc),
                    random_bytes=fake_random,
                )
                prepared = controller.prepare()
                backend.snapshot["state"] = "changed"
                try:
                    controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)
                except ControllerError:
                    pass
                else:
                    raise ControllerError("hardware self-test accepted changed state")
                backend.snapshot["state"] = "running"
                prepared = controller.prepare()
                controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)
                if len(backend.executed) != 1:
                    raise ControllerError("hardware self-test did not isolate one action")
        finally:
            shutil.rmtree(root)
    return {"hardware_access": 0, "mode": kind, "network_access": 0, "product_bodies": 0, "status": "PASS"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_0600_gates.py", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    performance = sub.add_parser("performance", allow_abbrev=False)
    performance.add_argument("--module", required=True)
    performance.add_argument("--test-file", required=True)
    performance.add_argument("--mode", choices=("calibrate", "verify"), required=True)
    performance.add_argument("--output", required=True)
    performance.add_argument("--performance-config")
    coverage = sub.add_parser("dev-coverage", allow_abbrev=False)
    coverage.add_argument("--task-id", required=True)
    coverage.add_argument("--evidence-root", required=True)
    coverage.add_argument("tokens", nargs=argparse.REMAINDER)
    self_test = sub.add_parser("contract-self-test", allow_abbrev=False)
    self_test.add_argument("--kind", choices=("quick", "candidate", "final", "hardware"), required=True)
    wrapper = sub.add_parser("wrapper", allow_abbrev=False)
    wrapper.add_argument("--kind", choices=("quick", "candidate", "final"), required=True)
    wrapper.add_argument("--matrix", choices=("quick", "candidate", "final"), required=True)
    wrapper.add_argument("--module", required=True)
    wrapper.add_argument("--shard", required=True)
    wrapper.add_argument("--run-id", required=True)
    wrapper.add_argument("--evidence-root", required=True)
    wrapper.add_argument("--expected-code-head", required=True)
    wrapper.add_argument("--gate-catalog", required=True)
    wrapper.add_argument("--performance-catalog", required=True)
    wrapper.add_argument("--support-profile", required=True)
    resume = sub.add_parser("wrapper-resume", allow_abbrev=False)
    resume.add_argument("--kind", choices=("candidate", "final"), required=True)
    resume.add_argument("--candidate-ledger")
    resume.add_argument("--final-checkpoint")
    resume.add_argument("--recovery-record", required=True)
    hardware = sub.add_parser("hardware", allow_abbrev=False)
    hardware.add_argument("--contract", choices=("0400", "0600"), required=True)
    hardware.add_argument("--repo", required=True)
    hardware.add_argument("--expected-code-head", required=True)
    hardware.add_argument("--final-run-id", required=True)
    hardware.add_argument("--evidence-root", required=True)
    hardware.add_argument("--hardware-input", required=True)
    hardware.add_argument("--mode", choices=("prepare", "execute", "resume"), required=True)
    hardware.add_argument("--nonce")
    hardware.add_argument("--action-digest")
    hardware.add_argument("--authorized", action="store_true")
    hardware.add_argument("--checkpoint")
    hardware.add_argument("--recovery-record")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = _parser()
    args = parser.parse_args(raw_argv)
    try:
        if args.command == "performance":
            result = run_performance(
                Path.cwd(),
                args.module,
                Path(args.test_file),
                args.mode,
                Path(args.output),
                Path(args.performance_config) if args.performance_config else None,
            )
        elif args.command == "dev-coverage":
            if "--" not in raw_argv:
                raise ControllerError("dev-coverage requires a literal -- token separator")
            tokens = list(args.tokens)
            if tokens and tokens[0] == "--":
                tokens.pop(0)
            result = run_dev_coverage(Path.cwd(), args.task_id, Path(args.evidence_root), tokens)
        elif args.command == "contract-self-test":
            result = _contract_self_test(args.kind)
        elif args.command == "wrapper":
            controller_name = {
                "quick": "run_0600_quick.ps1",
                "candidate": "run_0600_candidate.ps1",
                "final": "run_0600_final.ps1",
            }[args.kind]
            result = run_wrapper_contract(
                kind=args.kind,
                matrix=args.matrix,
                module=args.module,
                shard=args.shard,
                run_id=args.run_id,
                evidence_root=Path(args.evidence_root),
                expected_code_head=args.expected_code_head,
                gate_catalog=Path(args.gate_catalog),
                performance_catalog=Path(args.performance_catalog),
                support_profile=Path(args.support_profile),
                controller_path=Path(__file__).with_name(controller_name),
            )
        elif args.command == "hardware":
            repo = Path(args.repo)
            evidence_root = Path(args.evidence_root)
            if not repo.is_absolute() or not repo.is_dir() or not evidence_root.is_absolute():
                raise ControllerError("hardware repository/evidence paths must be absolute")
            controller_head = _git_text(repo, ["rev-parse", "HEAD"])
            if HEX40.fullmatch(controller_head) is None:
                raise ControllerError("hardware controller HEAD is invalid")
            if args.mode == "execute":
                if (
                    HEX64.fullmatch(args.nonce or "") is None
                    or HEX64.fullmatch(args.action_digest or "") is None
                    or not args.authorized
                    or args.checkpoint
                    or args.recovery_record
                ):
                    raise ControllerError("hardware execute arguments are not closed")
            elif args.mode == "resume":
                if (
                    not args.checkpoint
                    or not args.recovery_record
                    or args.nonce
                    or args.action_digest
                    or args.authorized
                ):
                    raise ControllerError("hardware resume arguments are not closed")
            elif any((args.nonce, args.action_digest, args.authorized, args.checkpoint, args.recovery_record)):
                raise ControllerError("hardware prepare arguments are not closed")

            verified_sources = _verify_hardware_caller_trust(
                repo, controller_head, capture_modules=True
            )
            _load_verified_hardware_verifiers(
                repo, controller_head, verified_sources
            )

            class ReservedBackend:
                def prepare(self, _action_id: str) -> dict[str, object]:
                    raise ControllerError("reserved hardware action reached a product prepare boundary")

                def observe(self, _action_id: str) -> dict[str, str]:
                    raise ControllerError("reserved hardware action reached a product observe boundary")

                def execute(self, _action_id: str) -> dict[str, object]:
                    raise ControllerError("reserved hardware action reached a product execute boundary")

            support_profile, hardware_identity, hardware_campaign = load_hardware_campaign_input(
                Path(args.hardware_input),
                expected_generator_code_head=controller_head,
            )
            controller = HardwareContractController(
                contract=args.contract,
                repo=repo,
                catalog=repo / "tools/release/gates_0600.json",
                expected_code_head=args.expected_code_head,
                controller_code_head=controller_head,
                final_run_id=args.final_run_id,
                evidence_root=evidence_root,
                backend=ReservedBackend(),
                support_profile=support_profile,
                hardware_identity=hardware_identity,
                hardware_campaign=hardware_campaign,
            )
            if args.mode == "prepare":
                result = controller.prepare_reserved()
            elif args.mode == "execute":
                result = controller.execute(args.nonce, args.action_digest, authorized=True)
            else:
                result = controller.resume(Path(args.checkpoint), Path(args.recovery_record))
        else:
            if args.kind == "candidate":
                if not args.candidate_ledger or args.final_checkpoint:
                    raise ControllerError("candidate resume requires only CandidateLedger and RecoveryRecord")
                result = run_wrapper_resume(
                    kind="candidate",
                    candidate_ledger_path=Path(args.candidate_ledger),
                    recovery_record_path=Path(args.recovery_record),
                )
            else:
                if not args.final_checkpoint or args.candidate_ledger:
                    raise ControllerError("final resume requires only FinalCheckpoint and RecoveryRecord")
                result = run_final_resume(
                    checkpoint_path=Path(args.final_checkpoint),
                    recovery_record_path=Path(args.recovery_record),
                )
    except (ControllerError, VerificationError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
