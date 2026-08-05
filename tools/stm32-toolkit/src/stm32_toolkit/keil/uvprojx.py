"""Read-only Keil .uvprojx inspection.

Owns project discovery, bounded XML parsing, target selection, option
extraction, path validation, input hashing, and scanner orchestration.
"""

from __future__ import annotations

import codecs
import hashlib
import os
import re
import stat
import xml.etree.ElementTree as ET
from pathlib import Path

from stm32_toolkit.keil import armcc_scan
from stm32_toolkit.keil.model import (
    KeilEvidence,
    KeilFinding,
    KeilInspection,
    KeilInspectionError,
    KeilInputDigest,
    KeilMemoryRegion,
    KeilOutputSpec,
    KeilScopedOptions,
    KeilSource,
    KeilWarning,
)

PROJECT_XML_LIMIT = 8 * 1024 * 1024
_MAX_UINT64 = 0xFFFFFFFFFFFFFFFF

_XML_DECL_ENCODING_RE = re.compile(
    rb"<\?xml[^>]*encoding\s*=\s*['\"]([A-Za-z0-9._-]+)['\"]", re.IGNORECASE
)
_CPUTYPE_RE = re.compile(r'CPUTYPE\s*\(\s*"([^"]*)"\s*\)')
_MEMORY_TOKEN_RE = re.compile(r"(IROM2|IRAM2|IROM|IRAM)\s*\(")
_MEMORY_VALUE_RE = re.compile(r"^\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_REGION_OUTPUT_NAMES = {
    "IROM": "IROM1",
    "IROM2": "IROM2",
    "IRAM": "IRAM1",
    "IRAM2": "IRAM2",
}
_REGION_ORDER = ("IROM1", "IROM2", "IRAM1", "IRAM2")
_FPU_TOKENS = ("FPU4", "FPU3", "FPU2", "FPU")
_FILE_TYPE_LANGUAGES = {"1": "c", "2": "asm"}
_SUFFIX_LANGUAGES = {
    ".c": "c",
    ".cc": "cxx",
    ".cpp": "cxx",
    ".cxx": "cxx",
    ".s": "asm",
    ".asm": "asm",
    ".a51": "asm",
    ".h": "header",
    ".hpp": "header",
    ".a": "library",
    ".lib": "library",
}
_SCANNED_LANGUAGES = ("c", "cxx", "asm")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_children(element, name: str):
    for child in element:
        if _local(child.tag) == name:
            yield child


def _descendant(element, *names):
    current = element
    for name in names:
        found = None
        for child in _iter_children(current, name):
            found = child
            break
        if found is None:
            return None
        current = found
    return current


def _text_of(element, name: str) -> str | None:
    if element is None:
        return None
    for child in _iter_children(element, name):
        text = child.text
        if text is None:
            return ""
        return text.strip()
    return None


def _raw_text_of(element, name: str) -> str | None:
    """Return element text without stripping (used for misc controls)."""
    if element is None:
        return None
    for child in _iter_children(element, name):
        text = child.text
        if text is None:
            return ""
        return text
    return None


def _raise(code: str, message: str, details: dict[str, object]) -> KeilInspectionError:
    return KeilInspectionError(code, message, details)


def _read_limited(path: Path, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes; callers enforce the cap on the result.

    A growing or replaced file can therefore never be loaded beyond the limit.
    """
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def _decoded_has_dtd_or_entity(data: bytes, encoding: str) -> bool:
    try:
        text = data.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return False
    lowered = text.lower()
    return "<!doctype" in lowered or "<!entity" in lowered


def _contains_dtd_or_entity(data: bytes) -> bool:
    """Reject case-insensitive DTD/ENTITY declarations before XML parsing.

    Covers UTF-8, UTF-8 BOM, UTF-16 LE/BE with BOM, and encodings declared in
    the XML declaration; the byte scan already covers every ASCII-compatible
    single-byte encoding.  The XML parse never sees a document that declares
    a DTD or entity, so no external resource can be requested.
    """
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        return True
    if data[:2] == b"\xff\xfe":
        return _decoded_has_dtd_or_entity(data, "utf-16-le")
    if data[:2] == b"\xfe\xff":
        return _decoded_has_dtd_or_entity(data, "utf-16-be")
    prolog = data[:1024]
    match = _XML_DECL_ENCODING_RE.search(prolog)
    if match is not None:
        try:
            info = codecs.lookup(match.group(1).decode("ascii", errors="replace"))
        except LookupError:
            info = None
        if info is not None and info.name in (
            "utf-16",
            "utf-16-le",
            "utf-16-be",
            "utf-16le",
            "utf-16be",
        ):
            encoding = (
                "utf-16-le"
                if info.name in ("utf-16", "utf-16-le", "utf-16le")
                else "utf-16-be"
            )
            return _decoded_has_dtd_or_entity(data, encoding)
    if b"\x00" in prolog:
        return _decoded_has_dtd_or_entity(data, "utf-16-le") or _decoded_has_dtd_or_entity(
            data, "utf-16-be"
        )
    return False


# ---------------------------------------------------------------------------
# root and project selection
# ---------------------------------------------------------------------------


def _validate_root(root: object) -> Path:
    if not isinstance(root, Path):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "project root must be a Path naming an existing directory",
            {"field": "projectRoot", "rule": "directory"},
        )
    if "\x00" in str(root):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "project root is invalid",
            {"field": "projectRoot", "rule": "directory"},
        )
    try:
        canonical = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "project root is invalid or unreadable",
            {"field": "projectRoot", "rule": "directory"},
        )
    if not canonical.is_dir():
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "project root must be an existing directory",
            {"field": "projectRoot", "rule": "directory"},
        )
    return canonical


def _select_project(root: Path, uvprojx: object) -> tuple[str, Path]:
    if uvprojx is None:
        candidates = sorted(
            (path for path in root.glob("*.uvprojx") if path.is_file()),
            key=lambda path: path.name.casefold(),
        )
        if not candidates:
            raise _raise(
                "KEIL_PROJECT_NOT_FOUND",
                "no .uvprojx project found in the project root",
                {"pattern": "*.uvprojx"},
            )
        if len(candidates) > 1:
            raise _raise(
                "KEIL_PROJECT_SELECTION_REQUIRED",
                "multiple .uvprojx projects found; select one explicitly",
                {"candidates": [path.name for path in candidates]},
            )
        candidate = candidates[0]
        _check_redirects(candidate, root, "uvprojx")
        return candidate.name, candidate
    if not isinstance(uvprojx, Path):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "uvprojx must be a Path",
            {"field": "uvprojx", "rule": "withinProjectRoot"},
        )
    raw = str(uvprojx)
    if "\x00" in raw or not raw.lower().endswith(".uvprojx"):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "uvprojx must name a .uvprojx file",
            {"field": "uvprojx", "rule": "withinProjectRoot"},
        )
    candidate = uvprojx if uvprojx.is_absolute() else root / uvprojx
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "uvprojx path is invalid",
            {"field": "uvprojx", "rule": "withinProjectRoot"},
        )
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise _raise(
            "KEIL_PROJECT_PATH_INVALID",
            "uvprojx must be inside the canonical project root",
            {"field": "uvprojx", "rule": "withinProjectRoot"},
        )
    _check_redirects(candidate, root, "uvprojx")
    try:
        metadata = os.stat(resolved)
    except FileNotFoundError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is missing",
            {"path": relative.as_posix()},
        )
    except NotADirectoryError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is unavailable",
            {"path": relative.as_posix()},
        )
    except OSError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is unavailable",
            {"path": relative.as_posix()},
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project path is not a regular file",
            {"path": relative.as_posix()},
        )
    return relative.as_posix(), resolved


def _read_project(project_abs: Path, project_rel: str) -> tuple[ET.Element, str, int]:
    try:
        data = _read_limited(project_abs, PROJECT_XML_LIMIT)
    except FileNotFoundError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is missing",
            {"path": project_rel},
        )
    except NotADirectoryError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is unavailable",
            {"path": project_rel},
        )
    except OSError:
        raise _raise(
            "KEIL_PROJECT_UNAVAILABLE",
            "project file is unavailable",
            {"path": project_rel},
        )
    if len(data) > PROJECT_XML_LIMIT:
        raise _raise(
            "KEIL_XML_LIMIT_EXCEEDED",
            "project XML exceeds the size limit",
            {"limitBytes": PROJECT_XML_LIMIT},
        )
    if _contains_dtd_or_entity(data):
        raise _raise(
            "KEIL_XML_UNSAFE",
            "project XML declares a DTD or entity",
            {"rule": "doctypeOrEntity"},
        )
    try:
        tree = ET.fromstring(data)
    except ET.ParseError as error:
        line, column = getattr(error, "position", (0, 0))
        raise _raise(
            "KEIL_XML_INVALID",
            "project XML is malformed",
            {"path": project_rel, "line": line, "column": column},
        )
    return tree, hashlib.sha256(data).hexdigest(), len(data)


# ---------------------------------------------------------------------------
# target selection and fact extraction
# ---------------------------------------------------------------------------


def _collect_targets(tree: ET.Element) -> list[tuple[str, ET.Element]]:
    targets: list[tuple[str, ET.Element]] = []
    for targets_element in _iter_children(tree, "Targets"):
        for target in _iter_children(targets_element, "Target"):
            name = _text_of(target, "TargetName")
            if name:
                targets.append((name, target))
    return targets


def _select_target(
    targets: list[tuple[str, ET.Element]], target_name: str | None
) -> tuple[str, ET.Element]:
    if not targets:
        raise _raise(
            "KEIL_TARGET_INVALID",
            "the project has no valid targets",
            {"field": "targetName", "rule": "missing"},
        )
    if target_name is None:
        if len(targets) > 1:
            raise _raise(
                "KEIL_TARGET_SELECTION_REQUIRED",
                "multiple targets found; select one explicitly",
                {"targets": sorted(name for name, _ in targets)},
            )
        return targets[0]
    for name, element in targets:
        if name == target_name:
            return name, element
    raise _raise(
        "KEIL_TARGET_NOT_FOUND",
        "requested target does not exist",
        {"targetName": target_name, "targets": sorted(name for name, _ in targets)},
    )


def _parse_cpu(cpu_text: str) -> tuple[str, str | None]:
    match = _CPUTYPE_RE.search(cpu_text)
    if match is None:
        raise _raise(
            "KEIL_TARGET_INVALID",
            "target Cpu setting has no CPUTYPE",
            {"field": "cpu", "rule": "missing"},
        )
    cpu = match.group(1)
    fpu = next((token for token in _FPU_TOKENS if re.search(rf"\b{token}\b", cpu_text)), None)
    return cpu, fpu


def _parse_int(raw: str, field: str) -> int:
    try:
        return int(raw, 0)
    except ValueError:
        try:
            return int(raw, 10)
        except ValueError:
            raise _raise(
                "KEIL_TARGET_INVALID",
                "target memory value is malformed",
                {"field": field, "rule": "parse"},
            )


def _parse_memory(cpu_text: str, target_option) -> tuple[KeilMemoryRegion, ...]:
    regions: dict[str, tuple[int, int]] = {}

    def add(name: str, start: int, length: int) -> None:
        if length == 0:
            return
        existing = regions.get(name)
        if existing is not None:
            if existing != (start, length):
                raise _raise(
                    "KEIL_MEMORY_CONFLICT",
                    "conflicting memory region definitions",
                    {"region": name},
                )
            return
        regions[name] = (start, length)

    for match in _MEMORY_TOKEN_RE.finditer(cpu_text):
        token = match.group(1)
        open_index = match.end() - 1
        depth = 0
        cursor = open_index
        while cursor < len(cpu_text):
            char = cpu_text[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if depth != 0:
            raise _raise(
                "KEIL_TARGET_INVALID",
                "target memory expression is malformed",
                {"field": "memory", "rule": "parse"},
            )
        value_match = _MEMORY_VALUE_RE.match(cpu_text[open_index + 1 : cursor])
        if value_match is None:
            raise _raise(
                "KEIL_TARGET_INVALID",
                "target memory expression is malformed",
                {"field": "memory", "rule": "parse"},
            )
        start = _parse_int(value_match.group(1), "memory")
        length = _parse_int(value_match.group(2), "memory")
        add(_REGION_OUTPUT_NAMES[token], start, length)

    common = _descendant(target_option, "TargetCommonOption")
    if common is not None:
        for tag in _REGION_ORDER:
            raw = _text_of(common, tag)
            if not raw:
                continue
            parts = raw.split()
            if len(parts) != 2:
                raise _raise(
                    "KEIL_TARGET_INVALID",
                    "target memory field is malformed",
                    {"field": "memory", "rule": "parse"},
                )
            start = _parse_int(parts[0], "memory")
            length = _parse_int(parts[1], "memory")
            add(tag, start, length)

    return tuple(
        KeilMemoryRegion(
            name,
            regions[name][0],
            regions[name][1],
            "r-x" if name.startswith("IROM") else "rwx",
        )
        for name in _REGION_ORDER
        if name in regions
    )


def _parse_compiler(target) -> tuple[str, str | None, KeilWarning | None]:
    raw = _text_of(target, "pCCUsed")
    uac6 = _text_of(target, "uAC6")
    family = "unknown"
    version: str | None = None
    if raw:
        parts = raw.split("::")
        name = parts[-1].strip()
        if name.upper() == "ARMCC":
            family = "armcc"
        elif name.upper() == "ARMCLANG":
            family = "armclang"
        if len(parts) >= 2 and parts[1].strip():
            version = parts[1].strip()
        elif parts and parts[0].strip():
            version = parts[0].strip()
    if family == "unknown" and uac6 == "1":
        family = "armclang"
    warning = None
    if family == "unknown":
        warning = KeilWarning(
            "KEIL_COMPILER_UNKNOWN",
            "compiler family could not be determined",
            (),
        )
    return family, version, warning


def _split_defines(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;]", raw):
        item = part.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _split_includes(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for part in raw.split(";"):
        item = part.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _extract_options(various_controls):
    if various_controls is None:
        return None
    defines = _split_defines(_text_of(various_controls, "Define"))
    include_paths = _split_includes(_text_of(various_controls, "IncludePath"))
    misc = _raw_text_of(various_controls, "MiscControls")
    misc_tuple = (misc,) if misc else ()
    if not defines and not include_paths and not misc_tuple:
        return None
    return defines, include_paths, misc_tuple


def _language_for(filetype: str | None, path: str) -> str:
    if filetype in _FILE_TYPE_LANGUAGES:
        return _FILE_TYPE_LANGUAGES[filetype]
    suffix = path.lower().rsplit(".", 1)[-1]
    return _SUFFIX_LANGUAGES.get("." + suffix, "other") if "." in path else "other"


def _collect_entries(target) -> list[tuple]:
    """Return ordered group/file records preserving document order."""
    entries: list[tuple] = []
    for groups_element in _iter_children(target, "Groups"):
        for group in _iter_children(groups_element, "Group"):
            group_name = _text_of(group, "GroupName") or ""
            group_options = _extract_options(
                _descendant(group, "GroupOption", "GroupArmAds", "Cads", "VariousControls")
            )
            if group_options is not None:
                entries.append(("group", group_name, group_options))
            for files_element in _iter_children(group, "Files"):
                for file_element in _iter_children(files_element, "File"):
                    file_name = _text_of(file_element, "FileName") or ""
                    file_type = _text_of(file_element, "FileType")
                    file_path = _text_of(file_element, "FilePath") or file_name
                    include_raw = _text_of(file_element, "IncludeInBuild")
                    included = include_raw != "0"
                    file_options = _extract_options(
                        _descendant(file_element, "FileOption", "FileArmAds", "Cads", "VariousControls")
                    )
                    entries.append(
                        ("source", group_name, file_name, file_type, file_path, included, file_options)
                    )
    return entries


# ---------------------------------------------------------------------------
# path validation
# ---------------------------------------------------------------------------


def _check_redirects(path: Path, root: Path, field: str) -> None:
    """Accept redirects whose canonical target stays in the root; reject escapes.

    Symlinks/reparse points (and NTFS junctions on Windows) are resolved to
    their canonical target and accepted when that target remains inside the
    canonical project root.  Escapes, cycles, resolution failures, and
    inspection errors are rejected conservatively.
    """
    _resolve_contained(path, root, field)


def _resolve_contained(path: Path, root: Path, field: str) -> Path:
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path resolution failed",
            {"field": field, "rule": "withinProjectRoot"},
        )
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path escapes the canonical project root",
            {"field": field, "rule": "withinProjectRoot"},
        )
    return resolved


def _normalize_keil_path(
    raw: str | None, base_dir: Path, root: Path, field: str, allow_dir: bool = False
) -> tuple[str, Path] | None:
    if raw is None:
        return None
    if "\x00" in raw:
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path contains a NUL byte",
            {"field": field, "rule": "withinProjectRoot"},
        )
    stripped = raw.strip()
    if not stripped:
        return None
    if (
        stripped.startswith("/")
        or stripped.startswith("\\")
        or _DRIVE_PREFIX_RE.match(stripped)
        or stripped.startswith("\\\\")
        or stripped.startswith("//")
    ):
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path form is not allowed",
            {"field": field, "rule": "withinProjectRoot"},
        )
    normalized = stripped.replace("\\", "/")
    parts = [component for component in normalized.split("/") if component not in ("", ".")]
    if not parts:
        if allow_dir:
            absolute = _resolve_contained(base_dir, root, field)
            root_relative = absolute.relative_to(root).as_posix()
            if not root_relative:
                root_relative = "."
            return root_relative, absolute
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path resolves to an empty location",
            {"field": field, "rule": "withinProjectRoot"},
        )
    # Keil paths are relative to the .uvprojx directory: resolve ``..`` from
    # base_dir first, then require the final canonical target inside the root.
    absolute = _resolve_contained(base_dir.joinpath(*parts), root, field)
    try:
        root_relative = absolute.relative_to(root).as_posix()
    except ValueError:
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path escapes the canonical project root",
            {"field": field, "rule": "withinProjectRoot"},
        )
    if not root_relative:
        root_relative = "."
    if not allow_dir and root_relative == ".":
        raise _raise(
            "KEIL_PATH_OUTSIDE_PROJECT",
            "path resolves to an empty location",
            {"field": field, "rule": "withinProjectRoot"},
        )
    return root_relative, absolute


def resolve_project_path(root: Path, relative: str) -> Path:
    """Revalidate a repository-relative path and return its resolved form."""
    candidate = root.joinpath(*relative.split("/"))
    return _resolve_contained(candidate, root, "artifact")


def _classify_path(abs_path: Path) -> str:
    try:
        os.stat(abs_path)
        return "ok"
    except FileNotFoundError:
        return "missing"
    except NotADirectoryError:
        return "missing"
    except OSError:
        return "unavailable"


# ---------------------------------------------------------------------------
# framework evidence
# ---------------------------------------------------------------------------


def _framework_evidence(
    defines: tuple[str, ...],
    include_paths: tuple[str, ...],
    sources: tuple[KeilSource, ...],
    scanned_includes: tuple[KeilEvidence, ...],
) -> tuple[KeilEvidence, ...]:
    evidence: list[KeilEvidence] = []

    def add(category: str, value: str, framework: str) -> None:
        item = KeilEvidence(category, value, framework)
        if item not in evidence:
            evidence.append(item)

    for define in defines:
        if define == "USE_STDPERIPH_DRIVER" or re.fullmatch(
            r"STM32F.*_StdPeriph_Driver", define, re.IGNORECASE
        ):
            add("define", define, "spl")
        if define == "USE_HAL_DRIVER":
            add("define", define, "hal")
        if define == "USE_FULL_LL_DRIVER":
            add("define", define, "ll")
    for include in scanned_includes:
        add(include.category, include.value, include.framework)

    all_paths = list(include_paths) + [source.path for source in sources]
    has_hal_driver_path = False
    ll_basenames: list[str] = []
    for path in all_paths:
        components = path.split("/")
        for index in range(len(components) - 1):
            if components[index].lower() == "libraries" and re.fullmatch(
                r"STM32.*_StdPeriph_Driver", components[index + 1], re.IGNORECASE
            ):
                add("path", f"{components[index]}/{components[index + 1]}", "spl")
            if components[index].lower() == "drivers" and re.fullmatch(
                r"STM32.*_HAL_Driver", components[index + 1], re.IGNORECASE
            ):
                add("path", f"{components[index]}/{components[index + 1]}", "hal")
                has_hal_driver_path = True
        basename = components[-1]
        if "_ll_" in basename.lower():
            ll_basenames.append(basename)
    if has_hal_driver_path:
        for basename in ll_basenames:
            add("path", basename, "ll")
    return tuple(evidence)


def _select_framework(
    evidence: tuple[KeilEvidence, ...],
) -> tuple[str | None, tuple[str, ...], KeilWarning | None]:
    categories: dict[str, set[str]] = {}
    for item in evidence:
        categories.setdefault(item.framework, set()).add(item.category)
    candidates = tuple(sorted(categories))
    qualified = [framework for framework in candidates if len(categories[framework]) >= 2]
    if len(qualified) == 1:
        return qualified[0], candidates, None
    if candidates:
        warning = KeilWarning(
            "KEIL_FRAMEWORK_SELECTION_REQUIRED",
            "framework evidence is ambiguous or insufficient",
            (("candidates", candidates),),
        )
        return None, candidates, warning
    return None, candidates, None


# ---------------------------------------------------------------------------
# input hashing
# ---------------------------------------------------------------------------


def _hash_inputs(entries: list[tuple[str, Path, int]]) -> tuple[KeilInputDigest, ...]:
    """Bounded reads; re-enforce the per-file limit on the actual bytes read."""
    digests: list[KeilInputDigest] = []
    for relative, absolute, limit in entries:
        try:
            data = _read_limited(absolute, limit)
        except OSError:
            continue
        if len(data) > limit:
            raise _raise(
                "KEIL_SCAN_LIMIT_EXCEEDED",
                "input exceeds the per-file scan limit",
                {"limitBytes": limit, "scope": "file"},
            )
        digests.append(
            KeilInputDigest(relative, hashlib.sha256(data).hexdigest(), len(data))
        )
    return tuple(digests)


def _normalize_option_includes(
    includes: tuple[str, ...], base_dir: Path, root: Path
) -> tuple[str, ...]:
    """Normalize scoped-option include paths to POSIX repository-relative form."""
    result: list[str] = []
    for raw in includes:
        normalized = _normalize_keil_path(raw, base_dir, root, "includePath", allow_dir=True)
        if normalized is None:
            continue
        result.append(normalized[0])
    return tuple(result)


# ---------------------------------------------------------------------------
# inspection orchestration
# ---------------------------------------------------------------------------


def inspect_keil(
    root: Path,
    uvprojx: Path | None = None,
    target_name: str | None = None,
) -> KeilInspection:
    canonical_root = _validate_root(root)
    project_rel, project_abs = _select_project(canonical_root, uvprojx)
    tree, project_sha256, project_size = _read_project(project_abs, project_rel)
    selected_name, target = _select_target(_collect_targets(tree), target_name)

    target_option = _descendant(target, "TargetOption")
    common = _descendant(target_option, "TargetCommonOption")
    device = _text_of(common, "Device")
    if not device:
        raise _raise(
            "KEIL_TARGET_INVALID",
            "selected target has no device",
            {"field": "device", "rule": "missing"},
        )
    pack_id = _text_of(common, "PackID")
    cpu_text = _text_of(common, "Cpu") or ""
    cpu, fpu = _parse_cpu(cpu_text)
    float_abi = _text_of(common, "uFloatingPoint")
    compiler, compiler_version, compiler_warning = _parse_compiler(target)
    memory_regions = _parse_memory(cpu_text, target_option)

    arm_ads = _descendant(target_option, "TargetArmAds")
    target_options = _extract_options(_descendant(arm_ads, "Cads", "VariousControls"))
    defines = target_options[0] if target_options else ()
    raw_include_paths = target_options[1] if target_options else ()
    target_misc = target_options[2] if target_options else ()
    ldads = _descendant(arm_ads, "LDads", "VariousControls")
    scatter_raw = _text_of(ldads, "ScatterFile")
    linker_misc = _text_of(ldads, "MiscControls") or ""

    base_dir = project_abs.parent
    out_dir = _normalize_keil_path(
        _text_of(target_option, "OutputDirectory"), base_dir, canonical_root, "outputDirectory"
    )
    listing_dir = _normalize_keil_path(
        _text_of(target_option, "ListingPath"), base_dir, canonical_root, "listingDirectory"
    )
    out_name_raw = _text_of(target_option, "OutputName")
    output_name = out_name_raw.strip() if out_name_raw and out_name_raw.strip() else None
    object_directory = out_dir[0] if out_dir else None
    listing_directory = listing_dir[0] if listing_dir else None
    axf = f"{object_directory}/{output_name}.axf" if object_directory and output_name else None
    map_file = f"{object_directory}/{output_name}.map" if object_directory and output_name else None
    scatter = _normalize_keil_path(scatter_raw, base_dir, canonical_root, "scatter")

    warnings: list[KeilWarning] = []
    if compiler_warning is not None:
        warnings.append(compiler_warning)

    scoped_options: list[KeilScopedOptions] = []
    if target_options is not None:
        scoped_options.append(
            KeilScopedOptions(
                "target",
                selected_name,
                True,
                target_options[0],
                _normalize_option_includes(target_options[1], base_dir, canonical_root),
                target_options[2],
            )
        )

    sources: list[KeilSource] = []
    seen_paths: set[str] = set()
    absolute_by_path: dict[str, Path] = {}
    for entry in _collect_entries(target):
        if entry[0] == "group":
            _, group_name, group_options = entry
            scoped_options.append(
                KeilScopedOptions(
                    "group",
                    group_name,
                    True,
                    group_options[0],
                    _normalize_option_includes(group_options[1], base_dir, canonical_root),
                    group_options[2],
                )
            )
            continue
        _, group_name, file_name, file_type, file_path, included, file_options = entry
        normalized = _normalize_keil_path(file_path, base_dir, canonical_root, "source")
        if normalized is None:
            raise _raise(
                "KEIL_TARGET_INVALID",
                "source entry has no path",
                {"field": "source", "rule": "missing"},
            )
        source_rel, source_abs = normalized
        language = _language_for(file_type, file_path)
        if source_rel in seen_paths:
            warnings.append(
                KeilWarning(
                    "KEIL_DUPLICATE_SOURCE",
                    "duplicate source path",
                    (("path", source_rel),),
                )
            )
            continue
        seen_paths.add(source_rel)
        absolute_by_path[source_rel] = source_abs
        kind = _classify_path(source_abs)
        if kind == "missing":
            warnings.append(
                KeilWarning(
                    "KEIL_SOURCE_MISSING",
                    "referenced source is missing",
                    (("path", source_rel),),
                )
            )
        elif kind == "unavailable":
            raise _raise(
                "KEIL_PATH_OUTSIDE_PROJECT",
                "source path inspection failed",
                {"field": "source", "rule": "withinProjectRoot"},
            )
        sources.append(KeilSource(source_rel, group_name, language, included))
        if file_options is not None:
            scoped_options.append(
                KeilScopedOptions(
                    "file",
                    source_rel,
                    included,
                    file_options[0],
                    _normalize_option_includes(file_options[1], base_dir, canonical_root),
                    file_options[2],
                )
            )

    include_paths: list[str] = []
    for raw_include in raw_include_paths:
        normalized = _normalize_keil_path(
            raw_include, base_dir, canonical_root, "includePath", allow_dir=True
        )
        if normalized is None:
            continue
        include_rel, include_abs = normalized
        kind = _classify_path(include_abs)
        if kind == "missing":
            warnings.append(
                KeilWarning(
                    "KEIL_INCLUDE_PATH_MISSING",
                    "referenced include path is missing",
                    (("path", include_rel),),
                )
            )
        elif kind == "unavailable":
            raise _raise(
                "KEIL_PATH_OUTSIDE_PROJECT",
                "include path inspection failed",
                {"field": "includePath", "rule": "withinProjectRoot"},
            )
        include_paths.append(include_rel)

    scatter_rel = scatter[0] if scatter else None
    scatter_abs = scatter[1] if scatter else None
    if scatter_abs is not None:
        kind = _classify_path(scatter_abs)
        if kind == "unavailable":
            raise _raise(
                "KEIL_PATH_OUTSIDE_PROJECT",
                "scatter path inspection failed",
                {"field": "scatter", "rule": "withinProjectRoot"},
            )

    linker_findings = armcc_scan.linker_findings(scatter_rel, linker_misc)
    scan_inputs = [
        (source.path, absolute_by_path[source.path], source.language)
        for source in sources
        if source.included and source.language in _SCANNED_LANGUAGES
    ]
    scan_outcome = armcc_scan.scan_sources(scan_inputs)
    for unreadable_rel in scan_outcome.unreadable:
        warnings.append(
            KeilWarning(
                "KEIL_SOURCE_UNAVAILABLE",
                "referenced source is unreadable",
                (("path", unreadable_rel),),
            )
        )
    findings = tuple(
        sorted(
            linker_findings + scan_outcome.findings,
            key=lambda finding: (finding.path, finding.line, finding.column, finding.rule_id),
        )
    )

    evidence = _framework_evidence(
        defines,
        tuple(include_paths),
        tuple(sources),
        scan_outcome.include_evidence,
    )
    framework, framework_candidates, framework_warning = _select_framework(evidence)
    if framework_warning is not None:
        warnings.append(framework_warning)

    hash_entries: list[tuple[str, Path, int]] = []
    for source_rel in scan_outcome.read:
        hash_entries.append(
            (source_rel, absolute_by_path[source_rel], armcc_scan.SCAN_FILE_LIMIT)
        )
    if scatter_abs is not None and _classify_path(scatter_abs) == "ok":
        try:
            if scatter_abs.stat().st_size > armcc_scan.SCAN_FILE_LIMIT:
                raise _raise(
                    "KEIL_SCAN_LIMIT_EXCEEDED",
                    "scatter file exceeds the per-file limit",
                    {"limitBytes": armcc_scan.SCAN_FILE_LIMIT, "scope": "file"},
                )
        except FileNotFoundError:
            pass
        else:
            hash_entries.append((scatter_rel, scatter_abs, armcc_scan.SCAN_FILE_LIMIT))

    digests = [KeilInputDigest(project_rel, project_sha256, project_size)]
    digests.extend(_hash_inputs(hash_entries))
    inputs = tuple(sorted(digests, key=lambda digest: digest.path))

    linker_inputs = tuple(
        dict.fromkeys(
            source.path for source in sources if source.language == "library" and source.included
        )
    )

    return KeilInspection(
        project_root=canonical_root,
        project_file=project_rel,
        project_sha256=project_sha256,
        target_name=selected_name,
        device=device,
        device_pack=pack_id,
        cpu=cpu,
        fpu=fpu,
        float_abi=float_abi,
        compiler=compiler,
        compiler_version=compiler_version,
        defines=defines,
        include_paths=tuple(include_paths),
        sources=tuple(sources),
        scoped_options=tuple(scoped_options),
        linker_inputs=linker_inputs,
        memory_regions=memory_regions,
        output=KeilOutputSpec(
            object_directory,
            listing_directory,
            output_name,
            axf,
            map_file,
            scatter_rel,
        ),
        framework=framework,
        framework_candidates=framework_candidates,
        framework_evidence=evidence,
        findings=findings,
        warnings=tuple(warnings),
        inputs=inputs,
    )
