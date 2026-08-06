"""Build orchestration, locking, and stale-output defense (STM32TK-0305).

``run_build`` validates the request and the managed Schema v2 configuration,
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
    atomic_write_json,
    atomic_write_text,
    build_identity_document,
    compute_build_id,
    git_evidence,
    hash_artifact,
    model_artifact_paths,
    read_bounded,
    read_evidence_json,
    read_map_text,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_identity_document,
    validate_elf,
)
from stm32_toolkit.build.map_file import MapError, parse_map
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
    SUPPORTED_PRESETS,
    build_error,
)
from stm32_toolkit.generation.managed_files import (
    GENERATED_TARGETS,
    parse_managed_manifest,
    portable_path_error,
    sha256_hex,
)
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


def _require_managed_configuration(root: Path) -> ProjectModel:
    try:
        model = load_project_model(root)
    except ProjectManifestError as error:
        raise build_error(BUILD_PROJECT_INVALID, error.message, error.details) from None
    if model.schema_version != 2:
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "schemaVersion", "rule": "version"},
        )
    if model.generation.tool != "stm32-toolkit":
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "generation.tool", "rule": "tool"},
        )
    if model.generation.version != __version__:
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
        records = parse_managed_manifest(manifest_data)
    except Exception as error:
        details = getattr(error, "details", None)
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            dict(details) if isinstance(details, dict) else {"path": manifest_rel, "rule": "manifest"},
        ) from None
    targets = set(GENERATED_TARGETS)
    for record in records:
        if record.path not in targets:
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
    for target in (
        "CMakeLists.txt",
        "CMakePresets.json",
        "cmake/arm-none-eabi-gcc.cmake",
        "linker/stm32tk.ld",
    ):
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


def _prior_evidence_matches(
    prior,
    model: ProjectModel,
    preset: str,
    snapshot,
    git: GitEvidence,
    elf_rel: str,
    map_rel: str,
    post_elf: _ArtifactState,
    post_map: _ArtifactState,
) -> bool:
    record, identity_doc = prior
    if record.get("status") != "success":
        return False
    if record.get("preset") != preset:
        return False
    if record.get("targetDevice") != model.target.device:
        return False
    if record.get("inputSnapshotSha256") != snapshot.sha256:
        return False
    if record.get("gitHead") != git.head:
        return False
    try:
        validate_identity_document(identity_doc)
    except BuildError:
        return False
    if compute_build_id(identity_doc) != identity_doc.get("buildId"):
        return False
    if identity_doc.get("preset") != preset:
        return False
    if identity_doc.get("targetDevice") != model.target.device:
        return False
    if identity_doc.get("inputSnapshotSha256") != snapshot.sha256:
        return False
    if identity_doc.get("gitHead") != git.head:
        return False
    if identity_doc.get("elfPath") != elf_rel or identity_doc.get("mapPath") != map_rel:
        return False
    if (
        identity_doc.get("elfSha256") != post_elf.sha256
        or identity_doc.get("mapSha256") != post_map.sha256
    ):
        return False
    if record.get("buildId") != identity_doc.get("buildId"):
        return False
    return True


def _require_fresh_outputs(
    root: Path,
    model: ProjectModel,
    preset: str,
    pre_elf: _ArtifactState,
    pre_map: _ArtifactState,
    elf_rel: str,
    map_rel: str,
    elf_path: Path,
    map_path: Path,
    snapshot,
    git: GitEvidence,
) -> None:
    post_elf = _artifact_state(elf_path)
    post_map = _artifact_state(map_path)
    if not post_elf.exists:
        raise build_error(
            BUILD_OUTPUT_STALE, "build outputs are stale", {"path": elf_rel, "rule": "missing"}
        )
    if not post_map.exists:
        raise build_error(
            BUILD_OUTPUT_STALE, "build outputs are stale", {"path": map_rel, "rule": "missing"}
        )
    if pre_elf != post_elf or pre_map != post_map:
        return
    prior = _load_prior_evidence(root, preset)
    if prior is None or not _prior_evidence_matches(
        prior, model, preset, snapshot, git, elf_rel, map_rel, post_elf, post_map
    ):
        raise build_error(
            BUILD_OUTPUT_STALE,
            "build outputs are stale",
            {"path": elf_rel, "rule": "unverifiable"},
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
    git_dirty: bool,
    input_snapshot_sha256: str | None,
    target_device: str,
    preset: str,
    started_at_utc: str,
    finished_at_utc: str,
    duration_ms: int,
    artifacts: list[dict],
    memory: list[dict],
    warnings: list[str],
) -> dict:
    return {
        "schemaVersion": 1,
        "status": status,
        "stage": stage,
        "code": code,
        "buildId": build_id,
        "gitHead": git_head,
        "gitDirty": git_dirty,
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
        snapshot = snapshot_project_inputs(model)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections
        )
    try:
        git = git_evidence(root)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "git", started_at, started_mono, sections
        )
    try:
        second = snapshot_project_inputs(model)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections
        )
    changed = _snapshot_difference(snapshot, second)
    if changed is not None:
        error = build_error(BUILD_INPUT_CHANGED, "build inputs changed", {"path": changed})
        return _publish_failure(
            error, root, model, preset, "snapshot", started_at, started_mono, sections
        )

    configure = _run_stage(
        "configure", ("cmake", "--preset", preset), root, request.timeout_seconds, sections
    )
    if configure.error is not None:
        return _publish_failure(
            configure.error, root, model, preset, "configure", started_at, started_mono, sections
        )
    build_argv = ("cmake", "--build", "--preset", preset)
    if request.clean:
        build_argv = build_argv + ("--clean-first",)
    build_outcome = _run_stage("build", build_argv, root, request.timeout_seconds, sections)
    if build_outcome.error is not None:
        return _publish_failure(
            build_outcome.error, root, model, preset, "build", started_at, started_mono, sections
        )

    try:
        post_snapshot = snapshot_project_inputs(model)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections
        )
    changed = _snapshot_difference(snapshot, post_snapshot)
    if changed is not None:
        error = build_error(BUILD_INPUT_CHANGED, "build inputs changed", {"path": changed})
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections
        )

    try:
        _require_fresh_outputs(
            root,
            model,
            preset,
            pre_elf,
            pre_map,
            elf_rel,
            map_rel,
            elf_path,
            map_path,
            snapshot,
            git,
        )
        map_text = read_map_text(map_path, map_rel)
        usages = parse_map(map_text, model.memory.regions, path=map_rel)
        map_size, map_sha = hash_artifact(map_path, map_rel, _MAP_LIMIT_BYTES, BUILD_MAP_INVALID)
        elf_evidence = validate_elf(elf_path, model)
        elf_size, elf_sha = hash_artifact(elf_path, elf_rel, _ELF_LIMIT_BYTES, BUILD_ARTIFACT_INVALID)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections
        )

    identity_doc = build_identity_document(
        model=model,
        preset=preset,
        git=git,
        snapshot=snapshot,
        elf=elf_evidence,
        elf_size=elf_size,
        elf_sha256=elf_sha,
        map_size=map_size,
        map_sha256=map_sha,
        built_at_utc=utc_now_rfc3339(),
    )
    try:
        validate_identity_document(identity_doc)
    except BuildError as error:
        return _publish_failure(
            error, root, model, preset, "validate", started_at, started_mono, sections
        )

    identity_rel = f"build/{preset}/firmware-identity.json"
    finished_at = utc_now_rfc3339()
    duration_ms = int((time.monotonic() - started_mono) * 1000)
    result_doc = build_result_document(
        status="success",
        stage="",
        code="OK",
        build_id=str(identity_doc["buildId"]),
        git_head=str(identity_doc["gitHead"]),
        git_dirty=bool(identity_doc["gitDirty"]),
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
        warnings=[],
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
        identity=FirmwareIdentity(
            schema_version=int(identity_doc["schemaVersion"]),
            build_id=str(identity_doc["buildId"]),
            logical_project_id=str(identity_doc["logicalProjectId"]),
            toolkit_version=str(identity_doc["toolkitVersion"]),
            git_head=str(identity_doc["gitHead"]),
            git_dirty=bool(identity_doc["gitDirty"]),
            input_snapshot_sha256=str(identity_doc["inputSnapshotSha256"]),
            newest_input_mtime_ns=int(identity_doc["newestInputMtimeNs"]),
            target_device=str(identity_doc["targetDevice"]),
            preset=str(identity_doc["preset"]),
            elf_path=str(identity_doc["elfPath"]),
            elf_sha256=str(identity_doc["elfSha256"]),
            elf_size=int(identity_doc["elfSize"]),
            map_path=str(identity_doc["mapPath"]),
            map_sha256=str(identity_doc["mapSha256"]),
            entry_point=int(identity_doc["entryPoint"]),
            vector_address=int(identity_doc["vectorAddress"]),
            reset_handler_address=int(identity_doc["resetHandlerAddress"]),
            built_at_utc=str(identity_doc["builtAtUtc"]),
        ),
        memory=usages,
        warnings=(),
        build_log_path=_LOG_REL,
        build_result_path=_RESULT_REL,
        identity_path=identity_rel,
        configure_duration_ms=configure.duration_ms,
        build_duration_ms=build_outcome.duration_ms,
    )
    return OperationResult.success(_OPERATION, report)
