from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_monitor.source_catalog as module
from stm32_toolkit.debug.source import ClangSourceAdapter, SourceDeclaration, SourceFunction, SourceIndex, SourceIssue, SourcePlan
from stm32_toolkit.debug.types import DwarfMember, DwarfSelection, DwarfType
from stm32_toolkit.debug.dwarf import DwarfCatalog, DwarfSourceFunction, DwarfSourceSymbol


def test_shared_wire_fixture_uses_backend_item_serializer() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "source_catalog_envelope.json").read_text(encoding="utf-8"))
    item = module.SourceItem("c" * 64, None, "counter", "int", "Src/main.c", 1, 5,
                             "global", None, (), "none", ("Src/main.c",), "counter",
                             False, "probe_required", False, False)
    assert fixture["operation"] == "monitor.catalog.source.variables"
    assert fixture["data"]["items"] == [item.to_dict()]
    assert fixture["data"]["identity"]["bindingEpoch"] == 0


def test_shared_tree_wire_fixture_uses_backend_page_serializer() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "source_tree_envelope.json").read_text(encoding="utf-8"))
    assert fixture["operation"] == "monitor.catalog.source.tree"
    index = SourceIndex("GNU Arm GCC + Clang", "gcc:14.3.1;clang:21.1.1", "compdb", 1, 1,
                        (), False, (), "f" * 64)
    view = module._View("a" * 64, fixture["data"]["identity"], index,
                        None, (), {}, None, False, {})
    items = (
        {"kind": "file", "id": "d" * 64, "parentId": None, "file": "Src/main.c", "name": "main.c",
         "variableCount": 120, "scopeCount": 2},
        {"kind": "file", "id": "e" * 64, "parentId": None, "file": "Src/safe.c", "name": "safe.c",
         "variableCount": 1, "scopeCount": 1},
        {"kind": "file", "id": "f" * 64, "parentId": None, "file": "Src/empty.c", "name": "empty.c",
         "variableCount": 0, "scopeCount": 0},
    )
    assert fixture["data"] == module._metadata_page_payload(view, items, "", None, 1000, None)


class _Adapter:
    def plan(self, _model: object) -> SourcePlan:
        return SourcePlan((), "compdb", "gcc:14.3.1;clang:21.1.1", "f" * 64)

    def close(self) -> None:
        pass


class _Dwarf:
    def __init__(self, declarations: tuple[SourceDeclaration, ...] = (),
                 dtype: DwarfType | None = None) -> None:
        scalar = dtype or DwarfType("integer", "int", 4)
        self.symbols = tuple(DwarfSourceSymbol(
            decl.name, decl.file, decl.line, None, decl.function,
            decl.translation_units[0], scalar, 0x20000000 + 4 * index,
            None, None, storage=decl.storage, scope_kind=decl.scope_kind,
        ) for index, decl in enumerate(declarations))

    def source_symbols(self) -> tuple[DwarfSourceSymbol, ...]:
        return self.symbols

    def lookup(self, selector: str) -> DwarfSelection:
        symbol = next(item for item in self.symbols if item.name == selector)
        assert symbol.address is not None and symbol.dwarf_type is not None
        return DwarfSelection(selector, symbol.address, symbol.dwarf_type)


def _setup(monkeypatch: pytest.MonkeyPatch, root: Path, *, aggregate: bool = False):
    model = SimpleNamespace(project_root=root, logical_project_id="project",
                            target=SimpleNamespace(device="STM32F407VG"))
    facts = [module._Facts(model, "b" * 64, "build", "e" * 64, None, None)]
    names = ("array",) if aggregate else ("first", "second")
    declarations = tuple(SourceDeclaration(char * 64, char * 64, name, "int", "Src/main.c", index + 1,
                                           1, "none", "global", None, (), ("Src/main.c",))
                         for index, (char, name) in enumerate(zip("cd", names)))
    index = SourceIndex("GNU Arm GCC + Clang", "gcc:14.3.1;clang:21.1.1", "compdb", 1, 1,
                        (), False, declarations, "f" * 64)
    dtype = DwarfType("array", "int[5000]", 20_000, element_type=DwarfType("integer", "int", 4), element_count=5000)
    dwarf = _Dwarf(declarations, dtype if aggregate else None)
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts[0])
    monkeypatch.setattr(module, "_load_base", lambda _adapter, _facts, _plan:
                        module._Base(index, dwarf, ("Src/main.c",)))
    def item_for(decl, *_args):
        return module.SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                                 decl.column, "global", None, (), "none", decl.translation_units,
                                 decl.name, False if aggregate else True,
                                 "aggregate" if aggregate else None, aggregate, aggregate), dtype if aggregate else None
    monkeypatch.setattr(module, "_item_for_declaration", item_for)
    monkeypatch.setattr(module, "_eligible_leaf",
                        lambda _selector, _dwarf, current_binding, *_args:
                        "probe_required" if current_binding is None else None)
    binding = SimpleNamespace(project_root=root, workspace_id="workspace", observation_session_id="session",
                              logical_project_id="project", target_device="STM32F407VG", build_id="build",
                              elf_sha256="e" * 64, input_snapshot_sha256="b" * 64, probe_id="probe", lease_id="lease")
    provider = module.SourceCatalogProvider(root, "workspace", "session", _Adapter())
    return provider, facts, binding


def test_page_cursor_and_selection_recheck_source_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, facts, binding = _setup(monkeypatch, tmp_path)

    async def scenario() -> None:
        first = await provider.page(query="", cursor=None, limit=1, parent_id=None, catalog_id=None,
                                    binding=binding, binding_epoch=0)
        assert first["total"] == 2 and len(first["items"]) == 1 and first["nextCursor"]
        second = await provider.page(query="", cursor=first["nextCursor"], limit=1, parent_id=None,
                                     catalog_id=first["catalogId"], binding=binding, binding_epoch=0)
        assert second["items"][0]["id"] != first["items"][0]["id"]
        selected = await provider.select(catalog_id=first["catalogId"], item_id=first["items"][0]["id"],
                                         selector=first["items"][0]["selector"], binding=binding, binding_epoch=0)
        assert selected["item"] == {"kind": "variable", "expression": "first"}
        facts[0] = module._Facts(facts[0].model, "9" * 64, "build", "e" * 64, None, None)
        with pytest.raises(module.SourceCatalogFailure, match="identity changed") as raised:
            await provider.select(catalog_id=first["catalogId"], item_id=first["items"][0]["id"],
                                  selector="first", binding=binding, binding_epoch=0)
        assert raised.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        with pytest.raises(module.SourceCatalogFailure) as cursor_error:
            await provider.page(query="", cursor=first["nextCursor"], limit=1, parent_id=None,
                                catalog_id=first["catalogId"], binding=binding, binding_epoch=0)
        assert cursor_error.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        provider.close()

    asyncio.run(scenario())


def test_aggregate_descendants_stop_at_root_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _, binding = _setup(monkeypatch, tmp_path, aggregate=True)

    async def scenario() -> None:
        root = await provider.page(query="array", cursor=None, limit=100, parent_id=None, catalog_id=None,
                                   binding=binding, binding_epoch=0)
        assert root["items"][0]["expandable"] and root["items"][0]["truncated"]
        parent_id = root["items"][0]["id"]
        child = await provider.page(query="", cursor=None, limit=100, parent_id=parent_id,
                                    catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
        assert child["total"] == 4096 and len(child["items"]) == 100
        count = 100
        while child["nextCursor"] is not None:
            child = await provider.page(query="", cursor=child["nextCursor"], limit=100, parent_id=parent_id,
                                        catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
            count += len(child["items"])
        assert count == 4096 and child["nextCursor"] is None
        provider.close()

    asyncio.run(scenario())


def test_sparse_aggregate_array_retains_late_readable_element_beyond_page_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scalar = DwarfType("integer", "int", 4)
    element = DwarfType("structure", "Element", 4,
                        members=(DwarfMember("value", 0, scalar),))
    dtype = DwarfType("array", "Element[5000]", 20_000,
                      element_type=element, element_count=5000)
    base = 0x20000000
    readable = base + 1000 * element.byte_size
    dwarf = SimpleNamespace(readable_regions=((readable, readable + 4),))
    monkeypatch.setattr(module, "_eligible_leaf", lambda selector, *_args:
                        "probe_required" if "[1000]" in selector else "read_range_denied")
    root = module.SourceItem("c" * 64, None, "records", dtype.name, "Src/main.c", 1, 1,
                             "global", None, (), "none", ("Src/main.c",), "records",
                             False, "aggregate", True, False)
    node = module._Node(root, dtype, 0, 0, base)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True, (), "f" * 64)
    view = module._View("a" * 64, {}, index, dwarf, (root,), {root.id: node},
                        None, False, {})
    assert module._observable_descendant("records", dtype, dwarf, base, 0, [4096])
    provider = module.SourceCatalogProvider(Path("."), "workspace", "session", _Adapter())
    try:
        children, total = provider._children(view, node)
        assert total == 1
        assert [item.selector for item in children] == ["records[1000]"]
        leaves, count = provider._children(view, view.nodes[children[0].id])
        assert count == 1 and leaves[0].selector == "records[1000].value"
        assert leaves[0].reason == "probe_required"
        monkeypatch.setattr(module, "_eligible_leaf", lambda *_args: "probe_required")
        full = SimpleNamespace(readable_regions=((base, base + dtype.byte_size),))
        full_root = module._Node(root, dtype, 0, 0, base)
        full_view = module._View("b" * 64, {}, index, full, (root,),
                                 {root.id: full_root}, None, False, {})
        bounded, bounded_total = provider._children(full_view, full_root)
        assert bounded_total == 4096 // 2
        assert bounded[0].truncated is False and bounded[-1].truncated is True
        final_leaf, final_count = provider._children(full_view, full_view.nodes[bounded[-1].id])
        assert final_count == 1 and final_leaf[0].selector == f"{bounded[-1].selector}.value"
    finally:
        provider.close()


@pytest.mark.parametrize("array_root", [False, True])
def test_budget_does_not_expose_an_aggregate_without_room_for_its_scalar(
        array_root: bool) -> None:
    scalar = DwarfType("integer", "int", 4)
    inner = DwarfType("structure", "Inner", 4, members=(DwarfMember("value", 0, scalar),))
    dtype = (DwarfType("array", "Inner[1]", 4, element_type=inner, element_count=1)
             if array_root else DwarfType("structure", "Root", 4,
                                          members=(DwarfMember("inner", 0, inner),)))
    base = 0x20000000
    class Catalog:
        readable_regions = ((base, base + 4),)
        def lookup(self, selector: str) -> DwarfSelection:
            return DwarfSelection(selector, base, scalar)
    root = module.SourceItem("c" * 64, None, "root", dtype.name, "Src/main.c", 1, 1,
                             "global", None, (), "none", ("Src/main.c",), "root",
                             False, "aggregate", True, False)
    node = module._Node(root, dtype, 0, 4095, base)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True, (), "f" * 64)
    view = module._View("a" * 64, {}, index, Catalog(), (root,), {root.id: node}, None, False, {})
    provider = module.SourceCatalogProvider(Path("."), "workspace", "session", _Adapter())
    try:
        with pytest.raises(module.SourceCatalogFailure, match="reached its bound") as failure:
            provider._children(view, node)
        assert failure.value.code == "MONITOR_SOURCE_INDEX_FAILED"
        assert view.nodes == {root.id: node}
        assert node.descendants == 4095 and node.reserved_descendants == 0
    finally:
        provider.close()


def test_aggregate_reservations_survive_sibling_expansion_order() -> None:
    scalar = DwarfType("integer", "int", 4)
    inner = DwarfType("structure", "Inner", 4, members=(DwarfMember("value", 0, scalar),))
    members = (DwarfMember("first", 0, inner), DwarfMember("second", 4, inner),
               *(DwarfMember(f"leaf{index}", 8 + index * 4, scalar) for index in range(4094)))
    dtype = DwarfType("structure", "Root", len(members) * 4, members=members)
    base = 0x20000000
    addresses = {f"root.{member.name}.value" if member.type is inner else f"root.{member.name}":
                 base + member.offset for member in members}
    class Catalog:
        readable_regions = ((base, base + dtype.byte_size),)
        def lookup(self, selector: str) -> DwarfSelection:
            return DwarfSelection(selector, addresses[selector], scalar)
    root = module.SourceItem("c" * 64, None, "root", dtype.name, "Src/main.c", 1, 1,
                             "global", None, (), "none", ("Src/main.c",), "root",
                             False, "aggregate", True, False)
    # The root's first proved path contains two descendant nodes.
    node = module._Node(root, dtype, 0, 0, base, 2, 2)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True, (), "f" * 64)
    view = module._View("a" * 64, {}, index, Catalog(), (root,), {root.id: node}, None, False, {})
    provider = module.SourceCatalogProvider(Path("."), "workspace", "session", _Adapter())
    try:
        children, total = provider._children(view, node)
        assert total == 4094 and children[-1].truncated
        assert node.descendants == 4094 and node.reserved_descendants == 2
        second, first = children[1], children[0]
        for item in (second, first):
            leaves, count = provider._children(view, view.nodes[item.id])
            assert count == 1 and leaves[0].selector == f"{item.selector}.value"
        assert node.descendants == 4096 and node.reserved_descendants == 0
    finally:
        provider.close()


@pytest.mark.parametrize("wrong_type", [False, True])
def test_aggregate_leaf_requires_exact_source_address_and_type_at_proof_and_selection(
        monkeypatch: pytest.MonkeyPatch, wrong_type: bool) -> None:
    scalar = DwarfType("integer", "int", 4)
    other_type = DwarfType("float", "float", 4)
    aggregate = DwarfType("structure", "Box", 4, members=(DwarfMember("value", 0, scalar),))
    base = 0x20000000
    class Catalog:
        readable_regions = ((base, base + 4), (base + 0x1000, base + 0x1004))
        def __init__(self) -> None:
            self.mismatch = True
        def lookup(self, selector: str) -> DwarfSelection:
            assert selector == "box.value"
            return DwarfSelection(selector, base if wrong_type or not self.mismatch else base + 0x1000,
                                  other_type if wrong_type and self.mismatch else scalar)
    dwarf = Catalog()
    symbol = DwarfSourceSymbol("box", "Src/a.c", 1, 1, None, "Src/a.c", aggregate,
                               base, None, None, cu_offset=0, die_offset=1)
    root = module.SourceItem("c" * 64, None, "box", "Box", "Src/a.c", 1, 1,
                             "global", None, (), "none", ("Src/a.c",), "box",
                             False, "aggregate", True, False)
    assert not module._root_observable(root, aggregate, dwarf, symbol)
    dwarf.mismatch = False
    assert module._root_observable(root, aggregate, dwarf, symbol)
    node = module._Node(root, aggregate, 0, 0, base, 1, 1)
    region = SimpleNamespace(origin=base, length=4, attributes="rw")
    binding = SimpleNamespace(memory_regions=(region,))
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True, (), "f" * 64)
    view = module._View("a" * 64, {}, index, dwarf, (root,), {root.id: node}, binding, True, {})
    provider = module.SourceCatalogProvider(Path("."), "workspace", "session", _Adapter())
    try:
        children, total = provider._children(view, node)
        assert total == 1 and children[0].can_add
        dwarf.mismatch = True
        async def saved_view(*_args: object) -> module._View:
            return view
        monkeypatch.setattr(provider, "_view", saved_view)
        async def scenario() -> None:
            with pytest.raises(module.SourceCatalogFailure) as failure:
                await provider.select(catalog_id=view.catalog_id, item_id=children[0].id,
                                      selector="box.value", binding=binding, binding_epoch=0)
            assert failure.value.code == "MONITOR_SOURCE_SELECTION_UNAVAILABLE"
        asyncio.run(scenario())
    finally:
        provider.close()


def test_unreadable_large_array_is_pruned_without_hiding_safe_sibling() -> None:
    scalar = DwarfType("integer", "int", 4)
    large = DwarfType("array", "int[5000]", 20_000, element_type=scalar, element_count=5000)
    safe = DwarfSourceSymbol("safe", "Src/safe.c", 1, 1, None, "Src/safe.c", scalar,
                             0x20010000, None, None, cu_offset=0, die_offset=1)
    unreadable = DwarfSourceSymbol("unreadable", "Src/unreadable.c", 1, 1, None,
                                   "Src/unreadable.c", large, 0x20000000,
                                   None, None, cu_offset=0, die_offset=2)
    class Catalog:
        elf_sha256 = "e" * 64
        readable_regions = ((0x20010000, 0x20010004),)
        def source_declarations(self) -> tuple[DwarfSourceSymbol, ...]:
            return safe, unreadable
        def lookup(self, selector: str) -> DwarfSelection:
            assert selector == "safe"
            return DwarfSelection(selector, safe.address, scalar)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True, (), "f" * 64)
    roots, _ = module._materialize(index, Catalog(), None, None,
                                   ("Src/safe.c", "Src/unreadable.c"))
    assert [item.name for item in roots] == ["safe"]
    catalog = Catalog()
    catalog.readable_regions = ((unreadable.address + 4500 * 4,
                                 unreadable.address + 4501 * 4),)
    with pytest.raises(module.SourceCatalogFailure, match="scan reached its bound") as failure:
        module._materialize(index, catalog, None, None,
                            ("Src/safe.c", "Src/unreadable.c"))
    assert failure.value.code == "MONITOR_SOURCE_INDEX_FAILED"


def test_partial_catalog_keeps_nested_navigation_but_root_retry_reindexes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _, binding = _setup(monkeypatch, tmp_path, aggregate=True)
    scalar = DwarfType("integer", "int", 4)
    nested = DwarfType("structure", "Nested", 4, members=(DwarfMember("value", 0, scalar),))
    outer = DwarfType("structure", "Outer", 4, members=(DwarfMember("nested", 0, nested),))
    declaration = SourceDeclaration("c" * 64, "c" * 64, "record", "Outer", "Src/main.c", 1,
                                    1, "none", "global", None, (), ("Src/main.c",))
    partial = SourceIndex("engine", "gcc:14.3.1;clang:21.1.1", "compdb", 2, 1,
                          (SourceIssue("Src/other.c", "MONITOR_SOURCE_INDEX_FAILED", "failed"),),
                          False, (declaration,), "f" * 64)
    loads = [0]

    def load(_adapter, _facts, _plan):
        loads[0] += 1
        return module._Base(partial, _Dwarf((declaration,), outer), ("Src/main.c",))

    monkeypatch.setattr(module, "_load_base", load)
    monkeypatch.setattr(module, "_item_for_declaration", lambda decl, *_args: (
        module.SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                          decl.column, "global", None, (), "none", decl.translation_units,
                          "record", False, "aggregate", True, False), outer))

    async def scenario() -> None:
        root = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=binding, binding_epoch=0)
        assert not root["coverage"]["complete"] and loads == [1]
        child = await provider.page(query="", cursor=None, limit=100, parent_id=root["items"][0]["id"],
                                    catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
        assert child["items"][0]["name"] == "nested"
        grandchild = await provider.page(query="", cursor=None, limit=100, parent_id=child["items"][0]["id"],
                                         catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
        assert grandchild["items"][0]["name"] == "value"
        assert loads == [1]
        retry = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                    catalog_id=None, binding=binding, binding_epoch=0,
                                    refresh=True)
        assert retry["catalogId"] == root["catalogId"] and loads == [2]
        with pytest.raises(module.SourceCatalogFailure) as invalid:
            await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                scope_id="a" * 64, catalog_id=None, binding=binding,
                                binding_epoch=0, refresh=True)
        assert invalid.value.code == "MONITOR_SOURCE_INDEX_FAILED"
        provider.close()

    asyncio.run(scenario())


def test_depth_limit_prunes_aggregate_without_reachable_scalar(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _, binding = _setup(monkeypatch, tmp_path, aggregate=True)
    dtype = DwarfType("integer", "int", 4)
    for depth in range(7):
        dtype = DwarfType("structure", f"Nested{depth}", 4,
                          members=(DwarfMember("next", 0, dtype),))
    monkeypatch.setattr(module, "_item_for_declaration", lambda decl, *_args: (
        module.SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                          decl.column, "global", None, (), "none", decl.translation_units,
                          "array", False, "aggregate", True, False), dtype))

    async def scenario() -> None:
        root = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=binding, binding_epoch=0)
        assert root["total"] == 0 and root["items"] == []
        tree = await provider.tree(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
        assert tree["items"] == []
        provider.close()

    asyncio.run(scenario())


def test_cancelled_waiter_cannot_pin_a_completed_partial_index(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _, binding = _setup(monkeypatch, tmp_path)
    declaration = SourceDeclaration("c" * 64, "c" * 64, "counter", "int", "Src/main.c", 1,
                                    1, "none", "global", None, (), ("Src/main.c",))
    complete = SourceIndex("engine", "version", "compdb", 1, 1, (), False,
                           (declaration,), "f" * 64)
    partial = replace(complete, parsed_units=0,
                      issues=(SourceIssue("Src/main.c", "MONITOR_SOURCE_INDEX_FAILED", "failed"),))
    entered = threading.Event()
    release = threading.Event()
    loads = [0]

    def load(_adapter, _facts, _plan):
        loads[0] += 1
        if loads[0] == 1:
            entered.set()
            assert release.wait(timeout=5)
            return module._Base(partial, _Dwarf(), ("Src/main.c",))
        return module._Base(complete, _Dwarf(), ("Src/main.c",))

    monkeypatch.setattr(module, "_load_base", load)

    async def scenario() -> None:
        first = asyncio.create_task(provider.page(query="", cursor=None, limit=100, parent_id=None,
                                                 catalog_id=None, binding=binding, binding_epoch=0))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        finally:
            release.set()
        await asyncio.sleep(0.05)
        retry = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                    catalog_id=None, binding=binding, binding_epoch=0,
                                    refresh=True)
        assert loads == [2] and retry["coverage"]["complete"]
        assert not provider._inflight
        provider.close()

    asyncio.run(scenario())


def test_duplicate_and_unnamed_members_prune_empty_aggregate(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _, binding = _setup(monkeypatch, tmp_path, aggregate=True)
    scalar = DwarfType("integer", "int", 4)
    dtype = DwarfType("structure", "Members", 16, members=(
        DwarfMember("", 0, scalar), DwarfMember("", 4, scalar),
        DwarfMember("same", 8, scalar), DwarfMember("same", 12, scalar)))
    monkeypatch.setattr(module, "_item_for_declaration", lambda decl, *_args: (
        module.SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                          decl.column, "global", None, (), "none", decl.translation_units,
                          "array", False, "aggregate", True, False), dtype))

    async def scenario() -> None:
        root = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=binding, binding_epoch=0)
        assert root["total"] == 0 and root["items"] == []
        provider.close()

    asyncio.run(scenario())


@pytest.fixture
def real_source_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A tiny owned ARM ELF gives the provider real AST, DWARF and old lookup."""
    root = tmp_path / "source-project"
    (root / "Src").mkdir(parents=True)
    (root / "Inc").mkdir()
    (root / "Inc" / "defs.h").write_text(
        "extern int counter;\nstruct Packet { int a; int b; };\n"
        "static int header_static = 7;\n", encoding="utf-8")
    (root / "Src" / "main.c").write_text(
        '#include "defs.h"\nint counter = 3;\nstatic int duplicate = 4;\n'
        'struct Packet packet = {1,2};\nint values[3] = {1,2,3};\n'
        'int sample(int parameter) { static int retained = 5; int local = parameter; '
        'return local + retained + duplicate + header_static; }\n', encoding="utf-8")
    (root / "Src" / "other.c").write_text(
        '#include "defs.h"\nstatic int duplicate = 6;\n'
        'int other(void) { return duplicate + header_static; }\n', encoding="utf-8")
    adapter = ClangSourceAdapter(ninja=None)
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    elf = root / "firmware.elf"
    command = [str(adapter.preprocessor), "-gdwarf-4", "-O0", "-mcpu=cortex-m4", "-mthumb",
               "-nostdlib", "-I", str(root / "Inc"), "-Wl,-Ttext=0x08000000",
               "-Wl,-Tdata=0x20000000", "-Wl,-e,0", "-o", str(elf),
               str(root / "Src" / "main.c"), str(root / "Src" / "other.c")]
    result = subprocess.run(command, cwd=root, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    ram = SimpleNamespace(name="RAM", origin=0x20000000, length=0x10000, attributes="rw")
    flash = SimpleNamespace(name="FLASH", origin=0x08000000, length=0x10000, attributes="rx")
    model = SimpleNamespace(
        project_root=root, logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG", core="cortex-m4", fpu=None, float_abi=None),
        memory=SimpleNamespace(regions=(ram, flash)),
        build=SimpleNamespace(sources=("Src/main.c", "Src/other.c"), include_paths=("Inc",),
                              defines=(), compile_options=(), presets=(), elf="firmware.elf"))
    data = elf.read_bytes()
    facts = [module._Facts(model, "b" * 64, "build", hashlib.sha256(data).hexdigest(),
                           "firmware.elf", len(data),
                           ("Inc/defs.h", "Src/main.c", "Src/other.c"),
                           ("Inc/defs.h", "Src/main.c", "Src/other.c"))]
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts[0])
    binding = SimpleNamespace(
        project_root=root, workspace_id="workspace", observation_session_id="session",
        logical_project_id="project", target_device="STM32F407VG", build_id="build",
        elf_sha256=facts[0].elf_sha, input_snapshot_sha256="b" * 64,
        probe_id="probe", lease_id="lease", memory_regions=(ram, flash))
    provider = module.SourceCatalogProvider(root, "workspace", "session", adapter)
    yield provider, facts, binding
    provider.close()


def test_real_ast_elf_attribution_leaf_children_and_binding_rechecks(real_source_project) -> None:
    provider, facts, binding = real_source_project

    async def scenario() -> None:
        page = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=binding, binding_epoch=0)
        assert page["coverage"]["complete"], page["coverage"]["issues"]
        rows = page["items"]
        counter = [item for item in rows if item["name"] == "counter"]
        assert any(item["file"] == "Src/main.c" and item["canAdd"] and item["selector"] == "counter"
                   for item in counter), counter
        assert any(item["file"] == "Inc/defs.h" and item["scope"]["kind"] == "global"
                   for item in counter)
        assert any(item["name"] == "retained" and item["scope"]["kind"] == "static_local"
                   and item["scope"]["function"] == "sample" and item["canAdd"]
                   and item["selector"] == "retained" for item in rows)
        for name in ("duplicate", "header_static"):
            assert not any(item["name"] == name for item in rows)
        for name in ("parameter", "local"):
            assert not any(item["name"] == name for item in rows)
        detached = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                       catalog_id=None, binding=None, binding_epoch=1)
        assert detached["items"] and all(item["reason"] == "probe_required" and not item["canAdd"]
                                         for item in detached["items"])
        for name, child_name, selector in (("packet", "a", "packet.a"),
                                           ("values", "0", "values[0]")):
            root = next(item for item in rows if item["name"] == name)
            assert root["reason"] == "aggregate" and root["expandable"] and not root["canAdd"]
            children = await provider.page(query="", cursor=None, limit=100, parent_id=root["id"],
                                           catalog_id=page["catalogId"], binding=binding, binding_epoch=0)
            child = next(item for item in children["items"] if item["name"] == child_name)
            assert child["canAdd"] and child["selector"] == selector, children["items"]
            selected = await provider.select(catalog_id=page["catalogId"], item_id=child["id"],
                                             selector=selector, binding=binding, binding_epoch=0)
            assert selected["item"]["expression"] == selector
        no_ram = SimpleNamespace(**{**vars(binding), "memory_regions": ()})
        range_page = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                         catalog_id=None, binding=no_ram, binding_epoch=0)
        assert any(item["file"] == "Src/main.c" and item["reason"] == "read_range_denied"
                   for item in range_page["items"])
        wrong_build = SimpleNamespace(**{**vars(binding), "build_id": "other"})
        mismatch = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                       catalog_id=None, binding=wrong_build, binding_epoch=0)
        assert all(not item["canAdd"] and item["reason"] == "source_mismatch"
                   for item in mismatch["items"])
        no_elf = replace(facts[0], build_id=None, elf_sha=None, elf_path=None, elf_size=None)
        facts[0] = no_elf
        unavailable = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                          catalog_id=None, binding=binding, binding_epoch=0)
        assert unavailable["total"] == 0 and unavailable["items"] == []
        denied = replace(facts[0], elf_sha="0" * 64)
        facts[0] = denied
        with pytest.raises(module.SourceCatalogFailure) as changed:
            await provider.select(catalog_id=page["catalogId"], item_id=counter[0]["id"],
                                  selector="counter", binding=binding, binding_epoch=0)
        assert changed.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"

    asyncio.run(scenario())


def test_aggregate_root_crossing_readable_boundary_keeps_proved_member(
    real_source_project,
) -> None:
    provider, facts, binding = real_source_project
    full = DwarfCatalog.from_elf(
        facts[0].elf_path, project_root=facts[0].model.project_root,
        readable_regions=((0x20000000, 0x20010000), (0x08000000, 0x08010000)),
    )
    member = full.lookup("packet.b")
    limited = SimpleNamespace(name="RAM", origin=member.address,
                              length=member.byte_size, attributes="rw")
    flash = binding.memory_regions[1]
    facts[0] = replace(facts[0], model=SimpleNamespace(
        **{**vars(facts[0].model), "memory": SimpleNamespace(regions=(limited, flash))}
    ))
    narrowed = SimpleNamespace(**{**vars(binding), "memory_regions": (limited, flash)})
    restricted = DwarfCatalog.from_elf(
        facts[0].elf_path, project_root=facts[0].model.project_root,
        readable_regions=((limited.origin, limited.origin + limited.length),
                          (flash.origin, flash.origin + flash.length)),
    )
    from stm32_toolkit.debug.dwarf import DwarfError
    with pytest.raises(DwarfError) as root_error:
        restricted.lookup("packet")
    assert root_error.value.code == "DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY"
    assert restricted.lookup("packet.b").address == member.address

    async def scenario() -> None:
        offline = await provider.page(query="packet", cursor=None, limit=100,
                                      parent_id=None, catalog_id=None,
                                      binding=None, binding_epoch=0)
        root = next(item for item in offline["items"] if item["name"] == "packet")
        assert root["reason"] == "aggregate"
        children = await provider.page(query="", cursor=None, limit=100,
                                       parent_id=root["id"], catalog_id=offline["catalogId"],
                                       binding=None, binding_epoch=0)
        assert [item["selector"] for item in children["items"]] == ["packet.b"]
        assert children["total"] == 1
        assert children["items"][0]["reason"] == "probe_required"
        connected = await provider.page(query="packet", cursor=None, limit=100,
                                        parent_id=None, catalog_id=None,
                                        binding=narrowed, binding_epoch=1)
        connected_root = next(item for item in connected["items"] if item["name"] == "packet")
        connected_children = await provider.page(query="", cursor=None, limit=100,
                                                 parent_id=connected_root["id"],
                                                 catalog_id=connected["catalogId"],
                                                 binding=narrowed, binding_epoch=1)
        leaf = connected_children["items"][0]
        assert leaf["canAdd"] and leaf["selector"] == "packet.b"
        selected = await provider.select(catalog_id=connected["catalogId"],
                                         item_id=leaf["id"], selector="packet.b",
                                         binding=narrowed, binding_epoch=1)
        assert selected["item"]["expression"] == "packet.b"

    asyncio.run(scenario())


def test_real_provider_partial_retry_reindexes_same_inputs(real_source_project) -> None:
    provider, _, binding = real_source_project
    original = provider.adapter.index
    attempts = [0]

    def fail_once(model, plan):
        result = original(model, plan)
        attempts[0] += 1
        if attempts[0] == 1:
            return replace(result, parsed_units=result.parsed_units - 1,
                           issues=(SourceIssue("Src/other.c", "MONITOR_SOURCE_INDEX_FAILED", "failed"),))
        return result

    provider.adapter.index = fail_once

    async def scenario() -> None:
        partial = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                      catalog_id=None, binding=binding, binding_epoch=0)
        assert not partial["coverage"]["complete"]
        assert any(item["canAdd"] for item in partial["items"])
        cached = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                     catalog_id=None, binding=binding, binding_epoch=0)
        assert cached["catalogId"] == partial["catalogId"] and attempts == [1]
        complete = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                       catalog_id=None, binding=binding, binding_epoch=0,
                                       refresh=True)
        assert complete["coverage"]["complete"] and attempts == [2]
        assert complete["catalogId"] != partial["catalogId"]
        assert any(item["canAdd"] for item in complete["items"])

    asyncio.run(scenario())


def test_real_provider_policy_revision_rejects_old_selection_and_cursor(
    real_source_project, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_toolkit.debug import source_asm_compat

    provider, _, binding = real_source_project

    async def scenario() -> None:
        first = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                    catalog_id=None, binding=binding, binding_epoch=0)
        old_item = next(item for item in first["items"] if item["canAdd"])
        first_page = await provider.page(query="", cursor=None, limit=1, parent_id=None,
                                         catalog_id=None, binding=binding, binding_epoch=0)
        assert first_page["nextCursor"] is not None
        monkeypatch.setattr(source_asm_compat, "POLICY_VERSION", source_asm_compat.POLICY_VERSION + "-next")
        revised = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                      catalog_id=None, binding=binding, binding_epoch=0)
        assert revised["coverage"]["complete"] and revised["catalogId"] != first["catalogId"]
        with pytest.raises(module.SourceCatalogFailure) as stale_selection:
            await provider.select(catalog_id=first["catalogId"], item_id=old_item["id"],
                                  selector=old_item["selector"], binding=binding, binding_epoch=0)
        assert stale_selection.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        with pytest.raises(module.SourceCatalogFailure) as stale_cursor:
            await provider.page(query="", cursor=first_page["nextCursor"], limit=1, parent_id=None,
                                catalog_id=first_page["catalogId"], binding=binding, binding_epoch=0)
        assert stale_cursor.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"

    asyncio.run(scenario())


def test_partial_ast_still_exposes_compiled_functions_parameters_and_selection(real_source_project) -> None:
    provider, _, binding = real_source_project
    original = provider.adapter.index

    def missing_main_ast(model, plan):
        result = original(model, plan)
        source_only = SourceDeclaration("a" * 64, "a" * 64, "phantom", "int", "Src/other.c", 2,
                                        1, "none", "global", None, (), ("Src/other.c",))
        return replace(result, parsed_units=result.parsed_units - 1,
                       declarations=tuple(entry for entry in result.declarations
                                          if "Src/main.c" not in entry.translation_units) + (source_only,),
                       functions=tuple(entry for entry in result.functions
                                       if "Src/main.c" not in entry.translation_units),
                       issues=(SourceIssue("Src/main.c", "MONITOR_SOURCE_INDEX_FAILED", "Clang failed"),))

    provider.adapter.index = missing_main_ast

    async def scenario() -> None:
        tree = await provider.tree(query="", cursor=None, limit=1000, parent_id=None,
                                   catalog_id=None, binding=binding, binding_epoch=0)
        assert not tree["coverage"]["complete"]
        assert tree["coverage"]["compiledDebug"]["available"]
        main = next(item for item in tree["items"] if item["file"] == "Src/main.c")
        assert main["variableCount"] > 0 and main["scopeCount"] > 0
        scopes = await provider.tree(query="", cursor=None, limit=1000, parent_id=main["id"],
                                     catalog_id=tree["catalogId"], binding=binding, binding_epoch=0)
        sample = next(item for item in scopes["items"] if item["function"] == "sample")
        assert sample["variableCount"] == 1
        variables = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                        scope_id=sample["id"], catalog_id=tree["catalogId"],
                                        binding=binding, binding_epoch=0)
        assert [item["name"] for item in variables["items"]] == ["retained"]
        global_scope = next(item for item in scopes["items"] if item["function"] is None)
        globals_page = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                           scope_id=global_scope["id"], catalog_id=tree["catalogId"],
                                           binding=binding, binding_epoch=0)
        counter = next(item for item in globals_page["items"] if item["name"] == "counter")
        assert counter["canAdd"] and counter["selector"] == "counter"
        assert (await provider.select(catalog_id=tree["catalogId"], item_id=counter["id"],
                                      selector="counter", binding=binding, binding_epoch=0))["item"]["expression"] == "counter"
        for name, child_name, selector in (("packet", "a", "packet.a"),
                                           ("values", "0", "values[0]")):
            root = next(item for item in globals_page["items"] if item["name"] == name)
            assert root["expandable"] and root["reason"] == "aggregate"
            children = await provider.page(query="", cursor=None, limit=100, parent_id=root["id"],
                                           catalog_id=tree["catalogId"], binding=binding, binding_epoch=0)
            child = next(item for item in children["items"] if item["name"] == child_name)
            assert child["canAdd"] and child["selector"] == selector
            assert (await provider.select(catalog_id=tree["catalogId"], item_id=child["id"],
                                          selector=selector, binding=binding, binding_epoch=0))["item"]["expression"] == selector
        other = await provider.page(query="phantom", cursor=None, limit=100, parent_id=None,
                                    catalog_id=tree["catalogId"], binding=binding, binding_epoch=0)
        assert other["total"] == 0 and other["items"] == []

    asyncio.run(scenario())


def test_compiled_local_reason_only_promises_frame_for_frame_or_register_location() -> None:
    dtype = DwarfType("integer", "int", 4)
    base = DwarfSourceSymbol("local", "Src/main.c", 5, 3, "main", "Src/main.c",
                             dtype, None, "DWARF_LOCATION_OPTIMIZED_OUT", None,
                             0, 10, 8, (), "none", "local", "variable", "unavailable")
    dwarf = SimpleNamespace(elf_sha256="e" * 64)
    optimized, _ = module._item_for_dwarf(base, dwarf, None, None)
    frame, _ = module._item_for_dwarf(replace(base, die_offset=11,
                                              location_error="DWARF_LOCATION_UNAVAILABLE",
                                              location_kind="frame"), dwarf, None, None)
    register, _ = module._item_for_dwarf(replace(base, die_offset=12,
                                                 location_error="DWARF_LOCATION_REGISTER_ONLY",
                                                 location_kind="register"), dwarf, None, None)
    assert optimized.reason == "unsupported_location"
    assert frame.reason == register.reason == "frame_required"
    assert not any(item.can_add for item in (optimized, frame, register))


def test_one_debug_symbol_cannot_authorize_two_distinct_source_entities() -> None:
    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("value", "Src/main.c", 1, None, None,
                               "Src/main.c", dtype, 0x20000000, None, None,
                               storage="static", scope_kind="file_static")
    first = SourceDeclaration("a" * 64, "a" * 64, "value", "int", "Src/main.c", 1, 5,
                              "static", "file_static", None, (), ("Src/main.c",))
    second = replace(first, id="b" * 64, entity_id="b" * 64, column=20)
    same_entity = replace(second, entity_id=first.entity_id)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), False,
                        (first, second), "f" * 64)

    class Catalog:
        def source_symbols(self):
            return (symbol,)

        def lookup(self, _selector):
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)

    roots, _ = module._materialize(index, Catalog(), "probe_required", None)
    assert all(item.reason == "ambiguous_symbol" and not item.can_add for item in roots)
    excluded, _ = module._materialize(index, Catalog(), "probe_required", None, source_files=())
    assert excluded == ()
    chained, _ = module._materialize(replace(index, declarations=(first, same_entity)),
                                     Catalog(), "probe_required", None)
    assert all(item.reason == "probe_required" for item in chained)


def test_concrete_die_only_coalesces_a_unique_ast_entity() -> None:
    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("value", "Src/main.c", 9, None, "work", "Src/main.c",
                               dtype, 0x20000000, None, None, cu_offset=0, die_offset=10,
                               function_die_offset=8, scope_path=("block@1",),
                               storage="static", scope_kind="static_local")
    first = SourceDeclaration("a" * 64, "a" * 64, "value", "int", "Src/main.c", 9, 5,
                              "static", "static_local", "work", ("block@1",), ("Src/main.c",),
                              function_id="f" * 64)
    second = replace(first, id="b" * 64, entity_id="b" * 64,
                     column=20, scope_path=("block@2",))
    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))

    class Catalog:
        elf_sha256 = "e" * 64
        def source_declarations(self):
            return (symbol,)
        def lookup(self, _selector):
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)

    def materialize(*declarations):
        index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                            declarations, "f" * 64)
        roots, _ = module._materialize(index, Catalog(), None, binding,
                                       source_files=("Src/main.c",))
        return roots

    (shared_die,) = materialize(first, second)
    assert shared_die.id not in {first.id, second.id}
    assert shared_die.can_add and shared_die.selector == "value"
    assert len(materialize(first)) == 1
    assert len(materialize(first, replace(second, entity_id=first.entity_id))) == 1

    global_symbol = replace(symbol, function=None, function_die_offset=None, scope_path=(),
                            scope_kind="global", storage="none")
    definition = replace(first, function=None, function_id=None, scope_path=(),
                         scope_kind="global", storage="none")
    previous = replace(definition, id="c" * 64, file="Inc/header.h", line=2, column=4,
                       storage="extern", entity_id=definition.entity_id)
    class GlobalCatalog(Catalog):
        def source_declarations(self):
            return (global_symbol,)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                        (definition, previous), "f" * 64)
    roots, _ = module._materialize(index, GlobalCatalog(), None, binding,
                                   source_files=("Src/main.c", "Inc/header.h"))
    assert len(roots) == 2
    assert roots[0].can_add and roots[1].id == previous.id and roots[1].can_add


def test_internal_cu_must_be_proven_for_direct_and_previous_decl_attribution() -> None:
    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("internal", "Inc/header.h", 3, None, None, None,
                               dtype, 0x20000000, None, None, cu_offset=0, die_offset=10,
                               storage="static", scope_kind="file_static")
    definition = SourceDeclaration("a" * 64, "a" * 64, "internal", "int", "Inc/header.h", 3, 5,
                                   "static", "file_static", None, (), ("Src/a.c",))
    previous = replace(definition, id="b" * 64, file="Inc/forward.h", line=1)
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                        (definition, previous), "f" * 64)
    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))

    def materialize(debug_symbol):
        class Catalog:
            elf_sha256 = "e" * 64
            def source_declarations(self):
                return (debug_symbol,)
            def lookup(self, _selector):
                return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)
        roots, _ = module._materialize(index, Catalog(), None, binding,
                                       source_files=("Inc/header.h", "Inc/forward.h"))
        return roots

    for unproven in (symbol, replace(symbol, compilation_unit="Src/b.c")):
        (positive_die,) = materialize(unproven)
        assert positive_die.can_add

    known = materialize(replace(symbol, compilation_unit="Src/a.c"))
    assert len(known) == 2  # The direct declaration coalesces into the positive DIE.
    assert known[0].can_add and known[1].id == previous.id and known[1].can_add

    global_definition = replace(definition, scope_kind="global", storage="none")
    global_previous = replace(previous, scope_kind="global", storage="extern")
    global_index = replace(index, declarations=(global_definition, global_previous))
    class GlobalCatalog:
        elf_sha256 = "e" * 64
        def source_declarations(self):
            return (replace(symbol, scope_kind="global", storage="none",
                            compilation_unit="Src/a.c"),)
        def lookup(self, _selector):
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)
    roots, _ = module._materialize(global_index, GlobalCatalog(), None, binding,
                                   source_files=("Inc/header.h", "Inc/forward.h"))
    assert len(roots) == 2
    assert roots[0].can_add and roots[1].id == previous.id and roots[1].can_add
    class UnknownCuCatalog(GlobalCatalog):
        def source_declarations(self):
            return (replace(symbol, scope_kind="global", storage="none"),)
    unknown, _ = module._materialize(global_index, UnknownCuCatalog(), None, binding,
                                     source_files=("Inc/header.h", "Inc/forward.h"))
    assert len(unknown) == 1 and unknown[0].can_add


def test_header_extern_uses_its_own_tu_definition_and_reports_source_site() -> None:
    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("testtime", "Inc/timer.h", 1, None, None, "Src/timer.c",
                               dtype, 0x20000408, None, None, cu_offset=1, die_offset=2,
                               storage="none", scope_kind="global")
    header = SourceDeclaration("a" * 64, "x" * 64, "testtime", "int", "Inc/timer.h", 1, 12,
                               "extern", "global", None, (), ("Src/timer.c",),
                               entity_by_unit=(("Src/timer.c", "x" * 64),))
    definition = SourceDeclaration("b" * 64, "x" * 64, "testtime", "int", "Src/timer.c", 7, 5,
                                   "none", "global", None, (), ("Src/timer.c",),
                                   entity_by_unit=(("Src/timer.c", "x" * 64),), is_definition=True)
    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))

    class Catalog:
        elf_sha256 = "e" * 64
        def source_declarations(self):
            return (symbol,)
        def lookup(self, _selector):
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000408)

    def materialize(*declarations: SourceDeclaration, debug_symbol=symbol):
        catalog = Catalog()
        catalog.source_declarations = lambda: (debug_symbol,)
        index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                            declarations, "f" * 64)
        roots, _ = module._materialize(index, catalog, None, binding,
                                       source_files=("Inc/timer.h", "Src/timer.c"))
        return roots

    roots = materialize(header, definition)
    dwarf_row = next(item for item in roots if item.id not in {header.id, definition.id})
    assert dwarf_row.declaration_kind == "extern_declaration" and dwarf_row.can_add
    assert dwarf_row.definition_site == ("Src/timer.c", 7)
    actual_definition = next(item for item in roots if item.id == definition.id)
    assert actual_definition.can_add and actual_definition.declaration_kind == "global_definition"
    assert actual_definition.definition_site == ("Src/timer.c", 7)

    mismatches = (
        ("homonym", replace(definition, entity_id="y" * 64,
                            entity_by_unit=(("Src/timer.c", "y" * 64),)), symbol),
        ("wrong-cu", definition, replace(symbol, compilation_unit="Src/other.c")),
        ("wrong-type", replace(definition, type_name="long"), symbol),
        ("internal", replace(definition, storage="static", scope_kind="file_static"), symbol),
        ("local", replace(definition, scope_kind="local", function="work"), symbol),
    )
    for _case, other, debug_symbol in mismatches:
        candidates = materialize(header, other, debug_symbol=debug_symbol)
        assert all(item.id != header.id for item in candidates), _case
    tls = replace(header, storage="thread_local")
    assert all(item.id != tls.id for item in materialize(tls, definition))


def test_tentative_redeclarations_use_unique_initialized_definition_site() -> None:
    dtype = DwarfType("integer", "int", 4)
    unit = "Src/main.c"
    header = SourceDeclaration("a" * 64, "x" * 64, "x", "int", "Inc/vars.h", 1, 12,
                               "extern", "global", None, (), (unit,),
                               entity_by_unit=((unit, "x" * 64),))
    x_tentative = tuple(SourceDeclaration(char * 64, "x" * 64, "x", "int", unit, line, 5,
                                          "none", "global", None, (), (unit,),
                                          entity_by_unit=((unit, "x" * 64),))
                        for char, line in (("b", 2), ("c", 3)))
    x_initialized = SourceDeclaration("d" * 64, "x" * 64, "x", "int", unit, 4, 5,
                                      "none", "global", None, (), (unit,),
                                      entity_by_unit=((unit, "x" * 64),), is_definition=True)
    y_tentative = SourceDeclaration("e" * 64, "y" * 64, "y", "int", unit, 5, 12,
                                    "static", "file_static", None, (), (unit,),
                                    entity_by_unit=((unit, "y" * 64),))
    y_initialized = replace(y_tentative, id="f" * 64, line=6, is_definition=True)
    x_symbol = DwarfSourceSymbol("x", "Inc/vars.h", 1, None, None, unit, dtype,
                                 0x20000000, None, None, cu_offset=1, die_offset=2,
                                 storage="none", scope_kind="global")
    y_symbol = DwarfSourceSymbol("y", unit, 5, None, None, unit, dtype,
                                 0x20000004, None, None, cu_offset=1, die_offset=3,
                                 storage="static", scope_kind="file_static")

    class Catalog:
        elf_sha256 = "e" * 64
        def source_declarations(self):
            return (x_symbol, y_symbol)
        def lookup(self, name):
            address = 0x20000000 if name == "x" else 0x20000004
            return SimpleNamespace(type=dtype, byte_size=4, address=address)

    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                        (header, *x_tentative, x_initialized, y_tentative, y_initialized),
                        "f" * 64)
    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))
    rows, _ = module._materialize(index, Catalog(), None, binding,
                                   source_files=("Inc/vars.h", unit))
    by_id = {row.id: row for row in rows}
    # The exact DIE location deduplicates its AST declaration, but receives
    # that declaration's proved role and the later initialized source site.
    dwarf_header = next(row for row in rows if row.file == "Inc/vars.h")
    assert dwarf_header.can_add and dwarf_header.declaration_kind == "extern_declaration"
    assert dwarf_header.definition_site == (unit, 4)
    assert by_id[x_tentative[0].id].can_add
    assert by_id[x_tentative[0].id].definition_site == (unit, 4)
    dwarf_static = next(row for row in rows if row.name == "y" and row.id != y_initialized.id)
    assert dwarf_static.can_add and dwarf_static.declaration_kind == "file_static"
    assert dwarf_static.definition_site == (unit, 6)

    # C can also end with tentative definitions only. One concrete DIE at an
    # exact tentative site proves that site; neither list order nor the first
    # header declaration chooses it.
    tentative_symbol = replace(x_symbol, file=unit, line=3)
    tentative_catalog = Catalog()
    tentative_catalog.source_declarations = lambda: (tentative_symbol,)
    tentative_index = replace(index, declarations=(header, *x_tentative))
    tentative_rows, _ = module._materialize(tentative_index, tentative_catalog, None, binding,
                                             source_files=("Inc/vars.h", unit))
    tentative_header = next(row for row in tentative_rows if row.id == header.id)
    assert tentative_header.can_add and tentative_header.definition_site == (unit, 3)


@pytest.mark.parametrize("missing_site", ["line", "column", "zero_line", "bool_column"])
def test_real_clang_unmapped_definition_site_cannot_prove_extern_chain(
        tmp_path: Path, missing_site: str) -> None:
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "a.h").write_text("extern int x;\n", encoding="ascii")
    body = ('#line 1000 "Src/a.c"\n' if missing_site == "line" else "") + "int x = 1;\n"
    (tmp_path / "Src" / "a.c").write_text('#include "a.h"\nint x;\n' + body, encoding="ascii")
    model = SimpleNamespace(project_root=tmp_path, build=SimpleNamespace(
        sources=("Src/a.c",), include_paths=("Inc",), defines=(),
        compile_options=(), presets=()))
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        adapter.close()
        pytest.skip("installed GNU Arm GCC and Clang required")
    try:
        index = adapter.index(model)
    finally:
        adapter.close()
    assert index.complete and not index.issues
    header = next(row for row in index.declarations if row.name == "x" and row.file == "Inc/a.h")
    tentative = next(row for row in index.declarations if row.name == "x" and
                     row.file == "Src/a.c" and not row.is_definition)
    definition = next(row for row in index.declarations if row.name == "x" and
                      row.file == "Src/a.c" and row.is_definition)
    assert definition.is_definition
    assert dict(header.entity_by_unit)["Src/a.c"] == dict(definition.entity_by_unit)["Src/a.c"]
    assert dict(tentative.entity_by_unit)["Src/a.c"] == dict(definition.entity_by_unit)["Src/a.c"]
    assert tentative.line is not None and tentative.column is not None
    if missing_site == "line":
        assert definition.line is None and definition.column is None
    else:
        assert definition.line is not None and definition.column is not None
        bad = (replace(definition, column=None) if missing_site == "column" else
               replace(definition, line=0) if missing_site == "zero_line" else
               replace(definition, column=True))
        index = replace(index, declarations=tuple(
            bad if row.id == definition.id else row for row in index.declarations))

    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("x", "Inc/a.h", 1, None, None, "Src/a.c", dtype,
                               0x20000000, None, None, cu_offset=1, die_offset=2,
                               storage="none", scope_kind="global")
    class Catalog:
        elf_sha256 = "e" * 64
        def source_declarations(self):
            return (symbol,)
        def lookup(self, _name):
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)
    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))
    rows, _ = module._materialize(index, Catalog(), None, binding,
                                   source_files=("Inc/a.h", "Src/a.c"))
    assert all(row.id not in {header.id, tentative.id, definition.id} for row in rows)
    assert all(row.to_dict()["declaration"]["definitionSite"] is None for row in rows)


def test_unproved_extern_never_decorates_dwarf_fallback_and_distinct_dies_conflict() -> None:
    dtype = DwarfType("integer", "int", 4)
    unit = "Src/main.c"
    header = SourceDeclaration("a" * 64, "x" * 64, "x", "int", "Inc/vars.h", 1, 12,
                               "extern", "global", None, (), (unit,),
                               entity_by_unit=((unit, "x" * 64),))
    definition = SourceDeclaration("b" * 64, "x" * 64, "x", "int", unit, 2, 5,
                                   "none", "global", None, (), (unit,),
                                   entity_by_unit=((unit, "x" * 64),), is_definition=True)
    header_symbol = DwarfSourceSymbol("x", "Inc/vars.h", 1, None, None, unit,
                                      dtype, 0x20000000, None, None, cu_offset=1,
                                      die_offset=2, storage="none", scope_kind="global")
    source_symbol = replace(header_symbol, file=unit, line=2, die_offset=3)

    class Catalog:
        elf_sha256 = "e" * 64
        def __init__(self, symbols):
            self.symbols = symbols
        def source_declarations(self):
            return self.symbols
        def lookup(self, _name):
            if len(self.symbols) != 1:
                raise module.DwarfError("DWARF_SYMBOL_AMBIGUOUS", "duplicate")
            return SimpleNamespace(type=dtype, byte_size=4, address=0x20000000)

    binding = SimpleNamespace(memory_regions=(SimpleNamespace(origin=0x20000000,
        length=0x1000, attributes="rw"),))
    def rows(*declarations, symbols):
        index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                            declarations, "f" * 64)
        return module._materialize(index, Catalog(symbols), None, binding,
                                    source_files=("Inc/vars.h", unit))[0]

    unproved = rows(header, symbols=(header_symbol,))
    assert all(row.id != header.id for row in unproved)
    fallback = next(row for row in unproved)
    assert fallback.declaration_kind == "unknown" and fallback.definition_site is None

    conflicting = rows(header, definition, symbols=(header_symbol, source_symbol))
    assert conflicting == ()


def test_legal_long_translation_units_fit_page_budget_with_actual_cursor() -> None:
    item = module.SourceItem("0" * 64, None, "wide", "int", "Src/main.c", 1, 1,
                             "global", None, (), "none", ("a" * 512,) * 256,
                             "wide", False, "probe_required", False, False)
    items = tuple(replace(item, id=f"{index:064x}") for index in range(100))
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), False, (), "f" * 64)
    view = module._View("c" * 64, {"workspaceId": "workspace", "bindingEpoch": 0},
                        index, None, items, {}, None, False, {})
    first = module._page_payload(view, items, 100, "", None, 100, None)
    assert first["total"] == 100 and 1 <= len(first["items"]) < 100
    assert first["nextCursor"] is not None
    assert len(json.dumps(first, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) < 1024 * 1024
    second = module._page_payload(view, items, 100, "", first["nextCursor"], 100, None)
    assert second["items"][0]["id"] == items[len(first["items"])].id


def test_tree_real_ast_files_scopes_and_independent_variable_pages(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "decls.inc").write_text("int included_local = 7;\n", encoding="utf-8")
    (tmp_path / "Inc" / "header.h").write_text("extern int header_value;\n", encoding="utf-8")
    (tmp_path / "Src" / "main.c").write_text(
        '#include "header.h"\n' + "".join(f"int main_{number};\n" for number in range(120)) +
        'int main(void) {\n#include "decls.inc"\nreturn included_local;\n}\n'
        'void empty_function(void) {}\n', encoding="utf-8")
    (tmp_path / "Src" / "safe.c").write_text("int safe_value;\n", encoding="utf-8")
    (tmp_path / "Src" / "empty.c").write_text("/* no declarations */\n", encoding="utf-8")
    model = SimpleNamespace(project_root=tmp_path, logical_project_id="project",
                            target=SimpleNamespace(device="STM32F407VG"),
                            build=SimpleNamespace(sources=("Src/main.c", "Src/safe.c", "Src/empty.c"),
                                                  include_paths=("Inc",), defines=(), compile_options=(), presets=()))
    paths = ("Src/main.c", "Src/safe.c", "Src/empty.c", "Inc/header.h", "Inc/decls.inc")
    facts = module._Facts(model, "b" * 64, None, None, None, None,
                          tuple(path for path in paths if path.endswith((".c", ".h"))), paths)
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    provider = module.SourceCatalogProvider(tmp_path, "workspace", "session", adapter)

    async def scenario() -> None:
        first = await provider.tree(query="", cursor=None, limit=1, parent_id=None, catalog_id=None,
                                    binding=None, binding_epoch=0)
        page = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=first["catalogId"], binding=None, binding_epoch=0)
        assert first["total"] == page["total"] == 0
        assert first["items"] == page["items"] == []
        assert first["coverage"]["compiledDebug"]["available"] is False
        assert first["coverage"]["parsedUnits"] == first["coverage"]["totalUnits"]
        # AST coverage remains diagnostic even when no ELF can prove a leaf.
        index = provider._views[first["catalogId"]].index
        assert any(declaration.name == "included_local" for declaration in index.declarations)
        assert any(function.name == "main" for function in index.functions)
        provider.close()

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_eligible_real_ast_scope_paginates_after_filtering_and_keeps_cursor_domains(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "header.h").write_text("extern int header_only;\n", encoding="utf-8")
    (tmp_path / "Src" / "main.c").write_text(
        '#include "header.h"\n' + "".join(f"int main_{number};\n" for number in range(120)) +
        "int main(void) { int automatic = 1; return automatic; }\n",
        encoding="utf-8")
    (tmp_path / "Src" / "safe.c").write_text("int safe_value;\n", encoding="utf-8")
    (tmp_path / "Src" / "empty.c").write_text("/* no declarations */\n", encoding="utf-8")
    model = SimpleNamespace(project_root=tmp_path, logical_project_id="project",
                            target=SimpleNamespace(device="STM32F407VG"),
                            build=SimpleNamespace(sources=("Src/main.c", "Src/safe.c", "Src/empty.c"),
                                                  include_paths=("Inc",), defines=(), compile_options=(), presets=()))
    plan = adapter.plan(model)
    index = adapter.index(model, plan)
    eligible = tuple(declaration for declaration in index.declarations
                     if declaration.name.startswith("main_") or declaration.name == "safe_value")
    assert len(eligible) == 121
    scalar = DwarfType("integer", "int", 4)
    symbols = tuple(DwarfSourceSymbol(
        declaration.name, declaration.file, declaration.line, declaration.column,
        declaration.function, declaration.translation_units[0], scalar,
        0x20000000 + ordinal * 4, None, None, cu_offset=0, die_offset=ordinal + 1,
        storage=declaration.storage, scope_kind=declaration.scope_kind)
        for ordinal, declaration in enumerate(eligible))
    by_name = {symbol.name: symbol for symbol in symbols}
    class Catalog:
        elf_sha256 = "e" * 64
        readable_regions = ((0x20000000, 0x20001000),)
        def source_declarations(self) -> tuple[DwarfSourceSymbol, ...]:
            return symbols
        def source_functions(self) -> tuple[()]:
            return ()
        def lookup(self, selector: str) -> DwarfSelection:
            symbol = by_name[selector]
            return DwarfSelection(selector, symbol.address, scalar)
    paths = ("Src/main.c", "Src/safe.c", "Src/empty.c", "Inc/header.h")
    facts = module._Facts(model, "b" * 64, "build", "e" * 64, None, None, paths, paths)
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    monkeypatch.setattr(module, "_load_base", lambda *_args: module._Base(index, Catalog(), paths))
    provider = module.SourceCatalogProvider(tmp_path, "workspace", "session", adapter)

    async def scenario() -> None:
        tree = await provider.tree(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=None, binding_epoch=0)
        assert tree["total"] == 2
        assert {item["file"] for item in tree["items"]} == {"Src/main.c", "Src/safe.c"}
        main = next(item for item in tree["items"] if item["file"] == "Src/main.c")
        assert main["scopeCount"] == 1 and main["variableCount"] == 120
        scopes = await provider.tree(query="", cursor=None, limit=100, parent_id=main["id"],
                                     catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        assert scopes["total"] == 1 and scopes["items"][0]["variableCount"] == 120
        scope_id = scopes["items"][0]["id"]
        first = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                    scope_id=scope_id, catalog_id=tree["catalogId"],
                                    binding=None, binding_epoch=0)
        assert first["total"] == 120 and len(first["items"]) == 100 and first["nextCursor"]
        second = await provider.page(query="", cursor=first["nextCursor"], limit=100,
                                     parent_id=None, scope_id=scope_id,
                                     catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        assert second["total"] == 120 and len(second["items"]) == 20 and second["nextCursor"] is None
        assert {item["name"] for item in (*first["items"], *second["items"])} == {
            f"main_{number}" for number in range(120)}
        assert all(item["reason"] == "probe_required" for item in (*first["items"], *second["items"]))
        with pytest.raises(module.SourceCatalogFailure) as wrong_domain:
            await provider.tree(query="", cursor=first["nextCursor"], limit=100,
                                parent_id=main["id"], catalog_id=tree["catalogId"],
                                binding=None, binding_epoch=0)
        assert wrong_domain.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        safe = next(item for item in tree["items"] if item["file"] == "Src/safe.c")
        safe_scopes = await provider.tree(query="", cursor=None, limit=100, parent_id=safe["id"],
                                          catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        with pytest.raises(module.SourceCatalogFailure) as wrong_scope:
            await provider.page(query="", cursor=first["nextCursor"], limit=100,
                                parent_id=None, scope_id=safe_scopes["items"][0]["id"],
                                catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        assert wrong_scope.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        filtered = await provider.tree(query="main_1", cursor=None, limit=100,
                                       parent_id=None, catalog_id=tree["catalogId"],
                                       binding=None, binding_epoch=0)
        assert filtered["total"] == 1 and filtered["items"][0]["variableCount"] == 31
        filtered_page = await provider.page(query="main_1", cursor=None, limit=100,
                                            parent_id=None, scope_id=scope_id,
                                            catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        assert filtered_page["total"] == len(filtered_page["items"]) == 31

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_long_unicode_query_cursors_work_across_public_tree_and_variable_pages(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, facts, binding = _setup(monkeypatch, tmp_path)
    query = "中" * 128
    files = (f"Src/{query}a.c", f"Src/{query}b.c")
    declarations = tuple(SourceDeclaration(f"{number:064x}", f"{number:064x}", f"visible_{number}", "int", file, 1, 1,
                                           "none", "global", None, (), (file,))
                         for number, file in enumerate(files, 1))
    index = SourceIndex("engine", "version", "compdb", 1, 1, (), False, declarations, "f" * 64)
    monkeypatch.setattr(module, "_load_base", lambda *_args: module._Base(index, _Dwarf(declarations), files))
    facts[0] = replace(facts[0], source_files=files, snapshot_paths=files)

    async def scenario() -> None:
        first_tree = await provider.tree(query=query, cursor=None, limit=1, parent_id=None,
                                         catalog_id=None, binding=binding, binding_epoch=0)
        assert len(first_tree["nextCursor"]) > 512
        second_tree = await provider.tree(query=query, cursor=first_tree["nextCursor"], limit=1,
                                          parent_id=None, catalog_id=first_tree["catalogId"],
                                          binding=binding, binding_epoch=0)
        assert second_tree["items"][0]["file"] == files[1]
        first_vars = await provider.page(query=query, cursor=None, limit=1, parent_id=None,
                                         catalog_id=first_tree["catalogId"], binding=binding, binding_epoch=0)
        assert len(first_vars["nextCursor"]) > 512
        second_vars = await provider.page(query=query, cursor=first_vars["nextCursor"], limit=1,
                                          parent_id=None, catalog_id=first_tree["catalogId"],
                                          binding=binding, binding_epoch=0)
        assert second_vars["items"][0]["file"] == files[1]
        provider.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("policy,expected_code,expected_guidance", [
    (module.LEGACY_INPUT_DISCOVERY_POLICY, "MONITOR_SOURCE_UNTRACKED_AST",
     "clean firmware rebuild"),
    (module.SOURCE_LOCAL_HEADERS_POLICY, "MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY",
     "verify project source and include-directory declarations"),
])
def test_untracked_ast_file_and_unbound_local_are_partial_not_tree_facts(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, policy: str,
        expected_code: str, expected_guidance: str) -> None:
    model = SimpleNamespace(project_root=tmp_path)
    facts = module._Facts(model, "b" * 64, None, None, None, None,
                          ("Src/main.c",), ("Src/main.c",), policy)
    main = SourceDeclaration("1" * 64, "1" * 64, "valid", "int", "Src/main.c", 1, 1,
                             "none", "global", None, (), ("Src/main.c",))
    rogue = replace(main, id="2" * 64, file="Src/rogue.c", name="rogue")
    unbound = replace(main, id="3" * 64, name="orphan", function="work",
                      scope_kind="local", function_id="4" * 64)
    unnamed = replace(main, id="6" * 64, name="unnamed", function=None,
                      scope_kind="parameter", function_id=None)
    function = SourceFunction("5" * 64, "other", "Src/rogue.c", 1, 1, ("Src/main.c",))
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), False,
                        (main, rogue, unbound, unnamed), "f" * 64, (function,))
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    adapter = SimpleNamespace(index=lambda *_args: index)
    base = module._load_base(adapter, facts, SourcePlan((), "manifest", "version", "f" * 64))
    assert not base.index.complete
    assert [declaration.name for declaration in base.index.declarations] == ["valid"]
    assert base.index.functions == ()
    assert base.source_files == ("Src/main.c",)
    assert {issue.code for issue in base.index.issues} == {
        expected_code, "MONITOR_SOURCE_FUNCTION_UNBOUND"}
    untracked_issue = next(issue for issue in base.index.issues
                           if issue.code == expected_code)
    assert untracked_issue.unit == "Src/rogue.c"
    assert "Src/rogue.c" in untracked_issue.message
    assert expected_guidance in untracked_issue.message
    if policy == module.SOURCE_LOCAL_HEADERS_POLICY:
        assert "rebuild is needed to include this header" not in untracked_issue.message


def test_public_provider_treats_empty_snapshot_as_authoritative(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = SimpleNamespace(project_root=tmp_path, logical_project_id="project",
                            target=SimpleNamespace(device="STM32F407VG"))
    facts = module._Facts(model, "b" * 64, None, None, None, None, (), ())
    declaration = SourceDeclaration("1" * 64, "1" * 64, "rogue", "int", "Src/rogue.c", 1, 1,
                                    "none", "global", None, (), ("Src/rogue.c",))
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                        (declaration,), "f" * 64)
    class Adapter(_Adapter):
        def plan(self, _model: object) -> SourcePlan:
            return SourcePlan((), "manifest", "version", "f" * 64)
        def index(self, _model: object, _plan: SourcePlan) -> SourceIndex:
            return index
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    provider = module.SourceCatalogProvider(tmp_path, "workspace", "session", Adapter())
    async def scenario() -> None:
        tree = await provider.tree(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=None, binding=None, binding_epoch=0)
        page = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                   catalog_id=tree["catalogId"], binding=None, binding_epoch=0)
        assert tree["total"] == page["total"] == 0
        assert tree["items"] == page["items"] == []
        assert tree["coverage"]["complete"] is False
        assert {issue["code"] for issue in tree["coverage"]["issues"]} == {"MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY"}
    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_merged_declaration_and_normalized_function_budgets_reject_before_pages() -> None:
    first = SourceDeclaration("1" * 64, "1" * 64, "first", "int", "Src/main.c", 1, 1,
                              "none", "global", None, (), ("Src/main.c",))
    second = replace(first, id="2" * 64, entity_id="2" * 64, name="second")
    index = SourceIndex("engine", "version", "manifest", 1, 1, (), True,
                        (first, second), "f" * 64)
    with pytest.raises(module.SourceCatalogFailure) as declarations:
        module._materialize(index, _Dwarf((first, second)), None, None,
                            ("Src/main.c",), max_declarations=1)
    assert declarations.value.code == "MONITOR_SOURCE_INDEX_FAILED"

    dwarf_function = DwarfSourceFunction("work", "Src/main.c", 4, 2, "Src/main.c", 1, 10)
    matching = SourceFunction("3" * 64, "work", "Src/main.c", 4, 2, ("Src/main.c",))
    distinct = replace(matching, id="4" * 64, line=5)
    class Functions:
        def source_functions(self):
            return (dwarf_function,)
    function_index = replace(index, declarations=(), functions=(matching, distinct))
    visible = module.SourceItem("e" * 64, None, "retained", "int", "Src/main.c", 4, 2,
                                "static_local", "work", (), "static", ("Src/main.c",),
                                "retained", True, None, False, False, matching.id)
    view = module._View("a" * 64, {}, function_index, Functions(), (visible,), {}, None, False, {},
                        source_files=("Src/main.c",))
    with pytest.raises(module.SourceCatalogFailure) as functions:
        module._tree_index(view, max_functions=1)
    assert functions.value.code == "MONITOR_SOURCE_INDEX_FAILED"
    module._tree_index(view, max_functions=2)
    assert len(view.scopes_by_file["Src/main.c"]) == 1
    ambiguous = replace(function_index, functions=(matching,))
    class AmbiguousFunctions:
        def source_functions(self):
            return (dwarf_function, replace(dwarf_function, die_offset=11))
    view.index = ambiguous
    view.dwarf = AmbiguousFunctions()
    module._tree_index(view, max_functions=3)
    assert len(view.scopes_by_file["Src/main.c"]) == 1


def test_auxiliary_debug_budget_does_not_break_legacy_lookup(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = ClangSourceAdapter(ninja=None)
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    root = tmp_path / "budget-project"
    (root / "Src").mkdir(parents=True)
    (root / "Src" / "main.c").write_text(
        "volatile int counter = 3;\n"
        "int first(int a) { return counter + a; }\n"
        "int second(int b) { return counter + b; }\n"
        "int third(int c) { return counter + c; }\n", encoding="utf-8")
    elf = root / "firmware.elf"
    command = [str(adapter.preprocessor), "-gdwarf-4", "-O0", "-mcpu=cortex-m4", "-mthumb",
               "-nostdlib", "-Wl,-Ttext=0x08000000", "-Wl,-Tdata=0x20000000", "-Wl,-e,0",
               "-o", str(elf), str(root / "Src" / "main.c")]
    result = subprocess.run(command, cwd=root, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    ram = SimpleNamespace(name="RAM", origin=0x20000000, length=0x10000, attributes="rw")
    flash = SimpleNamespace(name="FLASH", origin=0x08000000, length=0x10000, attributes="rx")
    limited = DwarfCatalog.from_elf(elf, project_root=root, max_catalog_entries=1,
                                    readable_regions=((ram.origin, ram.origin + ram.length),
                                                      (flash.origin, flash.origin + flash.length)))
    assert limited.lookup("counter").expression == "counter"
    assert limited.source_metadata_truncated
    assert len(limited.source_functions()) == 1
    assert len(limited.source_declarations()) <= 2  # one variable and one parameter
    positive_functions = {function.die_offset for function in limited.source_functions()}
    assert all(symbol.scope_kind != "global" and symbol.function_die_offset in positive_functions
               for symbol in limited.source_declarations() if symbol.kind == "parameter")
    assert not any(symbol.name in {"a", "b", "c"} and symbol.scope_kind == "global"
                   for symbol in limited.source_declarations())

    data = elf.read_bytes()
    model = SimpleNamespace(project_root=root, logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG"), memory=SimpleNamespace(regions=(ram, flash)),
        build=SimpleNamespace(sources=("Src/main.c",), include_paths=(), defines=(),
                              compile_options=(), presets=(), elf="firmware.elf"))
    facts = module._Facts(model, "b" * 64, "build", hashlib.sha256(data).hexdigest(),
                          "firmware.elf", len(data), ("Src/main.c",), ("Src/main.c",))
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    original = module.DwarfCatalog.from_elf
    monkeypatch.setattr(module.DwarfCatalog, "from_elf", staticmethod(
        lambda *args, **kwargs: original(*args, **kwargs, max_catalog_entries=1)))
    provider = module.SourceCatalogProvider(root, "workspace", "session", adapter)
    async def scenario() -> None:
        with pytest.raises(module.SourceCatalogFailure) as raised:
            await provider.tree(query="", cursor=None, limit=100, parent_id=None,
                                catalog_id=None, binding=None, binding_epoch=0)
        assert raised.value.code == "MONITOR_SOURCE_INDEX_FAILED"
    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_provider_slow_offline_facts_index_and_view_leave_event_loop_responsive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider, facts, binding = _setup(monkeypatch, tmp_path)
    base = module._Base(SourceIndex("engine", "version", "manifest", 1, 1, (), False, (), "f" * 64), _Dwarf())

    def slow_facts(_root):
        time.sleep(0.06)
        return facts[0]

    def slow_base(_adapter, _facts, _plan):
        time.sleep(0.06)
        return base

    monkeypatch.setattr(module, "_offline_facts", slow_facts)
    monkeypatch.setattr(module, "_load_base", slow_base)

    async def scenario() -> None:
        ticks = [0]
        task = asyncio.create_task(provider.page(query="", cursor=None, limit=100,
                                                 parent_id=None, catalog_id=None,
                                                 binding=binding, binding_epoch=0))
        while not task.done():
            ticks[0] += 1
            await asyncio.sleep(0.01)
        await task
        assert ticks[0] >= 10
        provider.close()

    asyncio.run(scenario())
