"""Offline gate runners and controller state machines for STM32 Toolkit 0.6."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from verify_0600_release import (
    CatalogError,
    VerificationError,
    canonical_json_bytes,
    create_candidate_ledger,
    create_shard_package,
    load_catalog,
    load_performance_catalog,
    reconcile_candidate,
    validate_candidate_ledger,
    validate_recovery_record,
    write_candidate_ledger,
)


KNOWN_MODULES = {"STM32TK-0601", "STM32TK-0602", "STM32TK-0603"}
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


class ControllerError(ValueError):
    """A controller input or retained state failed closed."""


VERIFIER_RELATIVE_PATH = "tools/release/verify_0600_release.py"


def _git_text(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ControllerError("Git verifier binding check failed")
    return completed.stdout.strip()


def _verify_verifier_blob(repo: Path, expected_code_head: str) -> Path:
    if HEX40.fullmatch(expected_code_head) is None:
        raise ControllerError("expected CodeHead is invalid")
    try:
        repository = repo.resolve(strict=True)
        script = repository.joinpath(*VERIFIER_RELATIVE_PATH.split("/"))
        if not script.is_file() or script.is_symlink():
            raise ControllerError("re-derived verifier is missing or linked")
    except OSError as exc:
        raise ControllerError("repository/verifier path is invalid") from exc
    if _git_text(repository, ["rev-parse", "HEAD"]) != expected_code_head:
        raise ControllerError("worktree HEAD does not match expected CodeHead")
    committed = _git_text(repository, ["rev-parse", f"{expected_code_head}:{VERIFIER_RELATIVE_PATH}"])
    working = _git_text(repository, ["hash-object", "--", str(script)])
    if HEX40.fullmatch(committed) is None or committed != working:
        raise ControllerError("release verifier working blob does not match CodeHead")
    return script


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
    result: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper.startswith(("COVERAGE_", "COV_CORE_")) or upper == "PYTEST_ADDOPTS":
            continue
        result[key] = value
    return result


def _metadata(
    gate: GateRequest,
    output: GateRunOutput,
    *,
    run_id: str,
    code_head: str,
    started: datetime,
) -> dict[str, object]:
    return {
        "argv": list(gate.argv),
        "code_head": code_head,
        "cwd": str(gate.cwd),
        "duration_ms": 0,
        "exit_code": output.exit_code,
        "gate_id": gate.gate_id,
        "run_id": run_id,
        "started_at_utc": _utc(started),
        "stderr": {"bytes": len(output.stderr), "sha256": hashlib.sha256(output.stderr).hexdigest()},
        "stdout": {"bytes": len(output.stdout), "sha256": hashlib.sha256(output.stdout).hexdigest()},
    }


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
    run_id: str = "00000000-0000-4000-8000-000000000000",
    code_head: str = "0" * 40,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[GateResult]:
    if matrix not in {"quick", "candidate", "final-readiness", "final"}:
        raise ControllerError("unknown matrix")
    ids = [gate.gate_id for gate in gates]
    if len(ids) != len(set(ids)):
        raise ControllerError("duplicate gate id")
    known = set(ids)
    for gate in gates:
        if not set(gate.prerequisites) <= known:
            raise ControllerError("unknown prerequisite")
    validate_resource_locks(gates)
    results: list[GateResult] = []
    statuses: dict[str, str] = {}
    environment = _safe_controller_env()
    for gate in gates:
        if any(statuses[item] != "PASS" for item in gate.prerequisites):
            output = GateRunOutput(-1, b"", b"", ())
            result = GateResult(
                gate.gate_id,
                "BLOCKED",
                "PREREQUISITE_NOT_PASS",
                _metadata(gate, output, run_id=run_id, code_head=code_head, started=now()),
            )
            results.append(result)
            statuses[gate.gate_id] = result.status
            continue
        if matrix in {"candidate", "final-readiness", "final"}:
            if precheck is None:
                raise ControllerError("matrix precheck is required")
            try:
                precheck(gate)
            except Exception as exc:  # external/precondition boundary, converted to evidence
                output = GateRunOutput(-1, b"", str(exc).encode("utf-8"), ())
                result = GateResult(
                    gate.gate_id,
                    "FAIL",
                    "PRECHECK_FAILED",
                    _metadata(gate, output, run_id=run_id, code_head=code_head, started=now()),
                )
                results.append(result)
                statuses[gate.gate_id] = result.status
                if matrix == "final":
                    break
                continue
        if matrix == "final-readiness":
            output = GateRunOutput(0, b"", b"", gate.expected_nodes)
        else:
            output = execute(gate, dict(environment))
            if not isinstance(output, GateRunOutput):
                raise ControllerError("executor returned an invalid result")
        node_mismatch = (
            len(output.selected_nodes) != len(set(output.selected_nodes))
            or output.selected_nodes != gate.expected_nodes
        )
        status = "PASS" if output.exit_code == 0 and not node_mismatch else "FAIL"
        reason = "NODE_INVENTORY_MISMATCH" if node_mismatch else "PASS" if status == "PASS" else "PRODUCT_FAILURE"
        result = GateResult(
            gate.gate_id,
            status,
            reason,
            _metadata(gate, output, run_id=run_id, code_head=code_head, started=now()),
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
        if performance_config is None or not performance_config.is_absolute() or not performance_config.is_file():
            raise ControllerError("verify requires an absolute performance config")
        value = _load_json(performance_config)
        if not isinstance(value, dict) or set(value) != {"schema", "profiles"} or value["schema"] != "stm32-performance-catalog/1" or not isinstance(value["profiles"], list):
            raise ControllerError("performance config is not closed")
        matching = [item for item in value["profiles"] if isinstance(item, dict) and item.get("module") == module]
        if len(matching) != 1 or set(matching[0]) != {"module", "test_file", "test_file_sha256", "profile_sha256"}:
            raise ControllerError("performance profile is missing or duplicated")
        profile = matching[0]
        if profile["test_file"] != test.relative_to(repo.resolve()).as_posix() or profile["test_file_sha256"] != test_digest or not isinstance(profile["profile_sha256"], str) or HEX64.fullmatch(profile["profile_sha256"]) is None:
            raise ControllerError("performance workload/config digest mismatch")
        profile_digest = str(profile["profile_sha256"])
    environment = dict(os.environ)
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
    result = _load_json(output)
    if (
        not isinstance(result, dict)
        or set(result) != {"schema", "mode", "module", "test_file_sha256", "workloads"}
        or result["schema"] != "stm32-performance-run/1"
        or result["mode"] != mode
        or result["module"] != module
        or result["test_file_sha256"] != test_digest
        or not isinstance(result["workloads"], list)
    ):
        raise ControllerError("performance output is stale or malformed")
    return result


def _changed_product_files(repo: Path, git_runner: Callable[[list[str]], list[str]]) -> list[str]:
    candidates = git_runner(["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"]) + git_runner(["ls-files", "--others", "--exclude-standard"])
    product_prefix = "tools/stm32-toolkit/src/stm32_toolkit/"
    paths = [item.replace("\\", "/") for item in candidates if item.replace("\\", "/").startswith(product_prefix) and item.casefold().endswith(".py")]
    if not paths:
        raise ControllerError("no changed product Python file")
    if len(paths) != len(set(paths)) or len(paths) != len({item.casefold() for item in paths}):
        raise ControllerError("changed product file duplicate")
    for relative in paths:
        _within_repo_file(repo, repo.joinpath(*relative.split("/")))
    return sorted(paths, key=lambda item: item.encode("utf-8"))


def _default_git_runner(repo: Path) -> Callable[[list[str]], list[str]]:
    def run(args: list[str]) -> list[str]:
        completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise ControllerError("git discovery failed")
        return [line for line in completed.stdout.splitlines() if line]

    return run


def run_dev_coverage(
    repo: Path,
    task_id: str,
    evidence_root: Path,
    pytest_tokens: Sequence[str],
    git_runner: Callable[[list[str]], list[str]] | None = None,
    runner: Callable[..., int] = _default_runner,
) -> dict[str, object]:
    if task_id not in KNOWN_MODULES:
        raise ControllerError("unknown coverage task")
    evidence = prepare_evidence_root(evidence_root)
    changed = _changed_product_files(repo, git_runner or _default_git_runner(repo))
    if not pytest_tokens:
        raise ControllerError("coverage pytest tokens are missing")
    validated: list[str] = []
    for token in pytest_tokens:
        if not isinstance(token, str) or not token or any(character in token for character in ";|&><\r\n") or any(char.isspace() for char in token):
            raise ControllerError("coverage shell token is forbidden")
        if token.startswith("--cov="):
            module = token.removeprefix("--cov=")
            if re.fullmatch(r"stm32_toolkit(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module) is None:
                raise ControllerError("coverage module is invalid")
        elif token.startswith("-"):
            raise ControllerError("coverage option is not allowed")
        else:
            path = Path(token)
            if not path.is_absolute():
                path = repo / path
            test = _within_repo_file(repo, path)
            relative = test.relative_to(repo.resolve()).as_posix()
            if not relative.startswith("tools/stm32-toolkit/tests/") or not test.name.startswith("test_") or test.suffix != ".py":
                raise ControllerError("coverage test path is invalid")
            token = str(test)
        validated.append(token)
    if _coverage_configured(os.environ):
        raise ControllerError("dev coverage rejects inherited coverage variables")
    raw_path = evidence / "coverage-raw.json"
    argv = [sys.executable, "-m", "pytest", *validated, "--cov-branch", f"--cov-report=json:{raw_path}"]
    return_code = runner(argv, cwd=repo, env=_safe_controller_env())
    if return_code != 0 or not raw_path.is_file():
        raise ControllerError("coverage subprocess failed")
    raw = _load_json(raw_path)
    if not isinstance(raw, dict) or set(raw) != {"files"} or not isinstance(raw["files"], dict):
        raise ControllerError("coverage JSON root is invalid")
    rows: dict[str, tuple[int, int]] = {}
    folded: set[str] = set()
    for raw_path_name, details in raw["files"].items():
        if not isinstance(raw_path_name, str) or not isinstance(details, dict) or set(details) != {"summary"} or not isinstance(details["summary"], dict):
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
        if set(summary) != {"covered_branches", "num_branches"}:
            raise ControllerError("coverage summary is not closed")
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
    (evidence / "branch-coverage.json").write_bytes(canonical_json_bytes(result))
    return result


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
    if set(members) != set(expected_paths) | {"support-manifest.json"}:
        raise ControllerError("support root has missing or extra entries")
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
        self.now = now
        self.random_bytes = random_bytes
        self.action_ids = loaded.hardware_gate_ids(contract)
        self.checkpoint_path = evidence_root / "checkpoint.json"

    def _initial(self) -> dict[str, object]:
        return {
            "schema": "stm32-hardware-checkpoint/1",
            "contract": self.contract,
            "final_run_id": self.final_run_id,
            "evidence_root": str(self.evidence_root),
            "controller_code_head": self.controller_code_head,
            "tested_code_head": self.expected_code_head,
            "action_inventory": list(self.action_ids),
            "actions": [{"id": item, "state": "pending", "result": None} for item in self.action_ids],
            "prepared": None,
            "used_nonces": [],
            "recovery_history": [],
            "contract_complete": False,
        }

    def _write(self, value: dict[str, object]) -> None:
        self.evidence_root.mkdir(parents=False, exist_ok=True)
        temporary = self.checkpoint_path.with_name("checkpoint.json.tmp")
        temporary.write_bytes(canonical_json_bytes(value))
        os.replace(temporary, self.checkpoint_path)

    def _load(self) -> dict[str, object]:
        if not self.checkpoint_path.is_file():
            return self._initial()
        data = self.checkpoint_path.read_bytes()
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ControllerError("hardware checkpoint is unreadable") from exc
        if data != canonical_json_bytes(value) or not isinstance(value, dict):
            raise ControllerError("hardware checkpoint is not canonical")
        expected = self._initial()
        if set(value) != set(expected) or any(value[key] != expected[key] for key in ("schema", "contract", "final_run_id", "evidence_root", "controller_code_head", "tested_code_head", "action_inventory")):
            raise ControllerError("hardware checkpoint binding mismatch")
        return value

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
        checkpoint = self._load()
        if checkpoint["prepared"] is not None:
            raise ControllerError("an action is already prepared")
        action = self._next_pending(checkpoint)
        if action is None:
            raise ControllerError("hardware contract is complete")
        summary = self.backend.prepare(str(action["id"]))
        expected_counters = {"identity_state_read": 1, "control": 0, "modify": 0, "reset": 0, "halt": 0, "write": 0, "flash": 0}
        if not isinstance(summary, dict) or set(summary) != {"snapshot", "counters"} or summary["counters"] != expected_counters or not isinstance(summary["snapshot"], dict):
            raise ControllerError("prepare did not perform exactly one OBSERVE-only snapshot")
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
            "prepare_summary": summary,
            "tested_code_head": self.expected_code_head,
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
        checkpoint = self._load()
        prepared = checkpoint["prepared"]
        if not authorized or not isinstance(prepared, dict) or prepared.get("consumed") is not False or nonce != prepared.get("nonce") or action_digest != prepared.get("action_digest"):
            raise ControllerError("hardware authorization is missing, consumed, or mismatched")
        try:
            expiry = datetime.strptime(str(prepared["expires_at_utc"]), UTC).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ControllerError("hardware authorization expiry is invalid") from exc
        if self.now() > expiry:
            raise ControllerError("hardware authorization expired")
        prepared["consumed"] = True
        self._write(checkpoint)
        action_id = str(prepared["action"])
        observed = self.backend.observe(action_id)
        if observed != prepared["summary"]:
            checkpoint["prepared"] = None
            self._write(checkpoint)
            raise ControllerError("identity/state changed before CONTROL/MODIFY")
        body = self.backend.execute(action_id)
        if not isinstance(body, dict) or set(body) != {"status", "artifacts"} or body["status"] not in {"PASS", "FAIL"} or not isinstance(body["artifacts"], list):
            raise ControllerError("hardware backend result is invalid")
        result = {
            "schema": "stm32-hardware-action-result/1",
            "action": action_id,
            "status": body["status"],
            "artifacts": body["artifacts"],
            "controller_code_head": self.controller_code_head,
            "tested_code_head": self.expected_code_head,
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
        self._write(checkpoint)
        return {"action": action_id, "status": "FRESH_PREPARE_REQUIRED"}


def run_wrapper_contract(
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
) -> dict[str, object]:
    """Run the Task-2 terminal wrapper path without activating reserved gates."""
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
    try:
        catalog = load_catalog(gate_catalog)
        load_performance_catalog(performance_catalog)
    except CatalogError as exc:
        raise ControllerError(str(exc)) from exc
    support = verify_support_root(support_profile)
    catalog_digest = hashlib.sha256(gate_catalog.read_bytes()).hexdigest()
    performance_digest = hashlib.sha256(performance_catalog.read_bytes()).hexdigest()
    support_digest = hashlib.sha256(support_profile.read_bytes()).hexdigest()
    candidate_ledger_path: Path | None = None
    candidate_ledger: dict[str, object] | None = None
    if kind == "candidate":
        candidate_root = evidence_root.parent
        if not candidate_root.is_dir():
            raise ControllerError("candidate root must already exist")
        candidate_ledger_path = candidate_root / "candidate-ledger.json"
        if candidate_ledger_path.exists():
            raise ControllerError("candidate ledger already exists; use the closed resume mode")
        candidate_ledger = create_candidate_ledger(
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
    reason = "CATALOG_FAMILIES_RESERVED"
    if kind == "candidate" and candidate_ledger is not None:
        try:
            reconcile_candidate(candidate_ledger)
        except VerificationError as exc:
            reason = f"CANDIDATE_PRECHECK_BLOCKED:{exc}"
    if not any(family.module == module for family in catalog.families):
        reason = "MODULE_FAMILY_MISSING"
    controller_result = {
        "schema": "stm32-gate-controller-result/1",
        "matrix": matrix,
        "module": module,
        "shard": shard,
        "run_id": run_id,
        "code_head": expected_code_head,
        "status": "BLOCKED",
        "reason": reason,
        "product_bodies": 0,
        "network_access": 0,
        "remote_git_actions": 0,
        "resume_count": 0,
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
                    "state": "blocked",
                    "resume_count": 0,
                    "interruption_event": None,
                }
            )
        )
    if candidate_ledger is not None and candidate_ledger_path is not None:
        previous = dict(candidate_ledger)
        updated = dict(candidate_ledger)
        updated["checkpoint"] = str(checkpoint)
        updated["state"] = "blocked"
        updated["updated_at_utc"] = _utc(now())
        write_candidate_ledger(candidate_ledger_path, updated, previous=previous)
    binding = {
        "owner": "Codex",
        "platform": f"windows-{platform.machine().casefold()}",
        "run_id": run_id,
        "code_head": expected_code_head,
        "catalog_sha256": catalog_digest,
        "locks": [],
        "support_sha256": str(support["manifest"]["sha256"]),
        "status": "BLOCKED",
    }
    package_path = evidence.parent / f"{evidence.name}.shard.zip"
    package = create_shard_package(evidence, package_path, binding)
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(package)
    )
    return {"status": "BLOCKED", "reason": reason, "binding": binding, "package": package}


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
}


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
    _, raw_ledger = _canonical_object_file(candidate_ledger_path)
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
    if set(checkpoint) != CONTROLLER_RESULT_KEYS:
        raise ControllerError("candidate checkpoint is not closed")
    if checkpoint.get("resume_count") != 0:
        raise ControllerError("candidate single-resume limit reached")
    if ledger["state"] not in {"blocked", "failed"}:
        raise ControllerError("candidate state is not resume-eligible")
    if (
        checkpoint.get("matrix") != "candidate"
        or checkpoint.get("module") != ledger["module"]
        or checkpoint.get("run_id") != ledger["candidate_run_id"]
        or checkpoint.get("code_head") != ledger["expected_code_head"]
        or checkpoint.get("status") not in {"FAIL", "BLOCKED"}
    ):
        raise ControllerError("candidate checkpoint identity/state mismatch")
    recovery_bytes, recovery = _canonical_object_file(recovery_record_path)
    try:
        validate_recovery_record(
            recovery,
            expected_run_kind="candidate-0601",
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
    checkpoint["resume_count"] = 1
    checkpoint_temp = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
    checkpoint_temp.write_bytes(canonical_json_bytes(checkpoint))
    os.replace(checkpoint_temp, checkpoint_path)
    previous = dict(ledger)
    ledger["state"] = "running"
    ledger["updated_at_utc"] = _utc(now())
    try:
        write_candidate_ledger(candidate_ledger_path, ledger, previous=previous)
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
    invocation_result = invoker(worktree, str(ledger["expected_code_head"]), verifier_args)
    if verifier_path != worktree.joinpath(*VERIFIER_RELATIVE_PATH.split("/")):
        raise ControllerError("candidate reconciliation returned a non-fixed verifier")
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
    if checkpoint.get("resume_count") != 0:
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
    checkpoint["resume_count"] = 1
    checkpoint["state"] = "running"
    temporary = checkpoint_path.with_name("checkpoint.json.tmp")
    temporary.write_bytes(canonical_json_bytes(checkpoint))
    os.replace(temporary, checkpoint_path)
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
    invocation_result = invoker(worktree, str(checkpoint["code_head"]), verifier_args)
    return {
        "status": "RESUMED",
        "checkpoint": str(checkpoint_path),
        "recovery_record_sha256": hashlib.sha256(recovery_bytes).hexdigest(),
        "verifier_result": None if invocation_result is None else str(invocation_result),
    }


def _contract_self_test(kind: str) -> dict[str, object]:
    if kind not in {"quick", "hardware"}:
        raise ControllerError("unknown self-test kind")
    if kind == "quick":
        fake_calls: list[str] = []

        def fake_execute(gate: GateRequest, _environment: dict[str, str]) -> GateRunOutput:
            fake_calls.append(gate.gate_id)
            code = 1 if gate.gate_id == "FAIL" else 0
            return GateRunOutput(code, b"fake", b"", gate.expected_nodes)

        fixture = [
            GateRequest("PASS", (sys.executable, "fake"), Path.cwd(), 1, ("fake::pass",)),
            GateRequest("FAIL", (sys.executable, "fake"), Path.cwd(), 1, ("fake::fail",)),
            GateRequest("BLOCKED", (sys.executable, "fake"), Path.cwd(), 1, ("fake::blocked",), prerequisites=("FAIL",)),
        ]
        states = [item.status for item in run_gate_matrix("quick", fixture, execute=fake_execute)]
        if states != ["PASS", "FAIL", "BLOCKED"] or fake_calls != ["PASS", "FAIL"]:
            raise ControllerError("quick self-test transitions failed")
    else:
        class FakeBackend:
            def __init__(self) -> None:
                self.snapshot = {"board": "fixture", "state": "running"}
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
    self_test.add_argument("--kind", choices=("quick", "hardware"), required=True)
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
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
