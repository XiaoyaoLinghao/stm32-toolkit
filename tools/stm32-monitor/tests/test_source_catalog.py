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
    monkeypatch.setattr(module, "_load_base", lambda _adapter, _facts, _plan:
                        module._Base(index, dwarf, ("Src/main.c",)))
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
        return module._Base(partial, _Dwarf(), ("Src/main.c",))

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
        for name in ("duplicate", "header_static"):
            assert all(item["reason"] == "ambiguous_symbol" and not item["canAdd"]
                       for item in rows if item["name"] == name)
        for name in ("parameter", "local"):
            assert all(item["reason"] in {"frame_required", "unsupported_location"}
                       and not item["canAdd"] for item in rows if item["name"] == name), [
                           (item["name"], item["reason"], item["scope"])
                           for item in rows if item["name"] in {"parameter", "local"}]
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
        assert sample["variableCount"] >= 3
        variables = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                        scope_id=sample["id"], catalog_id=tree["catalogId"],
                                        binding=binding, binding_epoch=0)
        assert any(item["name"] == "parameter" and item["reason"] == "frame_required"
                   for item in variables["items"])
        assert any(item["name"] == "local" and item["reason"] == "frame_required"
                   for item in variables["items"])
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
        assert len(other["items"]) == 1 and other["items"][0]["reason"] == "debug_entry_missing"
        assert not other["items"][0]["canAdd"]

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
        files = list(first["items"])
        cursor = first["nextCursor"]
        while cursor is not None:
            page = await provider.tree(query="", cursor=cursor, limit=1, parent_id=None,
                                       catalog_id=first["catalogId"], binding=None, binding_epoch=0)
            files.extend(page["items"])
            cursor = page["nextCursor"]
        by_path = {item["file"]: item for item in files}
        assert set(paths) == set(by_path)
        assert by_path["Src/empty.c"]["variableCount"] == 0
        assert by_path["Src/safe.c"]["variableCount"] == 1
        main_id = by_path["Src/main.c"]["id"]
        main_scopes = await provider.tree(query="", cursor=None, limit=1000, parent_id=main_id,
                                          catalog_id=first["catalogId"], binding=None, binding_epoch=0)
        assert any(scope["function"] == "empty_function" and scope["variableCount"] == 0
                   for scope in main_scopes["items"])
        global_scope = next(scope for scope in main_scopes["items"] if scope["function"] is None)
        first_vars = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                         scope_id=global_scope["id"], catalog_id=first["catalogId"],
                                         binding=None, binding_epoch=0)
        assert first_vars["total"] == 120 and len(first_vars["items"]) == 100
        second_vars = await provider.page(query="", cursor=first_vars["nextCursor"], limit=100,
                                          parent_id=None, scope_id=global_scope["id"],
                                          catalog_id=first["catalogId"], binding=None, binding_epoch=0)
        assert len(second_vars["items"]) == 20
        included = await provider.tree(query="", cursor=None, limit=1000,
                                       parent_id=by_path["Inc/decls.inc"]["id"],
                                       catalog_id=first["catalogId"], binding=None, binding_epoch=0)
        projected = next(scope for scope in included["items"] if scope["function"] == "main")
        assert projected["line"] is None and projected["file"] == "Inc/decls.inc"
        local = await provider.page(query="", cursor=None, limit=100, parent_id=None,
                                    scope_id=projected["id"], catalog_id=first["catalogId"],
                                    binding=None, binding_epoch=0)
        assert [(item["name"], item["file"]) for item in local["items"]] == [("included_local", "Inc/decls.inc")]
        assert next(function for function in provider._views[first["catalogId"]].index.functions
                    if function.name == "main").id == next(declaration.function_id
                    for declaration in provider._views[first["catalogId"]].index.declarations
                    if declaration.name == "included_local")
        with pytest.raises(module.SourceCatalogFailure) as wrong_domain:
            await provider.tree(query="", cursor=first_vars["nextCursor"], limit=1, parent_id=None,
                                catalog_id=first["catalogId"], binding=None, binding_epoch=0)
        assert wrong_domain.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        with pytest.raises(module.SourceCatalogFailure) as wrong_scope:
            await provider.page(query="", cursor=first_vars["nextCursor"], limit=100, parent_id=None,
                                scope_id=projected["id"], catalog_id=first["catalogId"],
                                binding=None, binding_epoch=0)
        assert wrong_scope.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        provider.close()

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_long_unicode_query_cursors_work_across_public_tree_and_variable_pages(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, facts, binding = _setup(monkeypatch, tmp_path)
    query = "中" * 128
    files = (f"Src/{query}a.c", f"Src/{query}b.c")
    declarations = tuple(SourceDeclaration(f"{number:064x}", f"{number:064x}", query, "int", file, 1, 1,
                                           "none", "global", None, (), (file,))
                         for number, file in enumerate(files, 1))
    index = SourceIndex("engine", "version", "compdb", 1, 1, (), False, declarations, "f" * 64)
    monkeypatch.setattr(module, "_load_base", lambda *_args: module._Base(index, _Dwarf(), files))
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


def test_untracked_ast_file_and_unbound_local_are_partial_not_tree_facts(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = SimpleNamespace(project_root=tmp_path)
    facts = module._Facts(model, "b" * 64, None, None, None, None,
                          ("Src/main.c",), ("Src/main.c",))
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
        "MONITOR_SOURCE_UNTRACKED_AST", "MONITOR_SOURCE_FUNCTION_UNBOUND"}
    assert all(issue.unit is None and "rogue.c" not in issue.message for issue in base.index.issues)


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
