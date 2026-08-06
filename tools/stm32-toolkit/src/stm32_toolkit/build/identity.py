"""Firmware identity evidence construction (STM32TK-0305).

Builds the schema-1 firmware identity for one successful build: a bounded
input snapshot (manifest plus declared sources), bounded Git HEAD/branch/
target evidence, ELF32 little-endian ARM validation (vector table,
Reset_Handler, entry-point consistency, undefined symbols), GNU MAP memory
usage, a deterministic build id, schema validation, and atomic JSON helpers.
All file reads are bounded; all paths in evidence are portable ``/`` paths.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from hashlib import sha256
from importlib import resources
from io import BytesIO
from pathlib import Path

from jsonschema import Draft202012Validator
from elftools.elf.elffile import ELFFile

from stm32_toolkit.build.model import (
    BUILD_EVIDENCE_INVALID,
    BUILD_IDENTITY_INVALID,
    BuildError,
    FirmwareIdentity,
    InputSnapshot,
    InputSnapshotFile,
    MemoryUsage,
)
from stm32_toolkit.process import ProcessError, ProcessRequest, run_process
from stm32_toolkit.project_model import ProjectModel

_WINDOWS = os.name == "nt"

#: Per-file and aggregate bounds for the input snapshot.
_MAX_INPUT_FILE_BYTES = 8 * 1024 * 1024
_MAX_INPUT_TOTAL_BYTES = 64 * 1024 * 1024

#: Bounds for ELF/MAP artifacts and evidence JSON.
_MAX_ELF_BYTES = 64 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_EVIDENCE_JSON_BYTES = 8 * 1024 * 1024

#: Bounded Git evidence probes.
_GIT_TIMEOUT_SECONDS = 5.0
_GIT_MAX_BYTES = 4096
_GIT_MAX_LINES = 4

_IDENTITY_SCHEMA_NAME = "firmware-identity.schema.json"
_READ_CHUNK = 64 * 1024

_VALIDATOR: Draft202012Validator | None = None


@dataclass(frozen=True)
class GitEvidence:
    """Bounded Git state for one project root."""

    head: str | None
    branch: str | None
    target: str | None


@dataclass(frozen=True)
class ElfEvidence:
    """Validated ELF facts for one firmware image."""

    entry_point: int
    isr_vector_present: bool
    reset_handler_present: bool
    reset_handler_address: int | None
    entry_point_consistent: bool
    undefined_symbols: tuple[str, ...]


def snapshot_inputs(project_root: Path, model: ProjectModel) -> InputSnapshot:
    """Snapshot the manifest plus declared sources/assembly inputs."""
    paths = (".stm32-project.json", *model.build.sources, *model.build.assembly_sources)
    return _snapshot_entries(project_root, paths)


def snapshot_sha256(project_root: Path, relative_paths: tuple[str, ...]) -> str:
    """Aggregate snapshot digest for a fixed list of project-relative paths."""
    return _snapshot_entries(project_root, relative_paths).sha256


def _snapshot_entries(project_root: Path, relative_paths: tuple[str, ...]) -> InputSnapshot:
    normalized: list[str] = []
    for relative in relative_paths:
        portable = str(relative).replace("\\", "/")
        if portable not in normalized:
            normalized.append(portable)
    entries: list[InputSnapshotFile] = []
    total = 0
    for portable in sorted(normalized):
        absolute = project_root / portable
        if not absolute.is_file():
            raise BuildError(
                BUILD_EVIDENCE_INVALID,
                "Build input is missing",
                {"path": portable, "rule": "missingInput"},
            )
        digest, size = _snapshot_file(absolute, portable)
        total += size
        if total > _MAX_INPUT_TOTAL_BYTES:
            raise BuildError(
                BUILD_EVIDENCE_INVALID,
                "Build inputs exceed the aggregate size limit",
                {"rule": "inputSize"},
            )
        entries.append(InputSnapshotFile(path=portable, sha256=digest))
    files = tuple(entries)
    canonical = json.dumps(
        {"files": [entry.to_dict() for entry in files]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return InputSnapshot(sha256=sha256(canonical.encode("utf-8")).hexdigest(), files=files)


def _snapshot_file(absolute: Path, portable: str) -> tuple[str, int]:
    try:
        return sha256_file(absolute, _MAX_INPUT_FILE_BYTES, "inputSize")
    except BuildError as error:
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            error.message,
            {"path": portable, **error.details},
        ) from error


def sha256_file(path: Path, max_bytes: int, rule: str) -> tuple[str, int]:
    """Stream a file with a hard byte bound; return ``(sha256, size)``."""
    digest = sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise BuildError(
                        BUILD_EVIDENCE_INVALID,
                        "Build artifact exceeds the size limit",
                        {"rule": rule},
                    )
                digest.update(chunk)
    except BuildError:
        raise
    except OSError:
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "Build artifact is not readable",
            {"rule": rule},
        ) from None
    return digest.hexdigest(), size


def git_evidence(project_root: Path) -> GitEvidence:
    """Return bounded Git evidence; unavailable probes become ``None``."""
    return GitEvidence(
        head=_git_value(project_root, ("rev-parse", "HEAD")),
        branch=_git_value(project_root, ("branch", "--show-current")),
        target=_git_value(project_root, ("symbolic-ref", "--short", "refs/remotes/origin/HEAD")),
    )


def _git_value(project_root: Path, arguments: tuple[str, ...]) -> str | None:
    try:
        result = run_process(
            ProcessRequest(
                argv=("git", *arguments),
                cwd=project_root,
                timeout_seconds=_GIT_TIMEOUT_SECONDS,
                max_bytes=_GIT_MAX_BYTES,
                max_lines=_GIT_MAX_LINES,
            )
        )
    except ProcessError:
        return None
    if result.timed_out or result.returncode != 0:
        return None
    line = result.stdout.strip()
    return line or None


def validate_elf(elf_path: Path) -> ElfEvidence:
    """Validate an ELF32 little-endian ARM image and return its facts."""
    try:
        raw = _read_bounded(elf_path, _MAX_ELF_BYTES, "elfSize", "missingElf")
    except BuildError:
        raise
    try:
        with BytesIO(raw) as stream:
            elf = ELFFile(stream)
            if elf.elfclass != 32:
                raise BuildError(
                    BUILD_EVIDENCE_INVALID,
                    "Firmware ELF must be 32-bit",
                    {"rule": "elfClass"},
                )
            if not elf.little_endian:
                raise BuildError(
                    BUILD_EVIDENCE_INVALID,
                    "Firmware ELF must be little-endian",
                    {"rule": "elfData"},
                )
            if elf.header["e_machine"] != "EM_ARM":
                raise BuildError(
                    BUILD_EVIDENCE_INVALID,
                    "Firmware ELF must target the ARM architecture",
                    {"rule": "elfMachine"},
                )
            entry_point = int(elf.header["e_entry"])
            isr_vector_present = elf.get_section_by_name(".isr_vector") is not None
            reset_handler_address, reset_handler_present = _find_symbol(elf, "Reset_Handler")
            undefined_symbols = _undefined_symbols(elf)
    except BuildError:
        raise
    except Exception:
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "ELF artifact is not valid",
            {"rule": "elfFormat"},
        ) from None
    return ElfEvidence(
        entry_point=entry_point,
        isr_vector_present=isr_vector_present,
        reset_handler_present=reset_handler_present,
        reset_handler_address=reset_handler_address,
        entry_point_consistent=reset_handler_present and entry_point == reset_handler_address,
        undefined_symbols=undefined_symbols,
    )


def _find_symbol(elf: ELFFile, name: str) -> tuple[int | None, bool]:
    symtab = elf.get_section_by_name(".symtab")
    if symtab is None:
        return None, False
    for symbol in symtab.iter_symbols():
        if symbol.name == name:
            return int(symbol["st_value"]), True
    return None, False


def _undefined_symbols(elf: ELFFile) -> tuple[str, ...]:
    symtab = elf.get_section_by_name(".symtab")
    if symtab is None:
        return ()
    undefined: list[str] = []
    for symbol in symtab.iter_symbols():
        if not symbol.name:
            continue
        if symbol["st_shndx"] == "SHN_UNDEF" and symbol["st_info"]["bind"] != "STB_WEAK":
            undefined.append(symbol.name)
    return tuple(undefined)


def build_identity(
    *,
    preset: str,
    clean_first: bool,
    git: GitEvidence,
    snapshot: InputSnapshot,
    elf_path: str,
    elf_sha256: str,
    elf_size: int,
    map_path: str,
    map_sha256: str,
    map_size: int,
    elf_evidence: ElfEvidence,
    memory_usage: tuple[MemoryUsage, ...],
    built_at_utc: str,
) -> FirmwareIdentity:
    """Construct the schema-1 firmware identity with a deterministic build id."""
    identity = FirmwareIdentity(
        schema_version=1,
        build_id="",
        built_at_utc=built_at_utc,
        status="success",
        preset=preset,
        clean_first=clean_first,
        git_head=git.head,
        git_branch=git.branch,
        git_target=git.target,
        input_snapshot=snapshot,
        elf_path=elf_path,
        elf_sha256=elf_sha256,
        elf_size=elf_size,
        map_path=map_path,
        map_sha256=map_sha256,
        map_size=map_size,
        entry_point=hex(elf_evidence.entry_point),
        isr_vector_present=elf_evidence.isr_vector_present,
        reset_handler_present=elf_evidence.reset_handler_present,
        entry_point_consistent=elf_evidence.entry_point_consistent,
        undefined_symbols=elf_evidence.undefined_symbols,
        memory_usage=memory_usage,
    )
    build_id = _compute_build_id(identity.to_dict())
    return replace(identity, build_id=build_id)


def _compute_build_id(payload: dict[str, object]) -> str:
    """SHA-256 over every field except schema, build id, and timestamp."""
    excluded = {"schemaVersion", "buildId", "builtAtUtc"}
    core = {key: value for key, value in payload.items() if key not in excluded}
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_identity_document(payload: dict[str, object]) -> None:
    """Validate one identity document against the packaged schema (fail closed)."""
    validator = _identity_validator()
    errors = sorted(validator.iter_errors(payload), key=_error_sort_key)
    if errors:
        error = errors[0]
        raise BuildError(
            BUILD_IDENTITY_INVALID,
            "Firmware identity does not satisfy schema version 1",
            {"rule": error.validator},
        )


def _error_sort_key(error: object) -> tuple[str, str, str]:
    path = list(error.absolute_path)  # type: ignore[attr-defined]
    field = ".".join(str(component) for component in path) or "$"
    return (field, str(error.validator), str(error.validator_value))  # type: ignore[attr-defined]


def _identity_validator() -> Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        try:
            schema_text = (
                resources.files("stm32_toolkit")
                .joinpath("schemas", _IDENTITY_SCHEMA_NAME)
                .read_text(encoding="utf-8")
            )
            schema = json.loads(schema_text)
            Draft202012Validator.check_schema(schema)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BuildError(
                BUILD_IDENTITY_INVALID,
                "Firmware identity schema is not available",
                {"rule": "unavailable"},
            ) from error
        _VALIDATOR = Draft202012Validator(schema)
    return _VALIDATOR


def read_text_bounded(path: Path, max_bytes: int, rule: str = "size") -> str:
    """Read a text file with a hard byte bound; UTF-8 with replacement."""
    raw = _read_bounded(path, max_bytes, rule, rule)
    return raw.decode("utf-8", errors="replace")


def read_json_bounded(path: Path, max_bytes: int) -> dict:
    """Read one bounded evidence JSON object; malformed evidence fails closed."""
    raw = _read_bounded(path, max_bytes, "size", "missing")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "Evidence JSON is malformed",
            {"rule": "format"},
        ) from None
    if not isinstance(payload, dict):
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "Evidence JSON must be an object",
            {"rule": "format"},
        )
    return payload


def _read_bounded(path: Path, max_bytes: int, size_rule: str, failure_rule: str) -> bytes:
    """Read a file with a hard byte bound; oversize or unreadable fails closed."""
    try:
        with path.open("rb") as stream:
            data = bytearray()
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise BuildError(
                        BUILD_EVIDENCE_INVALID,
                        "Evidence exceeds the size limit",
                        {"rule": size_rule},
                    )
            return bytes(data)
    except BuildError:
        raise
    except OSError:
        raise BuildError(
            BUILD_EVIDENCE_INVALID,
            "Evidence is not readable",
            {"rule": failure_rule},
        ) from None


def write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write one JSON object (UTF-8, indent 2, one final LF)."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    write_text_atomic(path, text)


def write_text_atomic(path: Path, text: str) -> None:
    """Atomically write one UTF-8 text file via fsync + replace."""
    _atomic_write(path, text.encode("utf-8"))


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    if _WINDOWS:
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
