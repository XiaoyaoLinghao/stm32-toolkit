from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from elftools.elf.elffile import ELFFile

from stm32_toolkit.debug.source import (ClangSourceAdapter, SourceCatalogError,
                                        SourceDeclaration, SourceFunction, SourcePlan,
                                        _declarations, _discover)
from stm32_toolkit.debug.dwarf import _die_source


def _model(root: Path, sources: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(project_root=root, build=SimpleNamespace(
        sources=sources, include_paths=("Inc",), defines=(), compile_options=(), presets=()))


def test_failed_unit_leaks_no_prefix_or_duplicate_translation_unit(monkeypatch: pytest.MonkeyPatch,
                                                                   tmp_path: Path) -> None:
    import stm32_toolkit.debug.source as source_module

    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    for name in ("good", "bad"):
        (tmp_path / "Src" / f"{name}.c").write_text("int shared;\n", encoding="ascii")
    model = _model(tmp_path, ("Src/good.c", "Src/bad.c"))
    plan = SourcePlan(tuple((name, tmp_path, (name,)) for name in model.build.sources),
                      "manifest", "test-engine", "test-fingerprint")
    shared = SourceDeclaration("shared-id", "shared-id", "shared", "int", "Src/good.c", 1, 5,
                               "none", "global", None, (), ("Src/good.c",))
    good_function = SourceFunction("function-id", "good", "Src/good.c", 1, 1, ("Src/good.c",))
    leaked = SourceDeclaration("leaked-id", "leaked-id", "leaked", "int", "Src/bad.c", 1, 5,
                               "none", "global", None, (), ("Src/bad.c",))

    def discover(_ast, _root, unit, _content):
        if unit == "Src/good.c":
            yield good_function
            yield shared
        else:
            yield SourceFunction("function-id", "good", "Src/good.c", 1, 1, (unit,))
            yield SourceDeclaration(**{**vars(shared), "translation_units": (unit,)})
            yield leaked
            raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "late path failure")

    adapter = ClangSourceAdapter()
    monkeypatch.setattr(source_module, "_discover", discover)
    monkeypatch.setattr(adapter, "_run", lambda argv, *_: b'# 1 "Src/good.c"\nint shared;\n'
                        if "-E" in argv else b'{"kind":"TranslationUnitDecl"}')
    try:
        index = adapter.index(model, plan)
    finally:
        adapter.close()
    assert index.parsed_units == 1 and not index.complete
    assert tuple(issue.unit for issue in index.issues) == ("Src/bad.c",)
    assert index.declarations == (shared,)
    assert index.functions == (good_function,)


@pytest.mark.parametrize("limit_kind", ["declaration", "function"])
def test_entry_limit_stages_duplicate_merge_before_rejecting_new_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit_kind: str,
) -> None:
    import stm32_toolkit.debug.source as source_module

    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    for name in ("good", "bad"):
        (tmp_path / "Src" / f"{name}.c").write_text("int x;\n", encoding="ascii")
    model = _model(tmp_path, ("Src/good.c", "Src/bad.c"))
    plan = SourcePlan(tuple((name, tmp_path, (name,)) for name in model.build.sources),
                      "manifest", "test-engine", "test-fingerprint")
    good_decl = SourceDeclaration("same", "same", "x", "int", "Src/good.c", 1, 5,
                                  "none", "global", None, (), ("Src/good.c",))
    good_func = SourceFunction("same", "func", "Src/good.c", 1, 1, ("Src/good.c",))

    def discover(_ast, _root, unit, _content):
        if unit == "Src/good.c":
            yield good_decl
            yield good_func
        else:
            yield SourceDeclaration(**{**vars(good_decl), "translation_units": (unit,)})
            yield SourceFunction(**{**vars(good_func), "translation_units": (unit,)})
            if limit_kind == "declaration":
                yield SourceDeclaration(**{**vars(good_decl), "id": "new", "translation_units": (unit,)})
            else:
                yield SourceFunction(**{**vars(good_func), "id": "new", "translation_units": (unit,)})

    monkeypatch.setattr(source_module, "_discover", discover)
    monkeypatch.setattr(source_module, "MAX_DECLARATIONS", 1)
    monkeypatch.setattr(source_module, "MAX_FUNCTIONS", 1)
    adapter = ClangSourceAdapter()
    monkeypatch.setattr(adapter, "_run", lambda argv, *_: b'int x;\n' if "-E" in argv else b'{}')
    try:
        index = adapter.index(model, plan)
    finally:
        adapter.close()
    assert index.parsed_units == 1 and index.truncated and len(index.issues) == 1
    assert index.declarations == (good_decl,)
    assert index.functions == (good_func,)


@pytest.mark.parametrize("failure", ["deadline", "closed"])
def test_unit_readiness_check_prevents_late_adoption(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str,
) -> None:
    import stm32_toolkit.debug.source as source_module

    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "a.c").write_text("int x;\n", encoding="ascii")
    model = _model(tmp_path, ("Src/a.c",))
    plan = SourcePlan((("Src/a.c", tmp_path, ("Src/a.c",)),),
                      "manifest", "test-engine", "test-fingerprint")
    entry = SourceDeclaration("x", "x", "x", "int", "Src/a.c", 1, 5,
                              "none", "global", None, (), ("Src/a.c",))
    adapter = ClangSourceAdapter()

    def discover(*_args):
        yield entry
        if failure == "deadline":
            time.sleep(0.02)
        else:
            adapter._closed.set()

    monkeypatch.setattr(source_module, "_discover", discover)
    if failure == "deadline":
        monkeypatch.setattr(source_module, "MAX_UNIT_SECONDS", 0.005)
    monkeypatch.setattr(adapter, "_run", lambda argv, *_: b'int x;\n' if "-E" in argv else b'{}')
    try:
        index = adapter.index(model, plan)
    finally:
        adapter.close()
    assert index.parsed_units == 0 and index.declarations == ()
    assert len(index.issues) == 1 and index.issues[0].unit == "Src/a.c"


def test_discovery_memo_revalidates_each_unique_path_and_resets_per_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import stm32_toolkit.debug.source as source_module

    (tmp_path / "Src").mkdir()
    original = b"int a;\nint b;\n"
    (tmp_path / "Src" / "a.c").write_bytes(original)
    preprocessed = b'# 1 "Src/a.c"\n' + original
    ast = {"kind": "TranslationUnitDecl", "inner": [
        {"kind": "VarDecl", "name": name, "type": {"qualType": "int"},
         "loc": {"offset": preprocessed.index(b" " + name.encode() + b";", 15) + 1,
                 "col": 5}}
        for name in ("a", "b")
    ]}
    original_safe_path = source_module._safe_path
    calls: list[Path] = []

    def counting_safe_path(root, candidate, *, directory=False):
        calls.append(candidate)
        return original_safe_path(root, candidate, directory=directory)

    monkeypatch.setattr(source_module, "_safe_path", counting_safe_path)
    first = tuple(_discover(ast, tmp_path, "Src/a.c", preprocessed))
    second = tuple(_discover(ast, tmp_path, "Src/a.c", preprocessed))
    assert first == second and {item.name for item in first} == {"a", "b"}
    assert len(calls) == 4  # first use and final revalidation, anew for each unit


def test_discovery_final_revalidation_rejects_changed_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import stm32_toolkit.debug.source as source_module

    (tmp_path / "Src").mkdir()
    (tmp_path / "Src" / "a.c").write_text("int a;\n", encoding="ascii")
    preprocessed = b'# 1 "Src/a.c"\nint a;\n'
    ast = {"kind": "TranslationUnitDecl", "inner": [
        {"kind": "VarDecl", "name": "a", "type": {"qualType": "int"},
         "loc": {"offset": preprocessed.index(b" a;") + 1, "col": 5}},
    ]}
    original_safe_path = source_module._safe_path
    calls = [0]

    def changing_safe_path(root, candidate, *, directory=False):
        calls[0] += 1
        resolved, relative = original_safe_path(root, candidate, directory=directory)
        return (resolved, relative if calls[0] == 1 else "Src/changed.c")

    monkeypatch.setattr(source_module, "_safe_path", changing_safe_path)
    with pytest.raises(SourceCatalogError, match="changed during discovery"):
        tuple(_discover(ast, tmp_path, "Src/a.c", preprocessed))
    assert calls == [2]


def test_installed_gcc_preprocessing_preserves_real_conditional_branches_and_ast_locations(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "shared.h").write_text("extern int shared;\nstatic int header_static;\n", encoding="utf-8")
    (tmp_path / "Src" / "a.c").write_text(
        '#include "shared.h"\n'
        '#ifdef __clang__\nint clang_only;\n#else\nint gcc_only;\n#endif\n'
        '#if __GNUC__ >= 10\nint gnu_ten;\n#endif\n'
        'int shared;\nstatic int duplicate;\n'
        '#define DECLARE(name) static int name;\nDECLARE(from_macro)\n'
        'int sample(int parameter) { static int retained; int local = parameter; return local + retained; }\n',
        encoding="utf-8")
    (tmp_path / "Src" / "b.c").write_text(
        '#include "shared.h"\nstatic int duplicate;\nint other(void) { return duplicate; }\n',
        encoding="utf-8")
    try:
        plan = adapter.plan(_model(tmp_path, ("Src/a.c", "Src/b.c")))
        index = adapter.index(_model(tmp_path, ("Src/a.c", "Src/b.c")), plan)
    finally:
        adapter.close()
    assert plan.input_kind == "manifest"
    assert "gcc:" in index.engine_version and "clang:" in index.engine_version
    assert index.complete and index.parsed_units == index.total_units == 2, index.issues
    names = {decl.name for decl in index.declarations}
    assert {"gcc_only", "gnu_ten", "shared", "duplicate", "from_macro", "parameter", "local", "retained"} <= names
    assert "clang_only" not in names
    assert len([decl for decl in index.declarations if decl.name == "duplicate"]) == 2
    assert any(decl.name == "shared" and decl.file == "Inc/shared.h" and decl.line == 1 for decl in index.declarations)
    assert any(decl.name == "local" and decl.file == "Src/a.c" and decl.function == "sample" and decl.scope_kind == "local" for decl in index.declarations)
    assert any(decl.name == "parameter" and decl.scope_kind == "parameter" for decl in index.declarations)
    assert any(decl.name == "from_macro" and decl.file == "Src/a.c" for decl in index.declarations)
    assert len([decl for decl in index.declarations if decl.name == "header_static"
                and decl.file == "Inc/shared.h"]) == 2
    shared = [decl for decl in index.declarations if decl.name == "shared"]
    assert any(decl.file == "Inc/shared.h" for decl in shared)
    assert any(decl.file == "Src/a.c" for decl in shared)
    assert len({decl.entity_id for decl in shared if "Src/a.c" in decl.translation_units}) == 1
    header_decl = next(decl for decl in shared if decl.file == "Inc/shared.h")
    source_tentative = next(decl for decl in shared if decl.file == "Src/a.c")
    assert not header_decl.is_definition and not source_tentative.is_definition
    assert source_tentative.storage == "none" and source_tentative.scope_kind == "global"
    assert dict(header_decl.entity_by_unit)["Src/a.c"] == dict(source_tentative.entity_by_unit)["Src/a.c"]
    assert set(dict(header_decl.entity_by_unit)) == {"Src/a.c", "Src/b.c"}


def test_real_gnu_asm_compatibility_keeps_gcc_branch_locations_and_failed_unit_isolation(
    tmp_path: Path,
) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    header = tmp_path / "Inc" / "legacy.h"
    header.write_text(
        'static int from_header;\n'
        'static inline void set_fpscr(unsigned fpscr) {\n'
        '  __asm volatile ("VMSR fpscr, %0" : : "r" (fpscr) : "vfpcc");\n'
        '}\n', encoding="ascii")
    good = tmp_path / "Src" / "good.c"
    good.write_text(
        '#include "legacy.h"\n'
        '#ifdef __clang__\nint clang_branch;\n#else\nint gnu_branch;\n#endif\n'
        'int run(void) {\n'
        '  int local = gnu_branch;\n'
        '  set_fpscr((unsigned)local);\n'
        '  return local;\n'
        '}\n', encoding="ascii")
    bad = tmp_path / "Src" / "bad.c"
    bad.write_text(
        '#include "legacy.h"\n'
        '__asm volatile ("" : : : "unknown_clobber_xyz");\n'
        'int rejected;\n', encoding="ascii")
    original = {path: path.read_bytes() for path in (header, good, bad)}
    model = _model(tmp_path, ("Src/good.c", "Src/bad.c"))
    try:
        index = adapter.index(model)
    finally:
        adapter.close()
    assert index.parsed_units == 1 and index.total_units == 2 and not index.complete
    assert not index.truncated and tuple(issue.unit for issue in index.issues) == ("Src/bad.c",)
    assert {entry.name for entry in index.declarations}.isdisjoint({"clang_branch", "rejected"})
    branch = next(entry for entry in index.declarations if entry.name == "gnu_branch")
    assert (branch.file, branch.line, branch.column, branch.translation_units) == (
        "Src/good.c", 5, 5, ("Src/good.c",))
    function = next(entry for entry in index.functions if entry.name == "run")
    assert (function.file, function.line, function.column, function.translation_units) == (
        "Src/good.c", 7, 5, ("Src/good.c",))
    local = next(entry for entry in index.declarations if entry.name == "local")
    assert (local.file, local.line, local.column, local.function_id, local.scope_kind) == (
        "Src/good.c", 8, 7, function.id, "local")
    shared = next(entry for entry in index.declarations if entry.name == "from_header")
    assert (shared.file, shared.line, shared.translation_units) == (
        "Inc/legacy.h", 1, ("Src/good.c",))
    assert all(path.read_bytes() == contents for path, contents in original.items())


def test_parser_compatibility_revision_changes_engine_and_plan_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from stm32_toolkit.debug import source_asm_compat

    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "a.c").write_text("int a;\n", encoding="ascii")
    try:
        model = _model(tmp_path, ("Src/a.c",))
        original = adapter.plan(model)
        monkeypatch.setattr(source_asm_compat, "POLICY_VERSION", source_asm_compat.POLICY_VERSION + "-next")
        revised = adapter.plan(model)
    finally:
        adapter.close()
    assert original.fingerprint != revised.fingerprint
    assert original.engine_version != revised.engine_version
    assert revised.engine_version.endswith(source_asm_compat.POLICY_VERSION)


def test_real_function_scope_identity_survives_body_include(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "decls.inc").write_text("int local_from_include = 7;\n", encoding="utf-8")
    (tmp_path / "Src" / "main.c").write_text(
        'int main(void) {\n#include "decls.inc"\nreturn local_from_include;\n}\n'
        'void empty(void) {}\n', encoding="utf-8")
    try:
        index = adapter.index(_model(tmp_path, ("Src/main.c",)))
    finally:
        adapter.close()
    assert index.complete, index.issues
    main = next(function for function in index.functions if function.name == "main")
    assert any(function.name == "empty" and function.file == "Src/main.c" for function in index.functions)
    local = next(declaration for declaration in index.declarations if declaration.name == "local_from_include")
    assert local.file == "Inc/decls.inc" and local.function_id == main.id
    assert local.function == "main" and local.scope_kind == "local"


def test_real_ucn_function_keeps_ascii_local_out_of_global_scope(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "main.c").write_text(
        "void \\u51fd\\u6570(void) { int local = 0; }\n", encoding="utf-8")
    try:
        index = adapter.index(_model(tmp_path, ("Src/main.c",)))
    finally:
        adapter.close()
    assert index.complete, index.issues
    function = next(entry for entry in index.functions if entry.name == "函数")
    local = next(entry for entry in index.declarations if entry.name == "local")
    assert local.function_id == function.id
    assert local.function == "函数" and local.scope_kind == "local"


def test_dwarf_line_tables_v4_and_v5_use_their_own_file_and_directory_indexes(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Inc" / "shared.h").write_text("static int header_value = 7;\n", encoding="utf-8")
    (tmp_path / "Src" / "main.c").write_text(
        '#include "shared.h"\nint counter = 3;\nint sample(void) { return header_value; }\n',
        encoding="utf-8")
    try:
        for version, compiler in ((4, adapter.preprocessor), (5, adapter.compiler)):
            output = tmp_path / f"v{version}.o"
            result = subprocess.run(
                [str(compiler), f"-gdwarf-{version}", "-O0", "-mcpu=cortex-m4", "-mthumb",
                 "-I", str(tmp_path / "Inc"), "-c", "-o", str(output),
                 str(tmp_path / "Src" / "main.c")],
                cwd=tmp_path, capture_output=True, timeout=15)
            assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
            with output.open("rb") as stream:
                dwarf = ELFFile(stream).get_dwarf_info()
                locations = {}
                versions = set()
                for cu in dwarf.iter_CUs():
                    program = dwarf.line_program_for_CU(cu)
                    versions.add(program.header.version)
                    dies = tuple(cu.iter_DIEs())
                    boundaries = frozenset(die.offset for die in dies)
                    for die in dies:
                        if die.tag != "DW_TAG_variable" or "DW_AT_name" not in die.attributes:
                            continue
                        name = die.attributes["DW_AT_name"].value.decode("ascii")
                        locations[name] = _die_source(die, cu, dwarf, tmp_path, boundaries)
                assert versions == ({5} if version == 5 else {3})
                assert locations["counter"][:2] == ("Src/main.c", 2)
                assert locations["header_value"][:2] == ("Inc/shared.h", 1)
    finally:
        adapter.close()


def test_compile_options_refuse_response_files_and_plugins(tmp_path: Path) -> None:
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "a.c").write_text("int value;\n", encoding="utf-8")
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    try:
        for option in (
            "@outside.rsp", "-fplugin=payload.so", "-ffreestanding-extra",
            "-fcommon=unexpected", "-funknown-declaration-mode", "-Xclang", "-include", "-o",
        ):
            model = _model(tmp_path, ("Src/a.c",))
            model.build.compile_options = (option,)
            with pytest.raises((ValueError, SourceCatalogError)):
                adapter._flags(model, "Src/a.c", tmp_path, None)
    finally:
        adapter.close()


def test_manifest_freestanding_and_common_flags_preserve_real_source_semantics(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "a.c").write_text(
        "#if __STDC_HOSTED__ == 0\nint freestanding_selected;\n"
        "#else\nint hosted_selected;\n#endif\nint common_tentative;\n",
        encoding="utf-8",
    )
    model = _model(tmp_path, ("Src/a.c",))
    model.build.compile_options = ("-ffreestanding", "-fcommon")
    hosted_model = _model(tmp_path, ("Src/a.c",))
    hosted_model.build.compile_options = ("-fcommon",)
    calls: list[tuple[str, ...]] = []
    original_run = adapter._run

    def record_run(args, root, output_limit, timeout):
        calls.append(tuple(str(arg) for arg in args))
        return original_run(args, root, output_limit, timeout)

    try:
        flags = adapter._flags(model, "Src/a.c", tmp_path, None)
        assert "-ffreestanding" in flags
        assert "-fcommon" not in flags  # code-generation policy does not affect declaration parsing
        plan = adapter.plan(model)
        assert plan.input_kind == "manifest"
        assert plan.fingerprint != adapter.plan(hosted_model).fingerprint
        adapter._run = record_run
        index = adapter.index(model, plan)
    finally:
        adapter.close()
    assert index.complete and index.parsed_units == 1, index.issues
    names = {declaration.name for declaration in index.declarations}
    assert {"freestanding_selected", "common_tentative"} <= names
    assert "hosted_selected" not in names
    assert any("-E" in args for args in calls)
    assert any("-fsyntax-only" in args for args in calls)
    assert all("-ffreestanding" in args for args in calls if "-E" in args or "-fsyntax-only" in args)
    assert not any("-fcommon" in args for args in calls)


def test_real_clang_redeclaration_chain_marks_only_initialized_source_definition(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None:
        pytest.skip("installed GNU Arm GCC and Clang required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "Src" / "a.c").write_text(
        "extern int x;\nint x;\nint x;\nint x = 1;\n"
        "static int y;\nstatic int y = 2;\nextern int z = 3;\n"
        "void work(void) { static int local_static; (void)local_static; }\n",
        encoding="ascii",
    )
    try:
        index = adapter.index(_model(tmp_path, ("Src/a.c",)))
    finally:
        adapter.close()
    assert index.complete and index.parsed_units == 1, index.issues
    x = sorted((item for item in index.declarations if item.name == "x"), key=lambda item: item.line or 0)
    y = sorted((item for item in index.declarations if item.name == "y"), key=lambda item: item.line or 0)
    z = [item for item in index.declarations if item.name == "z"]
    local_static = [item for item in index.declarations if item.name == "local_static"]
    assert [(item.line, item.is_definition) for item in x] == [(1, False), (2, False), (3, False), (4, True)]
    assert [(item.line, item.is_definition) for item in y] == [(5, False), (6, True)]
    assert len({item.entity_by_unit for item in x}) == 1
    assert len({item.entity_by_unit for item in y}) == 1
    assert len(z) == 1 and z[0].storage == "extern" and z[0].is_definition
    assert len(local_static) == 1 and local_static[0].scope_kind == "static_local"
    assert not local_static[0].is_definition


def test_current_ninja_compdb_requires_model_provenance_and_marks_unknown_unit_partial(tmp_path: Path) -> None:
    adapter = ClangSourceAdapter()
    if adapter.preprocessor is None or adapter.compiler is None or adapter.ninja is None:
        pytest.skip("installed GNU Arm GCC, Clang and Ninja required")
    (tmp_path / "Src").mkdir()
    (tmp_path / "Inc").mkdir()
    (tmp_path / "cmake").mkdir()
    (tmp_path / "cmake" / "arm-none-eabi-gcc.cmake").write_text("", encoding="utf-8")
    for name in ("good", "bad"):
        (tmp_path / "Src" / f"{name}.c").write_text(f"int {name};\n", encoding="utf-8")
    build = tmp_path / "build" / "arm-debug"
    build.mkdir(parents=True)
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={tmp_path.as_posix()}\n"
        "CMAKE_BUILD_TYPE:STRING=Debug\n"
        f"CMAKE_TOOLCHAIN_FILE:FILEPATH={(tmp_path / 'cmake' / 'arm-none-eabi-gcc.cmake').as_posix()}\n",
        encoding="utf-8")
    compiler = adapter.preprocessor.as_posix()
    good = (tmp_path / "Src" / "good.c").as_posix().replace(":", "$:")
    bad = (tmp_path / "Src" / "bad.c").as_posix().replace(":", "$:")
    ninja = ("rule C_COMPILER__demo_Debug\n"
             f'  command = "{compiler}" -mcpu=cortex-m4 -mthumb -Og -I{(tmp_path / "Inc").as_posix()} $FLAGS -c $in -o $out\n'
             f"build good.o: C_COMPILER__demo_Debug {good}\n"
             "  FLAGS = -ffreestanding -fcommon\n"
             f"build bad.o: C_COMPILER__demo_Debug {bad}\n"
             "  FLAGS = -ffreestanding -fcommon -funknown-declaration-mode\n")
    (build / "build.ninja").write_text(ninja, encoding="utf-8")
    model = _model(tmp_path, ("Src/good.c", "Src/bad.c"))
    model.build.presets = ("arm-debug",)
    model.build.compile_options = ("-ffreestanding", "-fcommon")
    model.build.elf = "build/arm-debug/firmware.elf"
    model.target = SimpleNamespace(core="cortex-m4", fpu=None, float_abi=None)
    try:
        plan = adapter.plan(model)
        assert plan.input_kind == "compdb" and len(plan.commands) == 2
        assert "-ffreestanding" in adapter._flags(model, "Src/good.c", build, list(plan.commands[0][2]))
        model.build.compile_options = ("-fcommon",)
        mismatch = adapter.plan(model)
        assert mismatch.fingerprint != plan.fingerprint
        assert mismatch.commands[0][2][0] == "unsupported-semantic-command"
        model.build.compile_options = ("-ffreestanding", "-fcommon")
        index = adapter.index(model, plan)
        assert index.parsed_units == 1 and index.total_units == 2 and not index.complete
        assert any(issue.unit == "Src/bad.c" for issue in index.issues)
        # A stale graph with a missing source cannot be advertised as compdb.
        (build / "build.ninja").write_text(ninja.split("build bad.o:")[0], encoding="utf-8")
        stale = adapter.plan(model)
        assert stale.input_kind == "manifest" and stale.fingerprint != plan.fingerprint
        assert adapter.index(model, stale).complete
    finally:
        adapter.close()


def test_stdout_and_stderr_pipe_limits_apply_even_when_child_exits_quickly(tmp_path: Path) -> None:
    script = tmp_path / "flood.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(b'x'*1048576)\n"
        "sys.stderr.buffer.write(b'y'*1048576)\n", encoding="utf-8")
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    try:
        with pytest.raises(SourceCatalogError):
            adapter._run([sys.executable, str(script)], tmp_path, 4096, 5.0)
    finally:
        adapter.close()


def test_project_declaration_with_elided_column_is_retained_but_unplaced_unit_fails(tmp_path: Path) -> None:
    (tmp_path / "Src").mkdir()
    source = tmp_path / "Src" / "a.c"
    source.write_text("int value; // value\n", encoding="utf-8")
    marker = f'# 1 "{source.as_posix()}"\n'.encode("utf-8")
    ast = {"kind": "TranslationUnitDecl", "inner": [{
        "kind": "VarDecl", "id": "1", "name": "value", "type": {"qualType": "int"},
        "loc": {"offset": len(marker) + 4, "col": 1}}]}
    retained = tuple(_declarations(ast, tmp_path, "Src/a.c", marker + source.read_bytes()))
    assert len(retained) == 1 and retained[0].file == "Src/a.c"
    assert retained[0].line == 1 and retained[0].column is None
    ast["inner"][0]["loc"] = {}
    with pytest.raises(SourceCatalogError):
        tuple(_declarations(ast, tmp_path, "Src/a.c", b""))


@pytest.mark.skipif(os.name != "nt", reason="Windows compiler child-tree regression")
def test_two_index_keys_serialize_and_close_prevents_queued_compiler(tmp_path: Path) -> None:
    pid_path = tmp_path / "owned.pid"
    script = tmp_path / "slow.py"
    script.write_text(
        "import os,sys,time\n"
        "open(sys.argv[1],'w',encoding='ascii').write(str(os.getpid()))\n"
        "time.sleep(60)\n", encoding="utf-8")
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    starts: list[str] = []

    def pipeline(_model, plan):
        starts.append(plan.fingerprint)
        return adapter._run([sys.executable, str(script), str(pid_path)], tmp_path, 4096, 30.0)

    adapter._index_locked = pipeline
    first = SourcePlan((), "manifest", "version", "a" * 64)
    second = SourcePlan((), "manifest", "version", "b" * 64)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = pool.submit(adapter.index, object(), first)
            pid_text = ""
            for _ in range(100):
                if pid_path.exists():
                    pid_text = pid_path.read_text(encoding="ascii")
                    if pid_text.isdigit():
                        break
                time.sleep(0.02)
            assert pid_text.isdigit()
            queued = pool.submit(adapter.index, object(), second)
            adapter.close()
            with pytest.raises(SourceCatalogError):
                active.result(timeout=8)
            with pytest.raises(SourceCatalogError):
                queued.result(timeout=8)
        assert starts == [first.fingerprint]
        pid = int(pid_text)
        listing = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=5)
        assert f'"{pid}"' not in listing.stdout
    finally:
        adapter.close()


def test_run_queue_wait_expires_without_starting_a_compiler(tmp_path: Path) -> None:
    marker = tmp_path / "started.txt"
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    entered = threading.Event()
    adapter._run_lock.acquire()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            def queued() -> bytes:
                entered.set()
                return adapter._run([sys.executable, "-c",
                                     "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('started')",
                                     str(marker)], tmp_path, 4096, 0.12)

            future = pool.submit(queued)
            try:
                assert entered.wait(timeout=2)
                time.sleep(0.22)
            finally:
                adapter._run_lock.release()
            with pytest.raises(SourceCatalogError):
                future.result(timeout=2)
        assert not marker.exists()
    finally:
        if adapter._run_lock.locked():
            adapter._run_lock.release()
        adapter.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows child-tree regression")
def test_timeout_reaps_only_owned_compiler_child_tree(tmp_path: Path) -> None:
    pid_path = tmp_path / "child.pid"
    script = tmp_path / "driver.py"
    script.write_text(
        "import subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
        "open(sys.argv[1],'w',encoding='ascii').write(str(child.pid))\n"
        "time.sleep(60)\n", encoding="utf-8")
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    try:
        with pytest.raises(SourceCatalogError):
            adapter._run([sys.executable, str(script), str(pid_path)], tmp_path, 4096, 0.35)
        assert pid_path.is_file()
        child_pid = int(pid_path.read_text(encoding="ascii"))
        # tasklist is read-only; any fallback cleanup targets this test-owned PID.
        for _ in range(20):
            listing = subprocess.run(["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
                                     capture_output=True, text=True, timeout=5)
            if f'"{child_pid}"' not in listing.stdout:
                break
            time.sleep(0.1)
        else:
            subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"],
                           capture_output=True, timeout=5)
            pytest.fail("owned compiler child survived timeout")
    finally:
        adapter.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows child-tree regression")
@pytest.mark.parametrize("stop_mode", ["timeout", "close"])
def test_root_exits_first_but_owned_descendant_is_reaped(tmp_path: Path, stop_mode: str) -> None:
    pid_path = tmp_path / "descendant.pid"
    root_pid_path = tmp_path / "root.pid"
    script = tmp_path / "exiting_driver.py"
    script.write_text(
        "import os,subprocess,sys\n"
        "open(sys.argv[2],'w',encoding='ascii').write(str(os.getpid()))\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'],"
        "stdout=sys.stdout,stderr=sys.stderr,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
        "open(sys.argv[1],'w',encoding='ascii').write(str(child.pid))\n"
        "os._exit(0)\n",
        encoding="utf-8")
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    descendant_pid: int | None = None

    def alive(pid: int) -> bool:
        listing = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=5)
        return f'"{pid}"' in listing.stdout

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            started = time.monotonic()
            future = pool.submit(adapter._run,
                                 [sys.executable, str(script), str(pid_path), str(root_pid_path)],
                                 tmp_path, 4096, 1.0 if stop_mode == "timeout" else 30.0)
            try:
                for _ in range(100):
                    if (pid_path.is_file() and root_pid_path.is_file()
                            and pid_path.read_text(encoding="ascii").isdigit()
                            and root_pid_path.read_text(encoding="ascii").isdigit()):
                        break
                    time.sleep(0.02)
                assert pid_path.is_file() and root_pid_path.is_file()
                descendant_pid = int(pid_path.read_text(encoding="ascii"))
                root_pid = int(root_pid_path.read_text(encoding="ascii"))
                for _ in range(50):
                    if not alive(root_pid):
                        break
                    time.sleep(0.02)
                assert not alive(root_pid) and alive(descendant_pid)
                if stop_mode == "close":
                    started = time.monotonic()
                    adapter.close()
                with pytest.raises(SourceCatalogError):
                    future.result(timeout=12)
                assert time.monotonic() - started < 3.0
                assert not alive(descendant_pid)
            finally:
                adapter.close()
    finally:
        adapter.close()
        if descendant_pid is None and pid_path.is_file():
            text = pid_path.read_text(encoding="ascii")
            descendant_pid = int(text) if text.isdigit() else None
        if descendant_pid is not None and alive(descendant_pid):
            subprocess.run(["taskkill", "/PID", str(descendant_pid), "/T", "/F"],
                           capture_output=True, timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows native ownership contract")
def test_native_thread_enumeration_error_fails_before_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    from stm32_toolkit.debug import source_windows

    closed: list[int] = []

    def first(_snapshot: int, pointer: object) -> bool:
        entry = ctypes.cast(pointer, ctypes.POINTER(source_windows._ThreadEntry)).contents
        entry.th32OwnerProcessID = 1234
        entry.th32ThreadID = 5678
        return True

    def next_error(_snapshot: int, _pointer: object) -> bool:
        ctypes.set_last_error(5)
        return False

    monkeypatch.setattr(source_windows, "_SNAPSHOT", lambda _flags, _pid: 42)
    monkeypatch.setattr(source_windows, "_THREAD_FIRST", first)
    monkeypatch.setattr(source_windows, "_THREAD_NEXT", next_error)
    monkeypatch.setattr(source_windows, "_CLOSE_HANDLE", lambda handle: closed.append(handle) or True)
    monkeypatch.setattr(source_windows, "_OPEN_THREAD", lambda *_args: pytest.fail("opened a thread after enumeration failed"))
    with pytest.raises(OSError, match="enumerate initial thread"):
        source_windows._initial_thread(1234)
    assert closed == [42]


@pytest.mark.skipif(os.name != "nt", reason="Windows native ownership contract")
def test_native_job_close_failure_retains_owned_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    from stm32_toolkit.debug import source_windows

    job = source_windows.OwnedWindowsJob()
    handle = job._handle
    close_native = source_windows._CLOSE_HANDLE
    try:
        monkeypatch.setattr(source_windows, "_CLOSE_HANDLE", lambda _handle: False)
        with pytest.raises(OSError, match="close job"):
            job.close()
        assert job._handle == handle
    finally:
        monkeypatch.setattr(source_windows, "_CLOSE_HANDLE", close_native)
        job.close()
    assert job._handle is None
    job.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows native ownership contract")
def test_adapter_failed_job_cleanup_reaps_suspended_root_and_seals_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from stm32_toolkit.debug import source as source_module

    created: list[object] = []
    real_popen = subprocess.Popen
    roots: list[subprocess.Popen[bytes]] = []

    class FailingJob:
        closed = False
        fail_close = True

        def __init__(self) -> None:
            created.append(self)

        def assign(self, _handle: int) -> None:
            raise OSError("injected assignment failure")

        def close(self) -> None:
            if self.fail_close:
                raise OSError("injected job close failure")
            self.closed = True

    def capture_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child = real_popen(*args, **kwargs)
        roots.append(child)
        return child

    monkeypatch.setattr(source_module, "OwnedWindowsJob", FailingJob)
    monkeypatch.setattr(source_module.subprocess, "Popen", capture_popen)
    adapter = ClangSourceAdapter(compiler=Path(sys.executable), preprocessor=Path(sys.executable))
    try:
        with pytest.raises(OSError, match="injected job close failure"):
            adapter._start_child([sys.executable, "-c", "import time;time.sleep(60)"], tmp_path)
        assert adapter._closed.is_set()
        assert len(roots) == 1 and roots[0].poll() is not None
        assert adapter._job is created[0]
        with pytest.raises(SourceCatalogError, match="closed"):
            adapter._run([sys.executable, "-c", "print('unexpected')"], tmp_path, 4096, 1.0)
        assert len(roots) == 1
    finally:
        if created:
            created[0].fail_close = False
        adapter.close()
    assert adapter._job is None
