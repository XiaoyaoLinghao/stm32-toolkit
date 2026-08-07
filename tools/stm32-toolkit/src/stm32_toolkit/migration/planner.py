"""Deterministic, read-only ARMCC conversion planning.

``plan_keil_conversion`` validates the canonical Git root, revalidates every
inspection input byte-for-byte, captures read-only Git evidence, re-runs the
Keil inspection to reject forged/stale findings, applies the token-aware
source rules, proposes a validated Schema v2 manifest, and assembles an
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
from dataclasses import replace
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.keil import KeilInspection, KeilInspectionError, KeilInputDigest, inspect_keil
from stm32_toolkit.project_model import ProjectManifestError, first_schema_error, validate_model_document

from stm32_toolkit.migration import git_guard
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.model import (
    FilePatch,
    FixedSectionRequirement,
    GitBaseline,
    IgnoredObservation,
    MigrationBlocker,
    MigrationInput,
    MigrationPlan,
    MigrationPlanError,
    inspection_sha256_for,
    plan_id_for,
    portable_path_error,
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


def _inspection_blockers(inspection: KeilInspection) -> list[MigrationBlocker]:
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
            if input_sizes.get(source.path, 0) > 0:
                blockers.append(
                    MigrationBlocker(
                        "ARMCC_ASSEMBLY_UNSUPPORTED",
                        "ARMCC_ASSEMBLY_UNSUPPORTED",
                        source.path,
                        0,
                        0,
                        "",
                        "included ARM assembly source is unsupported",
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
    _, float_abi_blocker = _normalize_float_abi(inspection.float_abi)
    if float_abi_blocker is not None:
        blockers.append(
            MigrationBlocker(
                float_abi_blocker,
                float_abi_blocker,
                inspection.project_file,
                0,
                0,
                (inspection.float_abi or "")[:200],
                "unsupported or ambiguous Keil float ABI",
            )
        )
    for option in inspection.scoped_options:
        if option.misc_controls:
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
    """Validate the proposed manifest against the packaged Schema v2 and the
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
            "proposed manifest does not satisfy Schema v2",
            {"field": first[0], "rule": first[1]},
        )
    try:
        validate_model_document(root, payload, 2)
    except ProjectManifestError as error:
        raise _raise(
            "MIGRATION_MANIFEST_INVALID",
            "proposed manifest path validation failed",
            {
                "field": error.details.get("field", "$"),
                "rule": error.details.get("rule", "invalid"),
            },
        )


def _manifest_proposal(root: Path, inspection: KeilInspection) -> dict | None:
    """Deterministic Schema v2 proposal; ``None`` when framework selection is
    blocked (Schema v2 requires a concrete framework)."""
    if inspection.framework not in _ALLOWED_FRAMEWORKS:
        return None
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
    payload: dict = {
        "schemaVersion": 2,
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
            "includePaths": list(inspection.include_paths),
            "defines": list(inspection.defines),
            "compileOptions": [],
            "assemblySources": [
                source.path
                for source in inspection.sources
                if source.included and source.language == "asm"
            ],
            "presets": ["arm-debug", "arm-release"],
            "elf": f"build/arm-debug/{elf_basename}.elf",
        },
        "memory": {"source": "keil", "regions": regions},
        "debug": {},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }
    if inspection.fpu is not None:
        payload["target"]["fpu"] = inspection.fpu
    normalized_float_abi, _ = _normalize_float_abi(inspection.float_abi)
    if normalized_float_abi is not None:
        payload["target"]["floatAbi"] = normalized_float_abi
    if inspection.device_pack is not None:
        payload["target"]["devicePack"] = inspection.device_pack
    _validate_manifest_payload(root, payload)
    return payload


def _canonical_manifest_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def plan_keil_conversion(root: Path, inspection: KeilInspection) -> MigrationPlan:
    """Produce the deterministic, read-only conversion plan."""
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

    toplevel = git_guard.git_toplevel(canonical)
    if toplevel != canonical:
        raise _raise(
            "MIGRATION_ROOT_INVALID",
            "root is not the canonical Git worktree toplevel",
            {"field": "projectRoot", "rule": "canonicalRoot"},
        )

    exact_bytes = _revalidate_inputs(canonical, inspection.inputs)
    head = git_guard.git_head(canonical)
    status = git_guard.porcelain_status(canonical)

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

    blockers: list[MigrationBlocker] = []
    if status:
        blockers.append(
            MigrationBlocker(
                "MIGRATION_GIT_DIRTY",
                "MIGRATION_GIT_DIRTY",
                "",
                0,
                0,
                "",
                "Git working tree is not clean",
            )
        )
    blockers.extend(_inspection_blockers(inspection))

    scan_entries = [
        (source.path, exact_bytes[source.path], source.language)
        for source in inspection.sources
        if source.included
        and source.language in _SCANNED_LANGUAGES
        and source.path in exact_bytes
    ]
    scans = rules.scan_sources(scan_entries)

    fixed_sections: list[FixedSectionRequirement] = []
    ignored: list[IgnoredObservation] = []
    for scan in scans:
        fixed_sections.extend(scan.fixed_sections)
        ignored.extend(scan.ignored)
        blockers.extend(scan.blockers)

    memory_regions = inspection.memory_regions
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

    proposal = _manifest_proposal(canonical, inspection)
    proposal_bytes = _canonical_manifest_bytes(proposal) if proposal is not None else None

    inputs = [MigrationInput(digest.path, digest.sha256, digest.size) for digest in inspection.inputs]
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
                    "an existing .stm32-project.json differs from the proposal",
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
    ordered_blockers = tuple(unique_blockers.values())

    plan = MigrationPlan(
        project_root=canonical,
        inspection=fresh,
        plan_version=1,
        plan_id="",
        inspection_sha256=inspection_sha256_for(fresh),
        git=GitBaseline(head, "."),
        inputs=tuple(inputs),
        patches=tuple(patches),
        fixed_sections=tuple(
            sorted(
                fixed_sections,
                key=lambda s: (s.address, s.section, s.source_path, s.line, s.symbol),
            )
        ),
        blockers=ordered_blockers,
    )
    sorted_ignored = tuple(sorted(ignored, key=lambda o: (o.path, o.line, o.column, o.rule_id)))
    object.__setattr__(plan, "_ignored", sorted_ignored)
    plan = replace(plan, plan_id=plan_id_for(plan))
    object.__setattr__(plan, "_ignored", sorted_ignored)

    serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
    if len(serialized.encode("utf-8")) > _PLAN_LIMIT_BYTES:
        raise _raise(
            "MIGRATION_LIMIT_EXCEEDED",
            "serialized plan exceeds the limit",
            {"scope": "plan", "limitBytes": _PLAN_LIMIT_BYTES},
        )
    return plan
