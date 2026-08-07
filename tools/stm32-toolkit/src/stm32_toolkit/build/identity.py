"""Input snapshots, Git evidence, ELF validation, identity, and atomic evidence.

``snapshot_project_inputs`` hashes exact bytes for the manifest, declared
sources, assembly sources, all owned generated files, and recursively
bounded include directories (lexically sorted portable paths, regular files
only, escaping redirects/loops/special files/unreadable entries and
duplicate/casefold collisions rejected).  Git evidence comes only from the
fixed bounded ``git rev-parse --verify HEAD`` and
``git status --porcelain=v1 -z --untracked-files=all`` argv; build outputs
and ``artifacts/migration`` never contribute to the dirty interpretation.
ELF validation is fail-closed with pyelftools over an already bounded byte
buffer.  Identity documents are validated against the packaged schema and
published atomically (temp + flush + fsync + replace + directory fsync).
"""

from __future__ import annotations

import importlib.resources
import io
import json
import os
import re
import stat
import struct
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from jsonschema import Draft202012Validator

from stm32_toolkit import __version__
from stm32_toolkit.build.map_file import (
    ElfSectionEvidence,
    MapError,
    map_error,
    parse_map,
)
from stm32_toolkit.build.model import (
    BUILD_ARTIFACT_INVALID,
    BUILD_EVIDENCE_FAILED,
    BUILD_GIT_INVALID,
    BUILD_INPUT_INVALID,
    BUILD_MAP_INVALID,
    BUILD_PROJECT_INVALID,
    BUILD_REQUEST_INVALID,
    IDENTITY_SCHEMA_VERSION,
    SUPPORTED_PRESETS,
    BuildError,
    build_error,
)
from stm32_toolkit.generation.managed_files import (
    _reject_duplicate_json_keys,
    canonical_json_bytes,
    parse_managed_manifest,
    portable_path_error,
    portable_sort_key,
    sha256_hex,
)
from stm32_toolkit.process import ProcessError, ProcessRequest, run_process
from stm32_toolkit.project_model import MemoryRegion, ProjectModel

_FILE_LIMIT_BYTES = 8 * 1024 * 1024
_AGGREGATE_LIMIT_BYTES = 256 * 1024 * 1024
_FILE_LIMIT_COUNT = 10000
_ELF_LIMIT_BYTES = 64 * 1024 * 1024
_MAP_LIMIT_BYTES = 32 * 1024 * 1024
_EVIDENCE_LIMIT_BYTES = 8 * 1024 * 1024
_MAX_WALK_DEPTH = 64

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_FIXED_SECTION_RE = re.compile(r"^\.stm32tk\.abs\.([0-9A-Fa-f]{8})$")
_ARM_MACHINE = "EM_ARM"
_SHF_ALLOC = 0x2
_SHN_UNDEF = "SHN_UNDEF"
_STB_WEAK = "STB_WEAK"

def _default_sync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return  # directory fsync is unavailable on some platforms (e.g. Windows)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


#: Module seams (tests inject failures; Windows never touches missing APIs).
_lstat = os.lstat
_listdir = os.listdir
_fsync_file = os.fsync
_replace = os.replace
_sync_directory = _default_sync_directory


def _read_limited(path: Path, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes through the injectable open seam."""
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def read_bounded(path: Path, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes; callers enforce the bound."""
    return _read_limited(path, limit)


def utc_now_rfc3339() -> str:
    """RFC 3339 UTC with exactly six fractional digits and ``Z``."""
    now = datetime.now(timezone.utc)
    return f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond:06d}Z"


# ---------------------------------------------------------------------------
# model artifact mapping
# ---------------------------------------------------------------------------


def model_artifact_paths(model: ProjectModel, preset: str) -> tuple[str, str]:
    """Central validated mapping from the model ELF to preset-specific paths.

    Debug uses ``build/arm-debug/<basename>.elf``; release uses the same
    basename under ``build/arm-release``.  The MAP shares the directory and
    basename with a ``.map`` extension.
    """
    if preset not in SUPPORTED_PRESETS:
        raise build_error(
            BUILD_REQUEST_INVALID, "build request is invalid", {"field": "preset", "rule": "value"}
        )
    elf_rel = model.build.elf
    if elf_rel is None or not elf_rel.startswith("build/arm-debug/"):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "build.elf", "rule": "value"},
        )
    base = elf_rel[len("build/arm-debug/") :]
    if (
        not base
        or "/" in base
        or "\\" in base
        or not base.endswith(".elf")
        or len(base) <= len(".elf")
    ):
        raise build_error(
            BUILD_PROJECT_INVALID,
            "project model is invalid",
            {"field": "build.elf", "rule": "value"},
        )
    stem = base[: -len(".elf")]
    elf = elf_rel if preset == "arm-debug" else "build/arm-release/" + base
    return elf, f"build/{preset}/{stem}.map"


def _relative_to_root(path: Path, root: Path) -> str:
    return "/".join(path.resolve(strict=False).relative_to(root).parts)


# ---------------------------------------------------------------------------
# input snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEntry:
    path: str
    size: int
    sha256: str
    mtime_ns: int


@dataclass(frozen=True)
class InputSnapshot:
    entries: tuple[SnapshotEntry, ...]
    sha256: str
    newest_mtime_ns: int


def _input_invalid(path: str, rule: str) -> BuildError:
    return build_error(
        BUILD_INPUT_INVALID, "build input is invalid", {"path": path, "rule": rule}
    )


def _input_invalid_rule(rule: str) -> BuildError:
    return build_error(BUILD_INPUT_INVALID, "build input is invalid", {"rule": rule})


def snapshot_project_inputs(model: ProjectModel) -> InputSnapshot:
    """Hash exact bytes for every declared input and owned generated file.

    A regular file reached by both an explicit source declaration and
    include-directory traversal is counted exactly once (STM32TK-0306
    revision 1): the traversal skips any path that is already declared or
    that resolves to an already-declared canonical file.  Duplicate
    declarations of the same canonical file, Unicode casefold conflicts,
    and redirect/reparse escapes fail closed; include-only overlaps (for
    example two case-variant names for one file) remain distinct so the
    casefold collision check still fails closed.
    """
    root = model.project_root
    paths: list[str] = []
    declared_identities: dict[tuple[int, int], str] = {}
    declared = [".stm32-project.json", *model.build.sources, *model.build.assembly_sources]
    for rel in declared:
        _require_input_path(root, rel, paths, declared_identities)
    manifest_rel = model.generation.managed_manifest
    manifest_abs = root.joinpath(*manifest_rel.split("/"))
    try:
        manifest_data = _read_limited(manifest_abs, _FILE_LIMIT_BYTES)
    except FileNotFoundError:
        raise _input_invalid(manifest_rel, "missing") from None
    except OSError:
        raise _input_invalid(manifest_rel, "unreadable") from None
    if len(manifest_data) > _FILE_LIMIT_BYTES:
        raise _input_invalid(manifest_rel, "size")
    try:
        records = parse_managed_manifest(manifest_data)
    except Exception as error:
        details = getattr(error, "details", None)
        raise build_error(
            BUILD_PROJECT_INVALID,
            "managed configuration is invalid",
            dict(details) if isinstance(details, dict) else {"path": manifest_rel, "rule": "manifest"},
        ) from None
    for record in records:
        _require_input_path(root, record.path, paths, declared_identities)
    walked: set[str] = set()
    for include in model.build.include_paths:
        _walk_include(root, include, paths, declared_identities, walked)
    if len(paths) > _FILE_LIMIT_COUNT:
        raise _input_invalid_rule("fileCount")
    collision = casefold_collision(paths)
    if collision is not None:
        raise _input_invalid(collision, "collision")
    entries: list[SnapshotEntry] = []
    aggregate = 0
    for rel in paths:
        absolute = root.joinpath(*rel.split("/"))
        try:
            lst = _lstat(absolute)
        except FileNotFoundError:
            raise _input_invalid(rel, "missing") from None
        except OSError:
            raise _input_invalid(rel, "inspection") from None
        read_path = absolute
        if stat.S_ISLNK(lst.st_mode):
            try:
                resolved = absolute.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                raise _input_invalid(rel, "escape") from None
            read_path = resolved
            try:
                lst = _lstat(resolved)
            except OSError:
                raise _input_invalid(rel, "inspection") from None
        if not stat.S_ISREG(lst.st_mode):
            raise _input_invalid(rel, "regularFile")
        try:
            data = _read_limited(read_path, _FILE_LIMIT_BYTES)
        except OSError:
            raise _input_invalid(rel, "unreadable") from None
        if len(data) > _FILE_LIMIT_BYTES:
            raise _input_invalid(rel, "size")
        aggregate += len(data)
        if aggregate > _AGGREGATE_LIMIT_BYTES:
            raise _input_invalid_rule("aggregate")
        entries.append(
            SnapshotEntry(
                path=rel,
                size=len(data),
                sha256=sha256_hex(data),
                mtime_ns=lst.st_mtime_ns,
            )
        )
    entries.sort(key=lambda entry: portable_sort_key(entry.path))
    payload = [
        {"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in entries
    ]
    digest = sha256_hex(canonical_json_bytes(payload))
    newest = max((entry.mtime_ns for entry in entries), default=0)
    return InputSnapshot(entries=tuple(entries), sha256=digest, newest_mtime_ns=newest)


def _require_input_path(
    root: Path,
    rel: str,
    paths: list[str],
    declared_identities: dict[tuple[int, int], str],
) -> None:
    if portable_path_error(rel) is not None:
        raise _input_invalid(rel, "portable")
    if rel.startswith("build/") or rel.startswith("artifacts/migration"):
        raise _input_invalid(rel, "reserved")
    if rel in paths:
        raise _input_invalid_rule("duplicate")
    absolute = root.joinpath(*rel.split("/"))
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel, "escape") from None
    try:
        lst = _lstat(absolute)
    except FileNotFoundError:
        raise _input_invalid(rel, "missing") from None
    except OSError:
        raise _input_invalid(rel, "inspection") from None
    if not stat.S_ISREG(lst.st_mode):
        raise _input_invalid(rel, "regularFile")
    identity = _canonical_identity(absolute, lst, root, rel)
    if identity is not None and identity in declared_identities:
        raise _input_invalid_rule("duplicate")
    if identity is not None:
        declared_identities[identity] = rel
    paths.append(rel)


def _canonical_identity(
    absolute: Path, lst: os.stat_result, root: Path, rel: str
) -> tuple[int, int] | None:
    """Return the canonical ``(st_dev, st_ino)`` the path resolves to.

    Symlink declarations resolve to their target; redirect/reparse escapes
    and non-regular targets fail closed with the established rules.
    """
    if not stat.S_ISLNK(lst.st_mode):
        return (lst.st_dev, lst.st_ino)
    try:
        resolved = absolute.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel, "escape") from None
    try:
        target_lst = _lstat(resolved)
    except OSError:
        raise _input_invalid(rel, "inspection") from None
    if not stat.S_ISREG(target_lst.st_mode):
        raise _input_invalid(rel, "regularFile")
    return (target_lst.st_dev, target_lst.st_ino)


def _walk_include(
    root: Path,
    rel_dir: str,
    paths: list[str],
    declared_identities: dict[tuple[int, int], str],
    walked: set[str],
    depth: int = 0,
) -> None:
    if depth > _MAX_WALK_DEPTH:
        raise _input_invalid(rel_dir, "escape")
    if portable_path_error(rel_dir) is not None:
        raise _input_invalid(rel_dir, "portable")
    if rel_dir.startswith("build/") or rel_dir.startswith("artifacts/migration"):
        raise _input_invalid(rel_dir, "reserved")
    if rel_dir in walked:
        raise _input_invalid_rule("duplicate")
    walked.add(rel_dir)
    absolute = root.joinpath(*rel_dir.split("/"))
    try:
        lst = _lstat(absolute)
    except OSError:
        raise _input_invalid(rel_dir, "inspection") from None
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise _input_invalid(rel_dir, "escape") from None
    if stat.S_ISLNK(lst.st_mode):
        # follow a redirecting include directory; the target must be a directory
        try:
            lst = _lstat(resolved)
        except OSError:
            raise _input_invalid(rel_dir, "inspection") from None
    if not stat.S_ISDIR(lst.st_mode):
        raise _input_invalid(rel_dir, "directory")
    try:
        names = sorted(_listdir(absolute))
    except OSError:
        raise _input_invalid(rel_dir, "inspection") from None
    for name in names:
        rel = f"{rel_dir}/{name}"
        child = absolute / name
        try:
            child_lst = _lstat(child)
        except OSError:
            raise _input_invalid(rel, "inspection") from None
        if stat.S_ISLNK(child_lst.st_mode):
            try:
                resolved_child = child.resolve(strict=False)
                resolved_child.relative_to(root)
            except (OSError, RuntimeError, ValueError):
                raise _input_invalid(rel, "escape") from None
            try:
                target_lst = _lstat(resolved_child)
            except OSError:
                raise _input_invalid(rel, "inspection") from None
            if stat.S_ISDIR(target_lst.st_mode):
                _walk_include(root, rel, paths, declared_identities, walked, depth + 1)
            elif stat.S_ISREG(target_lst.st_mode):
                identity = (target_lst.st_dev, target_lst.st_ino)
                if rel in paths or identity in declared_identities:
                    continue
                paths.append(rel)
            else:
                raise _input_invalid(rel, "regularFile")
        elif stat.S_ISDIR(child_lst.st_mode):
            _walk_include(root, rel, paths, declared_identities, walked, depth + 1)
        elif stat.S_ISREG(child_lst.st_mode):
            identity = (child_lst.st_dev, child_lst.st_ino)
            if rel in paths or identity in declared_identities:
                continue
            paths.append(rel)
        else:
            raise _input_invalid(rel, "regularFile")


def casefold_collision(paths: list[str]) -> str | None:
    """Return the first duplicate or Unicode-casefold-colliding path, if any."""
    seen: dict[str, str] = {}
    for path in paths:
        folded = path.casefold()
        prior = seen.get(folded)
        if prior is not None and prior != path:
            return path
        seen[folded] = path
    return None


# ---------------------------------------------------------------------------
# git evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitEvidence:
    head: str
    dirty: bool


def _git_invalid(rule: str) -> BuildError:
    return build_error(BUILD_GIT_INVALID, "git evidence is unavailable", {"rule": rule})


def _porcelain_dirty(stdout: str) -> bool:
    """Dirty iff a porcelain entry outside ``build/``/``artifacts/migration`` exists."""
    for chunk in stdout.split("\x00"):
        if not chunk:
            continue
        path = chunk[3:] if len(chunk) >= 4 and chunk[2] == " " else chunk
        if path.startswith("build/") or path.startswith("artifacts/migration"):
            continue
        return True
    return False


def git_evidence(project_root: Path, timeout_seconds: int = 30) -> GitEvidence:
    """Collect bounded fixed-argv Git evidence; failure is always stable."""
    try:
        head_result = run_process(
            ProcessRequest(
                argv=("git", "rev-parse", "--verify", "HEAD"),
                cwd=project_root,
                timeout_seconds=timeout_seconds,
            )
        )
    except ProcessError:
        raise _git_invalid("head") from None
    if head_result.timed_out or head_result.returncode != 0:
        raise _git_invalid("head")
    head = head_result.stdout.strip()
    if _FULL_SHA_RE.fullmatch(head) is None:
        raise _git_invalid("head")
    try:
        status_result = run_process(
            ProcessRequest(
                argv=("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
                cwd=project_root,
                timeout_seconds=timeout_seconds,
            )
        )
    except ProcessError:
        raise _git_invalid("status") from None
    if status_result.timed_out or status_result.returncode != 0:
        raise _git_invalid("status")
    return GitEvidence(head=head, dirty=_porcelain_dirty(status_result.stdout))


# ---------------------------------------------------------------------------
# MAP reading
# ---------------------------------------------------------------------------


def read_map_text(path: Path, rel: str) -> str:
    """Read the MAP bounded to 32 MiB and decode strict UTF-8/ASCII text."""
    try:
        data = _read_limited(path, _MAP_LIMIT_BYTES)
    except FileNotFoundError:
        raise map_error("missing", rel) from None
    except OSError:
        raise map_error("unreadable", rel) from None
    if len(data) > _MAP_LIMIT_BYTES:
        raise map_error("size", rel)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise map_error("encoding", rel) from None


# ---------------------------------------------------------------------------
# ELF validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ElfEvidence:
    entry_point: int
    vector_address: int
    reset_handler_address: int
    sha256: str
    size: int
    sections: tuple[ElfSectionEvidence, ...]


def _artifact_invalid(rel: str, rule: str) -> BuildError:
    return build_error(
        BUILD_ARTIFACT_INVALID, "build artifact is invalid", {"path": rel, "rule": rule}
    )


def _in_region(addr: int, size: int, region: MemoryRegion) -> bool:
    return region.origin <= addr and addr + size <= region.origin + region.length


def _in_any_region(addr: int, size: int, model: ProjectModel) -> bool:
    return any(_in_region(addr, size, region) for region in model.memory.regions)


def _in_executable_region(addr: int, size: int, model: ProjectModel) -> bool:
    return any(
        "x" in region.attributes and _in_region(addr, size, region)
        for region in model.memory.regions
    )


def validate_elf(path: Path, model: ProjectModel) -> ElfEvidence:
    """Fail-closed ELF32 LE ARM validation over an already bounded buffer."""
    root = model.project_root
    rel = _relative_to_root(path, root)
    try:
        lst = _lstat(path)
    except FileNotFoundError:
        raise _artifact_invalid(rel, "missing") from None
    except OSError:
        raise _artifact_invalid(rel, "unreadable") from None
    if not stat.S_ISREG(lst.st_mode):
        raise _artifact_invalid(rel, "regularFile")
    try:
        data = _read_limited(path, _ELF_LIMIT_BYTES)
    except OSError:
        raise _artifact_invalid(rel, "unreadable") from None
    if len(data) > _ELF_LIMIT_BYTES:
        raise _artifact_invalid(rel, "size")
    if not data:
        raise _artifact_invalid(rel, "empty")
    try:
        elffile = ELFFile(io.BytesIO(data))
        return _inspect_elf(elffile, rel, model, data)
    except BuildError:
        raise
    except (ELFError, ValueError, KeyError, IndexError, struct.error) as error:
        raise _artifact_invalid(rel, "format") from error


def _inspect_elf(elffile: ELFFile, rel: str, model: ProjectModel, data: bytes) -> ElfEvidence:
    ident = elffile.header["e_ident"]
    if ident.get("EI_CLASS") != "ELFCLASS32":
        raise _artifact_invalid(rel, "class")
    if ident.get("EI_DATA") != "ELFDATA2LSB":
        raise _artifact_invalid(rel, "endian")
    if elffile.header.get("e_machine") != _ARM_MACHINE:
        raise _artifact_invalid(rel, "machine")

    vector = elffile.get_section_by_name(".isr_vector")
    if vector is None:
        raise _artifact_invalid(rel, "vector")
    vector_size = vector["sh_size"]
    if vector_size < 8:
        raise _artifact_invalid(rel, "vectorSize")
    if not vector["sh_flags"] & _SHF_ALLOC:
        raise _artifact_invalid(rel, "vectorAlloc")
    vector_addr = vector["sh_addr"]
    if not _in_executable_region(vector_addr, vector_size, model):
        raise _artifact_invalid(rel, "vectorRegion")
    vector_bytes = vector.data()[:8]
    vector_word = int.from_bytes(vector_bytes[4:8], "little")

    symtab = elffile.get_section_by_name(".symtab")
    if symtab is None:
        raise _artifact_invalid(rel, "symbols")
    reset_handler_addr: int | None = None
    for symbol in symtab.iter_symbols():
        if symbol.name == "Reset_Handler":
            if symbol["st_shndx"] == _SHN_UNDEF:
                raise _artifact_invalid(rel, "resetHandlerUndefined")
            reset_handler_addr = symbol["st_value"]
    if reset_handler_addr is None:
        raise _artifact_invalid(rel, "resetHandler")

    entry = elffile.header["e_entry"]
    if entry & 1 == 0:
        raise _artifact_invalid(rel, "entryThumb")
    if entry & ~1 != reset_handler_addr & ~1:
        raise _artifact_invalid(rel, "entry")
    if vector_word & ~1 != reset_handler_addr & ~1:
        raise _artifact_invalid(rel, "vectorReset")

    for symbol in symtab.iter_symbols():
        if symbol["st_shndx"] != _SHN_UNDEF:
            continue
        if not symbol.name:
            continue
        if symbol["st_info"]["bind"] != _STB_WEAK:
            raise _artifact_invalid(rel, "undefinedSymbols")

    section_evidence: list[ElfSectionEvidence] = []
    for section in elffile.iter_sections():
        size = section["sh_size"]
        if size == 0:
            continue
        alloc = bool(section["sh_flags"] & _SHF_ALLOC)
        addr = section["sh_addr"]
        if not alloc:
            section_evidence.append(
                ElfSectionEvidence(name=section.name, address=addr, size=size, alloc=False)
            )
            continue
        if not _in_any_region(addr, size, model):
            raise _artifact_invalid(rel, "sectionOutOfRange")
        fixed = _FIXED_SECTION_RE.fullmatch(section.name)
        if fixed is not None and addr != int(fixed.group(1), 16):
            raise _artifact_invalid(rel, "fixedSectionAddress")
        section_evidence.append(
            ElfSectionEvidence(name=section.name, address=addr, size=size, alloc=True)
        )

    return ElfEvidence(
        entry_point=entry,
        vector_address=vector_addr,
        reset_handler_address=reset_handler_addr,
        sha256=sha256_hex(data),
        size=len(data),
        sections=tuple(section_evidence),
    )


# ---------------------------------------------------------------------------
# identity construction and schema validation
# ---------------------------------------------------------------------------


def compute_build_id(document: dict) -> str:
    """Hash every identity field except ``schemaVersion``/``buildId``/``builtAtUtc``."""
    fields = {
        key: value
        for key, value in document.items()
        if key not in ("schemaVersion", "buildId", "builtAtUtc")
    }
    return sha256_hex(canonical_json_bytes(fields))


def build_identity_document(
    *,
    model: ProjectModel,
    preset: str,
    git: GitEvidence,
    snapshot: InputSnapshot,
    elf: ElfEvidence,
    elf_size: int,
    elf_sha256: str,
    map_size: int,
    map_sha256: str,
    built_at_utc: str,
) -> dict:
    """Construct the schema-1 firmware identity document in key order."""
    elf_rel, map_rel = model_artifact_paths(model, preset)
    document = {
        "schemaVersion": IDENTITY_SCHEMA_VERSION,
        "buildId": "",
        "logicalProjectId": str(model.logical_project_id),
        "toolkitVersion": __version__,
        "gitHead": git.head,
        "gitDirty": git.dirty,
        "inputSnapshotSha256": snapshot.sha256,
        "newestInputMtimeNs": snapshot.newest_mtime_ns,
        "targetDevice": model.target.device,
        "preset": preset,
        "elfPath": elf_rel,
        "elfSha256": elf_sha256,
        "elfSize": elf_size,
        "mapPath": map_rel,
        "mapSha256": map_sha256,
        "entryPoint": elf.entry_point,
        "vectorAddress": elf.vector_address,
        "resetHandlerAddress": elf.reset_handler_address,
        "builtAtUtc": built_at_utc,
    }
    document["buildId"] = compute_build_id(document)
    return document


def load_packaged_schema_bytes() -> bytes:
    resource = importlib.resources.files("stm32_toolkit").joinpath(
        "schemas", "firmware-identity.schema.json"
    )
    return resource.read_bytes()


def load_packaged_schema() -> dict:
    return json.loads(load_packaged_schema_bytes().decode("utf-8"))


_IDENTITY_VALIDATOR: Draft202012Validator | None = None


def _identity_validator() -> Draft202012Validator:
    global _IDENTITY_VALIDATOR
    if _IDENTITY_VALIDATOR is None:
        schema = load_packaged_schema()
        Draft202012Validator.check_schema(schema)
        _IDENTITY_VALIDATOR = Draft202012Validator(schema)
    return _IDENTITY_VALIDATOR


def validate_identity_document(document: dict) -> None:
    """Validate the identity against the packaged schema; fail closed."""
    try:
        validator = _identity_validator()
        errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    except Exception:
        raise build_error(
            BUILD_EVIDENCE_FAILED,
            "identity evidence is invalid",
            {"phase": "identity"},
        ) from None
    if errors:
        raise build_error(
            BUILD_EVIDENCE_FAILED,
            "identity evidence is invalid",
            {"phase": "identity"},
        )


# ---------------------------------------------------------------------------
# atomic evidence publication
# ---------------------------------------------------------------------------


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via unique sibling temp + flush + fsync + replace + dir fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".build-", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            _fsync_file(handle.fileno())
        _replace(tmp_path, str(path))
        tmp_path = None
        _sync_directory(path.parent)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def atomic_write_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


def read_evidence_json(path: Path, rel: str, limit: int) -> dict | None:
    """Read and strictly parse an evidence JSON file; ``None`` when invalid."""
    try:
        data = _read_limited(path, limit)
    except OSError:
        return None
    if len(data) > limit:
        return None
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def hash_artifact(path: Path, rel: str, limit: int, code: str) -> tuple[int, str]:
    """Hash exact artifact bytes after validation; reject oversized evidence."""
    data = read_bounded(path, limit)
    if len(data) > limit:
        raise build_error(code, "build artifact is invalid", {"path": rel, "rule": "size"})
    return len(data), sha256_hex(data)
