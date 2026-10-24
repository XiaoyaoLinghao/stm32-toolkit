"""Deterministic, read-only ARMCC conversion planning.

``plan_keil_conversion`` validates the canonical Git root, revalidates every
inspection input byte-for-byte, captures read-only Git evidence, re-runs the
Keil inspection to reject forged/stale findings, applies the token-aware
source rules, proposes a validated Schema v3 manifest, and assembles an
immutable ``MigrationPlan`` with deterministic hashes and ordering.  Planning
never writes, never creates staging, and never mutates Git state.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib.resources
import json
import os
import re
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.keil import KeilInspection, KeilInspectionError, KeilInputDigest, inspect_keil
from stm32_toolkit.memory_layout import (
    MemoryLayout,
    MemoryLayoutError,
    MemoryLayoutResolution,
    resolve_memory_layout,
)
from stm32_toolkit.project_model import ProjectManifestError, first_schema_error, validate_model_document

from stm32_toolkit.migration import git_guard
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.constant_context import SymbolSource
from stm32_toolkit.migration.model import (
    FilePatch,
    FixedSectionRequirement,
    GitBaseline,
    IgnoredObservation,
    IncludeMerge,
    MigrationBlocker,
    MigrationInput,
    MigrationPlan,
    MigrationPlanError,
    StartupAnalysis,
    StartupOptions,
    inspection_sha256_for,
    plan_id_for,
    portable_path_error,
)
from stm32_toolkit.migration.scoped_includes import (
    analyze_scoped_includes,
    classify_include_scopes,
)
from stm32_toolkit.migration.startup import (
    RUNTIME_INITIALIZATION,
    STARTUP_GENERATED_PATH,
    StartupOutcome,
    analyze_startup,
)

_FILE_LIMIT_BYTES = 8 * 1024 * 1024
_AGGREGATE_LIMIT_BYTES = 64 * 1024 * 1024
_PATCH_LIMIT_BYTES = 64 * 1024 * 1024
_PLAN_LIMIT_BYTES = 64 * 1024 * 1024
_MANIFEST_LIMIT_BYTES = 8 * 1024 * 1024

_MANIFEST_NAME = ".stm32-project.json"
_ARTIFACT_DIR = "artifacts/migration"
_UUID_NAMESPACE = uuid.UUID("a2e9f523-3c9e-5cb2-bf50-5cf9ff5d16a8")
_ALLOWED_FRAMEWORKS = ("spl", "hal", "ll", "cmsis", "bare-metal")
_SCANNED_LANGUAGES = ("c", "cxx")
_ELF_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_ELF_COLLAPSE_RE = re.compile(r"_+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
_ELF_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Inspection blocker findings exactly resolved by a supported migration rule:
# the rule re-derives the observation from the source or project settings, so
# the finding must not additionally become ARMCC_FINDING_UNSUPPORTED.
_RESOLVED_BLOCKER_FINDINGS = frozenset(
    {
        "ARMCC_SOURCE_ENCODING_UNSUPPORTED",
        "ARMCC_UNSUPPORTED_PRAGMA",
        "ARMCC_ABSOLUTE_PLACEMENT",
        "ARMCC_INLINE_ASSEMBLY_FUNCTION",
    }
)


def _raise(code: str, message: str, details: dict[str, object]) -> MigrationPlanError:
    return MigrationPlanError(code, message, details)


#: Exact GCC float ABIs the migration may emit (work order revision 1).
_KNOWN_FLOAT_ABIS = frozenset({"soft", "softfp", "hard"})

#: Verifiable Keil ``uFloatingPoint`` evidence mapped to a GCC float ABI.
#: Keil writes 0/1/2 for "Not Used"/"Single precision"/"Double precision"
#: (documented MDK-ARM project format).  "Not Used" (0) selects soft; both
#: precision values use the ARM softfp ABI that ARMCC and ARMCLANG apply for
#: hardware FPU (a hard ABI can only be selected through misc controls,
#: which are already blocked separately).  Any other text is unknown or
#: ambiguous and produces a stable blocker instead of entering the manifest.
_KEIL_FLOAT_ABI_EVIDENCE = {"0": "soft", "1": "softfp", "2": "softfp"}

# Verifiable Keil CPU/FPU evidence mapped to a GCC FPU spelling.  The mapping
# is deliberately closed: an unknown tuple must not become an inferred
# compiler option.
_KEIL_FPU_EVIDENCE = {("cortex-m4", "FPU2"): "fpv4-sp-d16"}


def _normalize_float_abi(raw: str | None) -> tuple[str | None, str | None]:
    """Map raw Keil ``uFloatingPoint`` text to a GCC float ABI.

    Returns ``(normalized_value, None)`` for verifiable evidence (the exact
    GCC spellings ``soft``/``softfp``/``hard`` and Keil's "Not Used" value
    ``0``), ``(None, None)`` for an absent/empty element, and
    ``(None, blocker_code)`` for unknown or ambiguous text so the raw value
    never enters the manifest.
    """
    if raw is None:
        return None, None
    value = raw.strip()
    if not value:
        return None, None
    if value in _KNOWN_FLOAT_ABIS:
        return value, None
    normalized = _KEIL_FLOAT_ABI_EVIDENCE.get(value)
    if normalized is not None:
        return normalized, None
    return None, "MIGRATION_FLOAT_ABI_UNSUPPORTED"


def _normalize_target_fpu_abi(
    inspection: KeilInspection,
) -> tuple[str | None, str | None, str | None]:
    """Normalize the atomic Keil FPU/ABI pair without guessing unsupported data."""
    raw_fpu = (inspection.fpu or "").strip()
    raw_abi = (inspection.float_abi or "").strip()
    if not raw_fpu:
        if raw_abi:
            return None, None, "MIGRATION_FLOAT_ABI_REQUIRES_FPU"
        return None, None, None
    fpu = _KEIL_FPU_EVIDENCE.get((inspection.cpu.casefold(), raw_fpu.upper()))
    if fpu is None:
        return None, None, "MIGRATION_FPU_UNSUPPORTED"
    if raw_abi:
        abi, blocker = _normalize_float_abi(raw_abi)
        if blocker is not None:
            return None, None, blocker
        assert abi is not None
        return fpu, abi, None
    if (
        inspection.compiler == "armcc"
        and inspection.cpu.casefold() == "cortex-m4"
        and raw_fpu.upper() == "FPU2"
    ):
        return fpu, "hard", None
    return None, None, "MIGRATION_FLOAT_ABI_REQUIRED"


def _canonical_root(root: object, field: str = "projectRoot") -> Path:
    if not isinstance(root, Path):
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "project root must be a Path",
            {"field": field, "rule": "type"},
        )
    if "\x00" in str(root):
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "project root is invalid",
            {"field": field, "rule": "directory"},
        )
    try:
        canonical = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "project root is invalid or unreadable",
            {"field": field, "rule": "directory"},
        )
    if not canonical.is_dir():
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "project root must be an existing directory",
            {"field": field, "rule": "directory"},
        )
    return canonical


def _resolve_contained(absolute: Path, root: Path, path: str) -> Path:
    """Resolve redirects; the canonical target must stay inside the root."""
    try:
        resolved = absolute.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "MIGRATION_INPUT_INVALID",
            "path resolution failed",
            {"path": path, "rule": "withinProjectRoot"},
        )
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _raise(
            "MIGRATION_INPUT_INVALID",
            "path escapes the canonical project root",
            {"path": path, "rule": "withinProjectRoot"},
        )
    return resolved


def _read_limited(abs_path: Path, limit: int) -> bytes:
    with abs_path.open("rb") as handle:
        return handle.read(limit + 1)


def _revalidate_inputs(
    root: Path, digests: tuple[KeilInputDigest, ...]
) -> dict[str, bytes]:
    """Revalidate every recorded input: portable form, containment, regular
    file, recorded size, and exact SHA-256.  Returns the exact current bytes.

    In-root redirects are accepted; escapes, loops, permission failures,
    non-regular files, growth beyond the recorded size, or mismatched bytes
    raise the stable planning errors.
    """
    exact_bytes: dict[str, bytes] = {}
    total = 0
    for digest in digests:
        path = digest.path
        if portable_path_error(path) is not None:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input path is not portable",
                {"path": path, "rule": "withinProjectRoot"},
            )
        if digest.size > _FILE_LIMIT_BYTES:
            raise _raise(
                "MIGRATION_LIMIT_EXCEEDED",
                "input exceeds the per-file limit",
                {"scope": "file", "limitBytes": _FILE_LIMIT_BYTES},
            )
        total += digest.size
        if total > _AGGREGATE_LIMIT_BYTES:
            raise _raise(
                "MIGRATION_LIMIT_EXCEEDED",
                "aggregate input size exceeds the limit",
                {"scope": "aggregate", "limitBytes": _AGGREGATE_LIMIT_BYTES},
            )
        absolute = _resolve_contained(root.joinpath(*path.split("/")), root, path)
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise _raise(
                "MIGRATION_INSPECTION_CHANGED",
                "recorded input is missing",
                {"path": path},
            )
        except NotADirectoryError:
            raise _raise(
                "MIGRATION_INSPECTION_CHANGED",
                "recorded input is missing",
                {"path": path},
            )
        except OSError:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input inspection failed",
                {"path": path, "rule": "regularFile"},
            )
        if not stat.S_ISREG(lst.st_mode):
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input is not a regular file",
                {"path": path, "rule": "regularFile"},
            )
        if lst.st_size > digest.size:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input size exceeds the recorded size",
                {"path": path, "rule": "size"},
            )
        try:
            data = _read_limited(absolute, digest.size)
        except FileNotFoundError:
            raise _raise(
                "MIGRATION_INSPECTION_CHANGED",
                "recorded input is missing",
                {"path": path},
            )
        except OSError:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input is unreadable",
                {"path": path, "rule": "regularFile"},
            )
        if len(data) > digest.size:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "input size exceeds the recorded size",
                {"path": path, "rule": "size"},
            )
        if len(data) != digest.size or hashlib.sha256(data).hexdigest() != digest.sha256:
            raise _raise(
                "MIGRATION_INSPECTION_CHANGED",
                "recorded input bytes changed",
                {"path": path},
            )
        exact_bytes[path] = data
    return exact_bytes


def _unified_diff(path: str, before_text: str, after_text: str) -> str:
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


def _finding_blockers(findings: tuple) -> list[MigrationBlocker]:
    """Map inspection findings to migration blockers.

    Severity-blocker findings resolved by a supported rule produce no extra
    blocker; every other severity-blocker finding becomes
    ``ARMCC_FINDING_UNSUPPORTED``.  Warning findings for linker settings
    become ``ARMCC_LINKER_CONFIGURATION_UNSUPPORTED``.
    """
    blockers: list[MigrationBlocker] = []
    for finding in findings:
        if finding.severity == "blocker":
            if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA":
                if rules.pragma_is_supported(finding.evidence):
                    # The token-aware rule rewrites exactly this directive;
                    # every other import/pragma keeps its blocker.
                    continue
                blockers.append(
                    MigrationBlocker(
                        "ARMCC_PRAGMA_UNSUPPORTED",
                        "ARMCC_PRAGMA_UNSUPPORTED",
                        finding.path,
                        finding.line,
                        finding.column,
                        finding.evidence,
                        "unsupported ARMCC pragma",
                    )
                )
            elif finding.rule_id not in _RESOLVED_BLOCKER_FINDINGS:
                blockers.append(
                    MigrationBlocker(
                        "ARMCC_FINDING_UNSUPPORTED",
                        "ARMCC_FINDING_UNSUPPORTED",
                        finding.path,
                        finding.line,
                        finding.column,
                        finding.evidence,
                        "unsupported inspection finding",
                    )
                )
        elif finding.rule_id == "ARMCC_CUSTOM_SECTION" and finding.path == "":
            blockers.append(
                MigrationBlocker(
                    "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED",
                    "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED",
                    finding.path,
                    finding.line,
                    finding.column,
                    finding.evidence,
                    "ARMCC linker configuration requires translation",
                )
            )
    return blockers


def _scoped_option_blockers(inspection: KeilInspection) -> list[MigrationBlocker]:
    """Scoped options that cannot be represented, in authored inspection order.

    Include-only scopes whose compiled sources are only included C/C++ are
    mergeable and must not receive this generic blocker; include-only scopes
    that also compile included assembly or an unknown language keep it so
    their semantics are never silently dropped.  Listed headers and
    precompiled libraries are not compiled and do not make a scope blocked.
    A scope with defines or misc controls always keeps it, and an
    excluded-file or no-compiled-source include scope is inert.
    """
    blocked_includes = set(classify_include_scopes(inspection).blocked)
    blockers: list[MigrationBlocker] = []
    for option in inspection.scoped_options:
        if option.scope not in {"group", "file"}:
            continue
        if not (option.defines or option.include_paths or option.misc_controls):
            continue
        if option.defines or option.misc_controls:
            message = "scoped ARMCC compiler options are not representable"
        elif option in blocked_includes:
            message = (
                "scoped include path also applies to included ARMCC assembly"
                " or an unknown compiled language and is not representable"
            )
        else:
            continue
        owner = option.owner if option.scope == "file" else ""
        blockers.append(
            MigrationBlocker(
                "ARMCC_OPTION_UNSUPPORTED",
                "ARMCC_OPTION_UNSUPPORTED",
                owner,
                0,
                0,
                f"{option.scope}:{option.owner}"[:200],
                message,
            )
        )
    return blockers


def _inspection_blockers(
    inspection: KeilInspection, resolved_assembly: str | None = None
) -> list[MigrationBlocker]:
    blockers: list[MigrationBlocker] = []
    if inspection.compiler != "armcc":
        blockers.append(
            MigrationBlocker(
                "MIGRATION_COMPILER_UNSUPPORTED",
                "MIGRATION_COMPILER_UNSUPPORTED",
                "",
                0,
                0,
                "",
                "compiler is not ARM Compiler 5",
            )
        )
    if inspection.framework not in _ALLOWED_FRAMEWORKS:
        blockers.append(
            MigrationBlocker(
                "MIGRATION_FRAMEWORK_SELECTION_REQUIRED",
                "MIGRATION_FRAMEWORK_SELECTION_REQUIRED",
                "",
                0,
                0,
                "",
                "driver framework selection is required",
            )
        )
    input_sizes = {digest.path: digest.size for digest in inspection.inputs}
    for source in inspection.sources:
        if source.included and source.language == "asm":
            if source.path == resolved_assembly:
                continue
            if input_sizes.get(source.path, 0) > 0:
                blockers.append(
                    MigrationBlocker(
                        "ARMCC_ASSEMBLY_UNSUPPORTED",
                        "ARMCC_ASSEMBLY_UNSUPPORTED",
                        source.path,
                        0,
                        0,
                        "",
                        "included ARMCC assembly requires a reviewed GNU-compatible assembly adaptation; if this is startup code, review vector table and initialization; no file was written by planning",
                    )
                )
    if inspection.output.scatter_file:
        blockers.append(
            MigrationBlocker(
                "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED",
                "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED",
                inspection.output.scatter_file,
                0,
                0,
                inspection.output.scatter_file[:200],
                "non-empty scatter-file linker setting",
            )
        )
    _, _, fpu_abi_blocker = _normalize_target_fpu_abi(inspection)
    if fpu_abi_blocker is not None:
        blocker_messages = {
            "MIGRATION_FPU_UNSUPPORTED": "unsupported or ambiguous Keil FPU evidence",
            "MIGRATION_FLOAT_ABI_REQUIRED": "Keil FPU evidence requires an explicit float ABI",
            "MIGRATION_FLOAT_ABI_REQUIRES_FPU": "Keil float ABI evidence requires FPU evidence",
            "MIGRATION_FLOAT_ABI_UNSUPPORTED": "unsupported or ambiguous Keil float ABI",
        }
        blocker_evidence = {
            "MIGRATION_FPU_UNSUPPORTED": inspection.fpu,
            "MIGRATION_FLOAT_ABI_REQUIRED": inspection.fpu,
            "MIGRATION_FLOAT_ABI_REQUIRES_FPU": inspection.float_abi,
            "MIGRATION_FLOAT_ABI_UNSUPPORTED": inspection.float_abi,
        }[fpu_abi_blocker]
        blockers.append(
            MigrationBlocker(
                fpu_abi_blocker,
                fpu_abi_blocker,
                inspection.project_file,
                0,
                0,
                (blocker_evidence or "")[:200],
                blocker_messages[fpu_abi_blocker],
            )
        )
    for option in inspection.scoped_options:
        if option.scope == "target" and option.misc_controls:
            owner = option.owner if option.scope == "file" else ""
            blockers.append(
                MigrationBlocker(
                    "ARMCC_OPTION_UNSUPPORTED",
                    "ARMCC_OPTION_UNSUPPORTED",
                    owner,
                    0,
                    0,
                    "",
                    "ARMCC target/group/file misc controls are not empty",
                )
            )
    blockers.extend(_finding_blockers(inspection.findings))
    return blockers


def _sanitize_elf_basename(name: str) -> str:
    collapsed = _ELF_COLLAPSE_RE.sub("_", _ELF_SAFE_RE.sub("_", name))
    cleaned = collapsed.strip("._-")
    return cleaned if _ELF_NAME_RE.match(cleaned) and cleaned else "firmware"


def _validate_manifest_payload(root: Path, payload: dict) -> None:
    """Validate the proposed manifest against the packaged Schema v3 and the
    shared model path rules; failure is MIGRATION_MANIFEST_INVALID, never a
    guessed repair."""
    try:
        schema_text = (
            importlib.resources.files("stm32_toolkit")
            .joinpath("schemas")
            .joinpath("stm32-project.schema.json")
            .read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
    except (OSError, ValueError):
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "packaged schema is unavailable",
            {"field": "$schema", "rule": "invalidSchema"},
        )
    first = first_schema_error(payload, schema)
    if first is not None:
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "proposed manifest does not satisfy Schema v3",
            {"field": first[0], "rule": first[1]},
        )
    try:
        validate_model_document(root, payload, 3)
    except ProjectManifestError as error:
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "proposed manifest path validation failed",
            {
                "field": error.details.get("field", "$"),
                "rule": error.details.get("rule", "invalid"),
            },
        )


def _manifest_proposal(
    root: Path,
    inspection: KeilInspection,
    startup: StartupOutcome | None = None,
    memory_layout: MemoryLayout | None = None,
    include_paths: tuple[str, ...] | None = None,
    newlib_specs: tuple[str, ...] = (),
) -> dict | None:
    """Deterministic Schema v3 proposal; ``None`` when framework selection is blocked.

    ``include_paths`` carries the reviewed target include list (target order
    plus any validated scoped include-only directories); ``None`` keeps the
    historical inspection list.  ``newlib_specs`` is added only when a written
    source directive requires it, so other proposals keep their exact bytes.
    """
    proposed_includes = (
        tuple(inspection.include_paths) if include_paths is None else include_paths
    )
    if inspection.framework not in _ALLOWED_FRAMEWORKS:
        return None
    startup_ready = startup is not None and startup.ready
    project_name = (inspection.output.output_name or "").strip()
    if not project_name:
        project_name = Path(inspection.project_file).stem
    if not project_name:
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "project name must be non-empty",
            {"field": "project.name", "rule": "nonEmpty"},
        )
    core = _WHITESPACE_RUN_RE.sub("-", inspection.cpu.strip().lower())
    if not core:
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "target core must be non-empty",
            {"field": "target.core", "rule": "nonEmpty"},
        )
    elf_basename = _sanitize_elf_basename(project_name)
    if not elf_basename:
        elf_basename = "firmware"
    regions = [
        {
            "name": region.name,
            "origin": region.origin,
            "length": region.length,
            "attributes": region.attributes,
        }
        for region in inspection.memory_regions
    ]
    assembly_sources = [
        STARTUP_GENERATED_PATH
        if startup_ready and startup is not None and source.path == startup.selected_source
        else source.path
        for source in inspection.sources
        if source.included and source.language == "asm"
    ]
    memory_payload: dict[str, object] = {"source": "keil", "regions": regions}
    generation_payload: dict[str, object] = {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    }
    if startup_ready and startup is not None:
        analysis = startup.analysis
        assert analysis.stack_size is not None and analysis.heap_size is not None
        memory_payload["stackSize"] = analysis.stack_size
        memory_payload["heapSize"] = analysis.heap_size
        generation_payload["runtimeInitialization"] = RUNTIME_INITIALIZATION
    if memory_layout is not None:
        # Only a reviewed explicit choice enters the manifest.  An implicit
        # single-Flash/single-RAM proposal stays byte-identical to the
        # historical output and keeps its model hash.
        memory_payload["layout"] = memory_layout.to_dict()
    payload: dict = {
        "schemaVersion": 3,
        "logicalProjectId": str(
            uuid.uuid5(
                _UUID_NAMESPACE,
                f"{inspection.project_file}\n{inspection.target_name}\n{inspection.device}",
            )
        ),
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": project_name, "origin": "keil-migration"},
        "target": {"device": inspection.device, "core": core},
        "framework": {"type": inspection.framework, "version": None},
        "build": {
            "sources": [
                source.path
                for source in inspection.sources
                if source.included and source.language in ("c", "cxx")
            ],
            "includePaths": list(proposed_includes),
            "defines": list(inspection.defines),
            "compileOptions": [],
            "linkStandardMath": True,
            "assemblySources": assembly_sources,
            "presets": ["arm-debug", "arm-release"],
            "elf": f"build/arm-debug/{elf_basename}.elf",
        },
        "memory": memory_payload,
        "debug": {},
        "generation": generation_payload,
    }
    if newlib_specs:
        payload["build"]["newlibSpecs"] = list(newlib_specs)
    normalized_fpu, normalized_float_abi, _ = _normalize_target_fpu_abi(inspection)
    if normalized_fpu is not None:
        payload["target"]["fpu"] = normalized_fpu
    if normalized_float_abi is not None:
        payload["target"]["floatAbi"] = normalized_float_abi
    if inspection.device_pack is not None:
        payload["target"]["devicePack"] = inspection.device_pack
    _validate_manifest_payload(root, payload)
    return payload


def _canonical_manifest_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


@dataclass(frozen=True)
class ConversionAnalysis:
    """Shared, read-only technical analysis for preflight and planning.

    ``blockers`` contains every technical and manifest blocker under the same
    rule set used by ``plan_keil_conversion``.  Git evidence is deliberately
    absent: callers may add their own stable blockers or report it separately.
    """

    project_root: Path
    inspection: KeilInspection
    inputs: tuple[MigrationInput, ...]
    patches: tuple[FilePatch, ...]
    fixed_sections: tuple[FixedSectionRequirement, ...]
    blockers: tuple[MigrationBlocker, ...]
    ignored: tuple[IgnoredObservation, ...]
    startup: StartupAnalysis | None = None
    memory_layout: MemoryLayoutResolution | None = None
    #: Reviewed include-only scope evidence and the resulting target include
    #: list.  Empty merges preserve the historical proposal bytes.
    include_merges: tuple[IncludeMerge, ...] = ()
    include_paths: tuple[str, ...] = ()


def _bind_analysis_root(root: object, inspection: object) -> Path:
    """Validate the inspection object and its exact canonical project root."""
    if not isinstance(inspection, KeilInspection):
        raise _raise(
            "MIGRATION_INSPECTION_INVALID",
            "inspection must be a KeilInspection",
            {"field": "inspection", "rule": "type"},
        )
    canonical = _canonical_root(root)
    try:
        inspection_root = inspection.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "MIGRATION_INSPECTION_INVALID",
            "inspection project root is invalid",
            {"field": "inspection", "rule": "rootMatch"},
        )
    if canonical != inspection_root:
        raise _raise(
            "MIGRATION_INSPECTION_INVALID",
            "root does not match the inspection project root",
            {"field": "inspection", "rule": "rootMatch"},
        )
    return canonical


def _validate_startup_options(options: object) -> StartupOptions | None:
    if options is None:
        return None
    if type(options) is not StartupOptions:
        raise _raise(
            "MIGRATION_STARTUP_OPTIONS_INVALID",
            "startup options are invalid",
            {"field": "startupOptions", "rule": "type"},
        )
    if options.strategy != "generate-cmsis-gcc":
        raise _raise(
            "MIGRATION_STARTUP_STRATEGY_UNSUPPORTED",
            "startupStrategy is not supported",
            {"field": "startupStrategy", "rule": "unsupported"},
        )
    if options.source is not None and (
        portable_path_error(options.source) is not None or "\\" in options.source
    ):
        raise _raise(
            "MIGRATION_STARTUP_OPTIONS_INVALID",
            "startupSource is not a portable project-relative path",
            {"field": "startupSource", "rule": "withinProjectRoot"},
        )
    return options


def _validate_memory_layout(layout: object) -> MemoryLayout | None:
    if layout is None:
        return None
    if type(layout) is not MemoryLayout:
        raise _raise(
            "MEMORY_LAYOUT_INVALID",
            "memoryLayout must be an explicit layout object",
            {
                "field": "memoryLayout",
                "rule": "type",
                "remediation": "Pass the five-role memoryLayout object.",
            },
        )
    return layout


def analyze_keil_conversion(
    root: Path,
    inspection: KeilInspection,
    *,
    block_source: Callable[[Path], tuple[MigrationBlocker, ...]] | None = None,
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
) -> ConversionAnalysis:
    """Run the single shared technical analysis used by preflight and plan.

    ``block_source`` runs after input revalidation and before the fresh
    inspection, preserving the planning error precedence and letting the
    Git-bound planner contribute its dirty-worktree blockers.  ``startup_options``
    selects the opt-in CMSIS startup generation route; omitted options preserve
    the existing assembly blockers byte-for-byte.
    """
    options = _validate_startup_options(startup_options)
    layout_option = _validate_memory_layout(memory_layout)
    canonical = _bind_analysis_root(root, inspection)
    exact_bytes = _revalidate_inputs(canonical, inspection.inputs)
    extra_blockers = block_source(canonical) if block_source is not None else ()

    try:
        fresh = inspect_keil(
            canonical,
            uvprojx=canonical / inspection.project_file,
            target_name=inspection.target_name,
        )
    except KeilInspectionError:
        raise _raise(
            "MIGRATION_INSPECTION_INVALID",
            "fresh inspection could not be reproduced",
            {"field": "inspection", "rule": "freshInspection"},
        )
    if inspection_sha256_for(fresh) != inspection_sha256_for(inspection):
        raise _raise(
            "MIGRATION_INSPECTION_INVALID",
            "fresh inspection does not match the supplied inspection",
            {"field": "inspection", "rule": "freshInspection"},
        )

    try:
        layout_resolution = resolve_memory_layout(
            inspection.memory_regions, layout_option
        )
    except MemoryLayoutError as error:
        raise _raise(error.code, error.message, error.details)

    startup_outcome = (
        analyze_startup(canonical, inspection, options, exact_bytes)
        if options is not None
        else None
    )
    resolved_assembly = (
        startup_outcome.selected_source
        if startup_outcome is not None and startup_outcome.ready
        else None
    )

    # One bounded, read-only include analysis feeds both the reviewed manifest
    # proposal and the blocker set.  Any invalid scope contributes no partial
    # merge, so the proposal keeps the historical target include list.
    include_analysis = analyze_scoped_includes(canonical, inspection)

    blockers: list[MigrationBlocker] = list(extra_blockers)
    scoped_option_blockers = _scoped_option_blockers(inspection)
    blockers.extend(_inspection_blockers(inspection, resolved_assembly))
    blockers.extend(include_analysis.blockers)
    if startup_outcome is not None:
        for diagnostic in startup_outcome.analysis.diagnostics:
            blockers.append(
                MigrationBlocker(
                    diagnostic.code,
                    diagnostic.code,
                    diagnostic.path,
                    diagnostic.line,
                    diagnostic.column,
                    diagnostic.evidence,
                    diagnostic.message,
                )
            )

    scan_entries = [
        (source.path, exact_bytes[source.path], source.language)
        for source in inspection.sources
        if source.included
        and source.language in _SCANNED_LANGUAGES
        and source.path in exact_bytes
    ]
    # Symbolic rule values (placements, alignment) resolve only from explicit
    # target defines and contained quoted includes under the reviewed include
    # search list.  The macro index is built lazily per source, so files with
    # literal-only values never read a header.
    symbols = SymbolSource(
        canonical, include_analysis.include_paths, inspection.defines
    )
    scans = rules.scan_sources(scan_entries, symbols=symbols)

    fixed_sections: list[FixedSectionRequirement] = []
    ignored: list[IgnoredObservation] = []
    link_specs: list[str] = []
    dependencies: dict[str, tuple[str, int]] = {}
    for scan in scans:
        fixed_sections.extend(scan.fixed_sections)
        ignored.extend(scan.ignored)
        blockers.extend(scan.blockers)
        for spec in scan.link_specs:
            if spec not in link_specs:
                link_specs.append(spec)
        for path, digest, size in scan.dependencies:
            dependencies.setdefault(path, (digest, size))

    memory_regions = inspection.memory_regions
    # A fixed address outside every declared region is a memory-definition
    # decision for the project owner.  Toolkit never invents external SRAM.
    for section in sorted(
        fixed_sections, key=lambda s: (s.address, s.section, s.source_path, s.line, s.symbol)
    ):
        if any(
            region.origin <= section.address < region.origin + region.length
            for region in memory_regions
        ):
            continue
        blockers.append(
            MigrationBlocker(
                "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY",
                "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY",
                section.source_path,
                section.line,
                0,
                f"{section.section} at 0x{section.address:08x}"[:200],
                "fixed placement address is outside every declared memory region;"
                " provide an explicit project-owned memory definition before"
                " applying (Toolkit never invents an external memory region)",
            )
        )
    if not any("x" in region.attributes for region in memory_regions) or not any(
        "w" in region.attributes for region in memory_regions
    ):
        blockers.append(
            MigrationBlocker(
                "MIGRATION_MEMORY_INCOMPLETE",
                "MIGRATION_MEMORY_INCOMPLETE",
                "",
                0,
                0,
                "",
                "memory regions need at least one executable and one writable region",
            )
        )

    if layout_resolution.requires_selection:
        blockers.append(
            MigrationBlocker(
                "MEMORY_LAYOUT_REQUIRED",
                "MEMORY_LAYOUT_REQUIRED",
                "",
                0,
                0,
                ",".join(layout_resolution.unresolved_roles),
                layout_resolution.remediation(),
            )
        )

    proposal = _manifest_proposal(
        canonical,
        inspection,
        startup_outcome,
        layout_option,
        include_analysis.include_paths,
        tuple(sorted(set(link_specs))),
    )
    proposal_bytes = _canonical_manifest_bytes(proposal) if proposal is not None else None

    inputs = [MigrationInput(digest.path, digest.sha256, digest.size) for digest in inspection.inputs]
    if startup_outcome is not None and startup_outcome.destination_bytes is not None:
        inputs.append(
            MigrationInput(
                STARTUP_GENERATED_PATH,
                hashlib.sha256(startup_outcome.destination_bytes).hexdigest(),
                len(startup_outcome.destination_bytes),
            )
        )
    # Every quoted header that supplied a symbolic value is bound byte-for-
    # byte, including headers no project source lists.  A changed, added, or
    # newly shadowing header therefore fails apply revalidation or the fresh
    # replan instead of silently changing an approved placement.
    known_inputs = {entry.path: entry for entry in inputs}
    folded_inputs = {entry.path.casefold(): entry.path for entry in inputs}
    for path, (digest, size) in sorted(dependencies.items()):
        existing = known_inputs.get(path)
        if existing is not None:
            if existing.sha256 != digest or existing.size != size:
                raise _raise(
                    "MIGRATION_INSPECTION_CHANGED",
                    "symbol dependency bytes changed",
                    {"path": path},
                )
            continue
        collision = folded_inputs.get(path.casefold())
        if collision is not None:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "symbol dependency path collides with a recorded input",
                {"path": path, "rule": "casefoldCollision"},
            )
        entry = MigrationInput(path, digest, size)
        inputs.append(entry)
        known_inputs[path] = entry
        folded_inputs[path.casefold()] = path
    manifest_input: MigrationInput | None = None
    manifest_abs = canonical / _MANIFEST_NAME
    try:
        os.lstat(manifest_abs)
    except FileNotFoundError:
        manifest_present = False
    except NotADirectoryError:
        manifest_present = False
    except OSError:
        raise _raise(
            "MIGRATION_INPUT_INVALID",
            "manifest inspection failed",
            {"path": _MANIFEST_NAME, "rule": "regularFile"},
        )
    else:
        manifest_present = True
    if manifest_present:
        resolved = _resolve_contained(manifest_abs, canonical, _MANIFEST_NAME)
        try:
            data = _read_limited(resolved, _MANIFEST_LIMIT_BYTES)
        except FileNotFoundError:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "manifest is missing",
                {"path": _MANIFEST_NAME, "rule": "regularFile"},
            )
        except OSError:
            raise _raise(
                "MIGRATION_INPUT_INVALID",
                "manifest is unreadable",
                {"path": _MANIFEST_NAME, "rule": "regularFile"},
            )
        if len(data) > _MANIFEST_LIMIT_BYTES:
            raise _raise(
                "MIGRATION_LIMIT_EXCEEDED",
                "manifest exceeds the per-file limit",
                {"scope": "file", "limitBytes": _MANIFEST_LIMIT_BYTES},
            )
        manifest_input = MigrationInput(
            _MANIFEST_NAME, hashlib.sha256(data).hexdigest(), len(data)
        )
        inputs.append(manifest_input)
        if proposal_bytes is None or data != proposal_bytes:
            blockers.append(
                MigrationBlocker(
                    "MIGRATION_MANIFEST_EXISTS",
                    "MIGRATION_MANIFEST_EXISTS",
                    _MANIFEST_NAME,
                    0,
                    0,
                    "",
                    "existing .stm32-project.json differs from the proposal; review and resolve it explicitly before replanning; no file was written",
                )
            )
    inputs.sort(key=lambda entry: entry.path)

    patches: list[FilePatch] = []
    for scan in scans:
        if scan.after == scan.before:
            continue
        before_text = scan.before.decode("utf-8-sig")
        after_text = scan.after.decode("utf-8-sig")
        patches.append(
            FilePatch(
                path=scan.path,
                before_sha256=hashlib.sha256(scan.before).hexdigest(),
                after_sha256=hashlib.sha256(scan.after).hexdigest(),
                before_size=len(scan.before),
                after_size=len(scan.after),
                rule_ids=scan.rule_ids,
                unified_diff=_unified_diff(scan.path, before_text, after_text),
                before_bytes=scan.before,
                after_bytes=scan.after,
            )
        )
    if (
        startup_outcome is not None
        and startup_outcome.ready
        and startup_outcome.generated_bytes is not None
        and startup_outcome.destination_state == "missing"
    ):
        generated_bytes = startup_outcome.generated_bytes
        patches.append(
            FilePatch(
                path=STARTUP_GENERATED_PATH,
                before_sha256=None,
                after_sha256=hashlib.sha256(generated_bytes).hexdigest(),
                before_size=None,
                after_size=len(generated_bytes),
                rule_ids=("MIGRATION_STARTUP_GCC",),
                unified_diff=_unified_diff(
                    STARTUP_GENERATED_PATH, "", generated_bytes.decode("utf-8")
                ),
                before_bytes=None,
                after_bytes=generated_bytes,
            )
        )
    if proposal_bytes is not None and manifest_input is None:
        patches.append(
            FilePatch(
                path=_MANIFEST_NAME,
                before_sha256=None,
                after_sha256=hashlib.sha256(proposal_bytes).hexdigest(),
                before_size=None,
                after_size=len(proposal_bytes),
                rule_ids=("MIGRATION_MANIFEST",),
                unified_diff=_unified_diff(_MANIFEST_NAME, "", proposal_bytes.decode("utf-8")),
                before_bytes=None,
                after_bytes=proposal_bytes,
            )
        )
    patches.sort(key=lambda patch: patch.path)

    patch_content = b"".join(patch.unified_diff.encode("utf-8") for patch in patches)
    if len(patch_content) > _PATCH_LIMIT_BYTES:
        raise _raise(
            "MIGRATION_LIMIT_EXCEEDED",
            "conversion patch exceeds the limit",
            {"scope": "patch", "limitBytes": _PATCH_LIMIT_BYTES},
        )

    def blocker_key(blocker: MigrationBlocker) -> tuple:
        return (blocker.path, blocker.line, blocker.column, blocker.code, blocker.rule_id)

    unique_blockers: dict[tuple, MigrationBlocker] = {}
    for blocker in sorted(blockers, key=blocker_key):
        unique_blockers.setdefault(
            (blocker.code, blocker.rule_id, blocker.path, blocker.line, blocker.column),
            blocker,
        )
    ordered_blockers = tuple(unique_blockers.values()) + tuple(scoped_option_blockers)

    return ConversionAnalysis(
        project_root=canonical,
        inspection=fresh,
        inputs=tuple(inputs),
        patches=tuple(patches),
        fixed_sections=tuple(
            sorted(
                fixed_sections,
                key=lambda s: (s.address, s.section, s.source_path, s.line, s.symbol),
            )
        ),
        blockers=ordered_blockers,
        ignored=tuple(sorted(ignored, key=lambda o: (o.path, o.line, o.column, o.rule_id))),
        startup=startup_outcome.analysis if startup_outcome is not None else None,
        memory_layout=layout_resolution,
        include_merges=include_analysis.merges,
        include_paths=include_analysis.include_paths,
    )


def _git_dirty_blockers(canonical: Path) -> tuple[tuple[MigrationBlocker, ...], str]:
    """Capture read-only Git evidence and map dirty entries to stable blockers."""
    head = git_guard.git_head(canonical)
    status = git_guard.porcelain_status(canonical)
    blockers: list[MigrationBlocker] = []
    for category, path in git_guard.dirty_paths(status):
        next_step = {
            "index": "Review staged changes and commit or preserve them before replanning.",
            "tracked": "Review tracked working-tree changes and commit or preserve them before replanning.",
            "untracked": "Review and intentionally preserve this untracked file before replanning; Toolkit will not delete it.",
        }[category]
        blockers.append(
            MigrationBlocker(
                "MIGRATION_GIT_DIRTY",
                f"MIGRATION_GIT_{category.upper()}_DIRTY",
                path,
                0,
                0,
                category,
                f"Git {category} path blocks the read-only conversion plan. {next_step}",
            )
        )
    return tuple(blockers), head


def plan_keil_conversion(
    root: Path,
    inspection: KeilInspection,
    *,
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
) -> MigrationPlan:
    """Produce the deterministic, read-only conversion plan."""
    options = _validate_startup_options(startup_options)
    layout_option = _validate_memory_layout(memory_layout)
    canonical = _bind_analysis_root(root, inspection)

    toplevel = git_guard.git_toplevel(canonical)
    if toplevel != canonical:
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "root is not the canonical Git worktree toplevel",
            {"field": "projectRoot", "rule": "canonicalRoot"},
        )

    git_evidence: dict[str, str] = {}

    def block_source(root_path: Path) -> tuple[MigrationBlocker, ...]:
        blockers, head = _git_dirty_blockers(root_path)
        git_evidence["head"] = head
        return blockers

    analysis = analyze_keil_conversion(
        canonical,
        inspection,
        block_source=block_source,
        startup_options=options,
        memory_layout=layout_option,
    )

    plan = MigrationPlan(
        project_root=canonical,
        inspection=analysis.inspection,
        plan_version=1,
        plan_id="",
        inspection_sha256=inspection_sha256_for(analysis.inspection),
        git=GitBaseline(git_evidence["head"], "."),
        inputs=analysis.inputs,
        patches=analysis.patches,
        fixed_sections=analysis.fixed_sections,
        blockers=analysis.blockers,
        startup=analysis.startup,
        startup_options=options,
        memory_layout=layout_option,
        memory_layout_resolution=analysis.memory_layout,
        include_merges=analysis.include_merges,
    )
    object.__setattr__(plan, "_ignored", analysis.ignored)
    plan = replace(plan, plan_id=plan_id_for(plan))
    object.__setattr__(plan, "_ignored", analysis.ignored)

    serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
    if len(serialized.encode("utf-8")) > _PLAN_LIMIT_BYTES:
        raise _raise(
            "MIGRATION_LIMIT_EXCEEDED",
            "serialized plan exceeds the limit",
            {"scope": "plan", "limitBytes": _PLAN_LIMIT_BYTES},
        )
    return plan
