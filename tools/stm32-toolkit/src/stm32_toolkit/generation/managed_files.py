"""Frozen generation values, hashes, portable paths, and manifest validation.

This module performs no subprocess, network, or template I/O.  It owns the
frozen public containers, canonical JSON hashing (model hash, plan ID),
portable-path validation, managed-manifest parsing/building, and the stable
``GenerationError`` contract shared with the orchestration module
:mod:`stm32_toolkit.generation.configure`.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.project_model import ProjectModel

#: Frozen generation contract values (work order sections 3 and 8.1).
PLAN_VERSION = 1
TEMPLATE_VERSION = 1
MANAGED_MANIFEST_PATH = ".stm32-toolkit/generated-files.json"
STAGING_ROOT = ".stm32-toolkit/configuration-staging"

#: Bounded I/O limits (work order section 12).
FILE_LIMIT_BYTES = 8 * 1024 * 1024
AGGREGATE_LIMIT_BYTES = 64 * 1024 * 1024
TEMPLATE_LIMIT_BYTES = 1024 * 1024
GENERATED_LIMIT_BYTES = 8 * 1024 * 1024
TOTAL_LIMIT_BYTES = 64 * 1024 * 1024
PLAN_LIMIT_BYTES = 64 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")

#: The nine generated targets.  The managed manifest itself is never a target.
GENERATED_TARGETS = (
    "CMakeLists.txt",
    "cmake/arm-none-eabi-gcc.cmake",
    "CMakePresets.json",
    "linker/stm32tk.ld",
    ".vscode/tasks.json",
    ".vscode/launch.json",
    ".vscode/c_cpp_properties.json",
    ".vscode/settings.json",
    ".vscode/extensions.json",
)

#: Supported cores with their exact GCC CPU flags (work order 7.2).
CORE_CPU_FLAGS = {
    "cortex-m0": "-mcpu=cortex-m0",
    "cortex-m0plus": "-mcpu=cortex-m0plus",
    "cortex-m3": "-mcpu=cortex-m3",
    "cortex-m4": "-mcpu=cortex-m4",
    "cortex-m7": "-mcpu=cortex-m7",
    "cortex-m23": "-mcpu=cortex-m23",
    "cortex-m33": "-mcpu=cortex-m33",
}

#: Exact three VS Code extension recommendations (work order 11).
VSCODE_EXTENSIONS = ("ms-vscode.cpptools", "ms-vscode.cmake-tools", "marus25.cortex-debug")

_FILE_STATUSES = frozenset(
    {"create", "unchanged", "update-managed", "user-drift", "unowned-collision"}
)

_BLOCKER_CODES = frozenset(
    {"GENERATED_FILE_DRIFT", "UNOWNED_COLLISION", "GENERATION_ORPHANED_MANAGED_FILE"}
)

#: Per-target template resource names (review copies under ``templates/``).
TARGET_TEMPLATES = {
    "CMakeLists.txt": "cmake/CMakeLists.txt.j2",
    "cmake/arm-none-eabi-gcc.cmake": "cmake/arm-none-eabi-gcc.cmake",
    "CMakePresets.json": "cmake/CMakePresets.json.j2",
    "linker/stm32tk.ld": "cmake/linker.ld.j2",
    ".vscode/tasks.json": "vscode/tasks.json.j2",
    ".vscode/launch.json": "vscode/launch.json.j2",
    ".vscode/c_cpp_properties.json": "vscode/c_cpp_properties.json.j2",
    ".vscode/settings.json": "vscode/settings.json.j2",
    ".vscode/extensions.json": "vscode/extensions.json",
}

_CONVERSION_REPORT_PATH = "artifacts/migration/conversion-report.json"
_STM32_PROJECT_MANIFEST = ".stm32-project.json"


class GenerationError(Exception):
    """A stable generation failure carrying a code and bounded details.

    ``details`` never contains host exception text, absolute paths, rendered
    content, source bytes, Git/config/environment output, or credentials.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details if details is not None else {})


def generation_error(code: str, message: str, details: dict[str, object]) -> GenerationError:
    return GenerationError(code, message, details)


# ---------------------------------------------------------------------------
# public frozen containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationInput:
    path: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class ManagedFileRecord:
    path: str
    ownership: str  # exactly "managed"
    template_version: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "ownership": self.ownership,
            "template_version": self.template_version,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    status: str  # create|unchanged|update-managed|user-drift|unowned-collision
    template_name: str
    template_version: int
    before_sha256: str | None
    after_sha256: str
    before_size: int | None
    after_size: int
    unified_diff: str
    before_bytes: bytes | None  # omitted from to_dict()
    after_bytes: bytes  # omitted from to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "template_name": self.template_name,
            "template_version": self.template_version,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "before_size": self.before_size,
            "after_size": self.after_size,
            "unified_diff": self.unified_diff,
        }


@dataclass(frozen=True)
class GenerationBlocker:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class GenerationPlan:
    project_root: Path  # omitted from to_dict()
    model: ProjectModel  # omitted from to_dict()
    plan_version: int  # exactly 1
    plan_id: str  # lowercase SHA-256 hex
    model_sha256: str
    inputs: tuple[GenerationInput, ...]
    files: tuple[GeneratedFile, ...]
    blockers: tuple[GenerationBlocker, ...]
    managed_manifest_path: str
    managed_manifest_bytes: bytes  # omitted from to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_version": self.plan_version,
            "plan_id": self.plan_id,
            "model_sha256": self.model_sha256,
            "inputs": [entry.to_dict() for entry in self.inputs],
            "files": [entry.to_dict() for entry in self.files],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "managed_manifest_path": self.managed_manifest_path,
        }


# ---------------------------------------------------------------------------
# canonical hashing
# ---------------------------------------------------------------------------


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def model_sha256_for(model: ProjectModel) -> str:
    """SHA-256 over canonical JSON of every serializable model field.

    ``project_root`` is excluded; the UUID is stringified; tuples become
    arrays; scalar values keep their native JSON types.
    """
    return sha256_hex(canonical_json_bytes(_model_payload(model)))


def _model_payload(model: ProjectModel) -> dict[str, object]:
    return {
        "schema_version": model.schema_version,
        "logical_project_id": str(model.logical_project_id),
        "project": {
            "name": model.project.name,
            "origin": model.project.origin,
        },
        "target": {
            "device": model.target.device,
            "core": model.target.core,
            "fpu": model.target.fpu,
            "float_abi": model.target.float_abi,
            "device_pack": model.target.device_pack,
        },
        "framework": {
            "type": model.framework.type,
            "version": model.framework.version,
        },
        "build": {
            "sources": list(model.build.sources),
            "include_paths": list(model.build.include_paths),
            "defines": list(model.build.defines),
            "compile_options": list(model.build.compile_options),
            "assembly_sources": list(model.build.assembly_sources),
            "presets": list(model.build.presets),
            "elf": model.build.elf,
        },
        "memory": {
            "source": model.memory.source,
            "regions": [
                {
                    "name": region.name,
                    "origin": region.origin,
                    "length": region.length,
                    "attributes": region.attributes,
                }
                for region in model.memory.regions
            ],
        },
        "debug": {
            "backend": model.debug.backend,
            "target": model.debug.target,
            "svd": model.debug.svd,
        },
        "generation": {
            "tool": model.generation.tool,
            "version": model.generation.version,
            "cube_mx_ioc": model.generation.cube_mx_ioc,
            "managed_manifest": model.generation.managed_manifest,
            "generated_directories": list(model.generation.generated_directories),
            "user_directories": list(model.generation.user_directories),
        },
    }


def plan_id_for(plan: GenerationPlan) -> str:
    """Deterministic lowercase SHA-256 plan ID (work order 6.2).

    The payload includes the plan version, model hash, Toolkit version,
    template version, every input, every file metadata/status/digest,
    blockers, the managed manifest path, and the SHA-256 of the proposed
    manifest bytes.  It excludes the plan ID itself, absolute paths, raw
    bytes, and unified diffs.
    """
    payload = {
        "plan_version": plan.plan_version,
        "model_sha256": plan.model_sha256,
        "toolkit_version": __version__,
        "template_version": TEMPLATE_VERSION,
        "inputs": [entry.to_dict() for entry in plan.inputs],
        "files": [
            {
                "path": entry.path,
                "status": entry.status,
                "template_name": entry.template_name,
                "template_version": entry.template_version,
                "before_sha256": entry.before_sha256,
                "after_sha256": entry.after_sha256,
                "before_size": entry.before_size,
                "after_size": entry.after_size,
            }
            for entry in plan.files
        ],
        "blockers": [blocker.to_dict() for blocker in plan.blockers],
        "managed_manifest_path": plan.managed_manifest_path,
        "managed_manifest_sha256": sha256_hex(plan.managed_manifest_bytes),
    }
    return sha256_hex(canonical_json_bytes(payload))


def unified_diff(path: str, before_text: str, after_text: str) -> str:
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="\n",
            n=3,
        )
    )


# ---------------------------------------------------------------------------
# portable-path validation
# ---------------------------------------------------------------------------

_PATH_REASONS = ("empty", "nul", "absolute", "drivePrefix", "unc", "component")


def portable_path_error(path: object) -> str | None:
    """Return a stable reason when ``path`` is not a portable project-relative path.

    Public paths use ``/``, are relative to the canonical project root, and
    contain no empty/``.``/``..`` component, drive prefix, UNC prefix, NUL,
    or absolute form.  ``None`` means the path is portable.
    """
    if not isinstance(path, str) or not path:
        return "empty"
    if "\x00" in path:
        return "nul"
    if path.startswith("\\\\") or path.startswith("//"):
        return "unc"
    if path.startswith("/") or path.startswith("\\"):
        return "absolute"
    if _DRIVE_PREFIX_RE.match(path):
        return "drivePrefix"
    if path.startswith("\\\\") or path.startswith("//"):
        return "unc"
    for component in re.split(r"[/\\]", path):
        if not component:
            return "component"
        if component in (".", ".."):
            return "component"
    return None


def sha256_error(value: object) -> str | None:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        return "sha256"
    return None


def portable_sort_key(path: str) -> bytes:
    """Bytewise portable path ordering (UTF-8 byte order)."""
    return path.encode("utf-8")


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
# managed manifest
# ---------------------------------------------------------------------------


def build_managed_manifest_bytes(files: tuple[GeneratedFile, ...], model_sha256: str) -> bytes:
    """Deterministic proposed manifest bytes (work order 8.1).

    ``files`` must already be sorted by portable path; every entry is
    recorded with ``ownership: managed`` and the current template version.
    The manifest itself is never listed.
    """
    payload = {
        "schemaVersion": 1,
        "tool": "stm32-toolkit",
        "toolVersion": __version__,
        "templateVersion": TEMPLATE_VERSION,
        "projectManifestSha256": model_sha256,
        "files": [
            {
                "path": entry.path,
                "ownership": "managed",
                "templateVersion": TEMPLATE_VERSION,
                "sha256": entry.after_sha256,
            }
            for entry in files
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def _manifest_error(rule: str) -> GenerationError:
    return generation_error(
        "GENERATION_MANIFEST_INVALID",
        "managed manifest is invalid",
        {"path": MANAGED_MANIFEST_PATH, "rule": rule},
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def parse_managed_manifest(data: bytes) -> list[ManagedFileRecord]:
    """Parse and strictly validate a prior managed manifest.

    Raises ``GENERATION_MANIFEST_INVALID`` with a portable rule for every
    malformed, unsafe, or non-canonical shape.  The manifest is evidence
    only; planning never repairs it silently.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _manifest_error("encoding") from None
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except ValueError:
        raise _manifest_error("json") from None
    if not isinstance(payload, dict):
        raise _manifest_error("type")
    allowed = {"schemaVersion", "tool", "toolVersion", "templateVersion", "projectManifestSha256", "files"}
    if not set(payload).issubset(allowed):
        raise _manifest_error("key")
    if payload.get("schemaVersion") != 1:
        raise _manifest_error("version")
    if payload.get("tool") != "stm32-toolkit":
        raise _manifest_error("tool")
    if payload.get("toolVersion") != __version__:
        raise _manifest_error("version")
    if payload.get("templateVersion") != TEMPLATE_VERSION:
        raise _manifest_error("version")
    if sha256_error(payload.get("projectManifestSha256")) is not None:
        raise _manifest_error("hash")
    files_value = payload.get("files")
    if not isinstance(files_value, list):
        raise _manifest_error("type")
    records: list[ManagedFileRecord] = []
    for item in files_value:
        if not isinstance(item, dict):
            raise _manifest_error("type")
        if set(item) != {"path", "ownership", "templateVersion", "sha256"}:
            raise _manifest_error("key")
        path = item.get("path")
        if not isinstance(path, str) or portable_path_error(path) is not None:
            raise _manifest_error("path")
        if item.get("ownership") != "managed":
            raise _manifest_error("ownership")
        if item.get("templateVersion") != TEMPLATE_VERSION:
            raise _manifest_error("version")
        if sha256_error(item.get("sha256")) is not None:
            raise _manifest_error("hash")
        if path == MANAGED_MANIFEST_PATH:
            raise _manifest_error("path")
        records.append(
            ManagedFileRecord(
                path=path,
                ownership="managed",
                template_version=TEMPLATE_VERSION,
                sha256=str(item["sha256"]),
            )
        )
    paths = [record.path for record in records]
    if len(set(paths)) != len(paths):
        raise _manifest_error("duplicate")
    if casefold_collision(paths) is not None:
        raise _manifest_error("casefold")
    if paths != sorted(paths, key=portable_sort_key):
        raise _manifest_error("order")
    return records
