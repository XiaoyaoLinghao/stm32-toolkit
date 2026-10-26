"""Deterministic, read-only generation planning and guarded atomic apply.

``plan_project_configuration`` validates the model, revalidates every input
byte-for-byte, validates optional fixed-section evidence, renders the nine
managed targets from packaged StrictUndefined Jinja templates, classifies
every target against the prior managed manifest, and assembles an immutable
``GenerationPlan`` with deterministic hashes and ordering.  Planning never
writes.

``apply_project_configuration`` revalidates the plan's every field/digest,
the canonical root, a fresh model, all inputs, current targets, a fresh
re-plan, and the absence of blockers before its first write; then stages
under ``.stm32-toolkit/configuration-staging/<plan_id>`` with exclusive
creation, fsync, sibling temporaries and ``os.replace``, and rolls back
byte/mode-exactly on any recoverable failure.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from jinja2 import Environment, StrictUndefined, UndefinedError

from stm32_toolkit import __version__
from stm32_toolkit.debug_configuration import (
    DebugConfiguration,
    DebugConfigurationError,
    normalize_debug_configuration,
)
from stm32_toolkit.memory_layout import (
    MemoryLayoutError,
    MemoryLayoutResolution,
    resolve_memory_layout,
    validate_memory_layout_regions,
)
from stm32_toolkit.linker_fragment import BUILD_REMEDIATION
from stm32_toolkit.project_upgrade import ProjectMutationLockError
from stm32_toolkit.project_model import (
    ProjectManifestError,
    ProjectModel,
    load_project_model,
    load_project_model_candidate,
)
from stm32_toolkit.result import OperationResult
from stm32_toolkit.vscode_configuration import (
    VSCodeConfiguration,
    VSCodeConfigurationError,
    build_vscode_guidance,
    normalize_vscode_configuration,
)

from stm32_toolkit.generation.managed_files import (
    AGGREGATE_LIMIT_BYTES,
    CORE_CPU_FLAGS,
    FILE_LIMIT_BYTES,
    GENERATED_LIMIT_BYTES,
    GENERATED_TARGETS,
    MANAGED_MANIFEST_PATH,
    PLAN_LIMIT_BYTES,
    PLAN_VERSION,
    PRESERVABLE_EDITOR_TARGETS,
    STAGING_ROOT,
    TARGET_TEMPLATES,
    TEMPLATE_LIMIT_BYTES,
    TEMPLATE_VERSION,
    TOTAL_LIMIT_BYTES,
    GenerationBlocker,
    GenerationError,
    GeneratedFile,
    GenerationInput,
    GenerationPlan,
    ManagedFileRecord,
    ManifestEdit,
    _reject_duplicate_json_keys,
    build_managed_manifest_bytes,
    canonical_json_bytes,
    generation_error,
    is_supported_generation_producer,
    model_sha256_for,
    parse_managed_manifest,
    plan_id_for,
    portable_path_error,
    portable_sort_key,
    sha256_error,
    sha256_hex,
    unified_diff,
)

_STM32_PROJECT_MANIFEST = ".stm32-project.json"
_CONVERSION_REPORT_PATH = "artifacts/migration/conversion-report.json"

_REGION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEFINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(=.*)?$")
_C_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FPU_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OPTION_FORBIDDEN = re.compile(r"[\s;\"\\$`@]")
#: The closed allowlist for ``build.newlibSpecs``.  This is a bounded
#: representation of the reviewed no-semihosting pragma, not a generic linker
#: customization channel.
_SUPPORTED_NEWLIB_SPECS = frozenset({"nosys.specs"})
_PRESERVED_EDITOR_GUIDANCE = (
    "Preserved VS Code files are user-owned; align their IDE settings with the generated build manually."
)

_ENV = Environment(undefined=StrictUndefined, autoescape=False, loader=None)
_ENV.filters["json"] = lambda value: json.dumps(value, indent=2, ensure_ascii=False)


def _raise_error(code: str, message: str, details: dict[str, object]) -> GenerationError:
    return generation_error(code, message, details)


class _ApplyFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _fail(code: str, message: str, details: dict[str, object]) -> _ApplyFailure:
    return _ApplyFailure(code, message, details)


def _plan_invalid(rule: str) -> _ApplyFailure:
    return _fail("GENERATION_PLAN_INVALID", "plan validation failed", {"rule": rule})


@dataclass(frozen=True)
class RenderedConfiguration:
    """Pure in-memory rendering of a candidate manifest for a new project.

    ``files`` holds every generated target with ``status="create"`` and the
    exact bytes the normal planning route would write.  The managed manifest
    bytes come from :func:`build_managed_manifest_bytes`, the single authority
    shared with planning/apply, so callers never rebuild digests by hand.
    """

    model: ProjectModel
    model_sha256: str
    files: tuple[GeneratedFile, ...]
    managed_manifest_path: str
    managed_manifest_bytes: bytes


# ---------------------------------------------------------------------------
# identifiers and CMake quoting
# ---------------------------------------------------------------------------


def sanitize_cmake_identifier(name: str) -> str:
    """Sanitize a project/ELF name into a safe CMake identifier (work order 7.2)."""
    value = re.sub(r"[^A-Za-z0-9_]", "_", name)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")
    if not value:
        return "stm32_firmware"
    if value[0].isdigit():
        value = "stm32_" + value
    return value


def _cmake_quote(value: str) -> str:
    """Quote a CMake list atom when it needs quoting.

    Escapes only ``\\``, ``"`` and ``;`` inside the controlled renderer;
    every other character is emitted verbatim.
    """
    if not re.search(r"[\s;]", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace(";", "\\;")
    return '"' + escaped + '"'


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------


def plan_project_configuration(
    model: ProjectModel,
    *,
    debug_backend: object = None,
    debug_target: object = None,
    vscode_toolkit_path: object = None,
    vscode_gcc_path: object = None,
) -> GenerationPlan:
    """Produce a deterministic, read-only configuration plan for the model.

    With every keyword argument omitted the historical build-only planning
    route and plan shape are unchanged.  Supplying the explicit debug pair (or
    only one of them, which is refused) plans a user-owned manifest edit that
    sets exactly ``debug.backend`` and ``debug.target`` and nothing else.  The
    optional VS Code pair is validated statically and rendered verbatim; it is
    never written into the project model.
    """
    try:
        configuration = normalize_debug_configuration(debug_backend, debug_target)
    except DebugConfigurationError as error:
        raise _raise_error(error.code, error.message, error.details) from None
    try:
        vscode = normalize_vscode_configuration(vscode_toolkit_path, vscode_gcc_path)
    except VSCodeConfigurationError as error:
        raise _raise_error(error.code, error.message, error.details) from None
    try:
        return _plan(model, configuration, vscode)
    except GenerationError:
        raise
    except ProjectManifestError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project model is not available",
            {"field": "model", "rule": "unavailable"},
        ) from None


def _plan(
    model: ProjectModel,
    configuration: DebugConfiguration | None = None,
    vscode_configuration: VSCodeConfiguration | None = None,
) -> GenerationPlan:
    _validate_model(model)
    root = model.project_root
    manifest_edit: ManifestEdit | None = None
    if configuration is None:
        fresh = load_project_model(root)
        if model_sha256_for(fresh) != model_sha256_for(model):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "project model is stale",
                {"field": "model", "rule": "stale"},
            )
        effective = model
    else:
        # The supplied model is the observed source model; the effective
        # candidate below is validated from freshly read source bytes and is
        # never written to disk during planning.
        source_bytes = _read_source_manifest(root)
        try:
            source_model = load_project_model_candidate(root, source_bytes)
        except ProjectManifestError:
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "project model is not available",
                {"field": "model", "rule": "unavailable"},
            ) from None
        if model_sha256_for(source_model) != model_sha256_for(model):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "project model is stale",
                {"field": "model", "rule": "stale"},
            )
        after_bytes, edit_status = _manifest_candidate_bytes(
            source_bytes, configuration
        )
        if len(after_bytes) > FILE_LIMIT_BYTES:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "project manifest exceeds the limit",
                {"path": _STM32_PROJECT_MANIFEST, "rule": "size"},
            )
        try:
            effective = load_project_model_candidate(root, after_bytes)
        except ProjectManifestError:
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "debug configuration candidate is not a valid project model",
                {"field": "model", "rule": "candidate"},
            ) from None
        if (
            effective.debug.backend != configuration.backend
            or effective.debug.target != configuration.target
        ):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "debug configuration candidate did not retain the requested pair",
                {"field": "debug.backend", "rule": "value"},
            )
        manifest_edit = ManifestEdit(
            path=_STM32_PROJECT_MANIFEST,
            status=edit_status,
            before_sha256=sha256_hex(source_bytes),
            after_sha256=sha256_hex(after_bytes),
            before_size=len(source_bytes),
            after_size=len(after_bytes),
            unified_diff=(
                unified_diff(
                    _STM32_PROJECT_MANIFEST,
                    source_bytes.decode("utf-8", "replace"),
                    after_bytes.decode("utf-8", "replace"),
                )
                if edit_status == "update"
                else ""
            ),
            before_bytes=source_bytes,
            after_bytes=after_bytes,
        )
    _validate_generation_spec(effective)
    options = _validate_options(effective)
    _validate_memory(effective)
    layout = (
        None
        if effective.generation.native_linker_script is not None
        else _memory_layout_resolution(effective)
    )
    report, report_sha = _read_conversion_report(root)
    fixed_sections = _validate_fixed_sections(report, effective)
    prior_data = _read_prior_manifest(root)
    prior = parse_managed_manifest(prior_data) if prior_data is not None else ()
    inputs = _collect_inputs(root, effective, prior_data, report_sha)
    if manifest_edit is not None:
        # The manifest input is the observed SOURCE evidence.  A concurrent
        # rewrite between the two reads is a race, never a new candidate.
        manifest_input = next(
            (entry for entry in inputs if entry.path == _STM32_PROJECT_MANIFEST),
            None,
        )
        if (
            manifest_input is None
            or manifest_input.sha256 != manifest_edit.before_sha256
            or manifest_input.size != manifest_edit.before_size
        ):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "project model changed while configuration was planning",
                {"field": "model", "rule": "stale"},
            )
    rendered = _render_targets(
        effective, options, fixed_sections, layout, vscode_configuration
    )
    files = _classify_targets(root, rendered, prior)
    blockers = _collect_blockers(prior, files)
    model_sha256 = model_sha256_for(effective)
    manifest_bytes = build_managed_manifest_bytes(
        files, model_sha256, linker_fragment=effective.generation.linker_fragment
    )
    if len(manifest_bytes) > TOTAL_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "generated configuration exceeds the aggregate limit",
            {"template": "$", "rule": "aggregateLimit"},
        )
    total = sum(len(data) for _, data in rendered.values()) + len(manifest_bytes)
    if total > TOTAL_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "generated configuration exceeds the aggregate limit",
            {"template": "$", "rule": "aggregateLimit"},
        )
    plan = GenerationPlan(
        project_root=root,
        model=effective,
        plan_version=PLAN_VERSION,
        plan_id="",
        model_sha256=model_sha256,
        inputs=tuple(inputs),
        files=tuple(files),
        blockers=tuple(blockers),
        managed_manifest_path=MANAGED_MANIFEST_PATH,
        managed_manifest_bytes=manifest_bytes,
        debug_configuration=configuration,
        manifest_edit=manifest_edit,
        vscode_configuration=vscode_configuration,
    )
    plan = replace(plan, plan_id=plan_id_for(plan))
    if len(canonical_json_bytes(plan.to_dict())) > PLAN_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_PLAN_INVALID",
            "serialized plan exceeds the limit",
            {"rule": "planLimit"},
        )
    return plan


def render_new_project_configuration(
    root: Path,
    manifest_bytes: bytes,
    *,
    conversion_report_bytes: bytes | None = None,
) -> RenderedConfiguration:
    """Render generated configuration from validated in-memory candidate bytes.

    This is the pure new-project seam used by independent delivery: the caller
    owns the destination, and the destination is required to be empty, so no
    prior managed manifest or current target is consulted.  The candidate
    manifest and optional conversion report are validated exactly as the
    normal configure route validates the files it reads; nothing is read from
    ``root`` except the packaged templates and nothing is written.

    ``root`` must be an existing directory for the shared containment rules.
    The returned model hash and rendered bytes are independent of that host
    path, so the same manifest renders identically after relocation.
    """
    if not isinstance(root, Path):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project root must be a Path",
            {"field": "projectRoot", "rule": "type"},
        )
    try:
        model = load_project_model_candidate(root, manifest_bytes)
    except ProjectManifestError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project model is not available",
            {"field": "model", "rule": "unavailable"},
        ) from None
    _validate_model(model)
    _validate_generation_spec(model)
    options = _validate_options(model)
    _validate_memory(model)
    layout = (
        None
        if model.generation.native_linker_script is not None
        else _memory_layout_resolution(model)
    )
    report: dict[str, object] | None = None
    if conversion_report_bytes is not None:
        report = _decode_conversion_report(conversion_report_bytes, _CONVERSION_REPORT_PATH)
    fixed_sections = _validate_fixed_sections(report, model)
    rendered = _render_targets(model, options, fixed_sections, layout, None)
    files = tuple(
        GeneratedFile(
            path=target,
            status="create",
            template_name=template_name,
            template_version=TEMPLATE_VERSION,
            before_sha256=None,
            before_size=None,
            after_sha256=sha256_hex(after_bytes),
            after_size=len(after_bytes),
            unified_diff="",
            before_bytes=None,
            after_bytes=after_bytes,
        )
        for target, (template_name, after_bytes) in sorted(
            rendered.items(), key=lambda item: portable_sort_key(item[0])
        )
    )
    model_sha256 = model_sha256_for(model)
    managed_manifest_bytes = build_managed_manifest_bytes(
        files, model_sha256, linker_fragment=model.generation.linker_fragment
    )
    if (
        len(managed_manifest_bytes) > TOTAL_LIMIT_BYTES
        or sum(entry.after_size for entry in files) + len(managed_manifest_bytes)
        > TOTAL_LIMIT_BYTES
    ):
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "generated configuration exceeds the aggregate limit",
            {"template": "$", "rule": "aggregateLimit"},
        )
    return RenderedConfiguration(
        model=model,
        model_sha256=model_sha256,
        files=files,
        managed_manifest_path=MANAGED_MANIFEST_PATH,
        managed_manifest_bytes=managed_manifest_bytes,
    )


def _read_source_manifest(root: Path) -> bytes:
    """Read the source manifest once under strict editing-route guards."""
    path = _STM32_PROJECT_MANIFEST
    absolute = root.joinpath(*path.split("/"))
    try:
        lst = os.lstat(absolute)
    except (FileNotFoundError, NotADirectoryError):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not available",
            {"field": "model", "rule": "unavailable"},
        ) from None
    except OSError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not available",
            {"field": "model", "rule": "unavailable"},
        ) from None
    if stat.S_ISLNK(lst.st_mode) or bool(
        getattr(lst, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "project manifest must not redirect",
            {"path": path, "rule": "redirect"},
        )
    if not stat.S_ISREG(lst.st_mode):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not a regular file",
            {"field": "model", "rule": "regularFile"},
        )
    resolved = _resolve_contained(absolute, root, path)
    try:
        data = _read_limited(resolved, FILE_LIMIT_BYTES)
    except OSError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is unreadable",
            {"field": "model", "rule": "unavailable"},
        ) from None
    if len(data) > FILE_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "project manifest exceeds the limit",
            {"path": path, "rule": "size"},
        )
    return data


def _manifest_candidate_bytes(
    source: bytes, configuration: DebugConfiguration
) -> tuple[bytes, str]:
    """Return ``(candidate_bytes, status)`` changing only the debug pair.

    Parsing rejects duplicate keys so the editing route fails closed instead
    of silently collapsing competing values.  When the requested pair already
    equals the source values the exact source bytes are returned, preserving
    the owner's formatting.
    """
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not valid UTF-8",
            {"field": "$", "rule": "encoding"},
        ) from None
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not valid JSON",
            {"field": "$", "rule": "json"},
        ) from None
    except ValueError:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest has duplicate keys",
            {"field": "$", "rule": "duplicate"},
        ) from None
    if not isinstance(payload, dict):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest is not an object",
            {"field": "$", "rule": "type"},
        )
    debug = payload.get("debug")
    if debug is None:
        debug = {}
        payload["debug"] = debug
    if not isinstance(debug, dict):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project manifest debug section is not an object",
            {"field": "debug", "rule": "type"},
        )
    if (
        debug.get("backend") == configuration.backend
        and debug.get("target") == configuration.target
    ):
        return source, "unchanged"
    debug["backend"] = configuration.backend
    debug["target"] = configuration.target
    after = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    return after, "update"


def _validate_model(model: object) -> None:
    if type(model) is not ProjectModel:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "model is not a ProjectModel",
            {"field": "model", "rule": "type"},
        )
    if model.schema_version not in (2, 3):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "model schema version is not supported",
            {"field": "schemaVersion", "rule": "version"},
        )
    if not isinstance(model.project_root, Path):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project root must be a Path",
            {"field": "projectRoot", "rule": "type"},
        )
    if "\x00" in str(model.project_root):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project root is invalid",
            {"field": "projectRoot", "rule": "directory"},
        )
    try:
        canonical = model.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project root is unavailable",
            {"field": "projectRoot", "rule": "directory"},
        ) from None
    if not canonical.is_dir():
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "project root must be an existing directory",
            {"field": "projectRoot", "rule": "directory"},
        )


def _validate_generation_spec(model: ProjectModel) -> None:
    if type(model.generation.tool) is not str or model.generation.tool != "stm32-toolkit":
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "generation tool is not supported",
            {"field": "generation.tool", "rule": "value"},
        )
    if not is_supported_generation_producer(model.generation.tool, model.generation.version):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "generation version is not supported",
            {"field": "generation.version", "rule": "value"},
        )
    if model.generation.managed_manifest != MANAGED_MANIFEST_PATH:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "managed manifest path is not supported",
            {"field": "generation.managedManifest", "rule": "value"},
        )
    if model.generation.native_linker_script is not None and portable_path_error(
        model.generation.native_linker_script
    ) is not None:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "native linker script path is not supported",
            {"field": "generation.nativeLinkerScript", "rule": "withinProjectRoot"},
        )
    fragment = model.generation.linker_fragment
    if fragment is not None:
        if portable_path_error(fragment.path) is not None or "\\" in fragment.path:
            raise _raise_error(
                "LINKER_FRAGMENT_INVALID",
                "linker fragment path is not portable",
                {
                    "path": fragment.path,
                    "field": "generation.linkerFragment",
                    "rule": "path",
                    "remediation": BUILD_REMEDIATION,
                },
            )
        if model.generation.native_linker_script is not None:
            raise _raise_error(
                "LINKER_FRAGMENT_INVALID",
                "a linker fragment cannot be combined with a native linker script",
                {
                    "path": fragment.path,
                    "field": "generation.linkerFragment",
                    "rule": "nativeLinkerOwned",
                    "remediation": BUILD_REMEDIATION,
                },
            )
    runtime_initialization = model.generation.runtime_initialization
    if runtime_initialization not in (None, "cmsis-gcc-v1"):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "runtime initialization contract is not supported",
            {"field": "generation.runtimeInitialization", "rule": "value"},
        )
    if (
        runtime_initialization is not None
        and model.generation.native_linker_script is not None
    ):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "runtime initialization contract requires the managed linker template",
            {"field": "generation.runtimeInitialization", "rule": "managedLinker"},
        )
    if (
        model.memory.layout is not None
        and model.generation.native_linker_script is not None
    ):
        raise _raise_error(
            "MEMORY_LAYOUT_INVALID",
            "an explicit memory layout cannot be combined with a native linker script",
            {
                "field": "memory.layout",
                "rule": "nativeLinkerOwned",
                "remediation": (
                    "Remove memory.layout and keep the native linker script "
                    "user-owned, or remove generation.nativeLinkerScript so the "
                    "managed linker template owns the explicit layout."
                ),
            },
        )


def _validate_options(model: ProjectModel) -> dict[str, object]:
    core_flag = CORE_CPU_FLAGS.get(model.target.core)
    if core_flag is None:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "target core is not supported",
            {"field": "target.core", "rule": "unsupported"},
        )
    fpu = model.target.fpu
    float_abi = model.target.float_abi
    if (fpu is None) != (float_abi is None):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "FPU and float ABI must be both present or both absent",
            {"field": "target.fpu", "rule": "pairing"},
        )
    if fpu is not None:
        if not _FPU_RE.fullmatch(fpu):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "FPU value is not supported",
                {"field": "target.fpu", "rule": "format"},
            )
        if float_abi not in ("soft", "softfp", "hard"):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "float ABI is not supported",
                {"field": "target.floatAbi", "rule": "unsupported"},
            )
    for define in model.build.defines:
        if not _DEFINE_RE.fullmatch(define) or any(ch in define for ch in "\r\n\x00;"):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "build define is not supported",
                {"field": "build.defines", "rule": "define"},
            )
    for option in model.build.compile_options:
        if (
            not isinstance(option, str)
            or not option.startswith("-")
            or len(option) < 2
            or _OPTION_FORBIDDEN.search(option) is not None
            or "SHELL:" in option
        ):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "compile option is not supported",
                {"field": "build.compileOptions", "rule": "option"},
            )
    specs = model.build.newlib_specs
    if not isinstance(specs, tuple) or len(set(specs)) != len(specs):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "newlib specs are not supported",
            {"field": "build.newlibSpecs", "rule": "value"},
        )
    for spec in specs:
        if spec not in _SUPPORTED_NEWLIB_SPECS:
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "newlib spec is not supported",
                {"field": "build.newlibSpecs", "rule": "value"},
            )
    if tuple(model.build.presets) != ("arm-debug", "arm-release"):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "build presets are not supported",
            {"field": "build.presets", "rule": "presets"},
        )
    elf = model.build.elf
    if elf is None or portable_path_error(elf) is not None or not elf.startswith(
        "build/arm-debug/"
    ):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "ELF output path is not supported",
            {"field": "build.elf", "rule": "value"},
        )
    basename = elf[len("build/arm-debug/") :]
    if (
        not basename
        or "/" in basename
        or "\\" in basename
        or not basename.endswith(".elf")
        or len(basename) <= len(".elf")
    ):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "ELF output path is not supported",
            {"field": "build.elf", "rule": "value"},
        )
    # A fully absent debug spec is a valid build-only configuration; it
    # never blocks configuration and never guesses a debug backend or
    # target.  A partially specified or unsupported debug spec still fails
    # closed with the accepted error.
    if (model.debug.backend is None) != (model.debug.target is None):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "debug backend or target is not supported",
            {"field": "debug.backend", "rule": "value"},
        )
    if model.debug.backend is not None and (
        model.debug.backend != "pyocd" or not model.debug.target
    ):
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "debug backend or target is not supported",
            {"field": "debug.backend", "rule": "value"},
        )
    return {
        "cpu_flag": core_flag,
        "fpu_flag": "-mfpu=" + fpu if fpu is not None else None,
        "float_abi_flag": "-mfloat-abi=" + float_abi if float_abi is not None else None,
    }


def _validate_memory(model: ProjectModel) -> None:
    for field, value, minimum in (
        ("stackSize", model.memory.stack_size, 1),
        ("heapSize", model.memory.heap_size, 0),
    ):
        if value is None:
            continue
        if (
            type(value) is not int
            or value < minimum
            or value > 0xFFFFFFFF
            or value % 8 != 0
        ):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "memory size is not supported",
                {"field": f"memory.{field}", "rule": "size"},
            )
    regions = model.memory.regions
    executable: list[str] = []
    writable: list[str] = []
    previous: tuple[int, int] | None = None
    ordered = sorted(regions, key=lambda region: (region.origin, region.length))
    for region in ordered:
        if _REGION_NAME_RE.fullmatch(region.name) is None:
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "memory region name is not supported",
                {"field": "memory.regions", "rule": "name"},
            )
        if (
            isinstance(region.origin, bool)
            or not isinstance(region.origin, int)
            or isinstance(region.length, bool)
            or not isinstance(region.length, int)
            or region.origin < 0
            or region.length < 1
            or region.origin + region.length > 0x100000000
        ):
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "memory region range is not supported",
                {"field": "memory.regions", "rule": "range"},
            )
        if previous is not None and previous[0] + previous[1] > region.origin:
            raise _raise_error(
                "GENERATION_MODEL_INVALID",
                "memory regions must not overlap",
                {"field": "memory.regions", "rule": "overlap"},
            )
        previous = (region.origin, region.length)
        if "x" in region.attributes:
            executable.append(region.name)
        if "w" in region.attributes:
            writable.append(region.name)
    if not executable:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "at least one executable memory region is required",
            {"field": "memory.regions", "rule": "executable"},
        )
    if not writable:
        raise _raise_error(
            "GENERATION_MODEL_INVALID",
            "at least one writable memory region is required",
            {"field": "memory.regions", "rule": "writable"},
        )
    if model.memory.layout is not None:
        try:
            validate_memory_layout_regions(model.memory.layout, model.memory.regions)
        except MemoryLayoutError as error:
            raise _raise_error(error.code, error.message, error.details) from None


def _memory_layout_resolution(model: ProjectModel) -> MemoryLayoutResolution:
    """Resolve the explicit or unambiguous implicit managed section layout."""
    resolution = resolve_memory_layout(
        model.memory.regions,
        model.memory.layout,
        extra_region_names=model.memory.extra_region_names,
    )
    if resolution.requires_selection:
        raise _raise_error(
            "MEMORY_LAYOUT_REQUIRED",
            "an explicit memory layout is required for multiple managed memory roles",
            resolution.blocker_details(),
        )
    assert resolution.layout is not None
    return resolution


def _resolve_contained(absolute: Path, root: Path, path: str) -> Path:
    """Resolve redirects; the canonical target must stay inside the root."""
    try:
        resolved = absolute.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "path resolution failed",
            {"path": path, "rule": "withinProjectRoot"},
        ) from None
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "path escapes the canonical project root",
            {"path": path, "rule": "withinProjectRoot"},
        ) from None
    return resolved


def _read_limited(abs_path: Path, limit: int) -> bytes:
    with abs_path.open("rb") as handle:
        return handle.read(limit + 1)


def _read_conversion_report(root: Path) -> tuple[dict[str, object] | None, str | None]:
    """Read and pre-validate the optional conversion report (work order 7.3)."""
    path = _CONVERSION_REPORT_PATH
    absolute = root.joinpath(*path.split("/"))
    try:
        resolved = _resolve_contained(absolute, root, path)
        lst = os.lstat(resolved)
    except FileNotFoundError:
        return None, None
    except NotADirectoryError:
        return None, None
    except GenerationError:
        raise
    except OSError:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report inspection failed",
            {"path": path, "rule": "regularFile"},
        ) from None
    if not stat.S_ISREG(lst.st_mode):
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report is not a regular file",
            {"path": path, "rule": "regularFile"},
        )
    try:
        data = _read_limited(resolved, FILE_LIMIT_BYTES)
    except OSError:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report is unreadable",
            {"path": path, "rule": "unreadable"},
        ) from None
    if len(data) > FILE_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report exceeds the limit",
            {"path": path, "rule": "size"},
        )
    return _decode_conversion_report(data, path), sha256_hex(data)


def _decode_conversion_report(data: bytes, path: str) -> dict[str, object]:
    """Decode one exact report byte image (no filesystem access)."""
    try:
        text = data.decode("utf-8")
        report = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except UnicodeDecodeError:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report is not valid UTF-8",
            {"path": path, "rule": "encoding"},
        ) from None
    except ValueError:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report is not valid JSON",
            {"path": path, "rule": "json"},
        ) from None
    if not isinstance(report, dict):
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report is not an object",
            {"path": path, "rule": "type"},
        )
    return report


def _validate_fixed_sections(
    report: dict[str, object] | None, model: ProjectModel
) -> tuple[tuple[str, int, str], ...]:
    """Validate fixed-section evidence into deterministic linker placements.

    Returns ``(section, address, region_name)`` triples sorted by address.
    """
    if report is None:
        return ()
    path = _CONVERSION_REPORT_PATH
    schema_version = report.get("schemaVersion")
    if schema_version == 1:
        # Schema 1 stays exactly as before: an explicit Git HEAD is required.
        if sha256_error(report.get("planId")) is not None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report plan id is invalid",
                {"path": path, "rule": "planId"},
            )
        if not isinstance(report.get("gitHead"), str) or _FULL_SHA_RE.fullmatch(
            report["gitHead"]
        ) is None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report git head is invalid",
                {"path": path, "rule": "gitHead"},
            )
    elif schema_version == 2:
        # Schema 2 identifies the source by content snapshot, never by Git.
        # Git evidence may be attached as optional metadata but is not required
        # and is never inferred.
        if sha256_error(report.get("planId")) is not None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report plan id is invalid",
                {"path": path, "rule": "planId"},
            )
        if sha256_error(report.get("sourceSnapshotSha256")) is not None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report source snapshot is invalid",
                {"path": path, "rule": "sourceSnapshotSha256"},
            )
        if "gitHead" in report and (
            not isinstance(report["gitHead"], str)
            or _FULL_SHA_RE.fullmatch(report["gitHead"]) is None
        ):
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report git head is invalid",
                {"path": path, "rule": "gitHead"},
            )
        _validate_report_extra_regions(report, model)
    else:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report schema is not supported",
            {"path": path, "rule": "schemaVersion"},
        )
    sections_value = report.get("fixedSections")
    if not isinstance(sections_value, list):
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report fixedSections is invalid",
            {"path": path, "rule": "type"},
        )
    entries: list[tuple[str, int, str, int, str]] = []
    for item in sections_value:
        if not isinstance(item, dict):
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section entry is invalid",
                {"path": path, "rule": "type"},
            )
        if set(item) != {"section", "address", "sourcePath", "line", "symbol"}:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section entry is invalid",
                {"path": path, "rule": "key"},
            )
        address = item["address"]
        if isinstance(address, bool) or not isinstance(address, int):
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section address is invalid",
                {"path": path, "rule": "address"},
            )
        if not 0 <= address <= 0xFFFFFFFF:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section address is invalid",
                {"path": path, "rule": "address"},
            )
        section = item["section"]
        if section != ".stm32tk.abs.%08x" % address:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section name is invalid",
                {"path": path, "rule": "section"},
            )
        source_path = item["sourcePath"]
        if source_path not in model.build.sources:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section source is not declared",
                {"path": path, "rule": "source"},
            )
        line = item["line"]
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section line is invalid",
                {"path": path, "rule": "line"},
            )
        symbol = item["symbol"]
        if not isinstance(symbol, str) or _C_IDENTIFIER_RE.fullmatch(symbol) is None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section symbol is invalid",
                {"path": path, "rule": "symbol"},
            )
        entries.append((section, address, source_path, line, symbol))
    unique: list[tuple[str, int, str, int, str]] = list(dict.fromkeys(entries))
    placements: dict[tuple[str, int], tuple[str, int, str]] = {}
    symbols: dict[str, int] = {}
    for section, address, source_path, line, symbol in unique:
        key = (section, address)
        prior = placements.get(key)
        if prior is not None and prior != (source_path, line, symbol):
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section evidence conflicts",
                {"path": path, "rule": "conflict"},
            )
        if symbols.get(symbol, address) != address:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section evidence conflicts",
                {"path": path, "rule": "conflict"},
            )
        placements[key] = (source_path, line, symbol)
        symbols[symbol] = address
    result: list[tuple[str, int, str]] = []
    for section, address, _source_path, _line, _symbol in unique:
        region = _region_for_address(model, address)
        if region is None:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "fixed section address is outside every memory region",
                {"path": path, "rule": "region"},
            )
        result.append((section, address, region))
    result.sort(key=lambda entry: entry[1])
    return tuple(result)


def _validate_report_extra_regions(
    report: dict[str, object], model: ProjectModel
) -> None:
    """Require Schema 2 extra-region evidence to match the explicit model memory.

    The model's ``memory.regions`` already contains the normalized base-plus-
    extra map, so fixed sections are checked against the same regions configure
    renders.  This adds the provenance check: the report cannot omit, add, or
    silently alter an explicit extra region.
    """
    path = _CONVERSION_REPORT_PATH
    expected = {
        region.name: (region.origin, region.length, region.attributes)
        for region in model.memory.regions
        if region.name in model.memory.extra_region_names
    }
    value = report.get("extraRegions")
    if value is None:
        if expected:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report omits explicit extra regions",
                {"path": path, "rule": "extraRegions"},
            )
        return
    if not isinstance(value, list):
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report extraRegions is invalid",
            {"path": path, "rule": "extraRegions"},
        )
    seen: dict[str, tuple[int, int, str]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "name",
            "origin",
            "length",
            "attributes",
        }:
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report extra region entry is invalid",
                {"path": path, "rule": "extraRegions"},
            )
        name = item["name"]
        origin = item["origin"]
        length = item["length"]
        attributes = item["attributes"]
        if (
            not isinstance(name, str)
            or isinstance(origin, bool)
            or not isinstance(origin, int)
            or isinstance(length, bool)
            or not isinstance(length, int)
            or not isinstance(attributes, str)
            or name in seen
        ):
            raise _raise_error(
                "GENERATION_FIXED_SECTION_INVALID",
                "conversion report extra region entry is invalid",
                {"path": path, "rule": "extraRegions"},
            )
        seen[name] = (origin, length, attributes)
    if seen != expected:
        raise _raise_error(
            "GENERATION_FIXED_SECTION_INVALID",
            "conversion report extra regions do not match the project memory",
            {"path": path, "rule": "extraRegions"},
        )


def _region_for_address(model: ProjectModel, address: int) -> str | None:
    for region in model.memory.regions:
        if region.origin <= address < region.origin + region.length:
            return region.name
    return None


def _read_prior_manifest(root: Path) -> bytes | None:
    """Read the optional prior managed manifest (bounded), or ``None``."""
    path = MANAGED_MANIFEST_PATH
    absolute = root.joinpath(*path.split("/"))
    try:
        resolved = _resolve_contained(absolute, root, path)
        lst = os.lstat(resolved)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None
    except GenerationError:
        raise
    except OSError:
        raise _raise_error(
            "GENERATION_MANIFEST_INVALID",
            "managed manifest inspection failed",
            {"path": path, "rule": "unreadable"},
        ) from None
    if not stat.S_ISREG(lst.st_mode):
        raise _raise_error(
            "GENERATION_MANIFEST_INVALID",
            "managed manifest is not a regular file",
            {"path": path, "rule": "regularFile"},
        )
    try:
        data = _read_limited(resolved, FILE_LIMIT_BYTES)
    except OSError:
        raise _raise_error(
            "GENERATION_MANIFEST_INVALID",
            "managed manifest is unreadable",
            {"path": path, "rule": "unreadable"},
        ) from None
    if len(data) > FILE_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_MANIFEST_INVALID",
            "managed manifest exceeds the limit",
            {"path": path, "rule": "size"},
        )
    return data


def _collect_inputs(
    root: Path,
    model: ProjectModel,
    prior_data: bytes | None,
    report_sha: str | None,
) -> list[GenerationInput]:
    """State-validate includes, then read every hashed input exactly once."""
    include_paths = list(model.build.include_paths)
    all_paths = [
        _STM32_PROJECT_MANIFEST,
        *model.build.sources,
        *model.build.assembly_sources,
    ]
    if model.debug.svd is not None:
        all_paths.append(model.debug.svd)
    if model.generation.cube_mx_ioc is not None:
        all_paths.append(model.generation.cube_mx_ioc)
    if model.generation.native_linker_script is not None:
        all_paths.append(model.generation.native_linker_script)
    fragment = model.generation.linker_fragment
    if fragment is not None:
        all_paths.append(fragment.path)
    if prior_data is not None:
        all_paths.append(MANAGED_MANIFEST_PATH)
    if report_sha is not None:
        all_paths.append(_CONVERSION_REPORT_PATH)

    for path in all_paths + include_paths:
        if portable_path_error(path) is not None:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input path is not portable",
                {"path": path, "rule": "withinProjectRoot"},
            )
        if path == model.generation.native_linker_script or (
            fragment is not None and path == fragment.path
        ):
            inspect_path = root.joinpath(*path.split("/"))
            try:
                inspect_lstat = os.lstat(inspect_path)
            except FileNotFoundError:
                continue
            except OSError:
                raise _raise_error(
                    "GENERATION_INPUT_INVALID",
                    "linker input inspection failed",
                    {"path": path, "rule": "unreadable"},
                ) from None
            if (
                stat.S_ISLNK(inspect_lstat.st_mode)
                or bool(getattr(inspect_lstat, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
            ):
                raise _raise_error(
                    "GENERATION_INPUT_INVALID",
                    "linker input must not redirect",
                    {"path": path, "rule": "redirect"},
                )
    duplicate = _duplicate_or_casefold(all_paths)
    if duplicate is not None:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "input paths are not unique",
            {"path": duplicate, "rule": "duplicate"},
        )
    if _casefold_collides_with_targets(all_paths):
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "input path collides with a generated target",
            {"path": next(
                p for p in all_paths if _target_casefold_collision(p)
            ), "rule": "casefoldCollision"},
        )

    for include in include_paths:
        absolute = _resolve_contained(root.joinpath(*include.split("/")), root, include)
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "include directory is missing",
                {"path": include, "rule": "directory"},
            ) from None
        except NotADirectoryError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "include directory is missing",
                {"path": include, "rule": "directory"},
            ) from None
        except OSError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "include directory inspection failed",
                {"path": include, "rule": "directory"},
            ) from None
        if not stat.S_ISDIR(lst.st_mode):
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "include path is not a directory",
                {"path": include, "rule": "directory"},
            )

    inputs: list[GenerationInput] = []
    total = 0
    for path in all_paths:
        absolute = _resolve_contained(root.joinpath(*path.split("/")), root, path)
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input is missing",
                {"path": path, "rule": "missing"},
            ) from None
        except NotADirectoryError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input is missing",
                {"path": path, "rule": "missing"},
            ) from None
        except OSError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input inspection failed",
                {"path": path, "rule": "unreadable"},
            ) from None
        if not stat.S_ISREG(lst.st_mode):
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input is not a regular file",
                {"path": path, "rule": "regularFile"},
            )
        try:
            data = _read_limited(absolute, FILE_LIMIT_BYTES)
        except OSError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input is unreadable",
                {"path": path, "rule": "unreadable"},
            ) from None
        if len(data) > FILE_LIMIT_BYTES:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "input exceeds the per-file limit",
                {"path": path, "rule": "size"},
            )
        total += len(data)
        if total > AGGREGATE_LIMIT_BYTES:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "aggregate input size exceeds the limit",
                {"path": path, "rule": "aggregateSize"},
            )
        digest = sha256_hex(data)
        if fragment is not None and path == fragment.path and digest != fragment.sha256:
            # The model parsed one exact byte image.  A second read that does
            # not match it is a race, not a new fragment to render.
            raise _raise_error(
                "LINKER_FRAGMENT_INVALID",
                "linker fragment changed while configuration was planning",
                {
                    "path": path,
                    "field": "generation.linkerFragment",
                    "rule": "changed",
                    "remediation": BUILD_REMEDIATION,
                },
            )
        inputs.append(GenerationInput(path=path, sha256=digest, size=len(data)))
    inputs.sort(key=lambda entry: portable_sort_key(entry.path))
    return inputs


def _duplicate_or_casefold(paths: list[str]) -> str | None:
    seen: dict[str, str] = {}
    for path in paths:
        folded = path.casefold()
        prior = seen.get(folded)
        if prior is not None:
            return path
        seen[folded] = path
    return None


def _target_casefold_collision(path: str) -> bool:
    folded = path.casefold()
    return any(folded == target.casefold() for target in GENERATED_TARGETS)


def _casefold_collides_with_targets(paths: list[str]) -> bool:
    return any(_target_casefold_collision(path) for path in paths)


def _render_targets(
    model: ProjectModel,
    options: dict[str, object],
    fixed_sections: tuple[tuple[str, int, str], ...],
    layout: MemoryLayoutResolution | None,
    vscode_configuration: VSCodeConfiguration | None = None,
) -> dict[str, tuple[str, bytes]]:
    contexts = _build_contexts(
        model, options, fixed_sections, layout, vscode_configuration
    )
    rendered: dict[str, tuple[str, bytes]] = {}
    for target in _targets_for_model(model):
        template_name = _target_template(target)
        if template_name.endswith(".j2"):
            data = _render_template(template_name, contexts[target])
        else:
            data = _render_template(template_name, {})
        rendered[target] = (template_name, data)
    return rendered


def _target_template(target: str) -> str:
    return TARGET_TEMPLATES[target]


def _targets_for_model(model: ProjectModel) -> tuple[str, ...]:
    """Return the generated Toolkit targets for generic or native output."""
    if model.generation.native_linker_script is None:
        return GENERATED_TARGETS
    return tuple(target for target in GENERATED_TARGETS if target != "linker/stm32tk.ld")


def _normalize_gnu_ld_attributes(attrs: str) -> str:
    """Normalize memory region attributes for GNU ld compatibility.

    Schema v2 model values are r--, rw-, r-x, rwx; GNU ld MEMORY flags
    reject hyphens (ARM GNU ld 2.44: "invalid character %c (45) in flags")
    and expect r, rw, rx, rwx.  The model enum values are never modified;
    this is a deterministic rendering-time mapping only.
    """
    return attrs.replace("-", "")


def _vscode_tasks_context(toolkit_command: str) -> dict[str, object]:
    """Render five independent ``process`` tasks with explicit project binding.

    Every task uses argv (never a shell string), the bound project root and
    ``cwd``, and no dependency/auto-run/group.  Build tasks call the existing
    build CLI contract.  Hardware tasks call the narrow ``ide task`` adapter and
    take the data root, session, probe and one-shot confirmation from prompts;
    nothing is persisted and the confirmation prompt defaults to ``deny``.
    Hardware prompts use ``runOptions.reevaluateOnRerun`` so a rerun always
    re-prompts instead of reusing the previous input.
    """
    project = "${workspaceFolder}"
    reevaluate = {"reevaluateOnRerun": True}

    def hardware_task(
        label: str,
        action: str,
        confirmation_input: str,
        prompt: str,
        *,
        ticket_input: str | None = None,
    ) -> dict[str, object]:
        args = [
            "--project-root",
            project,
            "ide",
            "task",
            action,
            "--data-root",
            "${input:stm32tkDataRoot}",
            "--session-id",
            "${input:stm32tkSessionId}",
            "--probe",
            "${input:stm32tkProbeId}",
        ]
        if ticket_input is not None:
            args.extend(["--ticket", "${input:" + ticket_input + "}"])
        args.extend(["--confirmation", "${input:" + confirmation_input + "}", "--json"])
        return {
            "label": label,
            "detail": prompt,
            "type": "process",
            "command": toolkit_command,
            "args": args,
            "options": {"cwd": project},
            "problemMatcher": [],
            "runOptions": dict(reevaluate),
        }

    tasks = [
        {
            "label": "STM32 Toolkit: Build Debug",
            "type": "process",
            "command": toolkit_command,
            "args": [
                "--project-root",
                project,
                "build",
                "--preset",
                "arm-debug",
                "--json",
            ],
            "options": {"cwd": project},
            "problemMatcher": [],
        },
        {
            "label": "STM32 Toolkit: Build Release",
            "type": "process",
            "command": toolkit_command,
            "args": [
                "--project-root",
                project,
                "build",
                "--preset",
                "arm-release",
                "--json",
            ],
            "options": {"cwd": project},
            "problemMatcher": [],
        },
        hardware_task(
            "STM32 Toolkit: Flash Debug",
            "flash",
            "stm32tkFlashConfirmation",
            "Flash Debug: program the current managed arm-debug build on the named probe.",
        ),
        hardware_task(
            "STM32 Toolkit: Handoff Begin Debug",
            "handoff-begin",
            "stm32tkHandoffBeginConfirmation",
            "Handoff Begin Debug: enter one debug handoff on the named probe.",
        ),
        hardware_task(
            "STM32 Toolkit: Handoff End Debug",
            "handoff-end",
            "stm32tkHandoffEndConfirmation",
            "Handoff End Debug: release the handoff using its original ticket.",
            ticket_input="stm32tkHandoffTicket",
        ),
    ]
    inputs = [
        {
            "id": "stm32tkDataRoot",
            "type": "promptString",
            "description": "Absolute machine-owned Toolkit data root outside this project (for example C:/data/stm32-toolkit).",
        },
        {
            "id": "stm32tkSessionId",
            "type": "promptString",
            "description": "Session id for this probe workspace: lowercase letters, digits, '-' or '_'.",
        },
        {
            "id": "stm32tkProbeId",
            "type": "promptString",
            "description": "Exact probeId from the separate read-only probe list; never guessed.",
        },
        {
            "id": "stm32tkFlashConfirmation",
            "type": "promptString",
            "description": "Flash Debug: type authorize for ONE explicit invocation; any other value (default deny) refuses.",
            "default": "deny",
        },
        {
            "id": "stm32tkHandoffBeginConfirmation",
            "type": "promptString",
            "description": "Handoff Begin Debug: type authorize for ONE explicit invocation; any other value (default deny) refuses.",
            "default": "deny",
        },
        {
            "id": "stm32tkHandoffTicket",
            "type": "promptString",
            "description": "Handoff End Debug: the original 64-character ticket returned by handoff-begin; it is never stored for you.",
        },
        {
            "id": "stm32tkHandoffEndConfirmation",
            "type": "promptString",
            "description": "Handoff End Debug: type authorize for ONE explicit reclaim invocation; any other value (default deny) refuses.",
            "default": "deny",
        },
    ]
    return {"tasks": {"version": "2.0.0", "tasks": tasks, "inputs": inputs}}


def _build_contexts(
    model: ProjectModel,
    options: dict[str, object],
    fixed_sections: tuple[tuple[str, int, str], ...],
    layout: MemoryLayoutResolution | None,
    vscode_configuration: VSCodeConfiguration | None = None,
) -> dict[str, dict[str, object]]:
    project_name = sanitize_cmake_identifier(model.project.name)
    basename = model.build.elf[len("build/arm-debug/") :]
    stem = basename[: -len(".elf")]
    target_name = sanitize_cmake_identifier(stem)
    # Deterministic defaults are explicit user-scope VS Code settings: host
    # discovery never freezes the coordinator's machine paths into the project.
    # An explicitly supplied pair renders its exact validated absolute paths.
    if vscode_configuration is None:
        toolkit_command = "${config:stm32-toolkit.executablePath}"
        compiler_path = "${config:stm32-toolkit.compilerPath}"
    else:
        toolkit_command = vscode_configuration.toolkit_path
        compiler_path = vscode_configuration.gcc_path
    if layout is not None and layout.layout is not None:
        roles = layout.layout
        flash_region = roles.flash
        data_region = roles.data
        bss_region = roles.bss
        heap_region = roles.heap
        stack_region = roles.stack
    else:
        flash_region = data_region = bss_region = heap_region = stack_region = None
    cmake = {
        "project_name": project_name,
        "target_name": target_name,
        "cpu_flag": options["cpu_flag"],
        "fpu_flag": options.get("fpu_flag"),
        "float_abi_flag": options.get("float_abi_flag"),
        "sources": [_cmake_quote(source) for source in model.build.sources],
        "assembly_sources": [
            _cmake_quote(source) for source in model.build.assembly_sources
        ],
        "includes": [_cmake_quote(include) for include in model.build.include_paths],
        "defines": list(model.build.defines),
        "compile_options": list(model.build.compile_options),
        "link_standard_math": model.build.link_standard_math,
        "newlib_specs": list(model.build.newlib_specs),
        "map_name": f"{stem}.map",
        "hex_name": f"{stem}.hex",
        "bin_name": f"{stem}.bin",
        "native_linker_script": model.generation.native_linker_script,
        # The conditional LINK_DEPENDS route exists only when a fragment
        # contributes to the merged managed linker; no-option bytes stay as
        # they were.
        "linker_fragment": (
            model.generation.linker_fragment.path
            if model.generation.linker_fragment is not None
            else None
        ),
    }
    linker = {
        "regions": [
            {
                "name": region.name,
                "attributes": _normalize_gnu_ld_attributes(region.attributes),
                "origin_hex": "0x%08x" % region.origin,
                "length_hex": "0x%08x" % region.length,
            }
            for region in model.memory.regions
        ],
        "heap_size_literal": (
            "0x%x" % model.memory.heap_size
            if model.memory.heap_size is not None
            else "4K"
        ),
        "stack_size_literal": (
            "0x%x" % model.memory.stack_size
            if model.memory.stack_size is not None
            else "1K"
        ),
        "runtime_initialization": model.generation.runtime_initialization
        == "cmsis-gcc-v1",
        "flash_region": flash_region,
        "data_region": data_region,
        "bss_region": bss_region,
        "heap_region": heap_region,
        "stack_region": stack_region,
        "fixed_sections": [
            {
                "name": section,
                "address_hex": "0x%08x" % address,
                "region": region,
            }
            for section, address, region in fixed_sections
        ],
        "fragment_sections": [
            {
                "name": section.name,
                "address_hex": (
                    None
                    if section.address is None
                    else "0x%08x" % section.address
                ),
                "region": section.region,
                "statement_lines": section.statement_lines(),
            }
            for section in (
                model.generation.linker_fragment.sections
                if model.generation.linker_fragment is not None
                else ()
            )
        ],
    }
    presets = {
        "presets": {
            "version": 3,
            "cmakeMinimumRequired": {"major": 3, "minor": 22, "patch": 0},
            "configurePresets": [
                {
                    "name": "arm-debug",
                    "displayName": "ARM Debug",
                    "generator": "Ninja",
                    "binaryDir": "${sourceDir}/build/arm-debug",
                    "toolchainFile": "${sourceDir}/cmake/arm-none-eabi-gcc.cmake",
                    "cacheVariables": {"CMAKE_BUILD_TYPE": "Debug"},
                },
                {
                    "name": "arm-release",
                    "displayName": "ARM Release",
                    "generator": "Ninja",
                    "binaryDir": "${sourceDir}/build/arm-release",
                    "toolchainFile": "${sourceDir}/cmake/arm-none-eabi-gcc.cmake",
                    "cacheVariables": {"CMAKE_BUILD_TYPE": "Release"},
                },
            ],
            "buildPresets": [
                {"name": "arm-debug", "configurePreset": "arm-debug"},
                {"name": "arm-release", "configurePreset": "arm-release"},
            ],
        }
    }
    tasks = _vscode_tasks_context(toolkit_command)
    # A live Cortex-Debug identity is available only after an authorized
    # handoff. Static generation therefore leaves launch configuration empty.
    launch = {
        "launch": {
            "version": "0.2.0",
            "configurations": [],
        }
    }
    c_cpp = {
        "c_cpp": {
            "version": 4,
            "configurations": [
                {
                    "name": "arm-debug",
                    "compilerPath": compiler_path,
                    "includePath": [
                        "${workspaceFolder}/" + include
                        for include in model.build.include_paths
                    ],
                    "defines": list(model.build.defines),
                    "intelliSenseMode": "gcc-arm",
                    "cStandard": "c11",
                    "cppStandard": "c++17",
                }
            ],
        }
    }
    settings = {"settings": {"cmake.configureOnOpen": False, "cmake.useCMakePresets": "always"}}
    contexts = {
        "CMakeLists.txt": cmake,
        "cmake/arm-none-eabi-gcc.cmake": {},
        "CMakePresets.json": presets,
        "linker/stm32tk.ld": linker,
        ".vscode/tasks.json": tasks,
        ".vscode/launch.json": launch,
        ".vscode/c_cpp_properties.json": c_cpp,
        ".vscode/settings.json": settings,
        ".vscode/extensions.json": {},
    }
    if model.generation.native_linker_script is not None:
        contexts.pop("linker/stm32tk.ld")
    return contexts


def _load_template_resource(name: str) -> bytes:
    parts = name.split("/")
    if len(parts) != 2 or parts[0] not in ("cmake", "vscode"):
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "template path is invalid",
            {"template": name, "rule": "missing"},
        )
    try:
        data = (
            importlib.resources.files("stm32_toolkit")
            .joinpath("templates", parts[0], parts[1])
            .read_bytes()
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "template resource is missing",
            {"template": name, "rule": "missing"},
        ) from None
    if len(data) > TEMPLATE_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "template resource exceeds the limit",
            {"template": name, "rule": "oversized"},
        )
    return data


def _render_template(name: str, context: dict[str, object]) -> bytes:
    data = _load_template_resource(name)
    if name.endswith(".j2"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise _raise_error(
                "GENERATION_TEMPLATE_INVALID",
                "template encoding is invalid",
                {"template": name, "rule": "encoding"},
            ) from None
        template = _ENV.from_string(text)
        try:
            rendered = template.render(**context)
        except UndefinedError:
            raise _raise_error(
                "GENERATION_TEMPLATE_INVALID",
                "template references undefined values",
                {"template": name, "rule": "undefined"},
            ) from None
        output = rendered.encode("utf-8")
    else:
        output = data
    output = output.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    output = output.rstrip(b"\n") + b"\n"
    if len(output) > GENERATED_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_TEMPLATE_INVALID",
            "rendered file exceeds the limit",
            {"template": name, "rule": "oversized"},
        )
    return output


def _classify_targets(
    root: Path,
    rendered: dict[str, tuple[str, bytes]],
    prior: tuple[ManagedFileRecord, ...],
) -> list[GeneratedFile]:
    prior_by_path = {record.path: record for record in prior}
    files: list[GeneratedFile] = []
    for target in sorted(rendered, key=portable_sort_key):
        template_name, after_bytes = rendered[target]
        after_sha256 = sha256_hex(after_bytes)
        prior_record = prior_by_path.get(target)
        if target in PRESERVABLE_EDITOR_TARGETS:
            editor_exists = _editor_target_exists(root, target)
            if editor_exists and prior_record is None:
                # The user's editor bytes are never opened, hashed, or adopted.
                # The rendered template is only candidate metadata for the plan.
                files.append(
                    GeneratedFile(
                        path=target,
                        status="preserved-unowned",
                        template_name=template_name,
                        template_version=TEMPLATE_VERSION,
                        before_sha256=None,
                        after_sha256=after_sha256,
                        before_size=None,
                        after_size=len(after_bytes),
                        unified_diff="",
                        before_bytes=None,
                        after_bytes=after_bytes,
                    )
                )
                continue
        current = _read_current_target(root, target)
        if prior_record is None:
            if current is None:
                status = "create"
            else:
                status = "unowned-collision"
        elif current is None:
            status = "update-managed"
        elif sha256_hex(current) == after_sha256:
            status = "unchanged"
        elif sha256_hex(current) == prior_record.sha256:
            status = "update-managed"
        else:
            status = "user-drift"
        before_text = "" if current is None else current.decode("utf-8", "replace")
        after_text = after_bytes.decode("utf-8", "replace")
        files.append(
            GeneratedFile(
                path=target,
                status=status,
                template_name=template_name,
                template_version=TEMPLATE_VERSION,
                before_sha256=None if current is None else sha256_hex(current),
                after_sha256=after_sha256,
                before_size=None if current is None else len(current),
                after_size=len(after_bytes),
                unified_diff=unified_diff(target, before_text, after_text),
                before_bytes=current,
                after_bytes=after_bytes,
            )
        )
    files.sort(key=lambda entry: portable_sort_key(entry.path))
    return files


def _editor_target_exists(root: Path, target: str) -> bool:
    """Classify a fixed editor path by metadata only, without following links."""
    parts = target.split("/")
    for index in range(1, len(parts) + 1):
        component = root.joinpath(*parts[:index])
        try:
            state = os.lstat(component)
        except FileNotFoundError:
            return False
        except NotADirectoryError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "editor target parent is not a directory",
                {"path": target, "rule": "directory"},
            ) from None
        except OSError:
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "editor target inspection failed",
                {"path": target, "rule": "unreadable"},
            ) from None
        if stat.S_ISLNK(state.st_mode) or bool(
            getattr(state, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "editor target must not redirect",
                {"path": target, "rule": "redirect"},
            )
        terminal = index == len(parts)
        if terminal and not stat.S_ISREG(state.st_mode):
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "editor target is not a regular file",
                {"path": target, "rule": "regularFile"},
            )
        if not terminal and not stat.S_ISDIR(state.st_mode):
            raise _raise_error(
                "GENERATION_INPUT_INVALID",
                "editor target parent is not a directory",
                {"path": target, "rule": "directory"},
            )
    return True


def _read_current_target(root: Path, target: str) -> bytes | None:
    absolute = root.joinpath(*target.split("/"))
    try:
        resolved = _resolve_contained(absolute, root, target)
    except GenerationError:
        raise _raise_error(
            "GENERATION_PATH_INVALID",
            "target path escapes the canonical project root",
            {"path": target, "rule": "withinProjectRoot"},
        ) from None
    try:
        lst = os.lstat(resolved)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None
    except GenerationError:
        raise
    except OSError:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "target inspection failed",
            {"path": target, "rule": "unreadable"},
        ) from None
    if not stat.S_ISREG(lst.st_mode):
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "target is not a regular file",
            {"path": target, "rule": "regularFile"},
        )
    try:
        data = _read_limited(resolved, FILE_LIMIT_BYTES)
    except OSError:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "target is unreadable",
            {"path": target, "rule": "unreadable"},
        ) from None
    if len(data) > FILE_LIMIT_BYTES:
        raise _raise_error(
            "GENERATION_INPUT_INVALID",
            "target exceeds the limit",
            {"path": target, "rule": "size"},
        )
    return data


def _collect_blockers(
    prior: tuple[ManagedFileRecord, ...], files: list[GeneratedFile]
) -> list[GenerationBlocker]:
    blockers: list[GenerationBlocker] = []
    target_set = {entry.path for entry in files}
    for entry in files:
        if entry.status == "user-drift":
            blockers.append(
                GenerationBlocker(
                    "GENERATED_FILE_DRIFT",
                    entry.path,
                    "managed file was modified outside the toolkit",
                )
            )
        elif entry.status == "unowned-collision":
            blockers.append(
                GenerationBlocker(
                    "UNOWNED_COLLISION",
                    entry.path,
                    "an unowned file occupies a generated path",
                )
            )
    for record in prior:
        if record.path not in target_set:
            blockers.append(
                GenerationBlocker(
                    "GENERATION_ORPHANED_MANAGED_FILE",
                    record.path,
                    "a previously managed file is no longer generated",
                )
            )
    blockers.sort(key=lambda blocker: (portable_sort_key(blocker.path), blocker.code))
    return blockers


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def apply_project_configuration(plan: GenerationPlan) -> OperationResult[dict[str, object]]:
    """Apply the accepted plan atomically, or fail without partial writes."""
    try:
        _validate_plan(plan)
        _canonical_root(plan.project_root)
        from stm32_toolkit.project_upgrade import project_mutation_lock
        with project_mutation_lock(plan.project_root):
            data = _apply(plan)
    except _ApplyFailure as failure:
        return OperationResult.failure(
            "project-configuration-apply",
            failure.code,
            failure.message,
            failure.details,
        )
    except GenerationError as error:
        return OperationResult.failure(
            "project-configuration-apply",
            error.code,
            error.message,
            error.details,
        )
    except (OSError, ProjectMutationLockError):
        return OperationResult.failure(
            "project-configuration-apply",
            "GENERATION_APPLY_FAILED",
            "apply failed",
            {"phase": "projectMutationLock"},
        )
    return OperationResult.success("project-configuration-apply", data)


def _validate_plan(plan: object) -> None:
    """Full structural and digest validation of the supplied plan."""
    if type(plan) is not GenerationPlan:
        raise _plan_invalid("type")
    if not isinstance(plan.plan_version, int) or plan.plan_version != PLAN_VERSION:
        raise _plan_invalid("planVersion")
    if not isinstance(plan.project_root, Path):
        raise _plan_invalid("type")
    if type(plan.model) is not ProjectModel:
        raise _plan_invalid("type")
    if sha256_error(plan.plan_id) is not None:
        raise _plan_invalid("planId")
    if sha256_error(plan.model_sha256) is not None:
        raise _plan_invalid("modelSha256")
    if plan.managed_manifest_path != MANAGED_MANIFEST_PATH:
        raise _plan_invalid("manifestPath")
    if not isinstance(plan.managed_manifest_bytes, bytes):
        raise _plan_invalid("type")
    if not isinstance(plan.inputs, tuple) or not all(
        isinstance(entry, GenerationInput) for entry in plan.inputs
    ):
        raise _plan_invalid("type")
    if not isinstance(plan.files, tuple) or not all(
        isinstance(entry, GeneratedFile) for entry in plan.files
    ):
        raise _plan_invalid("type")
    if not isinstance(plan.blockers, tuple) or not all(
        isinstance(blocker, GenerationBlocker) for blocker in plan.blockers
    ):
        raise _plan_invalid("type")

    input_paths = [entry.path for entry in plan.inputs]
    for entry in plan.inputs:
        if portable_path_error(entry.path) is not None:
            raise _plan_invalid("portablePath")
        if (
            sha256_error(entry.sha256) is not None
            or not isinstance(entry.size, int)
            or entry.size < 0
        ):
            raise _plan_invalid("digestFormat")
    if len(set(input_paths)) != len(input_paths):
        raise _plan_invalid("uniquePath")
    if _duplicate_or_casefold(input_paths) is not None:
        raise _plan_invalid("casefoldCollision")
    if input_paths != sorted(input_paths, key=portable_sort_key):
        raise _plan_invalid("sortedOrder")
    total_input = sum(entry.size for entry in plan.inputs)
    if total_input > AGGREGATE_LIMIT_BYTES or any(
        entry.size > FILE_LIMIT_BYTES for entry in plan.inputs
    ):
        raise _plan_invalid("inputLimit")

    file_paths = [entry.path for entry in plan.files]
    target_set = set(_targets_for_model(plan.model))
    for entry in plan.files:
        if portable_path_error(entry.path) is not None:
            raise _plan_invalid("portablePath")
        if entry.path not in target_set:
            raise _plan_invalid("targetPath")
        if entry.status not in {"create", "unchanged", "update-managed", "user-drift", "unowned-collision", "preserved-unowned"}:
            raise _plan_invalid("status")
        if entry.status == "preserved-unowned" and entry.path not in PRESERVABLE_EDITOR_TARGETS:
            raise _plan_invalid("status")
        if entry.template_name != _target_template(entry.path):
            raise _plan_invalid("templateName")
        if entry.template_version != TEMPLATE_VERSION:
            raise _plan_invalid("templateVersion")
        if not isinstance(entry.unified_diff, str):
            raise _plan_invalid("type")
        if not isinstance(entry.after_bytes, bytes) or not isinstance(
            entry.before_bytes, (bytes, type(None))
        ):
            raise _plan_invalid("type")
        if entry.before_bytes is None:
            if entry.before_sha256 is not None or entry.before_size is not None:
                raise _plan_invalid("fileDigest")
        else:
            if (
                sha256_error(entry.before_sha256) is not None
                or not isinstance(entry.before_size, int)
                or entry.before_size < 0
                or len(entry.before_bytes) != entry.before_size
                or sha256_hex(entry.before_bytes) != entry.before_sha256
            ):
                raise _plan_invalid("fileDigest")
        if (
            sha256_error(entry.after_sha256) is not None
            or not isinstance(entry.after_size, int)
            or entry.after_size < 0
            or len(entry.after_bytes) != entry.after_size
            or sha256_hex(entry.after_bytes) != entry.after_sha256
        ):
            raise _plan_invalid("fileDigest")
        if entry.status == "create" and entry.before_bytes is not None:
            raise _plan_invalid("fileDigest")
        if entry.status == "preserved-unowned" and (
            entry.before_bytes is not None
            or entry.before_sha256 is not None
            or entry.before_size is not None
            or entry.unified_diff != ""
        ):
            raise _plan_invalid("fileDigest")
        if entry.status in ("unchanged", "user-drift", "unowned-collision") and entry.before_bytes is None:
            raise _plan_invalid("fileDigest")
        if entry.status == "unchanged" and entry.before_bytes != entry.after_bytes:
            raise _plan_invalid("fileDigest")
        if entry.status == "update-managed" and entry.before_bytes is not None and entry.before_bytes == entry.after_bytes:
            raise _plan_invalid("fileDigest")
    if len(set(file_paths)) != len(file_paths):
        raise _plan_invalid("uniquePath")
    if file_paths != sorted(file_paths, key=portable_sort_key):
        raise _plan_invalid("sortedOrder")
    if _duplicate_or_casefold(input_paths + file_paths) is not None:
        raise _plan_invalid("casefoldCollision")

    blocker_paths = [blocker.path for blocker in plan.blockers]
    for blocker in plan.blockers:
        if blocker.code not in {"GENERATED_FILE_DRIFT", "UNOWNED_COLLISION", "GENERATION_ORPHANED_MANAGED_FILE"}:
            raise _plan_invalid("blockerCode")
        if portable_path_error(blocker.path) is not None:
            raise _plan_invalid("portablePath")
        if not isinstance(blocker.message, str):
            raise _plan_invalid("type")
    if blocker_paths != sorted(blocker_paths, key=portable_sort_key):
        raise _plan_invalid("sortedOrder")
    if list(plan.blockers) != sorted(
        plan.blockers, key=lambda blocker: (portable_sort_key(blocker.path), blocker.code)
    ):
        raise _plan_invalid("sortedOrder")

    if (plan.debug_configuration is None) != (plan.manifest_edit is None):
        raise _plan_invalid("debugConfiguration")
    if plan.debug_configuration is not None:
        configuration = plan.debug_configuration
        if type(configuration) is not DebugConfiguration:
            raise _plan_invalid("debugConfiguration")
        try:
            normalized = normalize_debug_configuration(
                configuration.backend, configuration.target
            )
        except DebugConfigurationError:
            raise _plan_invalid("debugConfiguration") from None
        if normalized != configuration:
            raise _plan_invalid("debugConfiguration")
        if (
            plan.model.debug.backend != configuration.backend
            or plan.model.debug.target != configuration.target
        ):
            raise _plan_invalid("debugConfiguration")
        _validate_manifest_edit(plan, configuration)

    if plan.vscode_configuration is not None:
        bound = plan.vscode_configuration
        if type(bound) is not VSCodeConfiguration:
            raise _plan_invalid("vscodeConfiguration")
        try:
            # Revalidation is static but current: the same pair must still
            # describe two existing native executables.  The exact strings
            # stay immutable and feed the plan ID.
            normalized = normalize_vscode_configuration(
                bound.toolkit_path, bound.gcc_path
            )
        except VSCodeConfigurationError:
            raise _plan_invalid("vscodeConfiguration") from None
        if normalized != bound:
            raise _plan_invalid("vscodeConfiguration")

    fragment = plan.model.generation.linker_fragment
    if fragment is not None:
        matching = [entry for entry in plan.inputs if entry.path == fragment.path]
        if len(matching) != 1 or matching[0].sha256 != fragment.sha256:
            raise _plan_invalid("linkerFragment")

    if len(plan.managed_manifest_bytes) > TOTAL_LIMIT_BYTES:
        raise _plan_invalid("manifestLimit")
    expected = build_managed_manifest_bytes(
        plan.files, plan.model_sha256, linker_fragment=fragment
    )
    if expected != plan.managed_manifest_bytes:
        raise _plan_invalid("manifestBytes")
    if model_sha256_for(plan.model) != plan.model_sha256:
        raise _plan_invalid("modelSha256")
    if plan_id_for(plan) != plan.plan_id:
        raise _plan_invalid("planId")
    if len(canonical_json_bytes(plan.to_dict())) > PLAN_LIMIT_BYTES:
        raise _plan_invalid("planLimit")


def _validate_manifest_edit(
    plan: GenerationPlan, configuration: DebugConfiguration
) -> None:
    """Bind the optional manifest edit to the pair and to the plan's model.

    The candidate bytes are recomputed from the recorded source bytes and the
    requested pair, so a forged edit (even with a recomputed plan ID) cannot
    introduce changes beyond ``debug.backend`` and ``debug.target``.
    """
    edit = plan.manifest_edit
    if type(edit) is not ManifestEdit:
        raise _plan_invalid("manifestEdit")
    if edit.path != _STM32_PROJECT_MANIFEST:
        raise _plan_invalid("manifestEdit")
    if edit.status not in ("unchanged", "update"):
        raise _plan_invalid("manifestEdit")
    if not isinstance(edit.unified_diff, str):
        raise _plan_invalid("manifestEdit")
    if not isinstance(edit.before_bytes, bytes) or not isinstance(
        edit.after_bytes, bytes
    ):
        raise _plan_invalid("manifestEdit")
    for digest, size, data in (
        (edit.before_sha256, edit.before_size, edit.before_bytes),
        (edit.after_sha256, edit.after_size, edit.after_bytes),
    ):
        if (
            sha256_error(digest) is not None
            or not isinstance(size, int)
            or size < 0
            or len(data) != size
            or sha256_hex(data) != digest
        ):
            raise _plan_invalid("manifestEdit")
    if (
        len(edit.before_bytes) > FILE_LIMIT_BYTES
        or len(edit.after_bytes) > FILE_LIMIT_BYTES
    ):
        raise _plan_invalid("manifestEdit")
    if edit.status == "unchanged":
        if edit.before_bytes != edit.after_bytes or edit.unified_diff != "":
            raise _plan_invalid("manifestEdit")
    elif edit.before_bytes == edit.after_bytes or edit.unified_diff == "":
        raise _plan_invalid("manifestEdit")
    try:
        derived_after, derived_status = _manifest_candidate_bytes(
            edit.before_bytes, configuration
        )
    except GenerationError:
        raise _plan_invalid("manifestEdit") from None
    if derived_after != edit.after_bytes or derived_status != edit.status:
        raise _plan_invalid("manifestEdit")
    expected_diff = (
        unified_diff(
            edit.path,
            edit.before_bytes.decode("utf-8"),
            edit.after_bytes.decode("utf-8"),
        )
        if edit.status == "update"
        else ""
    )
    if edit.unified_diff != expected_diff:
        raise _plan_invalid("manifestEdit")
    matching = [entry for entry in plan.inputs if entry.path == edit.path]
    if (
        len(matching) != 1
        or matching[0].sha256 != edit.before_sha256
        or matching[0].size != edit.before_size
    ):
        raise _plan_invalid("manifestEdit")
    if any(entry.path == edit.path for entry in plan.files):
        raise _plan_invalid("manifestEdit")
    try:
        candidate_model = load_project_model_candidate(
            plan.project_root, edit.after_bytes
        )
    except (ProjectManifestError, OSError):
        raise _plan_invalid("manifestEdit") from None
    if model_sha256_for(candidate_model) != plan.model_sha256:
        raise _plan_invalid("manifestEdit")
    if (
        candidate_model.debug.backend != configuration.backend
        or candidate_model.debug.target != configuration.target
    ):
        raise _plan_invalid("manifestEdit")


def _canonical_root(root: Path) -> Path:
    try:
        canonical = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _plan_invalid("projectRoot") from None
    if not canonical.is_dir():
        raise _plan_invalid("projectRoot")
    return canonical


def _resolve_apply_target(root: Path, path: str, code: str) -> Path:
    try:
        resolved = root.joinpath(*path.split("/")).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            code,
            "path resolution failed",
            {"path": path, "rule": "withinProjectRoot"},
        ) from None
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _fail(
            code,
            "path escapes the project root",
            {"path": path, "rule": "withinProjectRoot"},
        ) from None
    return resolved


def _revalidate_inputs(root: Path, plan: GenerationPlan) -> None:
    for entry in plan.inputs:
        path = entry.path
        try:
            absolute = _resolve_apply_target(root, path, "GENERATION_INPUT_CHANGED")
        except _ApplyFailure:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "recorded input is no longer inside the project root",
                {"path": path},
            ) from None
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            raise _fail("GENERATION_INPUT_CHANGED", "recorded input is missing", {"path": path}) from None
        except NotADirectoryError:
            raise _fail("GENERATION_INPUT_CHANGED", "recorded input is missing", {"path": path}) from None
        except OSError:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "recorded input inspection failed",
                {"path": path},
            ) from None
        if not stat.S_ISREG(lst.st_mode):
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "recorded input is not a regular file",
                {"path": path},
            )
        try:
            data = _read_limited(absolute, entry.size)
        except OSError:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "recorded input is unreadable",
                {"path": path},
            ) from None
        if len(data) > entry.size or len(data) != entry.size or sha256_hex(data) != entry.sha256:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "recorded input bytes changed",
                {"path": path},
            )


def _validate_destinations(root: Path, plan: GenerationPlan) -> None:
    for entry in plan.files:
        path = entry.path
        if entry.status == "preserved-unowned":
            _validate_preserved_editor(root, path)
            continue
        absolute = _resolve_apply_target(root, path, "GENERATION_PATH_INVALID")
        try:
            lst = os.lstat(absolute)
        except FileNotFoundError:
            if entry.before_bytes is not None:
                raise _fail("GENERATION_INPUT_CHANGED", "current target is missing", {"path": path}) from None
            continue
        except NotADirectoryError:
            if entry.before_bytes is not None:
                raise _fail("GENERATION_INPUT_CHANGED", "current target is missing", {"path": path}) from None
            continue
        except OSError:
            raise _fail(
                "GENERATION_PATH_INVALID",
                "current target inspection failed",
                {"path": path, "rule": "withinProjectRoot"},
            ) from None
        if entry.before_bytes is None:
            raise _fail("GENERATION_TARGET_EXISTS", "creation target already exists", {"path": path})
        if not stat.S_ISREG(lst.st_mode):
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "current target is not a regular file",
                {"path": path},
            )
        try:
            data = _read_limited(absolute, entry.before_size)
        except OSError:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "current target is unreadable",
                {"path": path},
            ) from None
        if len(data) != entry.before_size or sha256_hex(data) != entry.before_sha256:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "current target bytes changed",
                {"path": path},
            )
    if plan.manifest_edit is not None and plan.manifest_edit.status == "update":
        _validate_manifest_edit_destination(root, plan.manifest_edit)


def _validate_manifest_edit_destination(root: Path, edit: ManifestEdit) -> None:
    """Recheck the source manifest destination, including a redirect refusal."""
    path = edit.path
    lexical = root.joinpath(*path.split("/"))
    try:
        lst = os.lstat(lexical)
    except (FileNotFoundError, NotADirectoryError):
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "source manifest is missing",
            {"path": path},
        ) from None
    except OSError:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "source manifest inspection failed",
            {"path": path},
        ) from None
    if stat.S_ISLNK(lst.st_mode) or bool(
        getattr(lst, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise _fail(
            "GENERATION_PATH_INVALID",
            "source manifest must not redirect",
            {"path": path, "rule": "redirect"},
        )
    if not stat.S_ISREG(lst.st_mode):
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "source manifest is not a regular file",
            {"path": path},
        )
    absolute = _resolve_apply_target(root, path, "GENERATION_PATH_INVALID")
    try:
        data = _read_limited(absolute, edit.before_size)
    except OSError:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "source manifest is unreadable",
            {"path": path},
        ) from None
    if len(data) != edit.before_size or sha256_hex(data) != edit.before_sha256:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "source manifest bytes changed",
            {"path": path},
        )


def _validate_preserved_editor(root: Path, path: str) -> None:
    try:
        exists = _editor_target_exists(root, path)
    except GenerationError:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "preserved editor target type changed",
            {"path": path},
        ) from None
    if not exists:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "preserved editor target is missing",
            {"path": path},
        )


def _within_root_prefix(root_resolved: str, candidate: Path) -> bool:
    candidate_str = os.path.normcase(str(candidate))
    return candidate_str == root_resolved or candidate_str.startswith(root_resolved + os.sep)


def _validate_staging_containment(root: Path, staging: Path) -> None:
    """Reject any staging path component that escapes the project root."""
    portable = f"{STAGING_ROOT}/{staging.name}"
    try:
        root_resolved = os.path.normcase(str(root.resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "GENERATION_PATH_INVALID",
            "project root resolution failed",
            {"path": portable, "rule": "withinProjectRoot"},
        ) from None
    current = root
    for component in STAGING_ROOT.split("/") + [staging.name]:
        current = current.joinpath(component)
        try:
            resolved = current.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            raise _fail(
                "GENERATION_PATH_INVALID",
                "staging path resolution failed",
                {"path": portable, "rule": "withinProjectRoot"},
            ) from None
        if not _within_root_prefix(root_resolved, resolved):
            raise _fail(
                "GENERATION_PATH_INVALID",
                "staging path escapes the project root",
                {"path": portable, "rule": "withinProjectRoot"},
            )


class _FsyncError(OSError):
    pass


def _fsync(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as error:
        raise _FsyncError(error.errno, error.strerror) from error


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        _fsync(fd)
    finally:
        os.close(fd)


def _stage_write(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            _fsync(handle.fileno())
        os.chmod(path, mode)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _temp_write(path: Path, data: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            _fsync(handle.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _remove_staging(staging: Path) -> None:
    shutil.rmtree(staging)
    try:
        os.rmdir(staging.parent)
    except OSError:
        pass


def _remove_created_dirs(created_dirs: list[Path], skip: set[Path]) -> None:
    for directory in reversed(created_dirs):
        if directory in skip:
            continue
        try:
            os.rmdir(directory)
        except OSError:
            pass


def _ensure_dir(path: Path, created_dirs: list[Path]) -> None:
    if path.is_dir():
        return
    missing: list[Path] = []
    current = path
    while not current.is_dir():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    os.makedirs(path, exist_ok=True)
    created_dirs.extend(reversed(missing))


def _before_sha_by_path(plan: GenerationPlan) -> dict[str, str | None]:
    mapping = {
        entry.path: entry.before_sha256
        for entry in plan.files
        if entry.status != "preserved-unowned"
    }
    for entry in plan.inputs:
        if entry.path == MANAGED_MANIFEST_PATH:
            mapping[MANAGED_MANIFEST_PATH] = entry.sha256
    if plan.manifest_edit is not None:
        mapping[plan.manifest_edit.path] = plan.manifest_edit.before_sha256
    return mapping


def _map_fresh_error(error: GenerationError) -> None:
    code = error.code
    if code == "GENERATION_MODEL_INVALID":
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "project model changed since planning",
            {"path": _STM32_PROJECT_MANIFEST},
        )
    if code == "GENERATION_MANIFEST_INVALID":
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "managed manifest changed since planning",
            {"path": MANAGED_MANIFEST_PATH},
        )
    if code == "GENERATION_FIXED_SECTION_INVALID":
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "conversion report changed since planning",
            {"path": _CONVERSION_REPORT_PATH},
        )
    if code == "LINKER_FRAGMENT_INVALID":
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "linker fragment changed since planning",
            {"path": str(error.details.get("path", "generation.linkerFragment"))},
        )
    if code in ("GENERATION_INPUT_INVALID", "GENERATION_PATH_INVALID"):
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "recorded input changed since planning",
            {"path": str(error.details.get("path", ""))},
        )
    if code == "DEBUG_CONFIGURATION_INVALID":
        # A validated plan cannot replay an invalid request; treat it as
        # plan tampering rather than a source change.
        raise _plan_invalid("debugConfiguration")
    if code == "VSCODE_CONFIGURATION_INVALID":
        # The plan's immutable binding no longer validates (for example the
        # executable was removed or replaced by a redirect).  Nothing writes.
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "VS Code executable binding changed since planning",
            {
                "field": str(error.details.get("field", "vscode")),
                "rule": str(error.details.get("rule", "value")),
            },
        )
    raise _plan_invalid("freshPlan")


def _fresh_matches(fresh: GenerationPlan, plan: GenerationPlan) -> None:
    if fresh.plan_version != plan.plan_version:
        raise _plan_invalid("freshPlan")
    if fresh.model_sha256 != plan.model_sha256:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "project model changed since planning",
            {"path": _STM32_PROJECT_MANIFEST},
        )
    if fresh.managed_manifest_path != plan.managed_manifest_path:
        raise _plan_invalid("freshPlan")
    if fresh.inputs != plan.inputs:
        by_path = {entry.path: entry for entry in fresh.inputs}
        for entry in plan.inputs:
            if by_path.get(entry.path) != entry:
                raise _fail(
                    "GENERATION_INPUT_CHANGED",
                    "recorded input changed since planning",
                    {"path": entry.path},
                )
        extra = [
            entry.path
            for entry in fresh.inputs
            if entry.path not in {known.path for known in plan.inputs}
        ]
        if extra:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "an input appeared since planning",
                {"path": extra[0]},
            )
        raise _plan_invalid("freshPlan")
    if len(fresh.files) != len(plan.files):
        raise _plan_invalid("freshPlan")
    for fresh_file, plan_file in zip(fresh.files, plan.files):
        if fresh_file.to_dict() != plan_file.to_dict():
            if (
                fresh_file.before_sha256 != plan_file.before_sha256
                or fresh_file.status != plan_file.status
            ):
                raise _fail(
                    "GENERATION_INPUT_CHANGED",
                    "current target changed since planning",
                    {"path": plan_file.path},
                )
            raise _plan_invalid("freshPlan")
        if (
            fresh_file.before_bytes != plan_file.before_bytes
            or fresh_file.after_bytes != plan_file.after_bytes
        ):
            raise _plan_invalid("freshPlan")
    if fresh.blockers != plan.blockers:
        raise _plan_invalid("freshPlan")
    if fresh.managed_manifest_bytes != plan.managed_manifest_bytes:
        raise _plan_invalid("freshPlan")
    if fresh.debug_configuration != plan.debug_configuration:
        raise _plan_invalid("freshPlan")
    if fresh.manifest_edit != plan.manifest_edit:
        if (
            plan.manifest_edit is not None
            and fresh.manifest_edit is not None
            and fresh.manifest_edit.before_bytes != plan.manifest_edit.before_bytes
        ):
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "project model changed since planning",
                {"path": _STM32_PROJECT_MANIFEST},
            )
        raise _plan_invalid("freshPlan")
    if fresh.vscode_configuration != plan.vscode_configuration:
        raise _plan_invalid("freshPlan")


def _rollback(
    staging: Path,
    replaced: list[tuple[str, Path, Path]],
    created_files: list[tuple[str, Path]],
    created_dirs: list[Path],
    temp_files: list[tuple[str, Path]],
) -> None:
    """Restore every pre-apply byte and mode; failures retain recoverable staging."""
    failed: list[str] = []
    for path, temp in temp_files:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(path)
    for path, target, backup in reversed(replaced):
        try:
            os.replace(backup, target)
        except OSError:
            failed.append(path)
    for path, target in reversed(created_files):
        try:
            os.unlink(target)
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(path)
    if failed:
        raise _fail(
            "GENERATION_ROLLBACK_FAILED",
            "rollback could not restore every path",
            {"paths": sorted(set(failed), key=portable_sort_key)},
        )
    try:
        _remove_staging(staging)
    except OSError:
        pass
    _remove_created_dirs(created_dirs, {staging, staging.parent})


def _manifest_edit_result(plan: GenerationPlan) -> dict[str, object]:
    if plan.manifest_edit is None:
        return {}
    return {
        "manifestEditPath": plan.manifest_edit.path,
        "manifestEditStatus": plan.manifest_edit.status,
    }


def _vscode_guidance_result(plan: GenerationPlan) -> dict[str, object]:
    """Advisory binding guidance shared by every successful APPLY result.

    It is derived only from the validated binding and the plan's existing
    preserved-unowned statuses; applying never reads the preserved content or
    VS Code user settings.
    """
    return {
        "vscodeGuidance": build_vscode_guidance(
            plan.vscode_configuration,
            (
                entry.path
                for entry in plan.files
                if entry.status == "preserved-unowned"
            ),
        )
    }


def _apply(plan: GenerationPlan) -> dict[str, object]:
    _validate_plan(plan)

    canonical = _canonical_root(plan.project_root)
    try:
        planned_root = plan.project_root.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _plan_invalid("projectRoot") from None
    if planned_root != canonical:
        raise _plan_invalid("projectRoot")

    staging = canonical.joinpath(*STAGING_ROOT.split("/"), plan.plan_id)
    # A staging escape must be rejected before any other preflight step can
    # short-circuit with a less specific failure: the canonical staging path
    # (including the .stm32-toolkit and configuration-staging intermediates)
    # must stay inside the project root before the first write.
    _validate_staging_containment(canonical, staging)

    try:
        fresh_source_model = load_project_model(canonical)
    except ProjectManifestError:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "project model is no longer available",
            {"path": _STM32_PROJECT_MANIFEST},
        ) from None
    if plan.manifest_edit is None:
        source_changed = (
            model_sha256_for(fresh_source_model) != plan.model_sha256
        )
    else:
        # The edit route's plan model is the validated AFTER model, so the
        # source check must compare the observed source against the recorded
        # before bytes instead of weakening the comparison.
        try:
            before_model = load_project_model_candidate(
                canonical, plan.manifest_edit.before_bytes
            )
        except ProjectManifestError:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "project model changed since planning",
                {"path": _STM32_PROJECT_MANIFEST},
            ) from None
        source_changed = model_sha256_for(fresh_source_model) != model_sha256_for(
            before_model
        )
    if source_changed:
        raise _fail(
            "GENERATION_INPUT_CHANGED",
            "project model changed since planning",
            {"path": _STM32_PROJECT_MANIFEST},
        )

    _revalidate_inputs(canonical, plan)
    _validate_destinations(canonical, plan)

    staging = canonical.joinpath(*STAGING_ROOT.split("/"), plan.plan_id)
    _validate_staging_containment(canonical, staging)
    _reject_existing_staging(staging, plan)

    try:
        fresh = plan_project_configuration(
            fresh_source_model,
            debug_backend=(
                plan.debug_configuration.backend
                if plan.debug_configuration is not None
                else None
            ),
            debug_target=(
                plan.debug_configuration.target
                if plan.debug_configuration is not None
                else None
            ),
            vscode_toolkit_path=(
                plan.vscode_configuration.toolkit_path
                if plan.vscode_configuration is not None
                else None
            ),
            vscode_gcc_path=(
                plan.vscode_configuration.gcc_path
                if plan.vscode_configuration is not None
                else None
            ),
        )
    except GenerationError as error:
        _map_fresh_error(error)
    _fresh_matches(fresh, plan)

    if plan.blockers:
        drift = sorted(
            (blocker.path for blocker in plan.blockers if blocker.code == "GENERATED_FILE_DRIFT"),
            key=portable_sort_key,
        )
        if drift:
            raise _fail(
                "GENERATED_FILE_DRIFT",
                "generated files were modified outside the toolkit",
                {"paths": drift},
            )
        raise _fail(
            "GENERATION_BLOCKED",
            "configuration generation is blocked",
            {
                "codes": sorted({blocker.code for blocker in plan.blockers}),
                "paths": sorted(
                    (blocker.path for blocker in plan.blockers), key=portable_sort_key
                ),
            },
        )

    before_sha_by_path = _before_sha_by_path(plan)
    destinations: list[tuple[str, bytes, bool]] = []
    for entry in plan.files:
        if entry.status in ("create", "update-managed"):
            destinations.append((entry.path, entry.after_bytes, entry.before_bytes is not None))
    manifest_existed = any(entry.path == MANAGED_MANIFEST_PATH for entry in plan.inputs)
    if not manifest_existed:
        destinations.append((MANAGED_MANIFEST_PATH, plan.managed_manifest_bytes, False))
    else:
        try:
            current_manifest = _read_limited(
                canonical.joinpath(*MANAGED_MANIFEST_PATH.split("/")), FILE_LIMIT_BYTES
            )
        except OSError:
            raise _fail(
                "GENERATION_INPUT_CHANGED",
                "managed manifest is unreadable",
                {"path": MANAGED_MANIFEST_PATH},
            ) from None
        if current_manifest != plan.managed_manifest_bytes:
            destinations.append((MANAGED_MANIFEST_PATH, plan.managed_manifest_bytes, True))
    if plan.manifest_edit is not None and plan.manifest_edit.status == "update":
        # The user-owned manifest edit joins the same staging/backup/replace/
        # rollback transaction as every generated output and the managed
        # manifest.  It is never written in a separate phase.
        destinations.append(
            (plan.manifest_edit.path, plan.manifest_edit.after_bytes, True)
        )
    destinations.sort(key=lambda item: portable_sort_key(item[0]))

    if not destinations:
        return {
            "planId": plan.plan_id,
            "modelSha256": plan.model_sha256,
            "createdPaths": [],
            "updatedPaths": [],
            "unchangedPaths": sorted(
                (entry.path for entry in plan.files if entry.status == "unchanged"), key=portable_sort_key
            ),
            "preservedPaths": sorted(
                (entry.path for entry in plan.files if entry.status == "preserved-unowned"),
                key=portable_sort_key,
            ),
            "warnings": (
                [_PRESERVED_EDITOR_GUIDANCE]
                if any(entry.status == "preserved-unowned" for entry in plan.files)
                else []
            ),
            "managedManifestPath": MANAGED_MANIFEST_PATH,
            "managedManifestSha256": sha256_hex(plan.managed_manifest_bytes),
            "templateVersion": TEMPLATE_VERSION,
            **_manifest_edit_result(plan),
            **_vscode_guidance_result(plan),
        }

    staging = canonical.joinpath(*STAGING_ROOT.split("/"), plan.plan_id)
    _validate_staging_containment(canonical, staging)
    _reject_existing_staging(staging, plan)

    created_dirs: list[Path] = []
    replaced: list[tuple[str, Path, Path]] = []
    created_files: list[tuple[str, Path]] = []
    temp_files: list[tuple[str, Path]] = []
    success = False
    in_replace = False

    try:
        # --- stage phase ----------------------------------------------------
        stage_root = staging / "new"
        backup_root = staging / "backup"
        _ensure_dir(staging, created_dirs)
        _ensure_dir(stage_root, created_dirs)
        _ensure_dir(backup_root, created_dirs)
        for path, data, existed in destinations:
            staged = stage_root.joinpath(*path.split("/"))
            _ensure_dir(staged.parent, created_dirs)
            if existed:
                target = canonical.joinpath(*path.split("/"))
                lst = os.lstat(target)
                original_mode = stat.S_IMODE(lst.st_mode)
                backup = backup_root.joinpath(*path.split("/"))
                _ensure_dir(backup.parent, created_dirs)
                with target.open("rb") as handle:
                    original = handle.read()
                _stage_write(backup, original, original_mode)
                _stage_write(staged, data, original_mode)
            else:
                _stage_write(staged, data, 0o644)

        # --- replace phase --------------------------------------------------
        in_replace = True
        # Staging can take time. Recheck preserved editor categories by stat
        # before writing, without changing managed-target replace semantics.
        for entry in plan.files:
            if entry.status == "preserved-unowned":
                _validate_preserved_editor(canonical, entry.path)
        for path, data, existed in destinations:
            target = canonical.joinpath(*path.split("/"))
            _resolve_apply_target(canonical, path, "GENERATION_PATH_INVALID")
            _ensure_dir(target.parent, created_dirs)
            expected = before_sha_by_path.get(path)
            if existed:
                lst = os.lstat(target)
                if not stat.S_ISREG(lst.st_mode):
                    raise _fail(
                        "GENERATION_INPUT_CHANGED",
                        "current target is not a regular file",
                        {"path": path},
                    )
                with target.open("rb") as handle:
                    current = handle.read()
                if sha256_hex(current) != expected:
                    raise _fail(
                        "GENERATION_INPUT_CHANGED",
                        "current target bytes changed",
                        {"path": path},
                    )
                mode = stat.S_IMODE(lst.st_mode)
            else:
                try:
                    os.lstat(target)
                except FileNotFoundError:
                    pass
                except OSError:
                    raise _fail(
                        "GENERATION_PATH_INVALID",
                        "creation target state cannot be verified",
                        {"path": path, "rule": "withinProjectRoot"},
                    ) from None
                else:
                    raise _fail(
                        "GENERATION_TARGET_EXISTS",
                        "creation target appeared during apply",
                        {"path": path},
                    )
                mode = 0o644
            temp = target.parent / f".{plan.plan_id[:12]}.{target.name}.stm32tk-tmp"
            _temp_write(temp, data, mode)
            temp_files.append((path, temp))
            os.replace(temp, target)
            temp_files.remove((path, temp))
            # Record the completed replacement before the fallible chmod so a
            # post-replace failure can still restore every path, including the
            # user-owned project manifest.
            if existed:
                replaced.append((path, target, backup_root.joinpath(*path.split("/"))))
            else:
                created_files.append((path, target))
            os.chmod(target, mode)
            try:
                _fsync_dir(target.parent)
            except OSError as error:
                raise _FsyncError(error.errno, error.strerror) from error
        success = True
        _remove_staging(staging)
    except _ApplyFailure:
        # Semantic failures raised after the first real mutation (for
        # example GENERATION_INPUT_CHANGED or GENERATION_TARGET_EXISTS from
        # a replace-phase revalidation) must roll back exactly like any
        # other recoverable failure. A successful rollback preserves the
        # original stable code and details; a failed rollback returns
        # GENERATION_ROLLBACK_FAILED and retains recoverable staging.
        if in_replace:
            try:
                _rollback(staging, replaced, created_files, created_dirs, temp_files)
            except _ApplyFailure:
                raise
        raise
    except OSError as error:
        if isinstance(error, _FsyncError):
            phase = "fsync"
        elif success:
            phase = "stage"
        elif in_replace:
            phase = "replace"
        else:
            phase = "stage"
        try:
            if replaced or created_files or temp_files:
                _rollback(staging, replaced, created_files, created_dirs, temp_files)
            else:
                try:
                    _remove_staging(staging)
                except OSError:
                    pass
                _remove_created_dirs(created_dirs, {staging, staging.parent})
        except _ApplyFailure:
            raise
        raise _fail("GENERATION_APPLY_FAILED", "apply failed", {"phase": phase})

    return {
        "planId": plan.plan_id,
        "modelSha256": plan.model_sha256,
        "createdPaths": sorted(
            (path for path, _data, existed in destinations if not existed),
            key=portable_sort_key,
        ),
        "updatedPaths": sorted(
            (path for path, _data, existed in destinations if existed),
            key=portable_sort_key,
        ),
        "unchangedPaths": sorted(
            (entry.path for entry in plan.files if entry.status == "unchanged"),
            key=portable_sort_key,
        ),
        "preservedPaths": sorted(
            (entry.path for entry in plan.files if entry.status == "preserved-unowned"),
            key=portable_sort_key,
        ),
        "warnings": (
            [_PRESERVED_EDITOR_GUIDANCE]
            if any(entry.status == "preserved-unowned" for entry in plan.files)
            else []
        ),
        "managedManifestPath": MANAGED_MANIFEST_PATH,
        "managedManifestSha256": sha256_hex(plan.managed_manifest_bytes),
        "templateVersion": TEMPLATE_VERSION,
        **_manifest_edit_result(plan),
        **_vscode_guidance_result(plan),
    }


def _reject_existing_staging(staging: Path, plan: GenerationPlan) -> None:
    # Every intermediate component of the staging path must be an existing
    # directory or absent; a regular file in the way must be reported stably
    # as GENERATION_TARGET_EXISTS before any write, on every host (Windows
    # raises FileNotFoundError rather than NotADirectoryError for a file
    # intermediate, which would otherwise surface later as an apply failure).
    components = [
        (STAGING_ROOT.split("/")[0], staging.parent.parent),
        (STAGING_ROOT.split("/")[1], staging.parent),
    ]
    for name, component in components:
        try:
            lst = os.lstat(component)
        except FileNotFoundError:
            continue
        except NotADirectoryError:
            continue
        except OSError:
            raise _fail(
                "GENERATION_PATH_INVALID",
                "staging state cannot be verified",
                {"path": name, "rule": "withinProjectRoot"},
            ) from None
        if not stat.S_ISDIR(lst.st_mode):
            raise _fail(
                "GENERATION_TARGET_EXISTS",
                f"{name} is not a directory",
                {"path": name},
            )
    try:
        os.lstat(staging)
    except FileNotFoundError:
        pass
    except NotADirectoryError:
        raise _fail(
            "GENERATION_TARGET_EXISTS",
            "staging path already exists",
            {"path": f"{STAGING_ROOT}/{plan.plan_id}"},
        ) from None
    except OSError:
        raise _fail(
            "GENERATION_PATH_INVALID",
            "staging state cannot be verified",
            {"path": f"{STAGING_ROOT}/{plan.plan_id}", "rule": "withinProjectRoot"},
        ) from None
    else:
        raise _fail(
            "GENERATION_TARGET_EXISTS",
            "staging path already exists",
            {"path": f"{STAGING_ROOT}/{plan.plan_id}"},
        )
