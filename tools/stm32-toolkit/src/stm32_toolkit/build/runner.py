"""Build orchestration, locking, and stale-output defense (STM32TK-0305).

``run_build`` validates the request and the managed supported configuration,
takes the nonblocking advisory project lock, snapshots exact inputs, collects
bounded Git evidence, runs the exact fixed-argv ``cmake --preset`` configure
and ``cmake --build --preset`` (plus ``--clean-first`` only when requested)
stages through the bounded process layer, revalidates the input snapshot
immediately before configure and again after a successful build, refuses to
trust exit 0 without verifiable current ELF/MAP evidence, validates the GNU
MAP and ELF, constructs and schema-validates the firmware identity, and
publishes log → identity → build-result atomically with the build-result as
the freshness commit point.  Every failure after prerequisites publishes a
new failure log/result so a previous success can never remain fresh.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import (
    _ELF_LIMIT_BYTES,
    _EVIDENCE_LIMIT_BYTES,
    _FILE_LIMIT_BYTES,
    _MAP_LIMIT_BYTES,
    GitEvidence,
    GitUnavailableEvidence,
    SOURCE_LOCAL_HEADERS_POLICY,
    atomic_write_json,
    atomic_write_text,
    build_identity_document,
    collect_build_git_evidence,
    compute_build_id,
    identity_discovery_policy,
    hash_artifact,
    model_artifact_paths,
    read_bounded,
    read_evidence_json,
    read_map_text,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_identity_document,
    validate_elf,
    validate_snapshot_build_result,
)
from stm32_toolkit.build.map_file import MapError, parse_map
from stm32_toolkit.build.memory_margin import MemorySummaryError, build_memory_summary
from stm32_toolkit.build.model import (
    BUILD_ARTIFACT_INVALID,
    BUILD_BUSY,
    BUILD_CONFIGURE_FAILED,
    BUILD_EVIDENCE_FAILED,
    BUILD_FAILED,
    BUILD_INPUT_CHANGED,
    BUILD_MAP_INVALID,
    BUILD_OUTPUT_STALE,
    BUILD_PROJECT_INVALID,
    BUILD_REQUEST_INVALID,
    BUILD_TIMEOUT,
    BuildError,
    BuildReport,
    BuildRequest,
    FirmwareIdentity,
    SNAPSHOT_IDENTITY_SCHEMA_VERSION,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
    SUPPORTED_PRESETS,
    build_error,
)
from stm32_toolkit.generation.managed_files import (
    GENERATED_TARGETS,
    ManagedManifestFacts,
    is_supported_generation_producer,
    model_sha256_for,
    parse_managed_manifest_facts,
    portable_path_error,
    sha256_hex,
)
from stm32_toolkit.linker_fragment import BUILD_REMEDIATION
from stm32_toolkit.process import ProcessError, ProcessRequest, run_process
from stm32_toolkit.project_model import ProjectManifestError, ProjectModel, load_project_model
from stm32_toolkit.result import OperationResult

_OPERATION = "build"
_LOG_REL = "artifacts/migration/build.log"
_RESULT_REL = "artifacts/migration/build-result.json"

# ---------------------------------------------------------------------------
# advisory lock (product abstraction; real fcntl/msvcrt per host)
# ---------------------------------------------------------------------------

_IS_WINDOWS: bool = sys.platform == "win32"


def _lock_impl_windows(fd: int) -> bool:  # pragma: no cover - Windows-only
    import msvcrt

    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock_impl_windows(fd: int) -> None:  # pragma: no cover - Windows-only
    import msvcrt

    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _default_lock_impl(fd: int) -> bool:
    if _IS_WINDOWS:  # pragma: no cover - exercised on Windows
        return _lock_impl_windows(fd)  # pragma: no cover
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


_lock_impl = _default_lock_impl


def try_acquire_lock(fd: int) -> bool:
    try:
        return _lock_impl(fd)
    except OSError:
        return False


def release_lock(fd: int) -> None:
    try:
        if _IS_WINDOWS:  # pragma: no cover - exercised on Windows
            _unlock_impl_windows(fd)  # pragma: no cover
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


class _BuildLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            return False
        if not try_acquire_lock(fd):
            try:
                os.close(fd)
            except OSError:
                pass
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is not None:
            release_lock(self._fd)
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


# ---------------------------------------------------------------------------
# request and prerequisites
# ---------------------------------------------------------------------------


def _validate_request(request: BuildRequest) -> Path:
    if type(request) is not BuildRequest:
        raise build_error(
            BUILD_REQUEST_INVALID, "build request is invalid", {"field": "request", "rule": "type"}
        )
    if not isinstance(request.project_root, Path):
        raise build_error(
            BUILD_REQUEST_INVALID,
            "build request is invalid",
            {"field": "projectRoot", "rule": "type"},
        )
    try:
        root = request.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise build_error(
            BUILD_REQUEST_INVALID,
            "build request is invalid",
            {"field": "projectRoot", "rule": "value"},
        ) from None
    if not root.is_dir():
        raise build_error(
            BUILD_REQUEST_INVALID,
            "build request is invalid",
            {"field": "projectRoot", "rule": "value"},
        )
    if request.preset not in SUPPORTED_PRESETS:
        raise build_error(
            BUILD_REQUEST_INVALID, "build request is invalid", {"field": "preset", "rule": "value"}
        )
    if type(request.clean) is not bool:
        raise build_error(
            BUILD_REQUEST_INVALID, "build request is invalid", {"field": "clean", "rule": "type"}
        )
    if type(request.timeout_seconds) is not int:
        raise build_error(
            BUILD_REQUEST_INVALID,
            "build request is invalid",
            {"field": "timeoutSeconds", "rule": "type"},
        )
    if not 1 <= request.timeout_seconds <= 3600:
        raise build_error(
            BUILD_REQUEST_INVALID,
            "build request is invalid",
            {"field": "timeoutSeconds", "rule": "range"},
        )
    return root


def _fragment_provenance_error(path: str, rule: str) -> BuildError:
    return build_error(
        BUILD_PROJECT_INVALID,
        "managed configuration is invalid",
        {"path": path, "rule": rule, "remediation": BUILD_REMEDIATION},
    )


def _require_fragment_provenance(
    model: ProjectModel, facts: ManagedManifestFacts
) -> None:
    """Refuse stale managed output before any compiler can be spawned.

    The current manifest field alone is insufficient: a removed option would
    leave no field to inspect.  The configuration-time provenance recorded in
    the managed manifest is therefore compared with the current model, and a
    fragment project also requires the recorded project model hash to match
    the exact current model.
    """
    fragment = model.generation.linker_fragment
    recorded_path = facts.linker_fragment_path
    recorded_sha = facts.linker_fragment_sha256
    if fragment is None:
        if recorded_path is not None:
            raise _fragment_provenance_error(
                recorded_path, "linkerFragmentRemoved"
            )
        return
    if recorded_path is None or recorded_sha is None:
        raise _fragment_provenance_error(
            fragment.path, "linkerFragmentMissing"
        )
    if recorded_path != fragment.path or recorded_sha != fragment.sha256:
        raise _fragment_provenance_error(
            fragment.path, "linkerFragmentChanged"
        )
    if facts.project_manifest_sha256 != model_sha256_for(model):
        raise _fragment_provenance_error(
            ".stm32-project.json", "modelChanged"
        )


def _require_managed_configuration(root: Path) -> ProjectModel:
    try:
        model = load_project_model(root)
    except ProjectManifestError as error:
        raise build_error(BUILD_PROJECT_INVALID, error.message, error.details) from None
    if model.schema_version not in (2, 3):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "schemaVersion", "rule": "version"},
        )
    if type(model.generation.tool) is not str or model.generation.tool != "stm32-toolkit":
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "generation.tool", "rule": "tool"},
        )
    if not is_supported_generation_producer(model.generation.tool, model.generation.version):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "generation.version", "rule": "version"},
        )
    manifest_rel = model.generation.managed_manifest
    if portable_path_error(manifest_rel) is not None:
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            {"path": manifest_rel, "rule": "manifest"},
        )
    manifest_abs = root.joinpath(*manifest_rel.split("/"))
    try:
        manifest_data = read_bounded(manifest_abs, _FILE_LIMIT_BYTES)
    except OSError:
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            {"path": manifest_rel, "rule": "manifest"},
        ) from None
    if len(manifest_data) > _FILE_LIMIT_BYTES:
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            {"path": manifest_rel, "rule": "size"},
        )
    try:
        facts = parse_managed_manifest_facts(manifest_data)
    except Exception as error:
        details = getattr(error, "details", None)
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            dict(details) if isinstance(details, dict) else {"path": manifest_rel, "rule": "manifest"},
        ) from None
    records = facts.records
    _require_fragment_provenance(model, facts)
    native_linker = model.generation.native_linker_script
    targets = set(GENERATED_TARGETS)
    if native_linker is not None:
        targets.discard("linker/stm32tk.ld")
    for record in records:
        if record.path == native_linker or record.path not in targets:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "ownership"},
            )
        absolute = root.joinpath(*record.path.split("/"))
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "missing"},
            ) from None
        except OSError:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "unreadable"},
            ) from None
        if not stat.S_ISREG(lst.st_mode):
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "regularFile"},
            )
        try:
            file_bytes = read_bounded(absolute, _FILE_LIMIT_BYTES)
        except OSError:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "unreadable"},
            ) from None
        if len(file_bytes) > _FILE_LIMIT_BYTES:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "size"},
            )
        if sha256_hex(file_bytes) != record.sha256:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": record.path, "rule": "digest"},
            )
    required_targets = [
        "CMakeLists.txt",
        "CMakePresets.json",
        "cmake/arm-none-eabi-gcc.cmake",
    ]
    if native_linker is None:
        required_targets.append("linker/stm32tk.ld")
    else:
        native_absolute = root.joinpath(*native_linker.split("/"))
        try:
            native_lstat = os.lstat(native_absolute)
        except OSError:
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": native_linker, "rule": "missing"},
            ) from None
        if (
            stat.S_ISLNK(native_lstat.st_mode)
            or bool(getattr(native_lstat, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        ):
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": native_linker, "rule": "redirect"},
            )
        if not stat.S_ISREG(native_lstat.st_mode):
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": native_linker, "rule": "regularFile"},
            )
    for target in required_targets:
        if not (root / target).is_file():
            raise build_error(
                BUILD_PROJECT_INVALID,
                "managed configuration is invalid",
                {"path": target, "rule": "missing"},
            )
    return model


# ---------------------------------------------------------------------------
# stages, snapshots, stale-output defense
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ArtifactState:
    exists: bool
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class _StageOutcome:
    error: BuildError | None
    duration_ms: int = 0


def _artifact_state(path: Path) -> _ArtifactState:
    try:
        lst = os.lstat(path)
    except OSError:
        return _ArtifactState(False, 0, 0, "")
    if not stat.S_ISREG(lst.st_mode):
        return _ArtifactState(False, 0, 0, "")
    try:
        data = read_bounded(path, _ELF_LIMIT_BYTES)
    except OSError:
        return _ArtifactState(True, lst.st_size, lst.st_mtime_ns, "")
    if len(data) > _ELF_LIMIT_BYTES:
        return _ArtifactState(True, lst.st_size, lst.st_mtime_ns, "")
    return _ArtifactState(True, lst.st_size, lst.st_mtime_ns, sha256_hex(data))


def _snapshot_difference(first, second) -> str | None:
    a = {entry.path: (entry.size, entry.sha256) for entry in first.entries}
    b = {entry.path: (entry.size, entry.sha256) for entry in second.entries}
    if a != b:
        for path in sorted(set(a) | set(b)):
            if a.get(path) != b.get(path):
                return path
    return None


def _run_stage(
    stage: str,
    argv: tuple[str, ...],
    root: Path,
    timeout_seconds: int,
    sections: list[dict],
) -> _StageOutcome:
    try:
        result = run_process(
            ProcessRequest(argv=argv, cwd=root, timeout_seconds=timeout_seconds)
        )
    except ProcessError:
        sections.append(
            {
                "kind": "failure",
                "stage": stage,
                "code": "launch",
                "message": "process could not be launched",
            }
        )
        code = BUILD_CONFIGURE_FAILED if stage == "configure" else BUILD_FAILED
        message = "configure failed" if stage == "configure" else "build failed"
        return _StageOutcome(
            build_error(code, message, {"stage": stage, "rule": "launch", "log": _LOG_REL})
        )
    sections.append(
        {
            "kind": "process",
            "stage": stage,
            "argv": list(argv),
            "exitCode": result.returncode,
            "timedOut": result.timed_out,
            "stdoutTruncated": result.stdout_truncated,
            "stderrTruncated": result.stderr_truncated,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    if result.timed_out:
        return _StageOutcome(
            build_error(
                BUILD_TIMEOUT,
                "build timed out",
                {"stage": stage, "timeoutSeconds": timeout_seconds, "log": _LOG_REL},
            ),
            result.duration_ms,
        )
    if result.returncode != 0:
        code = BUILD_CONFIGURE_FAILED if stage == "configure" else BUILD_FAILED
        message = "configure failed" if stage == "configure" else "build failed"
        return _StageOutcome(
            build_error(
                code,
                message,
                {"stage": stage, "exitCode": result.returncode, "log": _LOG_REL},
            ),
            result.duration_ms,
        )
    return _StageOutcome(None, result.duration_ms)


def _load_prior_evidence(root: Path, preset: str):
    record = read_evidence_json(
        root.joinpath(*_RESULT_REL.split("/")), _RESULT_REL, _EVIDENCE_LIMIT_BYTES
    )
    identity_rel = f"build/{preset}/firmware-identity.json"
    identity_doc = read_evidence_json(
        root.joinpath(*identity_rel.split("/")), identity_rel, _EVIDENCE_LIMIT_BYTES
    )
    if record is None or identity_doc is None:
        return None
    return record, identity_doc


@dataclass(frozen=True)
class _EvidenceMatch:
    """Result of the single prior-evidence admission comparison.

    ``field``/``source`` are fixed names only; recorded values are never
    carried into diagnostics.
    """

    matched: bool
    reason: str | None = None
    field: str | None = None
    source: str | None = None


_EVIDENCE_MATCHED = _EvidenceMatch(True)

_STALE_OUTPUT_UNAVAILABLE = "output-unavailable"
_STALE_PRIOR_UNAVAILABLE = "prior-evidence-unavailable"
_STALE_PRIOR_FAILED = "prior-build-not-successful"
_STALE_INPUT_MISMATCH = "input-snapshot-mismatch"
_STALE_EVIDENCE_MISMATCH = "prior-evidence-mismatch"


def _evidence_mismatch(reason: str, field: str, source: str) -> _EvidenceMatch:
    return _EvidenceMatch(False, reason, field, source)


def _prior_evidence_check(
    prior,
    model: ProjectModel,
    preset: str,
    snapshot,
    provenance: GitEvidence | GitUnavailableEvidence,
    elf_rel: str,
    map_rel: str,
    post_elf: _ArtifactState,
    post_map: _ArtifactState,
) -> _EvidenceMatch:
    """Return the first bounded reason the prior success cannot be reused.

    The acceptance decision is unchanged: every predicate and its order is
    the same as the historical boolean comparison.  Only the first failing
    predicate is named so callers do not need a second validation algorithm.
    """
    record, identity_doc = prior
    if record.get("status") != "success":
        return _evidence_mismatch(_STALE_PRIOR_FAILED, "status", "record")
    if record.get("preset") != preset:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "preset", "record")
    if record.get("targetDevice") != model.target.device:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "targetDevice", "record")
    if record.get("inputSnapshotSha256") != snapshot.sha256:
        return _evidence_mismatch(_STALE_INPUT_MISMATCH, "inputSnapshotSha256", "record")
    try:
        validate_identity_document(identity_doc)
    except BuildError:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "identityDocument", "identity")
    if compute_build_id(identity_doc) != identity_doc.get("buildId"):
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "buildId", "identity")
    if identity_doc.get("preset") != preset:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "preset", "identity")
    if identity_doc.get("targetDevice") != model.target.device:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "targetDevice", "identity")
    if identity_doc.get("inputSnapshotSha256") != snapshot.sha256:
        return _evidence_mismatch(_STALE_INPUT_MISMATCH, "inputSnapshotSha256", "identity")
    if identity_discovery_policy(identity_doc) != snapshot.policy:
        return _evidence_mismatch(
            _STALE_EVIDENCE_MISMATCH, "inputDiscoveryPolicy", "identity"
        )
    if identity_doc.get("elfPath") != elf_rel:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "elfPath", "identity")
    if identity_doc.get("mapPath") != map_rel:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "mapPath", "identity")
    if identity_doc.get("elfSha256") != post_elf.sha256:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "elfSha256", "identity")
    if identity_doc.get("mapSha256") != post_map.sha256:
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "mapSha256", "identity")
    if record.get("buildId") != identity_doc.get("buildId"):
        return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "buildId", "record")
    if isinstance(provenance, GitEvidence):
        if record.get("schemaVersion") != 1:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "schemaVersion", "record")
        if identity_doc.get("schemaVersion") != 1:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "schemaVersion", "identity")
        if record.get("gitHead") != provenance.head:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitHead", "record")
        if identity_doc.get("gitHead") != provenance.head:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitHead", "identity")
        if "sourceBaseline" in identity_doc or "gitEvidence" in identity_doc:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "provenance", "identity")
    else:
        expected = provenance.to_dict()
        expected_artifacts = frozenset(
            {
                _LOG_REL,
                _RESULT_REL,
                f"build/{preset}/firmware-identity.json",
                elf_rel,
                map_rel,
            }
        )
        if not validate_snapshot_build_result(
            record, preset=preset, expected_artifact_paths=expected_artifacts
        ):
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "snapshotResult", "record")
        if identity_doc.get("schemaVersion") != SNAPSHOT_IDENTITY_SCHEMA_VERSION:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "schemaVersion", "identity")
        if identity_doc.get("logicalProjectId") != str(model.logical_project_id):
            return _evidence_mismatch(
                _STALE_EVIDENCE_MISMATCH, "logicalProjectId", "identity"
            )
        if identity_doc.get("toolkitVersion") != __version__:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "toolkitVersion", "identity")
        if identity_doc.get("sourceBaseline") != SOURCE_BASELINE_INPUT_SNAPSHOT:
            return _evidence_mismatch(
                _STALE_EVIDENCE_MISMATCH, "sourceBaseline", "identity"
            )
        if record.get("sourceBaseline") != SOURCE_BASELINE_INPUT_SNAPSHOT:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "sourceBaseline", "record")
        if identity_doc.get("gitHead") is not None or identity_doc.get("gitDirty") is not None:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitState", "identity")
        if record.get("gitHead") is not None or record.get("gitDirty") is not None:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitState", "record")
        if identity_doc.get("gitEvidence") != expected:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitEvidence", "identity")
        if record.get("gitEvidence") != expected:
            return _evidence_mismatch(_STALE_EVIDENCE_MISMATCH, "gitEvidence", "record")
    return _EVIDENCE_MATCHED


def _stale_remediation(
    reason: str, preset: str, clean_requested: bool, timeout_seconds: int
) -> dict[str, object]:
    """Return bounded advice for one stale reason; it never executes."""
    if reason == _STALE_OUTPUT_UNAVAILABLE:
        return {
            "action": "inspect-build-log",
            "summary": (
                "A required build output is unavailable after the command reported "
                "success. Do not repeat the same build automatically; inspect the "
                "build log and configuration first."
            ),
        }
    if clean_requested:
        return {
            "action": "inspect-build-log",
            "summary": (
                "The requested clean build did not produce outputs that match the "
                "current inputs and prior evidence. Do not repeat the same clean "
                "command automatically; inspect the build log and configuration first."
            ),
        }
    return {
        "action": "clean-rebuild",
        "summary": (
            "Current inputs and prior build evidence do not establish these outputs "
            "as fresh. A preset clean rebuild (CMake --clean-first) regenerates them, "
            "but it can still fail; this guidance executes nothing."
        ),
        "cli": {
            # ``arguments`` is only the command tail.  Prefix it with the
            # caller-verified executable, then this required option and the
            # caller's verified bound absolute project root.  The executable
            # label is symbolic, not a real path, and the bound root stays
            # outside this portable advice: no absolute path or shell string.
            "executable": "caller-verified-stm32-toolkit",
            "workingDirectory": "project-root",
            "projectRoot": {
                "option": "--project-root",
                "valueFrom": "same-bound-project-root",
                "required": True,
            },
            "arguments": [
                "build",
                "--preset",
                preset,
                "--clean",
                "--timeout-seconds",
                str(timeout_seconds),
            ],
        },
        "mcp": {
            "tool": "stm32_build",
            "arguments": {
                "preset": preset,
                "clean": True,
                "timeoutSeconds": timeout_seconds,
            },
        },
        "authorizationRequired": True,
        "authorization": (
            "Explicit user authorization for this exact clean build is required "
            "before execution."
        ),
    }


def _stale_details(
    *,
    path: str,
    rule: str,
    reason: str,
    preset: str,
    clean_requested: bool,
    timeout_seconds: int,
    evidence_field: str | None = None,
    evidence_source: str | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "path": path,
        "rule": rule,
        "reason": reason,
        "preset": preset,
        "cleanRequested": clean_requested,
        "logPath": _LOG_REL,
        "resultPath": _RESULT_REL,
        "identityPath": f"build/{preset}/firmware-identity.json",
        "remediation": _stale_remediation(
            reason, preset, clean_requested, timeout_seconds
        ),
    }
    if evidence_field is not None:
        details["evidenceField"] = evidence_field
    if evidence_source is not None:
        details["evidenceSource"] = evidence_source
    return details


def _require_fresh_outputs(
    root: Path,
    model: ProjectModel,
    request: BuildRequest,
    preset: str,
    pre_elf: _ArtifactState,
    pre_map: _ArtifactState,
    elf_rel: str,
    map_rel: str,
    elf_path: Path,
    map_path: Path,
    snapshot,
    provenance: GitEvidence | GitUnavailableEvidence,
) -> None:
    post_elf = _artifact_state(elf_path)
    post_map = _artifact_state(map_path)
    if not post_elf.exists:
        raise build_error(
            BUILD_OUTPUT_STALE,
            "build outputs are stale",
            _stale_details(
                path=elf_rel,
                rule="missing",
                reason=_STALE_OUTPUT_UNAVAILABLE,
                preset=preset,
                clean_requested=request.clean,
                timeout_seconds=request.timeout_seconds,
                evidence_source="output",
            ),
        )
    if not post_map.exists:
        raise build_error(
            BUILD_OUTPUT_STALE,
            "build outputs are stale",
            _stale_details(
                path=map_rel,
                rule="missing",
                reason=_STALE_OUTPUT_UNAVAILABLE,
                preset=preset,
                clean_requested=request.clean,
                timeout_seconds=request.timeout_seconds,
                evidence_source="output",
            ),
        )
    if pre_elf != post_elf or pre_map != post_map:
        return
    prior = _load_prior_evidence(root, preset)
    if prior is None:
        raise build_error(
            BUILD_OUTPUT_STALE,
            "build outputs are stale",
            _stale_details(
                path=elf_rel,
                rule="unverifiable",
                reason=_STALE_PRIOR_UNAVAILABLE,
                preset=preset,
                clean_requested=request.clean,
                timeout_seconds=request.timeout_seconds,
            ),
        )
    match = _prior_evidence_check(
        prior, model, preset, snapshot, provenance, elf_rel, map_rel, post_elf, post_map
    )
    if not match.matched:
        raise build_error(
            BUILD_OUTPUT_STALE,
            "build outputs are stale",
            _stale_details(
                path=elf_rel,
                rule="unverifiable",
                reason=match.reason or _STALE_EVIDENCE_MISMATCH,
                preset=preset,
                clean_requested=request.clean,
                timeout_seconds=request.timeout_seconds,
                evidence_field=match.field,
                evidence_source=match.source,
            ),
        )


# ---------------------------------------------------------------------------
# log rendering and build-result documents
# ---------------------------------------------------------------------------


def render_build_log(root: Path, sections: list[dict]) -> str:
    """Render the sanitized log: LF newlines, root spellings replaced."""
    lines: list[str] = []
    for section in sections:
        lines.append(f"[stage:{section['stage']}]")
        if section["kind"] == "process":
            lines.append("argv=" + json.dumps(section["argv"]))
            lines.append("exitCode=" + str(section["exitCode"]))
            lines.append("timedOut=" + str(section["timedOut"]).lower())
            lines.append("stdoutTruncated=" + str(section["stdoutTruncated"]).lower())
            lines.append("stderrTruncated=" + str(section["stderrTruncated"]).lower())
            lines.append("stdout:")
            lines.append(section["stdout"])
            lines.append("stderr:")
            lines.append(section["stderr"])
        else:
            lines.append("result=failure")
            lines.append("code=" + section["code"])
            lines.append("message=" + section["message"])
    text = "\n".join(lines) + "\n"
    text = text.replace(str(root), "<PROJECT_ROOT>")
    text = text.replace(root.as_posix(), "<PROJECT_ROOT>")
    return text


def build_result_document(
    *,
    status: str,
    stage: str,
    code: str,
    build_id: str | None,
    git_head: str | None,
    git_dirty: bool | None,
    input_snapshot_sha256: str | None,
    target_device: str,
    preset: str,
    started_at_utc: str,
    finished_at_utc: str,
    duration_ms: int,
    artifacts: list[dict],
    memory: list[dict],
    warnings: list[str],
    schema_version: int = 1,
    source_baseline: str | None = None,
    git_evidence: dict[str, str] | None = None,
) -> dict:
    document: dict[str, object] = {
        "schemaVersion": schema_version,
        "status": status,
        "stage": stage,
        "code": code,
        "buildId": build_id,
    }
    if source_baseline is not None:
        document["sourceBaseline"] = source_baseline
    document["gitHead"] = git_head
    document["gitDirty"] = git_dirty
    if git_evidence is not None:
        document["gitEvidence"] = dict(git_evidence)
    document.update(
        {
            "inputSnapshotSha256": input_snapshot_sha256,
            "targetDevice": target_device,
            "preset": preset,
            "startedAtUtc": started_at_utc,
            "finishedAtUtc": finished_at_utc,
            "durationMs": duration_ms,
            "artifacts": artifacts,
            "memory": memory,
            "warnings": warnings,
        }
    )
    return document


# ---------------------------------------------------------------------------
# failure publication
# ---------------------------------------------------------------------------


def _failure(error: BuildError) -> OperationResult[None]:
    return OperationResult.failure(_OPERATION, error.code, error.message, error.details)


def _publish_failure(
    error: BuildError,
    root: Path,
    model: ProjectModel,
    preset: str,
    stage: str,
    started_at: str,
    started_mono: float,
    sections: list[dict],
    provenance: GitEvidence | GitUnavailableEvidence | None = None,
) -> OperationResult[None]:
    finished_at = utc_now_rfc3339()
    duration_ms = int((time.monotonic() - started_mono) * 1000)
    log_text = render_build_log(
        root,
        [
            *sections,
            {
                "kind": "failure",
                "stage": stage,
                "code": error.code,
                "message": error.message,
            },
        ],
    )
    if isinstance(provenance, GitUnavailableEvidence):
        # A failed snapshot build never claims a Git state; both fields stay
        # null and the bounded availability diagnostic is retained.
        result_doc = build_result_document(
            status="failure",
            stage=stage,
            code=error.code,
            build_id=None,
            git_head=None,
            git_dirty=None,
            input_snapshot_sha256=None,
            target_device=model.target.device,
            preset=preset,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            duration_ms=duration_ms,
            artifacts=[{"path": _LOG_REL}],
            memory=[],
            warnings=[],
            schema_version=SNAPSHOT_IDENTITY_SCHEMA_VERSION,
            source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
            git_evidence=provenance.to_dict(),
        )
    else:
        # Legacy schema-1 failure records keep their exact established bytes:
        # no admitted identity exists, so the head is null and dirty is false
        # regardless of the collected provenance details.
        result_doc = build_result_document(
            status="failure",
            stage=stage,
            code=error.code,
            build_id=None,
            git_head=None,
            git_dirty=False,
            input_snapshot_sha256=None,
            target_device=model.target.device,
            preset=preset,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            duration_ms=duration_ms,
            artifacts=[{"path": _LOG_REL}],
            memory=[],
            warnings=[],
        )
    try:
        atomic_write_text(root.joinpath(*_LOG_REL.split("/")), log_text)
    except OSError:
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": _LOG_REL, "phase": "log"},
            )
        )
    try:
        atomic_write_json(root.joinpath(*_RESULT_REL.split("/")), result_doc)
    except OSError:
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": _RESULT_REL, "phase": "result"},
            )
        )
    return _failure(error)


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def run_build(request: BuildRequest) -> OperationResult[BuildReport]:
    """Run the bounded build and publish one current success/failure record."""
    try:
        root = _validate_request(request)
        model = _require_managed_configuration(root)
        preset = request.preset
        elf_rel, map_rel = model_artifact_paths(model, preset)
    except BuildError as error:
        return _failure(error)
    lock = _BuildLock(root / ".stm32-toolkit" / "build.lock")
    if not lock.acquire():
        return OperationResult.failure(
            _OPERATION,
            BUILD_BUSY,
            "another build holds the project lock",
            {"path": ".stm32-toolkit/build.lock"},
        )
    try:
        return _run_locked(request, root, model, preset, elf_rel, map_rel)
    finally:
        lock.release()


def _run_locked(
    request: BuildRequest,
    root: Path,
    model: ProjectModel,
    preset: str,
    elf_rel: str,
    map_rel: str,
) -> OperationResult:
    started_at = utc_now_rfc3339()
    started_mono = time.monotonic()
    elf_path = root.joinpath(*elf_rel.split("/"))
    map_path = root.joinpath(*map_rel.split("/"))
    pre_elf = _artifact_state(elf_path)
    pre_map = _artifact_state(map_path)
    sections: list[dict] = []

    try:
        snapshot = snapshot_project_inputs(model, policy=SOURCE_LOCAL_HEADERS_POLICY)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections
        )
    # Git availability never decides build success.  The strict collector
    # still propagates unexpected errors; only the stable availability error
    # becomes a bounded snapshot diagnostic.
    provenance = collect_build_git_evidence(root)
    try:
        second = snapshot_project_inputs(model, policy=SOURCE_LOCAL_HEADERS_POLICY)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections,
            provenance,
        )
    changed = _snapshot_difference(snapshot, second)
    if changed is not None:
        error = build_error(BUILD_INPUT_CHANGED, "build inputs changed", {"path": changed})
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections,
            provenance,
        )

    configure = _run_stage(
        "configure", ("cmake", "--preset", preset), root, request.timeout_seconds, sections
    )
    if configure.error is not None:
        return _publish_failure(
            configure.error, root, model, preset, "configure", started_at, started_mono,
            sections, provenance,
        )
    build_argv = ("cmake", "--build", "--preset", preset)
    if request.clean:
        build_argv = build_argv + ("--clean-first",)
    build_outcome = _run_stage("build", build_argv, root, request.timeout_seconds, sections)
    if build_outcome.error is not None:
        return _publish_failure(
            build_outcome.error, root, model, preset, "build", started_at, started_mono,
            sections, provenance,
        )

    try:
        post_snapshot = snapshot_project_inputs(model, policy=SOURCE_LOCAL_HEADERS_POLICY)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections,
            provenance,
        )
    changed = _snapshot_difference(snapshot, post_snapshot)
    if changed is not None:
        error = build_error(BUILD_INPUT_CHANGED, "build inputs changed", {"path": changed})
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections,
            provenance,
        )

    try:
        _require_fresh_outputs(
            root,
            model,
            request,
            preset,
            pre_elf,
            pre_map,
            elf_rel,
            map_rel,
            elf_path,
            map_path,
            snapshot,
            provenance,
        )
        # ELF format, security, and section attributes are validated first;
        # its immutable section evidence then classifies every non-zero MAP
        # output section (SHF_ALLOC vs debug/comment rows at VMA 0).
        elf_evidence = validate_elf(elf_path, model)
        elf_size, elf_sha = hash_artifact(
            elf_path, elf_rel, _ELF_LIMIT_BYTES, BUILD_ARTIFACT_INVALID
        )
        map_text = read_map_text(map_path, map_rel)
        usages = parse_map(
            map_text,
            model.memory.regions,
            path=map_rel,
            elf_sections=elf_evidence.sections,
        )
        try:
            memory_summary = build_memory_summary(usages)
        except MemorySummaryError:
            raise build_error(
                BUILD_EVIDENCE_FAILED,
                "build evidence is invalid",
                {"phase": "memorySummary"},
            ) from None
        memory_warnings = memory_summary.warning_texts()
        map_size, map_sha = hash_artifact(map_path, map_rel, _MAP_LIMIT_BYTES, BUILD_MAP_INVALID)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections,
            provenance,
        )

    identity_doc = build_identity_document(
        model=model,
        preset=preset,
        git=provenance if isinstance(provenance, GitEvidence) else None,
        git_unavailable=(
            provenance if isinstance(provenance, GitUnavailableEvidence) else None
        ),
        snapshot=snapshot,
        elf=elf_evidence,
        elf_size=elf_size,
        elf_sha256=elf_sha,
        map_size=map_size,
        map_sha256=map_sha,
        built_at_utc=utc_now_rfc3339(),
        memory_summary=memory_summary,
    )
    try:
        validate_identity_document(identity_doc)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections,
            provenance,
        )
    typed_identity = FirmwareIdentity.from_document(identity_doc)
    if typed_identity.to_dict() != identity_doc:
        # Typed evidence must round-trip the identity before any success
        # evidence is published; a mismatch must never leave a fresh success.
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": f"build/{preset}/firmware-identity.json", "phase": "identity"},
            )
        )

    identity_rel = f"build/{preset}/firmware-identity.json"
    finished_at = utc_now_rfc3339()
    duration_ms = int((time.monotonic() - started_mono) * 1000)
    snapshot_mode = identity_doc["schemaVersion"] == SNAPSHOT_IDENTITY_SCHEMA_VERSION
    result_doc = build_result_document(
        status="success",
        stage="",
        code="OK",
        build_id=str(identity_doc["buildId"]),
        git_head=identity_doc["gitHead"],
        git_dirty=identity_doc["gitDirty"],
        input_snapshot_sha256=str(identity_doc["inputSnapshotSha256"]),
        target_device=str(identity_doc["targetDevice"]),
        preset=preset,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        duration_ms=duration_ms,
        artifacts=[
            {"path": _LOG_REL},
            {"path": _RESULT_REL},
            {"path": identity_rel},
            {"path": elf_rel},
            {"path": map_rel},
        ],
        memory=[item.to_dict() for item in usages],
        warnings=list(memory_warnings),
        schema_version=(
            SNAPSHOT_IDENTITY_SCHEMA_VERSION if snapshot_mode else 1
        ),
        source_baseline=(
            SOURCE_BASELINE_INPUT_SNAPSHOT if snapshot_mode else None
        ),
        git_evidence=(
            dict(identity_doc["gitEvidence"]) if snapshot_mode else None
        ),
    )
    log_text = render_build_log(root, sections)
    try:
        atomic_write_text(root.joinpath(*_LOG_REL.split("/")), log_text)
    except OSError:
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": _LOG_REL, "phase": "log"},
            )
        )
    try:
        atomic_write_json(root.joinpath(*identity_rel.split("/")), identity_doc)
    except OSError:
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": identity_rel, "phase": "identity"},
            )
        )
    try:
        atomic_write_json(root.joinpath(*_RESULT_REL.split("/")), result_doc)
    except OSError:
        return _failure(
            build_error(
                BUILD_EVIDENCE_FAILED,
                "evidence publication failed",
                {"path": _RESULT_REL, "phase": "result"},
            )
        )

    report = BuildReport(
        identity=typed_identity,
        memory=usages,
        warnings=memory_warnings,
        build_log_path=_LOG_REL,
        build_result_path=_RESULT_REL,
        identity_path=identity_rel,
        configure_duration_ms=configure.duration_ms,
        build_duration_ms=build_outcome.duration_ms,
    )
    return OperationResult.success(_OPERATION, report)
