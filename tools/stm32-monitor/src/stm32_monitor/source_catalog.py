"""Offline source-variable pages and rechecked draft selection for Monitor."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Mapping

from stm32_toolkit.build.identity import snapshot_project_inputs, LEGACY_INPUT_DISCOVERY_POLICY, SOURCE_LOCAL_HEADERS_POLICY
from stm32_toolkit.debug.dwarf import DwarfCatalog, DwarfSourceFunction, DwarfSourceSymbol
from stm32_toolkit.debug.source import ClangSourceAdapter, SourceCatalogError, SourceDeclaration, SourceFunction, SourceIndex, SourceIssue, SourcePlan
from stm32_toolkit.debug.types import DwarfError, DwarfType
from stm32_toolkit.probe.flash import load_fresh_firmware_facts
from stm32_toolkit.probe.protocol import MAX_READ_BYTES
from stm32_toolkit.project_model import ProjectModel, load_project_model


_ID = re.compile(r"[0-9a-f]{64}\Z")
_EXPRESSION = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SCALAR = frozenset({"integer", "boolean", "float", "enum", "pointer"})
_CURSOR_KEY = secrets.token_bytes(32)
_PAGE_DATA_BUDGET = 900 * 1024  # Leave envelope/error metadata below the service's 1 MiB cap.
_MAX_CURSOR_LENGTH = 2048
_MAX_MERGED_DECLARATIONS = 100_000
_MAX_NORMALIZED_FUNCTIONS = 100_000


class SourceCatalogFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _Facts:
    model: ProjectModel
    source_sha: str
    build_id: str | None
    elf_sha: str | None
    elf_path: str | None
    elf_size: int | None
    source_files: tuple[str, ...] = ()
    snapshot_paths: tuple[str, ...] = ()
    policy: str = SOURCE_LOCAL_HEADERS_POLICY


@dataclass(frozen=True)
class _Base:
    index: SourceIndex
    dwarf: DwarfCatalog | None
    source_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceItem:
    id: str
    parent_id: str | None
    name: str
    type_name: str
    file: str
    line: int | None
    column: int | None
    scope_kind: str
    function: str | None
    scope_path: tuple[str, ...]
    storage: str
    translation_units: tuple[str, ...]
    selector: str | None
    can_add: bool
    reason: str | None
    expandable: bool
    truncated: bool
    function_id: str | None = None  # Private tree ownership; not part of the wire item.
    declaration_kind: str = "unknown"
    definition_site: tuple[str, int] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "parentId": self.parent_id, "name": self.name,
            "typeName": self.type_name, "file": self.file,
            "line": self.line, "column": self.column,
            "scope": {"kind": self.scope_kind, "function": self.function,
                      "path": list(self.scope_path)},
            "storage": self.storage, "translationUnits": list(self.translation_units),
            "selector": self.selector, "canAdd": self.can_add, "reason": self.reason,
            "expandable": self.expandable, "truncated": self.truncated,
            "declaration": {"kind": self.declaration_kind,
                            "definitionSite": ({"file": self.definition_site[0],
                                                "line": self.definition_site[1]}
                                               if self.definition_site is not None else None)},
        }


@dataclass
class _Node:
    item: SourceItem
    dwarf_type: DwarfType | None
    depth: int
    descendants: int
    address: int | None = None


@dataclass
class _View:
    catalog_id: str
    identity: dict[str, object]
    index: SourceIndex
    dwarf: DwarfCatalog | None
    roots: tuple[SourceItem, ...]
    nodes: dict[str, _Node]
    binding: object | None
    binding_ok: bool
    children_cache: dict[str, tuple[tuple[SourceItem, ...], int]]
    binding_signature: tuple[object, ...] = ()
    source_files: tuple[str, ...] = ()
    file_nodes: tuple[dict[str, object], ...] = ()
    scopes_by_file: dict[str, tuple[dict[str, object], ...]] | None = None
    roots_by_scope: dict[str, tuple[SourceItem, ...]] | None = None
    file_by_id: dict[str, str] | None = None
    scope_by_id: dict[str, dict[str, object]] | None = None
    compiled_debug: dict[str, object] | None = None
    policy: str = SOURCE_LOCAL_HEADERS_POLICY


def _offline_facts(root: Path) -> _Facts:
    model = load_project_model(root)
    firmware = None
    try:
        firmware = load_fresh_firmware_facts(root)
    except Exception:
        pass
    policy = firmware.input_discovery_policy if firmware is not None else SOURCE_LOCAL_HEADERS_POLICY
    snapshot = snapshot_project_inputs(model, policy=policy)
    source_sha = snapshot.sha256
    declared = set(model.build.sources) | set(model.build.assembly_sources)
    source_files = tuple(entry.path for entry in snapshot.entries
                         if entry.path in declared or entry.path.lower().endswith((".c", ".h")))
    build_id = elf_sha = elf_path = None
    elf_size = None
    if firmware is not None and firmware.input_snapshot_sha256 == source_sha:
        build_id, elf_sha, elf_path = firmware.build_id, firmware.elf_sha256, firmware.elf_path
        elf_size = (root / elf_path).stat().st_size
    return _Facts(model, source_sha, build_id, elf_sha, elf_path, elf_size, source_files,
                  tuple(entry.path for entry in snapshot.entries), policy)


def _readable_regions(model: ProjectModel) -> tuple[tuple[int, int], ...]:
    return tuple((region.origin, region.origin + region.length)
                 for region in model.memory.regions if "r" in region.attributes)


def _load_base(adapter: ClangSourceAdapter, facts: _Facts, plan: SourcePlan) -> _Base:
    index = adapter.index(facts.model, plan)
    verified = set(facts.source_files)
    # Source/assembly declarations and snapshot C headers are authoritative.
    # Other extensions join the tree only when the same snapshot contains AST facts.
    snapshot_files = set(facts.snapshot_paths)
    untracked = {entry.file for entry in (*index.declarations, *index.functions)
                 if entry.file not in snapshot_files}
    if untracked:
        if facts.policy == LEGACY_INPUT_DISCOVERY_POLICY:
            code = "MONITOR_SOURCE_UNTRACKED_AST"
            message = lambda path: (f"{path} is outside the verified legacy build snapshot; "
                                    "perform a clean firmware rebuild to include this header")
        else:
            code = "MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY"
            message = lambda path: (f"{path} is outside the verified {facts.policy} build snapshot; "
                                    "verify project source and include-directory declarations, "
                                    "then perform a clean firmware rebuild")
        warnings = tuple(SourceIssue(path, code, message(path))
                         for path in sorted(untracked, key=lambda value: (value.casefold(), value)))
        index = replace(index,
                        declarations=tuple(entry for entry in index.declarations if entry.file not in untracked),
                        functions=tuple(entry for entry in index.functions if entry.file not in untracked),
                        issues=(*index.issues, *warnings))
    functions = {function.id for function in index.functions}
    unbound = tuple(entry for entry in index.declarations
                    if (entry.function is not None or entry.scope_kind in {"local", "static_local", "parameter"})
                    and entry.function_id not in functions)
    if unbound:
        unbound_ids = {entry.id for entry in unbound}
        index = replace(index,
                        declarations=tuple(entry for entry in index.declarations if entry.id not in unbound_ids),
                        issues=(*index.issues, SourceIssue(None, "MONITOR_SOURCE_FUNCTION_UNBOUND",
                                                          f"{len(unbound)} local declaration(s) had no verified function scope")))
    verified.update(entry.file for entry in (*index.declarations, *index.functions)
                    if entry.file in snapshot_files)
    if len(verified) > 10_000:
        raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source file limit was reached")
    dwarf = None
    if facts.elf_path is not None and facts.elf_sha is not None and facts.elf_size is not None:
        try:
            dwarf = DwarfCatalog.from_elf(
                facts.elf_path, project_root=facts.model.project_root,
                expected_elf_size=facts.elf_size, expected_elf_sha256=facts.elf_sha,
                readable_regions=_readable_regions(facts.model),
            )
            if dwarf.source_metadata_truncated:
                raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Compiled source metadata limit was reached")
        except DwarfError as error:
            if error.code == "DWARF_CATALOG_LIMIT_EXCEEDED":
                raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Compiled debug directory limit was reached") from error
    after = _offline_facts(facts.model.project_root)
    if (after.policy, after.source_sha, after.build_id, after.elf_sha) != (facts.policy, facts.source_sha, facts.build_id, facts.elf_sha):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed while indexing")
    return _Base(index, dwarf, tuple(sorted(verified, key=lambda path: (path.casefold(), path))))


def _binding_signature(binding: object | None) -> tuple[object, ...]:
    if binding is None:
        return ()
    identity = tuple(getattr(binding, key, None) for key in
                     ("workspace_id", "observation_session_id", "logical_project_id",
                      "target_device", "build_id", "elf_sha256", "input_snapshot_sha256",
                      "probe_id", "lease_id", "flash_session_id", "git_head", "git_dirty"))
    regions = tuple((getattr(region, "name", None), getattr(region, "origin", None),
                     getattr(region, "length", None), getattr(region, "attributes", None))
                    for region in getattr(binding, "memory_regions", ()))
    return identity + (regions,)


def _binding_matches(binding: object | None, facts: _Facts, workspace: str, session: str) -> bool:
    if binding is None or facts.build_id is None or facts.elf_sha is None:
        return False
    return (getattr(binding, "project_root", None) == facts.model.project_root
            and getattr(binding, "workspace_id", None) == workspace
            and getattr(binding, "observation_session_id", None) == session
            and getattr(binding, "logical_project_id", None) == str(facts.model.logical_project_id)
            and getattr(binding, "target_device", None) == facts.model.target.device
            and getattr(binding, "build_id", None) == facts.build_id
            and getattr(binding, "elf_sha256", None) == facts.elf_sha
            and getattr(binding, "input_snapshot_sha256", None) == facts.source_sha)


def _normalized_type(value: str) -> str:
    value = re.sub(r"\b(?:const|volatile|restrict|_Atomic|signed|struct|union|enum)\b", "", value)
    return re.sub(r"\s+", "", value)


def _compatible(source: SourceDeclaration, dwarf_type: DwarfType | None) -> bool:
    if dwarf_type is None:
        return False
    text = _normalized_type(source.type_name)
    names = {dwarf_type.name, *dwarf_type.aliases}
    if dwarf_type.kind == "array" and dwarf_type.element_type is not None:
        names.update({dwarf_type.element_type.name, *dwarf_type.element_type.aliases})
        text = text.split("[", 1)[0]
    if dwarf_type.kind == "pointer" and dwarf_type.pointee_type is not None:
        names.update({dwarf_type.pointee_type.name + "*", *(alias + "*" for alias in dwarf_type.pointee_type.aliases)})
    return text in {_normalized_type(name) for name in names}


def _compatible_cu(candidate: SourceDeclaration, symbol: DwarfSourceSymbol) -> bool:
    internal = (candidate.scope_kind in {"file_static", "static_local"}
                or candidate.storage == "static"
                or symbol.scope_kind in {"file_static", "static_local"}
                or symbol.storage == "static")
    if internal:
        return (symbol.compilation_unit is not None
                and symbol.compilation_unit in candidate.translation_units)
    return (symbol.compilation_unit is None
            or symbol.compilation_unit in candidate.translation_units)


def _usable_source_site(candidate: SourceDeclaration) -> bool:
    return (type(candidate.line) is int and candidate.line > 0 and
            type(candidate.column) is int and candidate.column > 0)


def _direct_match(candidate: SourceDeclaration, symbol: DwarfSourceSymbol) -> bool:
    return (_usable_source_site(candidate) and
            candidate.name == symbol.name and candidate.file == symbol.file
            and candidate.line == symbol.line
            and candidate.function == symbol.function
            and (symbol.column is None or candidate.column == symbol.column)
            and candidate.scope_kind == symbol.scope_kind
            and (candidate.storage == symbol.storage or
                 candidate.storage == "extern" and symbol.storage == "none")
            and _compatible(candidate, symbol.dwarf_type)
            and _compatible_cu(candidate, symbol))


def _role(decl: SourceDeclaration) -> str:
    if decl.storage == "thread_local":
        return "unknown"
    if decl.scope_kind == "parameter":
        return "parameter"
    if decl.scope_kind == "local":
        return "automatic_local"
    if decl.scope_kind == "static_local":
        return "static_local"
    if decl.scope_kind == "file_static":
        return "file_static"
    if decl.storage == "extern" and not decl.is_definition:
        return "extern_declaration"
    return "global_definition" if decl.is_definition or decl.storage == "none" else "unknown"


def _chain_compatible(decl: SourceDeclaration, definition: SourceDeclaration,
                      symbol: DwarfSourceSymbol) -> bool:
    """A previousDecl link must preserve linkage, scope and the exact TU."""
    role = _role(decl)
    if (decl.name != definition.name or
            _normalized_type(decl.type_name) != _normalized_type(definition.type_name) or
            not _compatible(decl, symbol.dwarf_type) or
            symbol.kind != "variable"):
        return False
    if role in {"extern_declaration", "global_definition"}:
        return (_role(definition) == "global_definition" and
                definition.scope_kind == decl.scope_kind == symbol.scope_kind == "global" and
                definition.storage in {"none", "extern"} and
                symbol.storage in {"none", "extern"} and
                definition.function is decl.function is symbol.function is None and
                not definition.scope_path and not decl.scope_path and not symbol.scope_path)
    if role in {"file_static", "static_local"}:
        return (_role(definition) == role and
                definition.scope_kind == decl.scope_kind == symbol.scope_kind and
                definition.storage == decl.storage == symbol.storage == "static" and
                definition.function == decl.function == symbol.function and
                definition.scope_path == decl.scope_path == symbol.scope_path and
                definition.function_id == decl.function_id)
    return False


def _match(decl: SourceDeclaration,
           symbols_by_name: Mapping[str, tuple[DwarfSourceSymbol, ...]],
           entity_proofs: Mapping[tuple[str, str], tuple[tuple[SourceDeclaration, DwarfSourceSymbol], ...]]) -> tuple[DwarfSourceSymbol | None, str | None, tuple[str, int] | None]:
    if not _usable_source_site(decl):
        return None, "source_attribution_unproven", None
    same_name = symbols_by_name.get(decl.name, ())
    if not same_name:
        return None, "debug_entry_missing", None
    direct = tuple(symbol for symbol in same_name if _direct_match(decl, symbol))
    if decl.storage == "thread_local":
        return None, "unsupported_location", None
    if _role(decl) == "extern_declaration":
        direct = ()  # A declaration alone never proves an external definition.
    if len(direct) > 1:
        return None, "ambiguous_symbol", None
    # A declaration can be proved by a Clang previousDecl chain to an exact
    # DWARF anchor in the same TU. Name/CU proximity alone never admits it.
    if _role(decl) in {"extern_declaration", "global_definition", "file_static", "static_local"}:
        proved: dict[tuple[str, int, int], tuple[SourceDeclaration, DwarfSourceSymbol]] = {}
        for unit, entity in decl.entity_by_unit or tuple((unit, decl.entity_id) for unit in decl.translation_units):
            for definition, symbol in entity_proofs.get((unit, entity), ()):
                if (symbol not in same_name or symbol.compilation_unit != unit
                        or not _chain_compatible(decl, definition, symbol)):
                    continue
                if symbol.cu_offset is None or symbol.die_offset is None:
                    continue
                proved[(unit, symbol.cu_offset, symbol.die_offset)] = definition, symbol
        unique = {(definition.file, definition.line, symbol.address,
                   symbol.cu_offset, symbol.die_offset)
                  for definition, symbol in proved.values()}
        if len(unique) == 1:
            definition, symbol = next(iter(proved.values()))
            if direct and direct[0] != symbol:
                return None, "ambiguous_symbol", None
            return symbol, None, (definition.file, definition.line)
        if len(unique) > 1:
            return None, "ambiguous_symbol", None
    if len(direct) == 1:
        site = (decl.file, decl.line) if decl.is_definition or _role(decl) in {
            "global_definition", "file_static", "static_local"} else None
        return direct[0], None, site
    if len(same_name) > 1:
        return None, "ambiguous_symbol", None
    return None, "source_attribution_unproven", None


def _eligible_leaf(selector: str, dwarf: DwarfCatalog | None, binding: object | None,
                   expected: DwarfSourceSymbol | None = None) -> str | None:
    if dwarf is None:
        return "firmware_unavailable"
    try:
        selected = dwarf.lookup(selector)
    except DwarfError as error:
        if error.code == "DWARF_SYMBOL_AMBIGUOUS":
            return "ambiguous_symbol"
        if error.code == "DWARF_SYMBOL_NOT_FOUND":
            return "debug_entry_missing"
        if error.code == "DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY":
            return "read_range_denied"
        if error.code.startswith("DWARF_TYPE") or error.code in {"DWARF_BITFIELD_UNSUPPORTED", "DWARF_ARRAY_INDEX_OUT_OF_RANGE"}:
            return "unsupported_type"
        return "unsupported_location"
    if expected is not None and (expected.address is None or selected.address != expected.address
                                 or expected.dwarf_type != selected.type):
        return "source_attribution_unproven"
    if selected.type.kind not in _SCALAR or selected.byte_size > MAX_READ_BYTES:
        return "unsupported_type"
    if binding is None:
        return "probe_required"
    regions = getattr(binding, "memory_regions", ())
    if not any("r" in getattr(region, "attributes", "")
               and selected.address >= getattr(region, "origin", -1)
               and selected.address + selected.byte_size <= getattr(region, "origin", -1) + getattr(region, "length", 0)
               for region in regions):
        return "read_range_denied"
    return None


def _possible_scalar(dtype: DwarfType, depth: int) -> bool:
    if depth > 6:
        return False
    if dtype.kind in _SCALAR:
        return 0 < dtype.byte_size <= MAX_READ_BYTES
    if dtype.kind == "array":
        return (dtype.element_type is not None and dtype.element_count is not None
                and dtype.element_count > 0 and _possible_scalar(dtype.element_type, depth + 1))
    if dtype.kind in {"structure", "union"}:
        names = Counter(member.name for member in dtype.members)
        return any(member.bit_size is None and _EXPRESSION.fullmatch(member.name)
                   and names[member.name] == 1 and _possible_scalar(member.type, depth + 1)
                   for member in dtype.members)
    return False


def _array_candidate_indices(dwarf: DwarfCatalog, address: int,
                             stride: int, admitted: int):
    """Visit only array elements intersecting project-readable memory."""
    intervals = getattr(dwarf, "readable_regions", None)
    if not intervals:
        yield from range(admitted)
        return
    last = -1
    for start, end in intervals:
        low = max(last + 1, 0, (start - address - stride + 1) // stride)
        high = min(admitted - 1, (end - address - 1) // stride)
        if low <= high:
            yield from range(low, high + 1)
            last = high


def _observable_descendant(selector: str, dtype: DwarfType, dwarf: DwarfCatalog | None,
                           address: int | None, depth: int, budget: list[int]) -> bool:
    """Find a reader-proved scalar within the finite expansion envelope."""
    if dwarf is None or address is None or not _possible_scalar(dtype, depth):
        return False
    if dtype.kind in _SCALAR:
        if budget[0] <= 0:
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Observable directory scan reached its bound")
        budget[0] -= 1
        return _eligible_leaf(selector, dwarf, None) == "probe_required"
    if depth >= 6:
        return False
    if dtype.kind in {"structure", "union"}:
        names = Counter(member.name for member in dtype.members)
        for member in dtype.members[:4096]:
            if (member.bit_size is not None or not _EXPRESSION.fullmatch(member.name)
                    or names[member.name] != 1):
                continue
            if _observable_descendant(f"{selector}.{member.name}", member.type, dwarf,
                                      address + member.offset, depth + 1, budget):
                return True
        if len(dtype.members) > 4096:
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Observable directory scan reached its bound")
        return False
    element = dtype.element_type
    count = dtype.element_count
    if dtype.kind != "array" or element is None or count is None or element.byte_size <= 0:
        return False
    admitted = min(count, 4096)
    for index in _array_candidate_indices(dwarf, address, element.byte_size, admitted):
        if _observable_descendant(f"{selector}[{index}]", element, dwarf,
                                  address + index * element.byte_size,
                                  depth + 1, budget):
            return True
    if count > admitted:
        raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Observable directory scan reached its bound")
    return False


def _root_observable(item: SourceItem, dtype: DwarfType | None,
                     dwarf: DwarfCatalog | None, symbol: DwarfSourceSymbol | None) -> bool:
    if (item.selector is None or item.scope_kind in {"local", "parameter"}
            or dwarf is None or symbol is None or symbol.address is None
            or symbol.location_error is not None or symbol.type_error is not None):
        return False
    if dtype is None:
        return _eligible_leaf(item.selector, dwarf, None, symbol) == "probe_required"
    return _observable_descendant(item.selector, dtype, dwarf, symbol.address, 0, [4096])


def _context_reason(index: SourceIndex, facts: _Facts, binding: object | None,
                    binding_ok: bool) -> str | None:
    if facts.build_id is None:
        return "firmware_unavailable"
    if binding is None:
        return "probe_required"
    if not binding_ok:
        return "source_mismatch"
    return None


def _item_for_declaration(decl: SourceDeclaration,
                          symbols_by_name: Mapping[str, tuple[DwarfSourceSymbol, ...]],
                          entity_proofs: Mapping[tuple[str, str], tuple[tuple[SourceDeclaration, DwarfSourceSymbol], ...]],
                          dwarf: DwarfCatalog | None,
                          context_reason: str | None, binding: object | None) -> tuple[SourceItem, DwarfType | None]:
    symbol, reason, definition_site = _match(decl, symbols_by_name, entity_proofs)
    dtype = symbol.dwarf_type if symbol is not None else None
    selector = decl.name if symbol is not None and _EXPRESSION.fullmatch(decl.name) else None
    if decl.scope_kind in {"local", "parameter"}:
        if symbol is not None:
            reason = ("frame_required" if symbol.location_kind in {"frame", "register"}
                      else "unsupported_location")
        selector = None
    elif context_reason in {"firmware_unavailable", "source_mismatch"}:
        reason = context_reason
    elif symbol is not None:
        if symbol.type_error is not None or dtype is None:
            reason = "unsupported_type"
        elif symbol.address is None or symbol.location_error is not None:
            reason = "unsupported_location"
        elif dtype.kind in {"structure", "union", "array"}:
            reason = "aggregate"
        else:
            reason = _eligible_leaf(decl.name, dwarf, binding, symbol)
    if reason is None:
        reason = context_reason
    expandable = bool(symbol is not None and selector is not None and dtype is not None
                      and dtype.kind in {"structure", "union", "array"}
                      and symbol.address is not None and symbol.location_error is None
                      and decl.scope_kind not in {"local", "parameter"})
    aggregate_size = (dtype.element_count if dtype.kind == "array" else len(dtype.members)) if expandable and dtype is not None else 0
    return SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                      decl.column, decl.scope_kind, decl.function, decl.scope_path,
                      decl.storage, decl.translation_units, selector, reason is None,
                      reason, expandable, aggregate_size is not None and aggregate_size > 4096,
                      decl.function_id, _role(decl), definition_site), dtype if expandable else None


def _dwarf_function_id(cu_offset: int, die_offset: int) -> str:
    return f"dwarf:{cu_offset:x}:{die_offset:x}"


def _item_for_dwarf(symbol: DwarfSourceSymbol, dwarf: DwarfCatalog,
                    context_reason: str | None, binding: object | None,
                    source_decl: SourceDeclaration | None = None,
                    proved_definition_site: tuple[str, int] | None = None) -> tuple[SourceItem, DwarfType | None]:
    assert symbol.file is not None and symbol.cu_offset is not None and symbol.die_offset is not None
    dtype = symbol.dwarf_type
    type_name = dtype.name if dtype is not None and len(dtype.name) <= 512 else "<unknown>"
    selector = symbol.name if symbol.kind == "variable" and _EXPRESSION.fullmatch(symbol.name) else None
    if symbol.scope_kind in {"local", "parameter"}:
        reason = ("frame_required" if symbol.location_kind in {"frame", "register"}
                  else "unsupported_location")
    elif context_reason in {"firmware_unavailable", "source_mismatch"}:
        reason = context_reason
    elif symbol.type_error is not None or dtype is None or type_name == "<unknown>":
        reason = "unsupported_type"
    elif symbol.address is None or symbol.location_error is not None:
        reason = "unsupported_location"
    elif dtype.kind in {"structure", "union", "array"}:
        reason = "aggregate"
    else:
        reason = _eligible_leaf(symbol.name, dwarf, binding, symbol)
    if reason is None:
        reason = context_reason
    expandable = bool(selector is not None and dtype is not None
                      and dtype.kind in {"structure", "union", "array"}
                      and symbol.address is not None and symbol.location_error is None
                      and symbol.scope_kind not in {"local", "parameter"})
    aggregate_size = (dtype.element_count if dtype.kind == "array" else len(dtype.members)) if expandable and dtype is not None else 0
    identifier = _source_id("dwarf", f"{dwarf.elf_sha256}:{symbol.cu_offset:x}:{symbol.die_offset:x}")
    function_id = (_dwarf_function_id(symbol.cu_offset, symbol.function_die_offset)
                   if symbol.function_die_offset is not None else None)
    role = _role(source_decl) if source_decl is not None else "unknown"
    definition_site = proved_definition_site or ((source_decl.file, source_decl.line) if source_decl is not None and (
        source_decl.is_definition or role in {"global_definition", "file_static", "static_local"}
    ) and source_decl.line is not None else None)
    item = SourceItem(identifier, None, symbol.name, type_name, symbol.file, symbol.line,
                      symbol.column, symbol.scope_kind, symbol.function, symbol.scope_path,
                      symbol.storage, (symbol.compilation_unit or symbol.file,), selector,
                      reason is None, reason, expandable,
                      aggregate_size is not None and aggregate_size > 4096, function_id,
                      role, definition_site)
    return item, dtype if expandable else None


def _materialize(index: SourceIndex, dwarf: DwarfCatalog | None,
                 context: str | None, binding: object | None,
                 source_files: tuple[str, ...] | None = None,
                 max_declarations: int = _MAX_MERGED_DECLARATIONS) -> tuple[tuple[SourceItem, ...], dict[str, _Node]]:
    allowed = set(source_files) if source_files is not None else None
    symbols_by_name: dict[str, list[DwarfSourceSymbol]] = {}
    declarations = (dwarf.source_declarations() if dwarf is not None and
                    hasattr(dwarf, "source_declarations") else
                    dwarf.source_symbols() if dwarf is not None else ())
    for symbol in declarations:
        if allowed is not None and symbol.file not in allowed:
            continue
        symbols_by_name.setdefault(symbol.name, []).append(symbol)
    frozen_symbols = {name: tuple(group) for name, group in symbols_by_name.items()}
    group: dict[tuple[str, str], list[SourceDeclaration]] = {}
    anchors: dict[tuple[str, str], list[tuple[SourceDeclaration, DwarfSourceSymbol]]] = {}
    decorations: dict[int, list[SourceDeclaration]] = {}
    for declaration in index.declarations:
        pairs = declaration.entity_by_unit or tuple(
            (unit, declaration.entity_id) for unit in declaration.translation_units)
        for pair in pairs:
            group.setdefault(pair, []).append(declaration)
        candidates = frozen_symbols.get(declaration.name, ())
        direct = [symbol for symbol in candidates if _direct_match(declaration, symbol)]
        if len(direct) == 1:
            decorations.setdefault(id(direct[0]), []).append(declaration)
            if (direct[0].compilation_unit is not None and direct[0].file is not None
                    and direct[0].line is not None and direct[0].address is not None
                    and direct[0].cu_offset is not None and direct[0].die_offset is not None):
                for unit, entity in pairs:
                    if direct[0].compilation_unit == unit:
                        anchors.setdefault((unit, entity), []).append((declaration, direct[0]))
    chains: dict[tuple[str, str], tuple[tuple[SourceDeclaration, DwarfSourceSymbol], ...]] = {}
    for pair, members in group.items():
        direct_members = anchors.get(pair, [])
        initialized = {member.id: member for member in members if member.is_definition}
        if len(initialized) > 1:
            continue
        if initialized:
            definition = next(iter(initialized.values()))
        else:
            tentative = {member.id: member for member in members if
                         member.storage == "none" and member.scope_kind == "global"}
            # A static declaration may also be tentative. It is a source
            # anchor only when one exact same-CU DWARF declaration proves it.
            tentative.update({member.id: member for member, symbol in direct_members
                              if _role(member) in {"file_static", "static_local"} and
                              _chain_compatible(member, member, symbol)})
            if len(tentative) == 1:
                definition = next(iter(tentative.values()))
            else:
                anchored = {member.id: member for member, symbol in direct_members
                            if member.id in tentative and
                            _chain_compatible(member, member, symbol)}
                if len(anchored) != 1:
                    continue
                definition = next(iter(anchored.values()))
        # An initialized redeclaration with an unmapped Clang location cannot
        # prove a source definition site, even when its entity and DIE match.
        # Do not replace it with an earlier tentative declaration.
        if not _usable_source_site(definition):
            continue
        compatible = tuple((definition, symbol) for member, symbol in direct_members
                           if _chain_compatible(member, definition, symbol) and
                           _chain_compatible(definition, definition, symbol))
        concrete = {(symbol.compilation_unit, symbol.cu_offset, symbol.die_offset)
                    for _source, symbol in compatible}
        if len(concrete) != 1:
            continue
        chains[pair] = compatible
    entity_proofs = chains
    attributed_entities: dict[int, set[str]] = {}
    for declaration in index.declarations:
        matched, _, _ = _match(declaration, frozen_symbols, entity_proofs)
        if matched is not None:
            attributed_entities.setdefault(id(matched), set()).add(declaration.entity_id)
    nodes: dict[str, _Node] = {}
    roots: list[SourceItem] = []
    compiled = (dwarf.source_declarations() if dwarf is not None and
                hasattr(dwarf, "source_declarations") else ())
    for symbol in compiled:
        if (symbol.file is None or symbol.cu_offset is None or symbol.die_offset is None
                or allowed is not None and symbol.file not in allowed):
            continue
        verified = [(declaration, site) for declaration in decorations.get(id(symbol), ())
                    for proved_symbol, _, site in (_match(declaration, frozen_symbols, entity_proofs),)
                    if proved_symbol is symbol]
        role_source, proof_site = verified[0] if len(verified) == 1 else (None, None)
        item, dtype = _item_for_dwarf(symbol, dwarf, context, binding, role_source, proof_site)
        if not _root_observable(item, dtype, dwarf, symbol):
            continue
        if item.id in nodes or len(roots) >= max_declarations:
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Merged source declaration limit was reached")
        roots.append(item)
        nodes[item.id] = _Node(item, dtype, 0, 0, symbol.address)
    for declaration in index.declarations:
        if allowed is not None and declaration.file not in allowed:
            continue
        item, dtype = _item_for_declaration(declaration, frozen_symbols, entity_proofs,
                                            dwarf, context, binding)
        matched, _, _ = _match(declaration, frozen_symbols, entity_proofs)
        if matched is not None and len(attributed_entities[id(matched)]) > 1:
            item = replace(item, selector=None, can_add=False, reason="ambiguous_symbol", expandable=False)
            dtype = None
        elif matched is not None and _direct_match(declaration, matched) and matched.die_offset is not None:
            continue  # Only one AST entity belongs to this concrete DIE.
        if not _root_observable(item, dtype, dwarf, matched):
            continue
        if item.id in nodes or len(roots) >= max_declarations:
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Merged source declaration limit was reached")
        roots.append(item)
        nodes[item.id] = _Node(item, dtype, 0, 0, matched.address if matched is not None else None)
    return tuple(roots), nodes


def _source_id(kind: str, file: str) -> str:
    return hashlib.sha256((kind + "\0" + file).encode("utf-8")).hexdigest()


def _tree_index(view: _View, max_functions: int = _MAX_NORMALIZED_FUNCTIONS) -> None:
    visible_files = {item.file for item in view.roots}
    by_file: dict[str, list[dict[str, object]]] = {
        file: [] for file in view.source_files if file in visible_files
    }
    roots_by_scope: dict[str, list[SourceItem]] = {}
    compiled_functions: tuple[DwarfSourceFunction, ...] = (
        view.dwarf.source_functions() if view.dwarf is not None and hasattr(view.dwarf, "source_functions") else ()
    )
    functions: dict[str, tuple[str, str, int | None, int | None, str | None]] = {}
    dwarf_by_site_cu: dict[tuple[str, str, int | None, str | None], list[str]] = {}
    dwarf_by_site_cu_column: dict[tuple[str, str, int | None, str | None, int | None], list[str]] = {}
    for function in compiled_functions:
        if function.file in by_file:
            key = _dwarf_function_id(function.cu_offset, function.die_offset)
            functions[key] = (
                function.name, function.file, function.line, function.column, function.compilation_unit
            )
            site_cu = (function.file, function.name, function.line, function.compilation_unit)
            dwarf_by_site_cu.setdefault(site_cu, []).append(key)
            dwarf_by_site_cu_column.setdefault((*site_cu, function.column), []).append(key)
    if len(functions) > max_functions:
        raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Normalized source function limit was reached")
    canonical_function: dict[str, str] = {}
    normalized_count = len(functions)
    for function in view.index.functions:
        if function.file not in by_file:
            continue
        matches: list[str] = []
        for cu in (None, *dict.fromkeys(function.translation_units)):
            site_cu = (function.file, function.name, function.line, cu)
            candidates = (dwarf_by_site_cu.get(site_cu, ()) if function.column is None else
                          chain(dwarf_by_site_cu_column.get((*site_cu, function.column), ()),
                                dwarf_by_site_cu_column.get((*site_cu, None), ())))
            for key in candidates:
                matches.append(key)
                if len(matches) > 1:
                    break
            if len(matches) > 1:
                break
        canonical_function[function.id] = matches[0] if len(matches) == 1 else function.id
        if function.id not in functions and len(matches) != 1:
            normalized_count += 1
            if normalized_count > max_functions:
                raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Normalized source function limit was reached")
        functions[function.id] = (functions[matches[0]] if len(matches) == 1 else
                                  (function.name, function.file, function.line, function.column,
                                   function.translation_units[0] if function.translation_units else None))
    projected: set[str] = set()
    def add_function_scope(file: str, key: str) -> str:
        name, definition_file, line, _, _ = functions[key]
        scope_id = _source_id("function", file + "\0" + key)
        if scope_id not in projected:
            projected.add(scope_id)
            by_file[file].append({
                "kind": "scope", "id": scope_id, "parentId": _source_id("file", file),
                "file": file, "name": name, "function": name,
                "line": line if file == definition_file else None, "variableCount": 0,
            })
            roots_by_scope[scope_id] = []
        return scope_id
    for item in view.roots:
        if item.file not in by_file:
            continue
        if item.function is not None or item.scope_kind in {"local", "static_local", "parameter"}:
            key = canonical_function.get(item.function_id or "", item.function_id or "")
            if key not in functions:
                continue
            scope_id = add_function_scope(item.file, key)
        else:
            scope_id = _source_id("global", item.file)
        roots_by_scope.setdefault(scope_id, []).append(item)
    for file in by_file:
        global_id = _source_id("global", file)
        if roots_by_scope.get(global_id):
            by_file[file].append({
                "kind": "scope", "id": global_id, "parentId": _source_id("file", file),
                "file": file, "name": "global", "function": None, "line": None,
                "variableCount": 0,
            })
        by_file[file] = [scope for scope in by_file[file]
                         if roots_by_scope.get(str(scope["id"]))]
        by_file[file].sort(key=lambda scope: (scope["line"] is not None,
                                                scope["line"] or 0, str(scope["name"]).casefold(), str(scope["id"])))
    view.file_nodes = tuple({
        "kind": "file", "id": _source_id("file", file), "parentId": None,
        "file": file, "name": file.rsplit("/", 1)[-1], "variableCount": 0, "scopeCount": 0,
    } for file in view.source_files if file in visible_files)
    view.scopes_by_file = {file: tuple(scopes) for file, scopes in by_file.items()}
    view.roots_by_scope = {scope: tuple(items) for scope, items in roots_by_scope.items()}
    view.file_by_id = {str(node["id"]): str(node["file"]) for node in view.file_nodes}
    view.scope_by_id = {str(scope["id"]): scope for scopes in by_file.values() for scope in scopes}


def _matches(query: str, value: str) -> bool:
    return query in unicodedata.normalize("NFC", value).casefold()


def _matching_scopes(view: _View, file: str, query: str) -> tuple[tuple[dict[str, object], ...], dict[str, tuple[SourceItem, ...]]]:
    scopes = () if view.scopes_by_file is None else view.scopes_by_file.get(file, ())
    roots = view.roots_by_scope or {}
    file_hit = bool(query and _matches(query, file))
    included: list[dict[str, object]] = []
    matches: dict[str, tuple[SourceItem, ...]] = {}
    for scope in scopes:
        scope_id = str(scope["id"])
        function = scope["function"]
        function_hit = bool(query and isinstance(function, str) and _matches(query, function))
        scoped = roots.get(scope_id, ())
        filtered = (scoped if not query or file_hit or function_hit else
                    tuple(item for item in scoped if _matches(query, item.name)))
        if filtered:
            included.append({**scope, "variableCount": len(filtered)})
            matches[scope_id] = filtered
    return tuple(included), matches


def _tree_items(view: _View, query: str, parent_id: str | None) -> tuple[dict[str, object], ...]:
    if parent_id is None:
        files: list[dict[str, object]] = []
        for file_node in view.file_nodes:
            file = str(file_node["file"])
            scopes, matches = _matching_scopes(view, file, query)
            if scopes:
                files.append({**file_node, "scopeCount": len(scopes),
                              "variableCount": sum(len(items) for items in matches.values())})
        return tuple(files)
    file = (view.file_by_id or {}).get(parent_id)
    if file is None:
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source tree parent changed")
    scopes, _ = _matching_scopes(view, file, query)
    return scopes


def _catalog_id(identity: Mapping[str, object], signature: tuple[object, ...],
                index: SourceIndex, source_files: tuple[str, ...] = (),
                policy: str = SOURCE_LOCAL_HEADERS_POLICY) -> str:
    results = hashlib.sha256(json.dumps(
        ["source-observable-v1", policy, index.parsed_units, index.total_units, index.truncated,
         [[issue.unit, issue.code, issue.message] for issue in index.issues],
         [[decl.id, decl.entity_id, decl.entity_by_unit, decl.is_definition,
           decl.function_id, decl.translation_units] for decl in index.declarations],
         [[function.id, function.name, function.file, function.line, function.column,
           function.translation_units] for function in index.functions], source_files],
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    payload = json.dumps([identity, signature, index.engine_name, index.engine_version,
                          index.input_kind, index.argument_fingerprint, index.complete, results], sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _engine(view: _View) -> dict[str, object]:
    index = view.index
    return {"name": ("ELF DWARF + " if view.dwarf is not None else "") + index.engine_name,
            "version": index.engine_version + (";dwarf-directory:1" if view.dwarf is not None else ""),
            "inputKind": index.input_kind}


def _coverage(view: _View) -> dict[str, object]:
    result: dict[str, object] = {
        "complete": view.index.complete, "totalUnits": view.index.total_units,
        "parsedUnits": view.index.parsed_units, "issues": _issue_summary(view.index),
        "truncated": view.index.truncated,
    }
    if view.compiled_debug is not None:
        result["compiledDebug"] = view.compiled_debug
    return result


def _compiled_debug(dwarf: DwarfCatalog | None, source_files: tuple[str, ...]) -> dict[str, object]:
    if dwarf is None or not hasattr(dwarf, "source_declarations") or not hasattr(dwarf, "source_functions"):
        return {"available": False, "variableCount": 0, "functionCount": 0, "fileCount": 0}
    allowed = set(source_files)
    declarations = tuple(symbol for symbol in dwarf.source_declarations()
                         if symbol.file in allowed)
    functions = tuple(function for function in dwarf.source_functions()
                      if function.file in allowed)
    files = {symbol.file for symbol in declarations} | {function.file for function in functions}
    return {"available": True,
            "variableCount": len(declarations),
            "functionCount": len(functions), "fileCount": len(files)}


def _page_payload(view: _View, items: tuple[SourceItem, ...], actual_total: int,
                  normalized: str, cursor: str | None, limit: int,
                  parent_id: str | None, scope_id: str | None = None) -> dict[str, object]:
    if normalized and scope_id is None:
        items = tuple(item for item in items if _matches(normalized, item.name)
                      or _matches(normalized, item.file)
                      or _matches(normalized, item.function or ""))
    offset = _offset(cursor, view.catalog_id, normalized, parent_id, scope_id, "variables")
    if offset > len(items):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog cursor changed")
    data: dict[str, object] = {
        "schemaVersion": 1, "catalogId": view.catalog_id, "identity": view.identity,
        "engine": _engine(view),
        "coverage": _coverage(view),
        "total": len(items),
        "items": [], "nextCursor": None,
    }
    base_bytes = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    budget = _PAGE_DATA_BUDGET - base_bytes - _MAX_CURSOR_LENGTH
    selected: list[dict[str, object]] = []
    for item in items[offset:offset + limit]:
        serialized = item.to_dict()
        length = len(json.dumps(serialized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
        if length > budget:
            if not selected:
                raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source catalog item exceeds its page budget")
            break
        selected.append(serialized)
        budget -= length
    next_offset = offset + len(selected)
    data["items"] = selected
    data["nextCursor"] = (_cursor(view.catalog_id, normalized, parent_id, next_offset, scope_id, "variables")
                          if next_offset < len(items) else None)
    return data


def _issue_summary(index: SourceIndex) -> list[dict[str, object]]:
    listed = [issue.to_dict() for issue in index.issues[:5]]
    if len(index.issues) > 5:
        listed.append({"unit": None, "code": "MONITOR_SOURCE_INDEX_FAILED",
                       "message": f"{len(index.issues) - 5} additional source issues"})
    return listed


def _metadata_page_payload(view: _View, items: tuple[dict[str, object], ...], query: str,
                           cursor: str | None, limit: int, parent_id: str | None) -> dict[str, object]:
    offset = _offset(cursor, view.catalog_id, query, parent_id, None, "tree")
    if offset > len(items):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source tree cursor changed")
    data: dict[str, object] = {
        "schemaVersion": 1, "catalogId": view.catalog_id, "identity": view.identity,
        "engine": _engine(view),
        "coverage": _coverage(view),
        "total": len(items), "items": [], "nextCursor": None,
    }
    base_bytes = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    budget = _PAGE_DATA_BUDGET - base_bytes - _MAX_CURSOR_LENGTH
    selected: list[dict[str, object]] = []
    for item in items[offset:offset + limit]:
        length = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
        if length > budget:
            if not selected:
                raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source tree item exceeds its page budget")
            break
        selected.append(item)
        budget -= length
    next_offset = offset + len(selected)
    data["items"] = selected
    data["nextCursor"] = (_cursor(view.catalog_id, query, parent_id, next_offset, None, "tree")
                          if next_offset < len(items) else None)
    return data


def _cursor(catalog: str, query: str, parent: str | None, offset: int,
            scope: str | None = None, domain: str = "variables") -> str:
    raw = json.dumps([catalog, query, parent, scope, domain, offset], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    mac = hmac.new(_CURSOR_KEY, raw, "sha256").digest()
    return base64.urlsafe_b64encode(raw + mac).rstrip(b"=").decode("ascii")


def _offset(cursor: str | None, catalog: str, query: str, parent: str | None,
            scope: str | None = None, domain: str = "variables") -> int:
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or len(cursor) > _MAX_CURSOR_LENGTH:
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog cursor is invalid")
    try:
        encoded = cursor.encode("ascii")
        envelope = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
        if base64.urlsafe_b64encode(envelope).rstrip(b"=") != encoded or len(envelope) < 33:
            raise ValueError
        raw, mac = envelope[:-32], envelope[-32:]
        if not hmac.compare_digest(mac, hmac.new(_CURSOR_KEY, raw, "sha256").digest()):
            raise ValueError
        document = json.loads(raw)
        if (not isinstance(document, list) or len(document) != 6
                or document[:5] != [catalog, query, parent, scope, domain]
                or type(document[5]) is not int or document[5] < 1):
            raise ValueError
        return document[5]
    except (UnicodeError, binascii.Error, ValueError, json.JSONDecodeError):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog cursor is invalid") from None


class SourceCatalogProvider:
    def __init__(self, project_root: Path, workspace_id: str, session_id: str,
                 adapter: ClangSourceAdapter | None = None) -> None:
        self.root = project_root
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.adapter = adapter or ClangSourceAdapter()
        self._bases: OrderedDict[tuple[object, ...], _Base] = OrderedDict()
        self._inflight: dict[tuple[object, ...], asyncio.Task[_Base]] = {}
        self._views: OrderedDict[str, _View] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self.adapter.close()
        for task in self._inflight.values():
            task.cancel()

    async def _load_base_job(self, key: tuple[object, ...],
                             facts: _Facts, plan: SourcePlan) -> _Base:
        try:
            base = await asyncio.to_thread(_load_base, self.adapter, facts, plan)
            async with self._lock:
                if not self._closed and (base.index.complete or base.dwarf is not None):
                    self._bases[key] = base
                    self._bases.move_to_end(key)
                    while len(self._bases) > 2:
                        self._bases.popitem(last=False)
            return base
        finally:
            async with self._lock:
                if self._inflight.get(key) is asyncio.current_task():
                    self._inflight.pop(key)

    @staticmethod
    def _consume_background_failure(task: asyncio.Task[_Base]) -> None:
        # A canceled page waiter does not own the coalesced indexing job.
        if not task.cancelled():
            task.exception()

    async def _base(self, facts: _Facts, plan: SourcePlan, refresh: bool = False) -> _Base:
        key = (facts.policy, facts.source_sha, facts.build_id, facts.elf_sha, facts.elf_path,
               facts.elf_size, plan.fingerprint, plan.engine_version, plan.input_kind)
        async with self._lock:
            if self._closed:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog was closed")
            if refresh:
                self._bases.pop(key, None)
            if key in self._bases:
                self._bases.move_to_end(key)
                return self._bases[key]
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._load_base_job(key, facts, plan))
                task.add_done_callback(self._consume_background_failure)
                self._inflight[key] = task
        base = await asyncio.shield(task)
        if self._closed:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog was closed")
        return base

    async def _view(self, binding: object | None, binding_epoch: int,
                    requested_catalog_id: str | None = None, refresh: bool = False) -> _View:
        if self._closed:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog was closed")
        facts = await asyncio.to_thread(_offline_facts, self.root)
        if type(binding_epoch) is not int or binding_epoch < 0:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog context is invalid")
        plan = await asyncio.to_thread(self.adapter.plan, facts.model)
        identity: dict[str, object] = {
            "workspaceId": self.workspace_id, "sessionId": self.session_id,
            "logicalProjectId": str(facts.model.logical_project_id),
            "targetDevice": facts.model.target.device,
            "sourceSnapshotSha256": facts.source_sha,
            "buildId": facts.build_id, "elfSha256": facts.elf_sha,
            "bindingEpoch": binding_epoch,
        }
        signature = _binding_signature(binding)
        if requested_catalog_id is not None:
            async with self._lock:
                saved = self._views.get(requested_catalog_id)
                if (saved is not None and saved.identity == identity and saved.policy == facts.policy
                        and saved.binding_signature == signature
                        and saved.index.argument_fingerprint == plan.fingerprint
                        and saved.index.engine_version == plan.engine_version
                        and saved.index.input_kind == plan.input_kind):
                    self._views.move_to_end(requested_catalog_id)
                    return saved
        base = await self._base(facts, plan, refresh)
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (facts.policy, facts.source_sha, facts.build_id, facts.elf_sha) != (current.policy, current.source_sha, current.build_id, current.elf_sha):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed while indexing")
        catalog = await asyncio.to_thread(_catalog_id, identity, signature, base.index, base.source_files, facts.policy)
        async with self._lock:
            saved = self._views.get(catalog)
            if saved is not None:
                self._views.move_to_end(catalog)
                return saved
        binding_ok = _binding_matches(binding, facts, self.workspace_id, self.session_id)
        context = _context_reason(base.index, facts, binding, binding_ok)
        if base.dwarf is None and context != "source_mismatch":
            context = "firmware_unavailable"
        roots, nodes = await asyncio.to_thread(_materialize, base.index, base.dwarf, context,
                                               binding, base.source_files)
        view = _View(catalog, identity, base.index, base.dwarf, roots, nodes,
                     binding, binding_ok, {}, signature, base.source_files, policy=facts.policy)
        view.compiled_debug = _compiled_debug(base.dwarf, base.source_files)
        await asyncio.to_thread(_tree_index, view)
        async with self._lock:
            if self._closed:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog was closed")
            # Partial navigation is stable for this result digest, while a
            # root refresh without catalogId still reindexes the uncached base.
            self._views[catalog] = view
            self._views.move_to_end(catalog)
            while len(self._views) > 2:
                self._views.popitem(last=False)
        return view

    def _children(self, view: _View, parent: _Node) -> tuple[tuple[SourceItem, ...], int]:
        item = parent.item
        cached = view.children_cache.get(item.id)
        if cached is not None:
            return cached
        dtype = parent.dwarf_type
        if dtype is None or not item.expandable or item.selector is None or parent.depth >= 6:
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source aggregate cannot be expanded")
        root = parent
        while root.item.parent_id is not None:
            root = view.nodes[root.item.parent_id]
        remaining = max(0, 4096 - root.descendants)
        if remaining == 0:
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Observable directory expansion reached its bound")
        members: list[tuple[int, str, DwarfType | None, str | None, int | None]] = []
        member_name_counts: Counter[str] = Counter()
        if dtype.kind in {"structure", "union"}:
            capacity = remaining
            member_name_counts = Counter(member.name for member in dtype.members)
            members = [(ordinal, member.name, member.type, None if member.bit_size is None else "unsupported_type",
                        None if parent.address is None else parent.address + member.offset)
                       for ordinal, member in enumerate(dtype.members[:4096])]
        elif dtype.kind == "array" and dtype.element_type is not None and dtype.element_count is not None:
            # Leave room for a proved scalar path below each aggregate element.
            capacity = (remaining if dtype.element_type.kind in _SCALAR else
                        max(1, remaining // (7 - parent.depth)) if remaining else 0)
            admitted = min(dtype.element_count, 4096)
            indices = (_array_candidate_indices(view.dwarf, parent.address,
                                                 dtype.element_type.byte_size, admitted)
                       if view.dwarf is not None and parent.address is not None
                       and dtype.element_type.byte_size > 0 else ())
            members = [(index, str(index), dtype.element_type, None,
                        None if parent.address is None else parent.address + index * dtype.element_type.byte_size)
                       for index in indices]
        else:
            capacity = remaining
        children: list[SourceItem] = []
        context = None if view.binding_ok else (
            "probe_required" if view.binding is None else "source_mismatch")
        proof_budget = [4096]
        omitted_visible = False
        for ordinal, name, child_type, intrinsic, address in members:
            kind = "element" if dtype.kind == "array" else "member"
            selector = f"{item.selector}[{name}]" if kind == "element" else f"{item.selector}.{name}"
            if kind == "member":
                if not _EXPRESSION.fullmatch(name):
                    intrinsic = "unsupported_type"
                elif member_name_counts[name] > 1 and intrinsic is None:
                    intrinsic = "ambiguous_symbol"
            if (intrinsic is not None or child_type is None or
                    not _observable_descendant(selector, child_type, view.dwarf,
                                               address, parent.depth + 1, proof_budget)):
                continue
            if len(children) >= capacity:
                omitted_visible = True
                break
            identifier = hashlib.sha256((item.id + "\0" + str(ordinal) + "\0" + selector).encode("utf-8")).hexdigest()
            aggregate = child_type is not None and child_type.kind in {"structure", "union", "array"}
            has_descendants = bool(child_type is not None and (
                child_type.kind in {"structure", "union"} and child_type.members or
                child_type.kind == "array" and child_type.element_count is not None and child_type.element_count > 0))
            depth_limited = bool(aggregate and has_descendants and parent.depth + 1 >= 6)
            expandable = bool(aggregate and has_descendants and not depth_limited)
            reason = ("limit_reached" if depth_limited else intrinsic or
                      ("aggregate" if expandable else _eligible_leaf(selector, view.dwarf, view.binding)))
            if reason is None:
                reason = context
            child = SourceItem(identifier, item.id, name, child_type.name if child_type else "<unknown>",
                               item.file, item.line, item.column, kind, item.function,
                               (*item.scope_path, item.name), item.storage, item.translation_units,
                               selector if intrinsic is None else None,
                               reason is None, reason, expandable,
                               bool(depth_limited or
                                    child_type is not None and child_type.kind == "array" and
                                    child_type.element_count is not None and child_type.element_count > 4096),
                               None, kind, item.definition_site)
            children.append(child)
            view.nodes[identifier] = _Node(child, child_type if expandable else None,
                                           parent.depth + 1, 0, address)
        if omitted_visible and children:
            children[-1] = replace(children[-1], truncated=True)
            view.nodes[children[-1].id].item = children[-1]
        root.descendants += len(children)
        result = tuple(children), len(children)
        view.children_cache[item.id] = result
        return result

    async def page(self, *, query: str, cursor: str | None, limit: int,
                   parent_id: str | None, catalog_id: str | None,
                   binding: object | None, binding_epoch: int,
                   scope_id: str | None = None, refresh: bool = False) -> dict[str, object]:
        if (type(query) is not str or len(query) > 128 or any(ord(c) < 32 for c in query)
                or type(limit) is not int or not 1 <= limit <= 100
                or type(refresh) is not bool or refresh and (parent_id is not None or scope_id is not None
                                                              or catalog_id is not None or cursor is not None)
                or parent_id is not None and (not isinstance(parent_id, str) or not _ID.fullmatch(parent_id))
                or scope_id is not None and (not isinstance(scope_id, str) or not _ID.fullmatch(scope_id))
                or scope_id is not None and (parent_id is not None or catalog_id is None)
                or catalog_id is not None and (not isinstance(catalog_id, str) or not _ID.fullmatch(catalog_id))):
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source catalog query is invalid")
        normalized = unicodedata.normalize("NFC", query.strip()).casefold()
        view = await self._view(binding, binding_epoch, catalog_id, refresh)
        if catalog_id is not None and catalog_id != view.catalog_id:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog identity changed")
        if scope_id is not None:
            scope = (view.scope_by_id or {}).get(scope_id)
            if scope is None:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source scope changed")
            _, matches = await asyncio.to_thread(_matching_scopes, view, str(scope["file"]), normalized)
            if scope_id not in matches:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source scope changed")
            items = matches[scope_id]
            actual_total = len(items)
        elif parent_id is not None:
            if catalog_id is None or parent_id not in view.nodes:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog parent changed")
            async with self._lock:
                items, actual_total = await asyncio.to_thread(self._children, view, view.nodes[parent_id])
        else:
            items = view.roots
            actual_total = len(items)
        result = await asyncio.to_thread(_page_payload, view, items, actual_total,
                                         normalized, cursor, limit, parent_id, scope_id)
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (current.policy, current.source_sha, current.build_id, current.elf_sha) != (
                view.policy, view.identity["sourceSnapshotSha256"],
                view.identity["buildId"], view.identity["elfSha256"]):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed during page")
        return result

    async def tree(self, *, query: str, cursor: str | None, limit: int,
                   parent_id: str | None, catalog_id: str | None,
                   binding: object | None, binding_epoch: int,
                   refresh: bool = False) -> dict[str, object]:
        if (type(query) is not str or len(query) > 128 or any(ord(c) < 32 for c in query)
                or type(limit) is not int or not 1 <= limit <= 1000
                or type(refresh) is not bool or refresh and (parent_id is not None
                                                              or catalog_id is not None or cursor is not None)
                or parent_id is not None and (not isinstance(parent_id, str) or not _ID.fullmatch(parent_id)
                                              or catalog_id is None)
                or cursor is not None and catalog_id is None
                or catalog_id is not None and (not isinstance(catalog_id, str) or not _ID.fullmatch(catalog_id))):
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source tree query is invalid")
        normalized = unicodedata.normalize("NFC", query.strip()).casefold()
        view = await self._view(binding, binding_epoch, catalog_id, refresh)
        if catalog_id is not None and catalog_id != view.catalog_id:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog identity changed")
        items = await asyncio.to_thread(_tree_items, view, normalized, parent_id)
        result = await asyncio.to_thread(_metadata_page_payload, view, items, normalized,
                                         cursor, limit, parent_id)
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (current.policy, current.source_sha, current.build_id, current.elf_sha) != (
                view.policy, view.identity["sourceSnapshotSha256"],
                view.identity["buildId"], view.identity["elfSha256"]):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed during tree page")
        return result

    async def select(self, *, catalog_id: str, item_id: str, selector: str,
                     binding: object | None, binding_epoch: int) -> dict[str, object]:
        if (not isinstance(catalog_id, str) or not _ID.fullmatch(catalog_id)
                or not isinstance(item_id, str) or not _ID.fullmatch(item_id)
                or not isinstance(selector, str) or len(selector) > 256):
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source selection is invalid")
        view = await self._view(binding, binding_epoch, catalog_id)
        if view.catalog_id != catalog_id:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog identity changed")
        node = view.nodes.get(item_id)
        if (node is None or not node.item.can_add or node.item.selector != selector
                or not view.binding_ok):
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source selection is unavailable")
        if await asyncio.to_thread(_eligible_leaf, selector, view.dwarf, binding) is not None:
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source selection is unavailable")
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (current.policy, current.source_sha, current.build_id, current.elf_sha) != (
                view.policy, view.identity["sourceSnapshotSha256"],
                view.identity["buildId"], view.identity["elfSha256"]):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed during selection")
        return {"catalogId": catalog_id, "item": {"kind": "variable", "expression": selector}}
