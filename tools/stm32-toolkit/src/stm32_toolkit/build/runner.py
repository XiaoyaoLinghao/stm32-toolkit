"""Bounded build orchestration with atomic evidence publication (STM32TK-0305).

``run_build`` validates the request and project model, takes the advisory
``.stm32-toolkit/build.lock``, runs ``cmake --preset`` configure and
``cmake --build --preset`` stages through the bounded process layer, and on
success validates the current ELF/MAP evidence before publishing
``build.log`` -> ``firmware-identity.json`` -> ``build-result.json`` in that
order, with the result file as the freshness commit point.  Exit code 0 from
the toolchain is never trusted on its own; the ELF and MAP are re-validated
after the build.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from stm32_toolkit.build.identity import (
    FirmwareIdentity,
    build_identity,
    git_evidence,
    read_text_bounded,
    sha256_file,
    snapshot_inputs,
    validate_elf,
    validate_identity_document,
    write_json_atomic,
    write_text_atomic,
)
from stm32_toolkit.build.map_file import parse_map
from stm32_toolkit.build.model import (
    BUILD_BUSY,
    BUILD_ENVIRONMENT_ERROR,
    BUILD_EVIDENCE_INVALID,
    BUILD_FAILED,
    BUILD_IDENTITY_INVALID,
    BUILD_MODEL_INVALID,
    BUILD_PUBLICATION_FAILED,
    BUILD_REQUEST_INVALID,
    BUILD_TIMEOUT,
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    BuildError,
    BuildReport,
    BuildRequest,
    MemoryUsage,
)
from stm32_toolkit.process import ProcessError, ProcessRequest, ProcessResult, run_process
from stm32_toolkit.project_model import ProjectManifestError, ProjectModel, load_project_model
from stm32_toolkit.result import OperationResult

_OPERATION = "project.build"
_LOCK_RELATIVE = ".stm32-toolkit/build.lock"
_OUTPUT_RELATIVE = ".stm32-toolkit/build"
_LOG_NAME = "build.log"
_IDENTITY_NAME = "firmware-identity.json"
_RESULT_NAME = "build-result.json"
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

_IS_WINDOWS = os.name == "nt"

_STAGE_MESSAGES = {
    BUILD_ENVIRONMENT_ERROR: "Toolchain executable could not be started",
    BUILD_TIMEOUT: "Build stage timed out",
    BUILD_FAILED: "Toolchain command failed",
}


def run_build(request: BuildRequest) -> OperationResult[BuildReport]:
    """Run one bounded configure+build and publish the evidence chain."""
    rule = _validate_request(request)
    if rule is not None:
        return OperationResult.failure(
            _OPERATION,
            BUILD_REQUEST_INVALID,
            "Build request is invalid",
            {"rule": rule},
        )
    try:
        root = request.project_root.expanduser().resolve(strict=False)
    except (OSError, ValueError):
        return OperationResult.failure(
            _OPERATION,
            BUILD_REQUEST_INVALID,
            "Build request is invalid",
            {"rule": "projectRoot"},
        )
    try:
        model = load_project_model(root)
    except ProjectManifestError as error:
        return OperationResult.failure(_OPERATION, BUILD_MODEL_INVALID, error.message, error.details)
    if request.preset not in model.build.presets:
        return OperationResult.failure(
            _OPERATION,
            BUILD_MODEL_INVALID,
            "Build preset is not declared by the project model",
            {"preset": request.preset, "rule": "undeclaredPreset"},
        )
    if model.build.elf is None:
        return OperationResult.failure(
            _OPERATION,
            BUILD_MODEL_INVALID,
            "Build model declares no ELF output",
            {"rule": "missingElf"},
        )
    try:
        lock = _acquire_lock(root)
    except BuildError as error:
        return OperationResult.failure(_OPERATION, error.code, error.message, error.details)
    if lock is None:
        return OperationResult.failure(
            _OPERATION,
            BUILD_BUSY,
            "Another build is already running",
            {},
        )
    try:
        return _run_stages(request, root, model)
    finally:
        _release_lock(lock)


def _validate_request(request: BuildRequest) -> str | None:
    if not isinstance(request, BuildRequest):
        return "type"
    if not isinstance(request.preset, str) or not request.preset:
        return "preset"
    if not isinstance(request.clean_first, bool):
        return "cleanFirst"
    if not isinstance(request.timeout_seconds, (int, float)) or isinstance(
        request.timeout_seconds, bool
    ):
        return "timeout"
    if not (MIN_TIMEOUT_SECONDS <= request.timeout_seconds <= MAX_TIMEOUT_SECONDS):
        return "timeout"
    if not isinstance(request.project_root, Path):
        return "projectRoot"
    return None


def _acquire_lock(root: Path):
    """Return an open locked file object, ``None`` when busy, else raise."""
    lock_path = root / _LOCK_RELATIVE
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fileobj = lock_path.open("a+b")
    except OSError as error:
        raise BuildError(
            BUILD_ENVIRONMENT_ERROR,
            "Build lock is not available",
            {"rule": "lock"},
        ) from error
    try:
        acquired = _lock_fd(fileobj)
    except OSError as error:
        fileobj.close()
        raise BuildError(
            BUILD_ENVIRONMENT_ERROR,
            "Build lock is not available",
            {"rule": "lock"},
        ) from error
    if not acquired:
        fileobj.close()
        return None
    return fileobj


def _lock_fd(fileobj) -> bool:
    """Take one advisory non-blocking exclusive lock; False when busy."""
    if _IS_WINDOWS:
        try:
            import msvcrt

            msvcrt.locking(fileobj.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        import fcntl

        fcntl.flock(fileobj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release_lock(fileobj) -> None:
    try:
        fileobj.close()
    except OSError:
        pass


@dataclass(frozen=True)
class _StageOutcome:
    stage: str
    preset: str
    code: str | None
    result: ProcessResult

    @property
    def ok(self) -> bool:
        return self.code is None


def _stage_failure(outcome: _StageOutcome) -> OperationResult[None]:
    details: dict[str, object] = {"stage": outcome.stage, "preset": outcome.preset}
    if outcome.code == BUILD_FAILED:
        details["returncode"] = outcome.result.returncode
        details["timedOut"] = False
    elif outcome.code == BUILD_TIMEOUT:
        details["timedOut"] = True
        details["durationSeconds"] = outcome.result.duration_seconds
    return OperationResult.failure(
        _OPERATION,
        outcome.code,
        _STAGE_MESSAGES[outcome.code],
        details,
    )


def _run_stages(
    request: BuildRequest, root: Path, model: ProjectModel
) -> OperationResult[BuildReport]:
    preset = request.preset
    timeout = request.timeout_seconds
    configure = _run_stage(
        "configure", ("cmake", "--preset", preset), root, timeout, preset
    )
    if not configure.ok:
        return _stage_failure(configure)
    build_argv = ("cmake", "--build", "--preset", preset)
    if request.clean_first:
        build_argv = build_argv + ("--clean-first",)
    build = _run_stage("build", build_argv, root, timeout, preset)
    if not build.ok:
        return _stage_failure(build)
    try:
        evidence = _collect_evidence(root, model, request, configure.result, build.result)
    except BuildError as error:
        return OperationResult.failure(_OPERATION, error.code, error.message, error.details)
    try:
        report = _publish(root, preset, evidence)
    except BuildError as error:
        return OperationResult.failure(_OPERATION, error.code, error.message, error.details)
    return OperationResult.success(_OPERATION, report)


def _run_stage(
    stage: str, argv: tuple[str, ...], root: Path, timeout: float, preset: str
) -> _StageOutcome:
    try:
        result = run_process(ProcessRequest(argv=argv, cwd=root, timeout_seconds=timeout))
    except ProcessError:
        return _StageOutcome(
            stage=stage,
            preset=preset,
            code=BUILD_ENVIRONMENT_ERROR,
            result=ProcessResult(
                returncode=None, stdout="", stderr="", timed_out=False, duration_seconds=0.0
            ),
        )
    if result.timed_out:
        return _StageOutcome(stage=stage, preset=preset, code=BUILD_TIMEOUT, result=result)
    if result.returncode != 0:
        return _StageOutcome(stage=stage, preset=preset, code=BUILD_FAILED, result=result)
    return _StageOutcome(stage=stage, preset=preset, code=None, result=result)


@dataclass(frozen=True)
class _Evidence:
    identity: FirmwareIdentity
    log_text: str
    report: BuildReport


def _collect_evidence(
    root: Path,
    model: ProjectModel,
    request: BuildRequest,
    configure: ProcessResult,
    build: ProcessResult,
) -> _Evidence:
    preset = request.preset
    elf_path = Path(model.build.elf)
    elf_absolute = root / elf_path
    map_absolute = elf_absolute.with_suffix(".map")
    if not elf_absolute.is_file():
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "ELF artifact is missing after a successful build",
            {"rule": "missingElf"},
        )
    if not map_absolute.is_file():
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "MAP artifact is missing after a successful build",
            {"rule": "missingMap"},
        )
    snapshot = snapshot_inputs(root, model)
    git = git_evidence(root)
    elf_sha256, elf_size = sha256_file(elf_absolute, _MAX_ARTIFACT_BYTES, "elfSize")
    map_sha256, map_size = sha256_file(map_absolute, _MAX_ARTIFACT_BYTES, "mapSize")
    elf_evidence = validate_elf(elf_absolute)
    map_text = read_text_bounded(map_absolute, _MAX_ARTIFACT_BYTES, rule="mapSize")
    memory_usage: tuple[MemoryUsage, ...] = parse_map(map_text).region_usage()
    built_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elf_relative = elf_path.as_posix()
    map_relative = map_absolute.relative_to(root).as_posix()
    identity = build_identity(
        preset=preset,
        clean_first=request.clean_first,
        git=git,
        snapshot=snapshot,
        elf_path=elf_relative,
        elf_sha256=elf_sha256,
        elf_size=elf_size,
        map_path=map_relative,
        map_sha256=map_sha256,
        map_size=map_size,
        elf_evidence=elf_evidence,
        memory_usage=memory_usage,
        built_at_utc=built_at_utc,
    )
    output_dir = f"{_OUTPUT_RELATIVE}/{preset}"
    log_path = f"{output_dir}/{_LOG_NAME}"
    identity_path = f"{output_dir}/{_IDENTITY_NAME}"
    result_path = f"{output_dir}/{_RESULT_NAME}"
    report = BuildReport(
        preset=preset,
        clean_first=request.clean_first,
        success=True,
        returncode=build.returncode,
        timed_out=False,
        duration_seconds=configure.duration_seconds + build.duration_seconds,
        stdout=build.stdout,
        stderr=build.stderr,
        log_path=log_path,
        identity_path=identity_path,
        result_path=result_path,
        elf_path=elf_relative,
        map_path=map_relative,
        identity=identity,
        memory_usage=memory_usage,
        error_code=None,
    )
    return _Evidence(
        identity=identity,
        log_text=_compose_log(configure, build),
        report=report,
    )


def _compose_log(configure: ProcessResult, build: ProcessResult) -> str:
    sections = (
        ("=== configure stdout ===", configure.stdout),
        ("=== configure stderr ===", configure.stderr),
        ("=== build stdout ===", build.stdout),
        ("=== build stderr ===", build.stderr),
    )
    text = "".join(f"{header}\n{content}" for header, content in sections)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _publish(root: Path, preset: str, evidence: _Evidence) -> BuildReport:
    """Publish log -> identity -> result; the result is the commit point."""
    payload = evidence.identity.to_dict()
    validate_identity_document(payload)
    output_dir = root / _OUTPUT_RELATIVE / preset
    try:
        write_text_atomic(output_dir / _LOG_NAME, evidence.log_text)
        write_json_atomic(output_dir / _IDENTITY_NAME, payload)
        write_json_atomic(output_dir / _RESULT_NAME, evidence.report.to_dict())
    except OSError as error:
        raise BuildError(
            BUILD_PUBLICATION_FAILED,
            "Build evidence publication failed",
            {"rule": "write"},
        ) from error
    return evidence.report
