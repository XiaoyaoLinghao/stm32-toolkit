from __future__ import annotations

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

from stm32_toolkit.debug.source import ClangSourceAdapter, SourceCatalogError, SourcePlan, _declarations
from stm32_toolkit.debug.dwarf import _die_source


def _model(root: Path, sources: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(project_root=root, build=SimpleNamespace(
        sources=sources, include_paths=("Inc",), defines=(), compile_options=(), presets=()))


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
        for option in ("@outside.rsp", "-fplugin=payload.so", "-Xclang", "-include", "-o"):
            model = _model(tmp_path, ("Src/a.c",))
            model.build.compile_options = (option,)
            with pytest.raises((ValueError, SourceCatalogError)):
                adapter._flags(model, "Src/a.c", tmp_path, None)
    finally:
        adapter.close()


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
             "  FLAGS =\n"
             f"build bad.o: C_COMPILER__demo_Debug {bad}\n"
             "  FLAGS = -funknown-declaration-mode\n")
    (build / "build.ninja").write_text(ninja, encoding="utf-8")
    model = _model(tmp_path, ("Src/good.c", "Src/bad.c"))
    model.build.presets = ("arm-debug",)
    model.build.elf = "build/arm-debug/firmware.elf"
    model.target = SimpleNamespace(core="cortex-m4", fpu=None, float_abi=None)
    try:
        plan = adapter.plan(model)
        assert plan.input_kind == "compdb" and len(plan.commands) == 2
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
