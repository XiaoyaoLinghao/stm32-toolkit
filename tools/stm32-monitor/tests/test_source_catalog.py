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
from stm32_toolkit.debug.source import ClangSourceAdapter, SourceDeclaration, SourceIndex, SourceIssue, SourcePlan
from stm32_toolkit.debug.types import DwarfMember, DwarfType
from stm32_toolkit.debug.dwarf import DwarfSourceSymbol


def test_shared_wire_fixture_uses_backend_item_serializer() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "source_catalog_envelope.json").read_text(encoding="utf-8"))
    item = module.SourceItem("c" * 64, None, "counter", "int", "Src/main.c", 1, 5,
                             "global", None, (), "none", ("Src/main.c",), "counter",
                             False, "probe_required", False, False)
    assert fixture["operation"] == "monitor.catalog.source.variables"
    assert fixture["data"]["items"] == [item.to_dict()]
    assert fixture["data"]["identity"]["bindingEpoch"] == 0


class _Adapter:
    def plan(self, _model: object) -> SourcePlan:
        return SourcePlan((), "compdb", "gcc:14.3.1;clang:21.1.1", "f" * 64)

    def close(self) -> None:
        pass


class _Dwarf:
    def source_symbols(self) -> tuple[()]:
        return ()


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
    dwarf = _Dwarf()
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts[0])
    monkeypatch.setattr(module, "_load_base", lambda _adapter, _facts, _plan: module._Base(index, dwarf))
    dtype = DwarfType("array", "int[5000]", 20_000, element_type=DwarfType("integer", "int", 4), element_count=5000)
    def item_for(decl, *_args):
        return module.SourceItem(decl.id, None, decl.name, decl.type_name, decl.file, decl.line,
                                 decl.column, "global", None, (), "none", decl.translation_units,
                                 decl.name, False if aggregate else True,
                                 "aggregate" if aggregate else None, aggregate, aggregate), dtype if aggregate else None
    monkeypatch.setattr(module, "_item_for_declaration", item_for)
    monkeypatch.setattr(module, "_eligible_leaf", lambda *_args: None)
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
        assert child["total"] == 5000 and len(child["items"]) == 100
        count = 100
        while child["nextCursor"] is not None:
            child = await provider.page(query="", cursor=child["nextCursor"], limit=100, parent_id=parent_id,
                                        catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
            count += len(child["items"])
        assert count == 4096 and child["nextCursor"] is None
        provider.close()

    asyncio.run(scenario())


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
        return module._Base(partial, _Dwarf())

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
                                    catalog_id=None, binding=binding, binding_epoch=0)
        assert retry["catalogId"] == root["catalogId"] and loads == [2]
        provider.close()

    asyncio.run(scenario())


def test_depth_limit_marks_unexpanded_aggregate_as_truncated(
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
        current = root["items"][0]
        for _ in range(6):
            children = await provider.page(query="", cursor=None, limit=100, parent_id=current["id"],
                                           catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
            current = children["items"][0]
        assert current["reason"] == "limit_reached"
        assert current["truncated"] and not current["expandable"] and not current["canAdd"]
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
            return module._Base(partial, _Dwarf())
        return module._Base(complete, _Dwarf())

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
                                    catalog_id=None, binding=binding, binding_epoch=0)
        assert loads == [2] and retry["coverage"]["complete"]
        assert not provider._inflight
        provider.close()

    asyncio.run(scenario())


def test_duplicate_and_unnamed_members_have_unique_disabled_rows(
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
        children = await provider.page(query="", cursor=None, limit=100, parent_id=root["items"][0]["id"],
                                       catalog_id=root["catalogId"], binding=binding, binding_epoch=0)
        items = children["items"]
        assert len(items) == len({item["id"] for item in items}) == 4
        assert all(not item["canAdd"] and item["selector"] is None for item in items)
        assert [item["reason"] for item in items] == ["unsupported_type", "unsupported_type",
                                                     "ambiguous_symbol", "ambiguous_symbol"]
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
                           "firmware.elf", len(data))]
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
        for name in ("duplicate", "header_static"):
            assert all(item["reason"] == "ambiguous_symbol" and not item["canAdd"]
                       for item in rows if item["name"] == name)
        for name in ("parameter", "local"):
            assert all(item["reason"] == "frame_required" and not item["canAdd"]
                       for item in rows if item["name"] == name)
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
        assert all(item["reason"] == "firmware_unavailable" for item in unavailable["items"])
        denied = replace(facts[0], elf_sha="0" * 64)
        facts[0] = denied
        with pytest.raises(module.SourceCatalogFailure) as changed:
            await provider.select(catalog_id=page["catalogId"], item_id=counter[0]["id"],
                                  selector="counter", binding=binding, binding_epoch=0)
        assert changed.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"

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
        assert all(not item["canAdd"] and item["reason"] == "coverage_incomplete"
                   for item in partial["items"])
        complete = await provider.page(query="counter", cursor=None, limit=100, parent_id=None,
                                       catalog_id=None, binding=binding, binding_epoch=0)
        assert complete["coverage"]["complete"] and attempts == [2]
        assert complete["catalogId"] != partial["catalogId"]
        assert any(item["canAdd"] for item in complete["items"])

    asyncio.run(scenario())


def test_one_debug_symbol_cannot_authorize_two_distinct_source_entities() -> None:
    dtype = DwarfType("integer", "int", 4)
    symbol = DwarfSourceSymbol("value", "Src/main.c", 1, None, None,
                               "Src/main.c", dtype, 0x20000000, None, None)
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
    chained, _ = module._materialize(replace(index, declarations=(first, same_entity)),
                                     Catalog(), "probe_required", None)
    assert all(item.reason == "probe_required" for item in chained)


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
