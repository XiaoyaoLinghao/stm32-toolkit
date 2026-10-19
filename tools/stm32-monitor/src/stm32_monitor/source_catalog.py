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
from pathlib import Path
from typing import Mapping

from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.debug.dwarf import DwarfCatalog, DwarfSourceSymbol
from stm32_toolkit.debug.source import ClangSourceAdapter, SourceCatalogError, SourceDeclaration, SourceIndex, SourcePlan
from stm32_toolkit.debug.types import DwarfError, DwarfType
from stm32_toolkit.probe.flash import load_fresh_firmware_facts
from stm32_toolkit.probe.protocol import MAX_READ_BYTES
from stm32_toolkit.project_model import ProjectModel, load_project_model


_ID = re.compile(r"[0-9a-f]{64}\Z")
_EXPRESSION = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SCALAR = frozenset({"integer", "boolean", "float", "enum", "pointer"})
_CURSOR_KEY = secrets.token_bytes(32)
_PAGE_DATA_BUDGET = 900 * 1024  # Leave envelope/error metadata below the service's 1 MiB cap.


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


@dataclass(frozen=True)
class _Base:
    index: SourceIndex
    dwarf: DwarfCatalog | None


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
        }


@dataclass
class _Node:
    item: SourceItem
    dwarf_type: DwarfType | None
    depth: int
    descendants: int


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


def _offline_facts(root: Path) -> _Facts:
    model = load_project_model(root)
    source_sha = snapshot_project_inputs(model).sha256
    build_id = elf_sha = elf_path = None
    elf_size = None
    try:
        firmware = load_fresh_firmware_facts(root)
        if firmware.input_snapshot_sha256 == source_sha:
            build_id, elf_sha, elf_path = firmware.build_id, firmware.elf_sha256, firmware.elf_path
            elf_size = (root / elf_path).stat().st_size
    except Exception:
        pass
    return _Facts(model, source_sha, build_id, elf_sha, elf_path, elf_size)


def _readable_regions(model: ProjectModel) -> tuple[tuple[int, int], ...]:
    return tuple((region.origin, region.origin + region.length)
                 for region in model.memory.regions if "r" in region.attributes)


def _load_base(adapter: ClangSourceAdapter, facts: _Facts, plan: SourcePlan) -> _Base:
    index = adapter.index(facts.model, plan)
    dwarf = None
    if facts.elf_path is not None and facts.elf_sha is not None and facts.elf_size is not None:
        try:
            dwarf = DwarfCatalog.from_elf(
                facts.elf_path, project_root=facts.model.project_root,
                expected_elf_size=facts.elf_size, expected_elf_sha256=facts.elf_sha,
                readable_regions=_readable_regions(facts.model),
            )
        except DwarfError:
            pass
    after = _offline_facts(facts.model.project_root)
    if (after.source_sha, after.build_id, after.elf_sha) != (facts.source_sha, facts.build_id, facts.elf_sha):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed while indexing")
    return _Base(index, dwarf)


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


def _direct_match(candidate: SourceDeclaration, symbol: DwarfSourceSymbol) -> bool:
    return (candidate.name == symbol.name and candidate.file == symbol.file
            and candidate.line is not None and candidate.line == symbol.line
            and candidate.function == symbol.function
            and (symbol.column is None or candidate.column == symbol.column)
            and _compatible(candidate, symbol.dwarf_type)
            and (symbol.compilation_unit is None or symbol.compilation_unit in candidate.translation_units))


def _match(decl: SourceDeclaration,
           symbols_by_name: Mapping[str, tuple[DwarfSourceSymbol, ...]],
           entity_proofs: Mapping[str, tuple[str, DwarfSourceSymbol]]) -> tuple[DwarfSourceSymbol | None, str | None]:
    if decl.line is None or decl.column is None:
        return None, "source_attribution_unproven"
    same_name = symbols_by_name.get(decl.name, ())
    if not same_name:
        return None, "debug_entry_missing"
    if len(same_name) != 1:
        return None, "ambiguous_symbol"
    symbol = same_name[0]
    if _direct_match(decl, symbol):
        return symbol, None
    # A definition can be proved by a Clang previousDecl chain to the exact
    # DWARF declaration.  Name/CU proximity alone never admits it.
    proof = entity_proofs.get(decl.entity_id)
    if (decl.entity_id != decl.id and proof is not None and proof[0] != decl.id
            and proof[1] == symbol
            and (symbol.compilation_unit is None or symbol.compilation_unit in decl.translation_units)
            and _compatible(decl, symbol.dwarf_type)):
        return symbol, None
    return None, "source_attribution_unproven"


def _eligible_leaf(selector: str, dwarf: DwarfCatalog | None, binding: object | None) -> str | None:
    if dwarf is None:
        return "firmware_unavailable"
    try:
        selected = dwarf.lookup(selector)
    except DwarfError as error:
        if error.code == "DWARF_SYMBOL_AMBIGUOUS":
            return "ambiguous_symbol"
        if error.code == "DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY":
            return "read_range_denied"
        if error.code.startswith("DWARF_TYPE") or error.code in {"DWARF_BITFIELD_UNSUPPORTED", "DWARF_ARRAY_INDEX_OUT_OF_RANGE"}:
            return "unsupported_type"
        return "unsupported_location"
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


def _context_reason(index: SourceIndex, facts: _Facts, binding: object | None,
                    binding_ok: bool) -> str | None:
    if not index.complete:
        return "coverage_incomplete"
    if facts.build_id is None:
        return "firmware_unavailable"
    if binding is None:
        return "probe_required"
    if not binding_ok:
        return "source_mismatch"
    return None


def _item_for_declaration(decl: SourceDeclaration,
                          symbols_by_name: Mapping[str, tuple[DwarfSourceSymbol, ...]],
                          entity_proofs: Mapping[str, tuple[str, DwarfSourceSymbol]],
                          dwarf: DwarfCatalog | None,
                          context_reason: str | None, binding: object | None) -> tuple[SourceItem, DwarfType | None]:
    symbol, reason = _match(decl, symbols_by_name, entity_proofs)
    dtype = symbol.dwarf_type if symbol is not None else None
    selector = decl.name if symbol is not None and _EXPRESSION.fullmatch(decl.name) else None
    if decl.scope_kind in {"local", "parameter"}:
        reason = "frame_required"
        selector = None
    elif context_reason in {"coverage_incomplete", "firmware_unavailable", "source_mismatch"}:
        reason = context_reason
    elif symbol is not None:
        if symbol.type_error is not None or dtype is None:
            reason = "unsupported_type"
        elif symbol.address is None or symbol.location_error is not None:
            reason = "unsupported_location"
        elif dtype.kind in {"structure", "union", "array"}:
            reason = "aggregate"
        else:
            reason = _eligible_leaf(decl.name, dwarf, binding)
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
                      reason, expandable, aggregate_size is not None and aggregate_size > 4096), dtype if expandable else None


def _materialize(index: SourceIndex, dwarf: DwarfCatalog | None,
                 context: str | None, binding: object | None) -> tuple[tuple[SourceItem, ...], dict[str, _Node]]:
    symbols_by_name: dict[str, list[DwarfSourceSymbol]] = {}
    for symbol in dwarf.source_symbols() if dwarf is not None else ():
        symbols_by_name.setdefault(symbol.name, []).append(symbol)
    frozen_symbols = {name: tuple(group) for name, group in symbols_by_name.items()}
    entity_proofs: dict[str, tuple[str, DwarfSourceSymbol]] = {}
    for declaration in index.declarations:
        candidates = frozen_symbols.get(declaration.name, ())
        if len(candidates) == 1 and _direct_match(declaration, candidates[0]):
            entity_proofs.setdefault(declaration.entity_id, (declaration.id, candidates[0]))
    attributed_entities: dict[int, set[str]] = {}
    for declaration in index.declarations:
        matched, _ = _match(declaration, frozen_symbols, entity_proofs)
        if matched is not None:
            attributed_entities.setdefault(id(matched), set()).add(declaration.entity_id)
    nodes: dict[str, _Node] = {}
    roots: list[SourceItem] = []
    for declaration in index.declarations:
        item, dtype = _item_for_declaration(declaration, frozen_symbols, entity_proofs,
                                            dwarf, context, binding)
        matched, _ = _match(declaration, frozen_symbols, entity_proofs)
        if matched is not None and len(attributed_entities[id(matched)]) > 1:
            item = replace(item, selector=None, can_add=False, reason="ambiguous_symbol", expandable=False)
            dtype = None
        roots.append(item)
        nodes[item.id] = _Node(item, dtype, 0, 0)
    return tuple(roots), nodes


def _catalog_id(identity: Mapping[str, object], signature: tuple[object, ...],
                index: SourceIndex) -> str:
    results = hashlib.sha256(json.dumps(
        [index.parsed_units, index.total_units, index.truncated,
         [[issue.unit, issue.code, issue.message] for issue in index.issues],
         [[decl.id, decl.entity_id, decl.translation_units] for decl in index.declarations]],
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    payload = json.dumps([identity, signature, index.engine_name, index.engine_version,
                          index.input_kind, index.argument_fingerprint, index.complete, results], sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _page_payload(view: _View, items: tuple[SourceItem, ...], actual_total: int,
                  normalized: str, cursor: str | None, limit: int,
                  parent_id: str | None) -> dict[str, object]:
    if normalized:
        items = tuple(item for item in items if normalized in item.name.casefold()
                      or normalized in item.file.casefold()
                      or normalized in (item.function or "").casefold())
    offset = _offset(cursor, view.catalog_id, normalized, parent_id)
    if offset > len(items):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog cursor changed")
    data: dict[str, object] = {
        "schemaVersion": 1, "catalogId": view.catalog_id, "identity": view.identity,
        "engine": {"name": view.index.engine_name, "version": view.index.engine_version,
                   "inputKind": view.index.input_kind},
        "coverage": {"complete": view.index.complete,
                     "totalUnits": view.index.total_units,
                     "parsedUnits": view.index.parsed_units,
                     "issues": [issue.to_dict() for issue in view.index.issues],
                     "truncated": view.index.truncated},
        "total": actual_total if parent_id is not None and not normalized else len(items),
        "items": [], "nextCursor": None,
    }
    base_bytes = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    budget = _PAGE_DATA_BUDGET - base_bytes - 512  # cursor and transport metadata margin
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
    data["nextCursor"] = (_cursor(view.catalog_id, normalized, parent_id, next_offset)
                          if next_offset < len(items) else None)
    return data


def _cursor(catalog: str, query: str, parent: str | None, offset: int) -> str:
    raw = json.dumps([catalog, query, parent, offset], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    mac = hmac.new(_CURSOR_KEY, raw, "sha256").digest()
    return base64.urlsafe_b64encode(raw + mac).rstrip(b"=").decode("ascii")


def _offset(cursor: str | None, catalog: str, query: str, parent: str | None) -> int:
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or len(cursor) > 512:
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
        if (not isinstance(document, list) or len(document) != 4
                or document[:3] != [catalog, query, parent]
                or type(document[3]) is not int or document[3] < 1):
            raise ValueError
        return document[3]
    except (UnicodeError, binascii.Error, ValueError, json.JSONDecodeError):
        raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog cursor is invalid") from None


class SourceCatalogProvider:
    def __init__(self, project_root: Path, workspace_id: str, session_id: str,
                 adapter: ClangSourceAdapter | None = None) -> None:
        self.root = project_root
        self.workspace_id = workspace_id
        self.session_id = session_id
        self.adapter = adapter or ClangSourceAdapter()
        self._bases: OrderedDict[tuple[str, str | None, str], _Base] = OrderedDict()
        self._inflight: dict[tuple[str, str | None, str], asyncio.Task[_Base]] = {}
        self._views: OrderedDict[str, _View] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self.adapter.close()
        for task in self._inflight.values():
            task.cancel()

    async def _load_base_job(self, key: tuple[str, str | None, str],
                             facts: _Facts, plan: SourcePlan) -> _Base:
        try:
            base = await asyncio.to_thread(_load_base, self.adapter, facts, plan)
            async with self._lock:
                if not self._closed and base.index.complete:
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

    async def _base(self, facts: _Facts, plan: SourcePlan) -> _Base:
        key = facts.source_sha, facts.elf_sha, plan.fingerprint
        async with self._lock:
            if self._closed:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog was closed")
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
                    requested_catalog_id: str | None = None) -> _View:
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
                if (saved is not None and saved.identity == identity
                        and saved.binding_signature == signature
                        and saved.index.argument_fingerprint == plan.fingerprint
                        and saved.index.engine_version == plan.engine_version
                        and saved.index.input_kind == plan.input_kind):
                    self._views.move_to_end(requested_catalog_id)
                    return saved
        base = await self._base(facts, plan)
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (facts.source_sha, facts.build_id, facts.elf_sha) != (current.source_sha, current.build_id, current.elf_sha):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed while indexing")
        catalog = await asyncio.to_thread(_catalog_id, identity, signature, base.index)
        async with self._lock:
            saved = self._views.get(catalog)
            if saved is not None:
                self._views.move_to_end(catalog)
                return saved
        binding_ok = _binding_matches(binding, facts, self.workspace_id, self.session_id)
        context = _context_reason(base.index, facts, binding, binding_ok)
        if base.dwarf is None and context not in {"coverage_incomplete", "source_mismatch"}:
            context = "firmware_unavailable"
        roots, nodes = await asyncio.to_thread(_materialize, base.index, base.dwarf, context, binding)
        view = _View(catalog, identity, base.index, base.dwarf, roots, nodes,
                     binding, binding_ok, {}, signature)
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
        members: list[tuple[str, DwarfType | None, str | None]] = []
        member_name_counts: Counter[str] = Counter()
        actual_total = 0
        if dtype.kind in {"structure", "union"}:
            actual_total = len(dtype.members)
            member_name_counts = Counter(member.name for member in dtype.members)
            members = [(member.name, member.type, None if member.bit_size is None else "unsupported_type")
                       for member in dtype.members[:remaining]]
        elif dtype.kind == "array" and dtype.element_type is not None and dtype.element_count is not None:
            actual_total = dtype.element_count
            members = [(str(index), dtype.element_type, None) for index in range(min(dtype.element_count, remaining))]
        root.descendants += len(members)
        children: list[SourceItem] = []
        context = None if view.binding_ok and view.index.complete else (
            "coverage_incomplete" if not view.index.complete else
            "probe_required" if view.binding is None else "source_mismatch")
        for ordinal, (name, child_type, intrinsic) in enumerate(members):
            kind = "element" if dtype.kind == "array" else "member"
            selector = f"{item.selector}[{name}]" if kind == "element" else f"{item.selector}.{name}"
            if kind == "member":
                if not _EXPRESSION.fullmatch(name):
                    intrinsic = "unsupported_type"
                elif member_name_counts[name] > 1 and intrinsic is None:
                    intrinsic = "ambiguous_symbol"
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
                               bool(depth_limited or child_type is not None and child_type.kind == "array" and
                                    child_type.element_count is not None and child_type.element_count > 4096))
            children.append(child)
            view.nodes[identifier] = _Node(child, child_type if expandable else None,
                                           parent.depth + 1, 0)
        result = tuple(children), actual_total
        view.children_cache[item.id] = result
        return result

    async def page(self, *, query: str, cursor: str | None, limit: int,
                   parent_id: str | None, catalog_id: str | None,
                   binding: object | None, binding_epoch: int) -> dict[str, object]:
        if (type(query) is not str or len(query) > 128 or any(ord(c) < 32 for c in query)
                or type(limit) is not int or not 1 <= limit <= 100
                or parent_id is not None and (not isinstance(parent_id, str) or not _ID.fullmatch(parent_id))
                or catalog_id is not None and (not isinstance(catalog_id, str) or not _ID.fullmatch(catalog_id))):
            raise SourceCatalogFailure("MONITOR_SOURCE_INDEX_FAILED", "Source catalog query is invalid")
        normalized = unicodedata.normalize("NFC", query.strip()).casefold()
        view = await self._view(binding, binding_epoch, catalog_id)
        if catalog_id is not None and catalog_id != view.catalog_id:
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog identity changed")
        if parent_id is not None:
            if catalog_id is None or parent_id not in view.nodes:
                raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source catalog parent changed")
            async with self._lock:
                items, actual_total = await asyncio.to_thread(self._children, view, view.nodes[parent_id])
        else:
            items = view.roots
            actual_total = len(items)
        result = await asyncio.to_thread(_page_payload, view, items, actual_total,
                                         normalized, cursor, limit, parent_id)
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (current.source_sha, current.build_id, current.elf_sha) != (
                view.identity["sourceSnapshotSha256"], view.identity["buildId"], view.identity["elfSha256"]):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed during page")
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
                or not view.binding_ok or not view.index.complete):
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source selection is unavailable")
        if await asyncio.to_thread(_eligible_leaf, selector, view.dwarf, binding) is not None:
            raise SourceCatalogFailure("MONITOR_SOURCE_SELECTION_UNAVAILABLE", "Source selection is unavailable")
        current = await asyncio.to_thread(_offline_facts, self.root)
        if (current.source_sha, current.build_id, current.elf_sha) != (
                view.identity["sourceSnapshotSha256"], view.identity["buildId"], view.identity["elfSha256"]):
            raise SourceCatalogFailure("MONITOR_SOURCE_CONTEXT_CHANGED", "Source or firmware changed during selection")
        return {"catalogId": catalog_id, "item": {"kind": "variable", "expression": selector}}
