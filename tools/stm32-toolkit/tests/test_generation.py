"""Generation contract, template, security, and atomicity tests (STM32TK-0304).

Every fixture project lives below pytest temporary directories and is
disposable.  No timing assertions live in this file; performance is measured
by a separate script recorded in the implementation report.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.generation import (
    GenerationBlocker,
    GenerationError,
    GeneratedFile,
    GenerationInput,
    GenerationPlan,
    ManagedFileRecord,
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.generation import configure as configure_mod
from stm32_toolkit.generation.managed_files import (
    MANAGED_MANIFEST_PATH,
    STAGING_ROOT,
    TEMPLATE_VERSION,
    build_managed_manifest_bytes,
    canonical_json_bytes,
    model_sha256_for,
    parse_managed_manifest,
    plan_id_for,
    portable_path_error,
    sha256_error,
)
from stm32_toolkit.project_model import ProjectManifestError, load_project_model

REPO_ROOT = Path(__file__).resolve().parents[3]
UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

TARGETS = tuple(
    sorted(
        [
            "CMakeLists.txt",
            "cmake/arm-none-eabi-gcc.cmake",
            "CMakePresets.json",
            "linker/stm32tk.ld",
            ".vscode/tasks.json",
            ".vscode/launch.json",
            ".vscode/c_cpp_properties.json",
            ".vscode/settings.json",
            ".vscode/extensions.json",
        ]
    )
)

REPORT_PATH = "artifacts/migration/conversion-report.json"

EXPECTED_CMAKE = """cmake_minimum_required(VERSION 3.22)
project(firmware LANGUAGES C CXX ASM)

add_executable(firmware
  Src/main.c
  Src/app.c
  Startup/startup.s
)

set_target_properties(firmware PROPERTIES
  PREFIX ""
  SUFFIX ".elf"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

target_include_directories(firmware PRIVATE
  Inc
)

target_compile_definitions(firmware PRIVATE
  USE_HAL_DRIVER
  STM32F407xx
)

target_compile_options(firmware PRIVATE
  -mcpu=cortex-m4
  -mthumb
  -ffunction-sections
  -fdata-sections
  -mfpu=fpv4-sp-d16
  -mfloat-abi=hard
  -ffreestanding
  $<$<CONFIG:Debug>:-Og;-g3>
  $<$<CONFIG:Release>:-O2;-g0>
)

target_link_options(firmware PRIVATE
  -mcpu=cortex-m4
  -mthumb
  -mfpu=fpv4-sp-d16
  -mfloat-abi=hard
  -nostartfiles
  "-T${CMAKE_SOURCE_DIR}/linker/stm32tk.ld"
  "-Wl,-Map=${CMAKE_BINARY_DIR}/firmware.map"
  "-Wl,--gc-sections"
)

add_custom_command(TARGET firmware POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O ihex "$<TARGET_FILE:firmware>" "${CMAKE_BINARY_DIR}/firmware.hex"
  COMMAND ${CMAKE_OBJCOPY} -O binary "$<TARGET_FILE:firmware>" "${CMAKE_BINARY_DIR}/firmware.bin"
  VERBATIM
)
"""

EXPECTED_LINKER = """ENTRY(Reset_Handler)

_Min_Heap_Size = 4K;
_Min_Stack_Size = 1K;

MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 0x00100000
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00020000
}

SECTIONS
{
  .isr_vector :
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text*)
    *(.rodata*)
    KEEP(*(.init))
    KEEP(*(.fini))
    . = ALIGN(4);
    _etext = .;
  } > FLASH

  .ARM.extab :
  {
    *(.ARM.extab* .gnu.linkonce.arm.extab.*)
  } > FLASH

  .ARM.exidx :
  {
    *(.ARM.exidx* .gnu.linkonce.arm.exidx.*)
  } > FLASH

  .data :
  {
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM AT> FLASH
  _sidata = LOADADDR(.data);

  .bss :
  {
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM

  .heap (NOLOAD) :
  {
    . = ALIGN(8);
    __end__ = .;
    end = __end__;
    __HeapBase = .;
    . += _Min_Heap_Size;
    __HeapLimit = .;
  } > RAM

  .stack (NOLOAD) :
  {
    . = ALIGN(8);
    __StackTop = .;
    . += _Min_Stack_Size;
    __StackLimit = .;
  } > RAM
}
"""

EXPECTED_TOOLCHAIN = """set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_CXX_COMPILER arm-none-eabi-g++)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY arm-none-eabi-objcopy)
set(CMAKE_SIZE arm-none-eabi-size)
"""

EXPECTED_EXTENSIONS = """{
  "recommendations": [
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "marus25.cortex-debug"
  ]
}
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def standard_payload(**overrides):
    payload = {
        "schemaVersion": 2,
        "logicalProjectId": UUID,
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "firmware", "origin": "keil-migration"},
        "target": {
            "device": "STM32F407VGTx",
            "core": "cortex-m4",
            "fpu": "fpv4-sp-d16",
            "floatAbi": "hard",
        },
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["Src/main.c", "Src/app.c"],
            "includePaths": ["Inc"],
            "defines": ["USE_HAL_DRIVER", "STM32F407xx"],
            "compileOptions": ["-ffreestanding"],
            "assemblySources": ["Startup/startup.s"],
            "presets": ["arm-debug", "arm-release"],
            "elf": "build/arm-debug/firmware.elf",
        },
        "memory": {
            "source": "keil",
            "regions": [
                {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
                {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
            ],
        },
        "debug": {"backend": "pyocd", "target": "stm32f407vg"},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }
    payload.update(overrides)
    return payload


def write_project(root: Path, payload=None) -> Path:
    """Materialize a disposable Schema v2 project with exact UTF-8 bytes."""
    payload = standard_payload() if payload is None else payload
    root.mkdir(parents=True, exist_ok=True)
    for source in payload["build"]["sources"]:
        path = root.joinpath(*source.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("// %s\nint main(void) { return 0; }\n" % source).encode("utf-8"))
    for source in payload["build"]["assemblySources"]:
        path = root.joinpath(*source.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((".syntax unified\n// %s\n" % source).encode("utf-8"))
    for include in payload["build"]["includePaths"]:
        path = root.joinpath(*include.split("/"))
        path.mkdir(parents=True, exist_ok=True)
        path.joinpath("board.h").write_bytes(b"#pragma once\n")
    debug = payload.get("debug") or {}
    svd = debug.get("svd")
    if svd:
        path = root.joinpath(*svd.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"svd": true}\n')
    ioc = (payload.get("generation") or {}).get("cubeMxIoc")
    if ioc:
        path = root.joinpath(*ioc.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"[Mcu]\n")
    (root / ".stm32-project.json").write_bytes(
        json.dumps(payload, indent=2).encode("utf-8") + b"\n"
    )
    return root


def plan_for(root: Path) -> GenerationPlan:
    return plan_project_configuration(load_project_model(root))


def write_manifest_bytes(root: Path, content: bytes) -> None:
    path = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_report_bytes(root: Path, content: bytes) -> None:
    path = root.joinpath(*REPORT_PATH.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def report_payload(fixed_sections, **overrides):
    payload = {
        "schemaVersion": 1,
        "planId": "a" * 64,
        "gitHead": "b" * 40,
        "fixedSections": fixed_sections,
    }
    payload.update(overrides)
    return payload


def record(path: str, value: str | None = None) -> dict:
    return {
        "path": path,
        "ownership": "managed",
        "templateVersion": 1,
        "sha256": value or ("a" * 64),
    }


def tree_snapshot(root: Path) -> dict[str, tuple]:
    snapshot: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("link", os.readlink(path))
        elif path.is_file():
            lst = os.lstat(path)
            snapshot[relative] = ("file", stat.S_IMODE(lst.st_mode), lst.st_mtime_ns, path.read_bytes())
        elif path.is_dir():
            lst = os.lstat(path)
            snapshot[relative] = ("dir", stat.S_IMODE(lst.st_mode), lst.st_mtime_ns)
    return snapshot


def manifest_on_disk(root: Path) -> dict:
    path = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    return json.loads(path.read_text("utf-8"))


def staging_dir(root: Path, plan_id: str) -> Path:
    return root.joinpath(*STAGING_ROOT.split("/"), plan_id)


def _redirect_path(monkeypatch, link: Path, target: Path, is_dir: bool) -> None:
    """Create a path redirect without requiring administrator privileges.

    POSIX uses a real symlink. Windows uses a real NTFS junction for
    directory redirects and a deterministic reparse/resolve injection for
    file redirects, because unprivileged file symlinks do not exist on
    Windows and tests must not depend on developer mode.
    """
    if os.name != "nt":
        os.symlink(target, link)
        return
    if is_dir:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    original_resolve = Path.resolve
    real_lstat = os.lstat
    link_key = os.path.normcase(str(link))
    forged: list[os.stat_result] = []

    def selective_resolve(self, strict=False):
        if os.path.normcase(str(self)) == link_key:
            return target.resolve(strict=False)
        return original_resolve(self, strict=strict)

    def selective_lstat(path, *args, **kwargs):
        if os.path.normcase(str(path)) == link_key:
            if not forged:
                real = real_lstat(target)
                forged.append(
                    os.stat_result(
                        (
                            stat.S_IFLNK | stat.S_IMODE(real.st_mode),
                            real.st_ino,
                            real.st_dev,
                            real.st_nlink,
                            real.st_uid,
                            real.st_gid,
                            real.st_size,
                            real.st_atime,
                            real.st_mtime,
                            real.st_ctime,
                        )
                    )
                )
            return forged[0]
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", selective_resolve)
    monkeypatch.setattr("os.lstat", selective_lstat)


def upgrade_cmake_template(monkeypatch) -> None:
    original = configure_mod._load_template_resource

    def loader(name: str) -> bytes:
        data = original(name)
        if name == "cmake/CMakeLists.txt.j2":
            data = data + b"# upgraded template\n"
        return data

    monkeypatch.setattr(configure_mod, "_load_template_resource", loader)


def fail_replace_at(monkeypatch, fail_calls):
    calls: list[tuple[Path, Path]] = []
    original = os.replace

    def wrapper(source, destination):
        calls.append((Path(source), Path(destination)))
        if len(calls) in fail_calls:
            raise OSError("injected replace failure")
        return original(source, destination)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.replace", wrapper)
    return calls


def fail_fsync_at(monkeypatch, fail_calls):
    calls: list[int] = []

    def wrapper(fd: int) -> None:
        calls.append(1)
        if len(calls) in fail_calls:
            raise configure_mod._FsyncError(5, "injected fsync failure")
        os.fsync(fd)

    monkeypatch.setattr(configure_mod, "_fsync", wrapper)
    return calls


# ---------------------------------------------------------------------------
# public types, hashing, serialization
# ---------------------------------------------------------------------------


def test_generation_error_carries_code_message_and_details():
    error = GenerationError("CODE", "message", {"path": "x", "rule": "y"})
    assert error.code == "CODE"
    assert error.message == "message"
    assert error.details == {"path": "x", "rule": "y"}
    assert str(error) == "message"


def test_public_containers_are_frozen(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    for instance in (
        plan.inputs[0],
        plan.files[0],
        plan.model,
    ):
        with pytest.raises(FrozenInstanceError):
            instance.path = "other"  # type: ignore[attr-defined]
    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "other"  # type: ignore[attr-defined]
    blocker = GenerationBlocker("CODE", "path", "message")
    with pytest.raises(FrozenInstanceError):
        blocker.code = "other"  # type: ignore[attr-defined]
    record = ManagedFileRecord("x", "managed", 1, "a" * 64)
    with pytest.raises(FrozenInstanceError):
        record.ownership = "user"  # type: ignore[attr-defined]


def test_to_dict_is_fresh_json_safe_and_omits_bytes_and_roots(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    first = plan.to_dict()
    second = plan.to_dict()
    assert first == second
    assert first is not second
    text = json.dumps(first)
    assert str(root) not in text
    assert "before_bytes" not in text
    assert "after_bytes" not in text
    assert "project_root" not in text
    entry = plan.files[0]
    entry_dict = entry.to_dict()
    assert entry_dict["path"] == entry.path
    assert entry_dict["after_sha256"] == entry.after_sha256
    assert "before_bytes" not in entry_dict
    assert "after_bytes" not in entry_dict
    assert plan.plan_version == 1
    assert len(plan.plan_id) == 64
    assert plan.plan_id == plan.plan_id.lower()
    assert plan.managed_manifest_path == ".stm32-toolkit/generated-files.json"


def test_plan_to_dict_key_order_is_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert list(plan.to_dict()) == [
        "plan_version",
        "plan_id",
        "model_sha256",
        "inputs",
        "files",
        "blockers",
        "managed_manifest_path",
    ]
    assert list(plan.files[0].to_dict()) == [
        "path",
        "status",
        "template_name",
        "template_version",
        "before_sha256",
        "after_sha256",
        "before_size",
        "after_size",
        "unified_diff",
    ]


def test_canonical_json_bytes_is_deterministic():
    value = {"b": [2, 1], "a": {"z": "x", "y": 1}}
    assert canonical_json_bytes(value) == canonical_json_bytes(value)
    assert b" " not in canonical_json_bytes(value)


def test_model_sha256_is_deterministic_and_excludes_root(tmp_path):
    root_a = write_project(tmp_path / "a")
    root_b = write_project(tmp_path / "b")
    model_a = load_project_model(root_a)
    model_b = load_project_model(root_b)
    assert model_sha256_for(model_a) == model_sha256_for(model_b)
    assert model_sha256_for(model_a) == model_sha256_for(load_project_model(root_a))
    assert len(model_sha256_for(model_a)) == 64


def test_plan_id_is_deterministic_and_excludes_diffs_and_absolute_paths(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    plan_again = plan_for(root)
    assert plan_id_for(plan) == plan_id_for(plan_again)
    tampered_diff = replace(
        plan,
        files=tuple(
            replace(entry, unified_diff="") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert plan_id_for(tampered_diff) == plan_id_for(plan)
    tampered_bytes = replace(
        plan,
        files=tuple(
            replace(
                entry,
                after_bytes=b"tampered",
                after_sha256=sha256(b"tampered"),
                after_size=len(b"tampered"),
            )
            if entry.path == "CMakeLists.txt"
            else entry
            for entry in plan.files
        ),
    )
    assert plan_id_for(tampered_bytes) != plan_id_for(plan)


def test_portable_path_error_cases():
    assert portable_path_error(None) == "empty"
    assert portable_path_error("") == "empty"
    assert portable_path_error("a\x00b") == "nul"
    assert portable_path_error("/abs") == "absolute"
    assert portable_path_error("\\abs") == "absolute"
    assert portable_path_error("C:/x") == "drivePrefix"
    assert portable_path_error("C:x") == "drivePrefix"
    assert portable_path_error("//unc/x") == "unc"
    assert portable_path_error("\\\\unc\\x") == "unc"
    assert portable_path_error("a//b") == "component"
    assert portable_path_error("a/./b") == "component"
    assert portable_path_error("a/../b") == "component"
    assert portable_path_error("a/") == "component"
    assert portable_path_error("a/b") is None
    assert portable_path_error("Src/main.c") is None


def test_sha256_error():
    assert sha256_error(None) == "sha256"
    assert sha256_error("") == "sha256"
    assert sha256_error("A" * 64) == "sha256"
    assert sha256_error("a" * 63) == "sha256"
    assert sha256_error("a" * 64) is None


def test_manifest_build_and_parse_roundtrip(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    parsed = parse_managed_manifest(plan.managed_manifest_bytes)
    assert [entry.path for entry in parsed] == [entry.path for entry in plan.files]
    assert all(entry.ownership == "managed" for entry in parsed)
    assert all(entry.template_version == 1 for entry in parsed)
    rebuilt = build_managed_manifest_bytes(plan.files, plan.model_sha256)
    assert rebuilt == plan.managed_manifest_bytes
    assert parsed == parse_managed_manifest(rebuilt)


def test_generation_input_to_dict():
    entry = GenerationInput("Src/main.c", "a" * 64, 12)
    assert entry.to_dict() == {"path": "Src/main.c", "sha256": "a" * 64, "size": 12}


def test_first_plan_has_create_status_for_all_targets(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert [entry.path for entry in plan.files] == list(TARGETS)
    assert all(entry.status == "create" for entry in plan.files)
    assert plan.blockers == ()
    assert all(entry.before_bytes is None for entry in plan.files)
    assert plan.model_sha256 == model_sha256_for(plan.model)


def test_plan_inputs_cover_manifest_sources_and_assembly(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    paths = [entry.path for entry in plan.inputs]
    assert paths == sorted(paths)
    assert paths == [".stm32-project.json", "Src/app.c", "Src/main.c", "Startup/startup.s"]
    assert all(len(entry.sha256) == 64 for entry in plan.inputs)
    assert all(entry.size > 0 for entry in plan.inputs)


def test_generation_and_doctor_never_import_each_other():
    check = (
        "import stm32_toolkit.generation, sys; "
        "assert 'stm32_toolkit.doctor' not in sys.modules"
    )
    assert subprocess.run([sys.executable, "-c", check], capture_output=True).returncode == 0
    check = (
        "import stm32_toolkit.doctor, sys; "
        "assert 'stm32_toolkit.generation' not in sys.modules"
    )
    assert subprocess.run([sys.executable, "-c", check], capture_output=True).returncode == 0


# ---------------------------------------------------------------------------
# model validation
# ---------------------------------------------------------------------------


def test_model_wrong_type_is_rejected():
    for bad in (None, {}, "model", 42):
        with pytest.raises(GenerationError) as error:
            plan_project_configuration(bad)  # type: ignore[arg-type]
        assert error.value.code == "GENERATION_MODEL_INVALID"
        assert error.value.details == {"field": "model", "rule": "type"}


def test_schema_v1_model_is_rejected(tmp_path):
    payload = {
        "schemaVersion": 1,
        "logicalProjectId": UUID,
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "X", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["Src/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "elf": "build/arm-debug/firmware.elf",
        },
        "debug": {"backend": "pyocd", "target": "stm32f407vg"},
    }
    root = write_project(tmp_path / "proj", payload)
    model = load_project_model(root)
    assert model.schema_version == 1
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(model)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "version"}


def test_missing_project_root_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    missing = replace(model, project_root=Path(tmp_path) / "does-not-exist-0304")
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(missing)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "directory"}


def test_non_path_project_root_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(replace(model, project_root="Src/main.c"))  # type: ignore[arg-type]
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "type"}


def test_stale_model_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    payload = standard_payload()
    payload["build"]["defines"] = ["CHANGED"]
    write_project(root, payload)
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(model)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "model", "rule": "stale"}


def test_unloadable_model_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    (root / ".stm32-project.json").write_bytes(b"{not json")
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(model)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "model", "rule": "unavailable"}


@pytest.mark.parametrize(
    ("field", "rule"),
    [
        ("generation.tool", "value"),
        ("generation.version", "value"),
        ("generation.managedManifest", "value"),
    ],
)
def test_generation_spec_validation(tmp_path, field, rule):
    payload = standard_payload()
    if field == "generation.tool":
        payload["generatedBy"] = {"tool": "other", "version": __version__}
    elif field == "generation.version":
        payload["generatedBy"] = {"tool": "stm32-toolkit", "version": "9.9.9"}
    else:
        payload["generation"]["managedManifest"] = "other.json"
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": field, "rule": rule}


@pytest.mark.parametrize(
    "core",
    ["cortex-m0", "cortex-m0plus", "cortex-m3", "cortex-m4", "cortex-m7", "cortex-m23", "cortex-m33"],
)
def test_supported_cores_render_exact_cpu_flags(tmp_path, core):
    payload = standard_payload()
    payload["target"] = {"device": "X", "core": core}
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    flag = {"cortex-m0": "-mcpu=cortex-m0", "cortex-m0plus": "-mcpu=cortex-m0plus",
            "cortex-m3": "-mcpu=cortex-m3", "cortex-m4": "-mcpu=cortex-m4",
            "cortex-m7": "-mcpu=cortex-m7", "cortex-m23": "-mcpu=cortex-m23",
            "cortex-m33": "-mcpu=cortex-m33"}[core]
    assert ("  " + flag + "\n") in cmake.after_bytes.decode("utf-8")


def test_unsupported_core_is_rejected(tmp_path):
    payload = standard_payload()
    payload["target"] = {"device": "X", "core": "cortex-r4"}
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "target.core", "rule": "unsupported"}


@pytest.mark.parametrize(
    ("fpu", "float_abi", "rule"),
    [
        (None, "hard", "pairing"),
        ("fpv4-sp-d16", None, "pairing"),
        ("bad fpu", "hard", "format"),
        ("fpv4-sp-d16", "weird", "unsupported"),
    ],
)
def test_fpu_float_abi_validation(tmp_path, fpu, float_abi, rule):
    payload = standard_payload()
    target = {"device": "X", "core": "cortex-m4"}
    if fpu is not None:
        target["fpu"] = fpu
    if float_abi is not None:
        target["floatAbi"] = float_abi
    payload["target"] = target
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details["rule"] == rule


@pytest.mark.parametrize(
    "define",
    ["1BAD", "A;B", "A\nB", "A\x00B", "-D", "A B"],
)
def test_invalid_defines_are_rejected(tmp_path, define):
    payload = standard_payload()
    payload["build"]["defines"] = [define]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "build.defines", "rule": "define"}


def test_define_with_equals_value_is_accepted(tmp_path):
    payload = standard_payload()
    payload["build"]["defines"] = ["USE_HAL_DRIVER=1"]
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert b"USE_HAL_DRIVER=1" in cmake.after_bytes


@pytest.mark.parametrize(
    "option",
    ["not-a-flag", "-x y", "-D$X", "-D@X", "-D`x", "-DSHELL:cmd", "-D\"x\"", "-D\\x", "-Dx;y"],
)
def test_unsafe_compile_options_are_rejected(tmp_path, option):
    payload = standard_payload()
    payload["build"]["compileOptions"] = [option]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "build.compileOptions", "rule": "option"}


@pytest.mark.parametrize(
    "presets",
    [[], ["arm-debug"], ["arm-release", "arm-debug"], ["arm-debug", "arm-release", "arm-test"]],
)
def test_presets_must_be_exactly_arm_debug_release(tmp_path, presets):
    payload = standard_payload()
    payload["build"]["presets"] = presets
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "build.presets", "rule": "presets"}


@pytest.mark.parametrize(
    "elf",
    [None, "build/arm-release/firmware.elf", "build/arm-debug/a/b.elf", "build/arm-debug/.elf",
     "build/arm-debug/firmware"],
)
def test_invalid_elf_paths_are_rejected(tmp_path, elf):
    payload = standard_payload()
    payload["build"]["elf"] = elf
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "build.elf", "rule": "value"}


def test_absolute_elf_path_is_rejected_at_model_load(tmp_path):
    payload = standard_payload()
    payload["build"]["elf"] = "/abs/firmware.elf"
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(ProjectManifestError):
        load_project_model(root)


def test_elf_basename_with_extra_elf_suffix_is_accepted(tmp_path):
    payload = standard_payload()
    payload["build"]["elf"] = "build/arm-debug/firmware.elf.elf"
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert b"add_executable(firmware_elf\n" in cmake.after_bytes


def test_missing_debug_backend_is_rejected(tmp_path):
    payload = standard_payload()
    payload["debug"] = {}
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "debug.backend", "rule": "value"}


def test_non_pyocd_backend_is_rejected(tmp_path):
    payload = standard_payload()
    payload["debug"] = {"backend": "openocd", "target": "stm32f407vg"}
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "debug.backend", "rule": "value"}


def test_missing_debug_target_is_rejected(tmp_path):
    payload = standard_payload()
    payload["debug"] = {"backend": "pyocd"}
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "debug.backend", "rule": "value"}


def test_bad_region_name_is_rejected(tmp_path):
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "1FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
    ]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "name"}


def test_overlapping_regions_are_rejected(tmp_path):
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "RAM", "origin": 0x08001000, "length": 0x20000, "attributes": "rwx"},
    ]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "overlap"}


def test_no_executable_region_is_rejected(tmp_path):
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r--"},
        {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rw-"},
    ]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "executable"}


def test_no_writable_region_is_rejected(tmp_path):
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "r--"},
    ]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "writable"}


def test_negative_origin_and_bool_ranges_are_rejected_directly(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    from stm32_toolkit.project_model import MemoryRegion, MemorySpec

    for bad_origin, bad_length in ((True, 0x100), (0x100, True), (-1, 0x100), (0x100, 0)):
        memory = MemorySpec(
            source="manual",
            regions=(
                MemoryRegion("FLASH", bad_origin, bad_length, "r-x"),
                MemoryRegion("RAM", 0x20000000, 0x20000, "rwx"),
            ),
        )
        with pytest.raises(GenerationError) as error:
            configure_mod._validate_memory(replace(model, memory=memory))
        assert error.value.code == "GENERATION_MODEL_INVALID"
        assert error.value.details == {"field": "memory.regions", "rule": "range"}


def test_region_overflow_beyond_32_bits_is_rejected_directly(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    from stm32_toolkit.project_model import MemoryRegion, MemorySpec

    memory = MemorySpec(
        source="manual",
        regions=(
            MemoryRegion("FLASH", 0x08000000, 0x100000, "r-x"),
            MemoryRegion("RAM", 0xFFFFFF00, 0x20000, "rwx"),
        ),
    )
    with pytest.raises(GenerationError) as error:
        configure_mod._validate_memory(replace(model, memory=memory))
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "range"}


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------


def test_missing_source_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "Src/missing.c"]
    root = write_project(tmp_path / "proj", payload)
    (root / "Src/missing.c").unlink()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/missing.c", "rule": "missing"}


def test_missing_assembly_source_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["assemblySources"] = ["Startup/startup.s", "Startup/gone.s"]
    root = write_project(tmp_path / "proj", payload)
    (root / "Startup/gone.s").unlink()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Startup/gone.s", "rule": "missing"}


def test_missing_include_directory_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["includePaths"] = ["Inc", "Missing"]
    root = write_project(tmp_path / "proj", payload)
    shutil.rmtree(root / "Missing")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Missing", "rule": "directory"}


def test_include_that_is_a_file_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["includePaths"] = ["Inc"]
    root = write_project(tmp_path / "proj", payload)
    shutil.rmtree(root / "Inc")
    (root / "Inc").write_bytes(b"not a directory\n")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Inc", "rule": "directory"}


def test_source_that_is_a_directory_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    (root / "Src/main.c").unlink()
    (root / "Src/main.c").mkdir()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "regularFile"}


def test_missing_svd_is_rejected(tmp_path):
    payload = standard_payload()
    payload["debug"]["svd"] = "debug/stm32f407.svd"
    root = write_project(tmp_path / "proj", payload)
    (root / "debug/stm32f407.svd").unlink()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "debug/stm32f407.svd", "rule": "missing"}


def test_present_svd_is_hashed_as_input(tmp_path):
    payload = standard_payload()
    payload["debug"]["svd"] = "debug/stm32f407.svd"
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    assert any(entry.path == "debug/stm32f407.svd" for entry in plan.inputs)
    launch = next(entry for entry in plan.files if entry.path == ".vscode/launch.json")
    assert b"svdFile" in launch.after_bytes


def test_missing_cube_mx_ioc_is_rejected(tmp_path):
    payload = standard_payload()
    payload["generation"]["cubeMxIoc"] = "firmware.ioc"
    root = write_project(tmp_path / "proj", payload)
    (root / "firmware.ioc").unlink()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "firmware.ioc", "rule": "missing"}


def test_present_cube_mx_ioc_is_hashed_as_input(tmp_path):
    payload = standard_payload()
    payload["generation"]["cubeMxIoc"] = "firmware.ioc"
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    assert any(entry.path == "firmware.ioc" for entry in plan.inputs)


def test_oversized_input_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "FILE_LIMIT_BYTES", 2500)
    payload = standard_payload()
    root = write_project(tmp_path / "proj", payload)
    (root / "Src/main.c").write_bytes(b"x" * 3000)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "size"}


def test_aggregate_input_limit_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "FILE_LIMIT_BYTES", 4096)
    monkeypatch.setattr(configure_mod, "AGGREGATE_LIMIT_BYTES", 4096)
    payload = standard_payload()
    payload["build"]["sources"] = [f"Src/file{i}.c" for i in range(6)]
    root = write_project(tmp_path / "proj", payload)
    for index in range(6):
        (root / f"Src/file{index}.c").write_bytes(b"y" * 900)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details["rule"] == "aggregateSize"


def test_duplicate_source_paths_are_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details["rule"] == "duplicate"


def test_casefold_colliding_input_paths_are_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "Src/MAIN.C"]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details["rule"] == "duplicate"


def test_source_colliding_with_generated_target_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "CMakeLists.txt"]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details["rule"] == "casefoldCollision"


def test_source_casefold_colliding_with_generated_target_is_rejected(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "cmakelists.txt"]
    root = write_project(tmp_path / "proj", payload)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details["rule"] == "casefoldCollision"


def test_nul_traversal_drive_and_unc_paths_are_rejected_at_model_load(tmp_path):
    root = write_project(tmp_path / "proj")
    for bad in ["Src/\x00bad.c", "Src/../escape.c", "C:/outside.c", "\\\\unc\\share\\x.c"]:
        broken = standard_payload()
        broken["build"]["sources"] = [bad]
        (root / ".stm32-project.json").write_bytes(
            json.dumps(broken, indent=2).encode("utf-8") + b"\n"
        )
        with pytest.raises(ProjectManifestError) as error:
            load_project_model(root)
        assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert (tmp_path / "escape.c").exists() is False


def test_in_root_redirect_source_is_accepted(monkeypatch, tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    (root / "Src/main.c").unlink()
    (root / "Src/other.c").write_bytes(b"int other(void) { return 2; }\n")
    _redirect_path(monkeypatch, root / "Src/main.c", root / "Src/other.c", is_dir=False)
    model = load_project_model(root)
    plan = plan_project_configuration(model)
    entry = next(entry for entry in plan.inputs if entry.path == "Src/main.c")
    assert entry.sha256 == sha256(b"int other(void) { return 2; }\n")


def test_redirect_escape_source_is_rejected(monkeypatch, tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    (root / "Src/main.c").unlink()
    outside = tmp_path / "outside.c"
    outside.write_bytes(b"int outside(void) { return 3; }\n")
    _redirect_path(monkeypatch, root / "Src/main.c", outside, is_dir=False)
    with pytest.raises(ProjectManifestError) as error:
        load_project_model(root)
    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    with pytest.raises(GenerationError) as error:
        configure_mod._resolve_contained(root / "Src/main.c", root, "Src/main.c")
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "withinProjectRoot"}


def test_lstat_failure_is_rejected_conservatively(monkeypatch, tmp_path):
    payload = standard_payload()
    payload["build"]["includePaths"] = []
    root = write_project(tmp_path / "proj", payload)
    model = load_project_model(root)

    def unavailable(path, *args, **kwargs):
        raise OSError("injected inspection failure")

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", unavailable)
    with pytest.raises(GenerationError) as error:
        configure_mod._collect_inputs(root, model, None, None)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": ".stm32-project.json", "rule": "unreadable"}


def test_prior_manifest_is_an_input_when_present(tmp_path):
    root = write_project(tmp_path / "proj")
    write_manifest_bytes(root, _manifest_with([]))
    plan = plan_for(root)
    assert any(entry.path == MANAGED_MANIFEST_PATH for entry in plan.inputs)


# ---------------------------------------------------------------------------
# rendering snapshots and template contracts
# ---------------------------------------------------------------------------


def test_cmake_snapshot_hard_fpu(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert entry.after_bytes == EXPECTED_CMAKE.encode("utf-8")
    assert entry.after_bytes.endswith(b"\n")
    assert b"\r" not in entry.after_bytes


def test_cmake_snapshot_no_fpu(tmp_path):
    payload = standard_payload()
    payload["target"] = {"device": "X", "core": "cortex-m4"}
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = entry.after_bytes.decode("utf-8")
    assert "-mfpu=" not in text
    assert "-mfloat-abi=" not in text
    expected_options = (
        "target_compile_options(firmware PRIVATE\n"
        "  -mcpu=cortex-m4\n"
        "  -mthumb\n"
        "  -ffunction-sections\n"
        "  -fdata-sections\n"
        "  -ffreestanding\n"
        "  $<$<CONFIG:Debug>:-Og;-g3>\n"
        "  $<$<CONFIG:Release>:-O2;-g0>\n"
        ")\n"
    )
    assert expected_options in text


def test_cmake_link_options_exact_hard_fpu_snapshot(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = entry.after_bytes.decode("utf-8")
    expected = (
        "target_link_options(firmware PRIVATE\n"
        "  -mcpu=cortex-m4\n"
        "  -mthumb\n"
        "  -mfpu=fpv4-sp-d16\n"
        "  -mfloat-abi=hard\n"
        "  -nostartfiles\n"
        '  "-T${CMAKE_SOURCE_DIR}/linker/stm32tk.ld"\n'
        '  "-Wl,-Map=${CMAKE_BINARY_DIR}/firmware.map"\n'
        '  "-Wl,--gc-sections"\n'
        ")\n"
    )
    assert expected in text


def test_cmake_link_options_no_fpu_snapshot(tmp_path):
    payload = standard_payload()
    payload["target"] = {"device": "X", "core": "cortex-m4"}
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = entry.after_bytes.decode("utf-8")
    assert "-mfpu=" not in text
    assert "-mfloat-abi=" not in text
    expected = (
        "target_link_options(firmware PRIVATE\n"
        "  -mcpu=cortex-m4\n"
        "  -mthumb\n"
        "  -nostartfiles\n"
        '  "-T${CMAKE_SOURCE_DIR}/linker/stm32tk.ld"\n'
        '  "-Wl,-Map=${CMAKE_BINARY_DIR}/firmware.map"\n'
        '  "-Wl,--gc-sections"\n'
        ")\n"
    )
    assert expected in text


def test_cmake_link_arch_flags_match_compile_arch_flags_hard_fpu(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = entry.after_bytes.decode("utf-8")
    compile_block = text.split("target_compile_options(")[1].split(")")[0]
    link_block = text.split("target_link_options(")[1].split(")")[0]
    for flag in ("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"):
        assert flag in compile_block
        assert flag in link_block
    assert "-nostartfiles" in link_block
    assert "--gc-sections" in link_block
    assert "-Map=" in link_block
    assert "-T${CMAKE_SOURCE_DIR}" in link_block


def test_cmake_link_arch_flags_match_compile_arch_flags_no_fpu(tmp_path):
    payload = standard_payload()
    payload["target"] = {"device": "X", "core": "cortex-m3"}
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = entry.after_bytes.decode("utf-8")
    compile_block = text.split("target_compile_options(")[1].split(")")[0]
    link_block = text.split("target_link_options(")[1].split(")")[0]
    assert "-mcpu=cortex-m3" in compile_block
    assert "-mcpu=cortex-m3" in link_block
    assert "-mthumb" in link_block
    assert "-mfpu=" not in link_block
    assert "-mfloat-abi=" not in link_block
    assert "-nostartfiles" in link_block
    assert "-Wl,--gc-sections" in link_block


def test_cmake_snapshot_paths_with_spaces(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/my file.c"]
    payload["build"]["assemblySources"] = []
    payload["build"]["includePaths"] = ["Inc/My Dir"]
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = cmake.after_bytes.decode("utf-8")
    assert '  "Src/my file.c"\n' in text
    assert '  "Inc/My Dir"\n' in text
    c_cpp = next(entry for entry in plan.files if entry.path == ".vscode/c_cpp_properties.json")
    assert '"${workspaceFolder}/Inc/My Dir"' in c_cpp.after_bytes.decode("utf-8")


def test_cmake_snapshot_cpp_and_asm_sources(tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c", "Src/app.cpp"]
    payload["build"]["assemblySources"] = ["Startup/startup.s", "Startup/boot.s"]
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = cmake.after_bytes.decode("utf-8")
    assert "add_executable(firmware\n  Src/main.c\n  Src/app.cpp\n  Startup/startup.s\n  Startup/boot.s\n)\n" in text


def test_target_name_and_outputs_follow_elf_basename(tmp_path):
    payload = standard_payload()
    payload["build"]["elf"] = "build/arm-debug/my-fw_v2.elf"
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    text = cmake.after_bytes.decode("utf-8")
    assert "add_executable(my_fw_v2\n" in text
    assert "${CMAKE_BINARY_DIR}/my-fw_v2.map" in text
    assert "${CMAKE_BINARY_DIR}/my-fw_v2.hex" in text
    assert "${CMAKE_BINARY_DIR}/my-fw_v2.bin" in text
    launch = next(entry for entry in plan.files if entry.path == ".vscode/launch.json")
    assert "${workspaceFolder}/build/arm-debug/my-fw_v2.elf" in launch.after_bytes.decode("utf-8")


def test_sanitized_project_name_is_used(tmp_path):
    payload = standard_payload()
    payload["project"] = {"name": "My App!!", "origin": "keil-migration"}
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert b"project(My_App LANGUAGES C CXX ASM)" in cmake.after_bytes


def test_sanitize_identifier_fallbacks():
    assert configure_mod.sanitize_cmake_identifier("123abc") == "stm32_123abc"
    assert configure_mod.sanitize_cmake_identifier("!!!") == "stm32_firmware"
    assert configure_mod.sanitize_cmake_identifier("a--b") == "a_b"
    assert configure_mod.sanitize_cmake_identifier("firmware") == "firmware"


def test_linker_snapshot_no_fixed_sections(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    assert entry.after_bytes == EXPECTED_LINKER.encode("utf-8")


def test_linker_snapshot_with_ccm_region_preserves_order(tmp_path):
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
        {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
        {"name": "CCM", "origin": 0x10000000, "length": 0x10000, "attributes": "rwx"},
    ]
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    flash = text.index("FLASH (rx)")
    ram = text.index("RAM (rwx)")
    ccm = text.index("CCM (rwx)")
    assert flash < ram < ccm
    assert "0x10000000" in text
    assert text.count("> RAM") == 4


def _memory_block_attributes(text: str) -> list[str]:
    """Extract GNU ld MEMORY attributes (the parenthesized flag groups)."""
    memory = text.split("MEMORY", 1)[1].split("SECTIONS", 1)[0]
    return [
        line.split("(", 1)[1].split(")", 1)[0]
        for line in memory.splitlines()
        if "ORIGIN" in line
    ]


@pytest.mark.parametrize(
    "attrs,expected",
    [
        ("r--", "r"),
        ("rw-", "rw"),
        ("r-x", "rx"),
        ("rwx", "rwx"),
    ],
)
def test_linker_memory_attributes_normalized_for_gnu_ld(tmp_path, attrs, expected):
    """Schema v2 attributes must render as hyphen-free GNU ld flags."""
    payload = standard_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": attrs},
        {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
    ]
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    assert f"FLASH ({expected})" in text
    if attrs != expected:
        assert f"FLASH ({attrs})" not in text
    for attributes in _memory_block_attributes(text):
        assert "-" not in attributes


def test_no_hyphens_in_generated_linker_memory_attributes(tmp_path):
    """GNU ld rejects hyphens in MEMORY flags; no generated attribute may have one."""
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    for attributes in _memory_block_attributes(text):
        assert "-" not in attributes
        assert attributes in ("r", "rw", "rx", "rwx")


def test_toolchain_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "cmake/arm-none-eabi-gcc.cmake")
    assert entry.after_bytes == EXPECTED_TOOLCHAIN.encode("utf-8")
    assert b"/" not in entry.after_bytes.replace(b"//", b"")


def test_extensions_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/extensions.json")
    assert entry.after_bytes == EXPECTED_EXTENSIONS.encode("utf-8")


def test_presets_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakePresets.json")
    payload = json.loads(entry.after_bytes.decode("utf-8"))
    assert payload["version"] == 3
    assert payload["cmakeMinimumRequired"] == {"major": 3, "minor": 22, "patch": 0}
    assert [preset["name"] for preset in payload["configurePresets"]] == [
        "arm-debug",
        "arm-release",
    ]
    assert [preset["name"] for preset in payload["buildPresets"]] == ["arm-debug", "arm-release"]
    for preset in payload["configurePresets"]:
        assert preset["generator"] == "Ninja"
        assert preset["binaryDir"] == "${sourceDir}/build/" + preset["name"]
        assert preset["toolchainFile"] == "${sourceDir}/cmake/arm-none-eabi-gcc.cmake"
        assert preset["cacheVariables"]["CMAKE_BUILD_TYPE"] in ("Debug", "Release")


def test_tasks_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/tasks.json")
    payload = json.loads(entry.after_bytes.decode("utf-8"))
    labels = [task["label"] for task in payload["tasks"]]
    assert labels == [
        "STM32 Toolkit: Build Debug",
        "STM32 Toolkit: Build Release",
    ]
    for task in payload["tasks"]:
        assert task["type"] == "process"
        assert task["command"] == "stm32-toolkit"
        assert isinstance(task["args"], list)
        assert task["args"][:2] == ["build", "--preset"]
        assert task["args"][2] in ("arm-debug", "arm-release")
        assert task["args"][3:] == ["--project", "${workspaceFolder}"]
    joined = json.dumps(payload)
    for forbidden in ("pyocd", "cmake", "arm-none-eabi", "shell", "ninja", "objcopy", "flash", "handoff"):
        assert forbidden not in joined


def test_launch_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/launch.json")
    payload = json.loads(entry.after_bytes.decode("utf-8"))
    config = payload["configurations"][0]
    assert config["name"] == "STM32 Toolkit: Debug"
    assert config["type"] == "cortex-debug"
    assert config["request"] == "launch"
    assert config["servertype"] == "pyocd"
    assert config["target"] == "stm32f407vg"
    assert config["executable"] == "${workspaceFolder}/build/arm-debug/firmware.elf"
    assert config["preLaunchTask"] == "STM32 Toolkit: Debug Handoff Begin"
    assert config["postDebugTask"] == "STM32 Toolkit: Debug Handoff End"
    assert "svdFile" not in config


def test_launch_snapshot_with_svd(tmp_path):
    payload = standard_payload()
    payload["debug"]["svd"] = "debug/stm32f407.svd"
    root = write_project(tmp_path / "proj", payload)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/launch.json")
    config = json.loads(entry.after_bytes.decode("utf-8"))["configurations"][0]
    assert config["svdFile"] == "${workspaceFolder}/debug/stm32f407.svd"


def test_c_cpp_snapshot_exact(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/c_cpp_properties.json")
    payload = json.loads(entry.after_bytes.decode("utf-8"))
    config = payload["configurations"][0]
    assert config["name"] == "arm-debug"
    assert config["compilerPath"] == "arm-none-eabi-gcc"
    assert config["includePath"] == ["${workspaceFolder}/Inc"]
    assert config["defines"] == ["USE_HAL_DRIVER", "STM32F407xx"]
    assert config["intelliSenseMode"] == "gcc-arm"
    assert config["cStandard"] == "c11"
    assert config["cppStandard"] == "c++17"


def test_settings_snapshot_native_json_booleans(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/settings.json")
    text = entry.after_bytes.decode("utf-8")
    assert '"cmake.configureOnOpen": false' in text
    assert '"cmake.useCMakePresets": "always"' in text
    assert json.loads(text) == {"cmake.configureOnOpen": False, "cmake.useCMakePresets": "always"}


def test_all_generated_json_parses_and_uses_forward_slashes(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    for entry in plan.files:
        if entry.path.endswith(".json"):
            json.loads(entry.after_bytes.decode("utf-8"))
            assert b"\\" not in entry.after_bytes
            assert entry.after_bytes.endswith(b"\n")


def test_root_and_packaged_templates_are_byte_identical():
    import importlib.resources

    resources = [
        "cmake/CMakeLists.txt.j2",
        "cmake/arm-none-eabi-gcc.cmake",
        "cmake/CMakePresets.json.j2",
        "cmake/linker.ld.j2",
        "vscode/tasks.json.j2",
        "vscode/launch.json.j2",
        "vscode/c_cpp_properties.json.j2",
        "vscode/settings.json.j2",
        "vscode/extensions.json",
    ]
    for name in resources:
        root_bytes = (REPO_ROOT / "templates" / name).read_bytes()
        packaged = (
            importlib.resources.files("stm32_toolkit")
            .joinpath("templates", *name.split("/"))
            .read_bytes()
        )
        assert packaged == root_bytes, name
        assert sha256(packaged) == sha256(root_bytes)


def test_missing_template_resource_is_rejected():
    with pytest.raises(GenerationError) as error:
        configure_mod._load_template_resource("cmake/nope.j2")
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details == {"template": "cmake/nope.j2", "rule": "missing"}


def test_invalid_template_path_is_rejected():
    with pytest.raises(GenerationError) as error:
        configure_mod._load_template_resource("../evil.j2")
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"


def test_oversized_template_resource_is_rejected(monkeypatch):
    monkeypatch.setattr(configure_mod, "TEMPLATE_LIMIT_BYTES", 1)
    with pytest.raises(GenerationError) as error:
        configure_mod._load_template_resource("vscode/settings.json.j2")
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details["rule"] == "oversized"


def test_undefined_template_variable_is_rejected():
    with pytest.raises(GenerationError) as error:
        configure_mod._render_template("cmake/CMakeLists.txt.j2", {"project_name": "x"})
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details == {
        "template": "cmake/CMakeLists.txt.j2",
        "rule": "undefined",
    }


def test_invalid_template_encoding_is_rejected(monkeypatch):
    monkeypatch.setattr(
        configure_mod, "_load_template_resource", lambda name: b"\xff\xfe\x00"
    )
    with pytest.raises(GenerationError) as error:
        configure_mod._render_template("vscode/settings.json.j2", {"settings": {}})
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details["rule"] == "encoding"


def test_oversized_rendered_file_is_rejected(monkeypatch):
    monkeypatch.setattr(configure_mod, "GENERATED_LIMIT_BYTES", 1)
    with pytest.raises(GenerationError) as error:
        configure_mod._render_template("vscode/settings.json.j2", {"settings": {}})
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details["rule"] == "oversized"


def test_aggregate_generated_limit_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "TOTAL_LIMIT_BYTES", 100)
    root = write_project(tmp_path / "proj")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details["rule"] == "aggregateLimit"


def test_plan_serialization_limit_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "PLAN_LIMIT_BYTES", 10)
    root = write_project(tmp_path / "proj")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_PLAN_INVALID"
    assert error.value.details == {"rule": "planLimit"}


# ---------------------------------------------------------------------------
# fixed-section evidence
# ---------------------------------------------------------------------------


def test_fixed_section_report_absent_is_valid(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    assert b".stm32tk.abs." not in entry.after_bytes
    assert not any(entry.path == REPORT_PATH for entry in plan.inputs)


def test_fixed_section_valid_single_placement(tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(
        root,
        json.dumps(
            report_payload(
                [
                    {
                        "section": ".stm32tk.abs.08000000",
                        "address": 0x08000000,
                        "sourcePath": "Src/main.c",
                        "line": 13,
                        "symbol": "pinned_value",
                    }
                ]
            )
        ).encode("utf-8")
        + b"\n",
    )
    plan = plan_for(root)
    assert any(entry.path == REPORT_PATH for entry in plan.inputs)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    expected = (
        "\n  .stm32tk.abs.08000000 0x08000000 (NOLOAD) :\n"
        "  {\n"
        "    KEEP(*(.stm32tk.abs.08000000))\n"
        "  } > FLASH\n"
    )
    assert expected in text


def test_fixed_section_in_ram_region(tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(
        root,
        json.dumps(
            report_payload(
                [
                    {
                        "section": ".stm32tk.abs.20000000",
                        "address": 0x20000000,
                        "sourcePath": "Src/main.c",
                        "line": 13,
                        "symbol": "ram_pinned",
                    }
                ]
            )
        ).encode("utf-8")
        + b"\n",
    )
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    expected = (
        "\n  .stm32tk.abs.20000000 0x20000000 (NOLOAD) :\n"
        "  {\n"
        "    KEEP(*(.stm32tk.abs.20000000))\n"
        "  } > RAM\n"
    )
    assert expected in text
    assert b"0x20000000 (NOLOAD)" in entry.after_bytes


def test_fixed_section_multiple_placements_exact_snapshot(tmp_path):
    root = write_project(tmp_path / "proj")
    flash = {
        "section": ".stm32tk.abs.08000000",
        "address": 0x08000000,
        "sourcePath": "Src/main.c",
        "line": 13,
        "symbol": "pinned_value",
    }
    ram = {
        "section": ".stm32tk.abs.20000000",
        "address": 0x20000000,
        "sourcePath": "Src/main.c",
        "line": 14,
        "symbol": "ram_pinned",
    }
    write_report_bytes(
        root,
        json.dumps(report_payload([ram, flash])).encode("utf-8") + b"\n",
    )
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    text = entry.after_bytes.decode("utf-8")
    expected = (
        "\n  .stm32tk.abs.08000000 0x08000000 (NOLOAD) :\n"
        "  {\n"
        "    KEEP(*(.stm32tk.abs.08000000))\n"
        "  } > FLASH\n"
        "\n  .stm32tk.abs.20000000 0x20000000 (NOLOAD) :\n"
        "  {\n"
        "    KEEP(*(.stm32tk.abs.20000000))\n"
        "  } > RAM\n"
    )
    assert expected in text
    assert text.index("0x08000000 (NOLOAD)") < text.index("0x20000000 (NOLOAD)")


def test_fixed_section_duplicate_identical_entries_collapse(tmp_path):
    root = write_project(tmp_path / "proj")
    section = {
        "section": ".stm32tk.abs.08000000",
        "address": 0x08000000,
        "sourcePath": "Src/main.c",
        "line": 13,
        "symbol": "pinned_value",
    }
    write_report_bytes(
        root,
        json.dumps(report_payload([section, section, section])).encode("utf-8") + b"\n",
    )
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "linker/stm32tk.ld")
    assert entry.after_bytes.decode("utf-8").count(".stm32tk.abs.08000000") == 2  # name twice per placement


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        (b"not json", "json"),
        (b"\xff\xfe", "encoding"),
        (b'{"schemaVersion":1,"schemaVersion":2}', "json"),
        (json.dumps(report_payload([], schemaVersion=2)).encode(), "schemaVersion"),
        (json.dumps(report_payload([], planId="short")).encode(), "planId"),
        (json.dumps(report_payload([], gitHead="short")).encode(), "gitHead"),
        (json.dumps(report_payload(None)).encode(), "type"),
        (b"[]", "type"),
    ],
)
def test_fixed_section_report_structural_failures(tmp_path, content, rule):
    root = write_project(tmp_path / "proj")
    write_report_bytes(root, content + b"\n" if not content.endswith(b"\n") else content)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": rule}


def test_fixed_section_report_non_regular_file_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    path = root.joinpath(*REPORT_PATH.split("/"))
    path.mkdir(parents=True)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "regularFile"}


def test_fixed_section_oversized_report_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "FILE_LIMIT_BYTES", 1024)
    root = write_project(tmp_path / "proj")
    write_report_bytes(root, b"x" * 2048)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "size"}


def _bad_section(rule: str) -> dict:
    base = {
        "section": ".stm32tk.abs.08000000",
        "address": 0x08000000,
        "sourcePath": "Src/main.c",
        "line": 13,
        "symbol": "pinned_value",
    }
    return {
        "key": {**base, "extra": 1},
        "address": {**base, "address": "0x08000000"},
        "addressRange": {**base, "address": 0x100000000},
        "addressNegative": {**base, "address": -1},
        "section": {**base, "section": ".stm32tk.abs.08000001"},
        "source": {**base, "sourcePath": "Src/undeclared.c"},
        "line": {**base, "line": 0},
        "symbol": {**base, "symbol": "1bad"},
    }[rule]


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("key", "key"),
        ("address", "address"),
        ("addressRange", "address"),
        ("addressNegative", "address"),
        ("section", "section"),
        ("source", "source"),
        ("line", "line"),
        ("symbol", "symbol"),
    ],
)
def test_fixed_section_entry_failures(tmp_path, rule, expected):
    root = write_project(tmp_path / "proj")
    write_report_bytes(
        root, json.dumps(report_payload([_bad_section(rule)])).encode("utf-8") + b"\n"
    )
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": expected}


def test_fixed_section_entry_non_dict_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(root, json.dumps(report_payload([1])).encode("utf-8") + b"\n")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "type"}


def test_fixed_section_conflicts_are_rejected(tmp_path):
    first = {
        "section": ".stm32tk.abs.08000000",
        "address": 0x08000000,
        "sourcePath": "Src/main.c",
        "line": 13,
        "symbol": "pinned_value",
    }
    same_address_other_symbol = {
        **first,
        "symbol": "other",
    }
    same_symbol_other_address = {
        **first,
        "address": 0x20000000,
        "section": ".stm32tk.abs.20000000",
    }
    for variant in (same_address_other_symbol, same_symbol_other_address):
        root = write_project(tmp_path / "proj")
        write_report_bytes(
            root, json.dumps(report_payload([first, variant])).encode("utf-8") + b"\n"
        )
        with pytest.raises(GenerationError) as error:
            plan_for(root)
        assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
        assert error.value.details == {"path": REPORT_PATH, "rule": "conflict"}


def test_fixed_section_out_of_region_address_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(
        root,
        json.dumps(
            report_payload(
                [
                    {
                        "section": ".stm32tk.abs.30000000",
                        "address": 0x30000000,
                        "sourcePath": "Src/main.c",
                        "line": 13,
                        "symbol": "pinned_value",
                    }
                ]
            )
        ).encode("utf-8")
        + b"\n",
    )
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "region"}


# ---------------------------------------------------------------------------
# managed manifest validation
# ---------------------------------------------------------------------------


def _valid_manifest_bytes(root: Path, extra_records=()) -> bytes:
    plan = plan_for(root)
    payload = json.loads(plan.managed_manifest_bytes.decode("utf-8"))
    payload["files"] = payload["files"] + list(extra_records)
    payload["files"].sort(key=lambda item: item["path"].encode("utf-8"))
    return json.dumps(payload, indent=2).encode("utf-8") + b"\n"


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        (b"not json", "json"),
        (b"\xff\xfe", "encoding"),
        (b"[]", "type"),
        (b"{}", "version"),
        (b'{"extra": 1}', "key"),
        (b'{"schemaVersion":2,"tool":"stm32-toolkit","toolVersion":"0.3.0","templateVersion":1,"projectManifestSha256":"' + b"a" * 64 + b'","files":[]}', "version"),
        (b'{"schemaVersion":1,"tool":"other","toolVersion":"0.3.0","templateVersion":1,"projectManifestSha256":"' + b"a" * 64 + b'","files":[]}', "tool"),
        (b'{"schemaVersion":1,"tool":"stm32-toolkit","toolVersion":"9.9.9","templateVersion":1,"projectManifestSha256":"' + b"a" * 64 + b'","files":[]}', "version"),
        (b'{"schemaVersion":1,"tool":"stm32-toolkit","toolVersion":"0.3.0","templateVersion":2,"projectManifestSha256":"' + b"a" * 64 + b'","files":[]}', "version"),
        (b'{"schemaVersion":1,"tool":"stm32-toolkit","toolVersion":"0.3.0","templateVersion":1,"projectManifestSha256":"zzz","files":[]}', "hash"),
        (b'{"schemaVersion":1,"tool":"stm32-toolkit","toolVersion":"0.3.0","templateVersion":1,"projectManifestSha256":"' + b"a" * 64 + b'","files":{}}', "type"),
        (b'{"schemaVersion":1,"tool":"stm32-toolkit","toolVersion":"0.3.0","templateVersion":1,"projectManifestSha256":"' + b"a" * 64 + b'","files":[1]}', "type"),
    ],
)
def test_malformed_prior_manifests_are_rejected(tmp_path, content, rule):
    root = write_project(tmp_path / "proj")
    write_manifest_bytes(root, content)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MANIFEST_INVALID"
    assert error.value.details == {"path": MANAGED_MANIFEST_PATH, "rule": rule}


def _manifest_with(records, **overrides):
    payload = {
        "schemaVersion": 1,
        "tool": "stm32-toolkit",
        "toolVersion": __version__,
        "templateVersion": 1,
        "projectManifestSha256": "a" * 64,
        "files": records,
    }
    payload.update(overrides)
    return json.dumps(payload, indent=2).encode("utf-8") + b"\n"


def test_manifest_bad_file_keys_and_ownership_and_hash(tmp_path):
    root = write_project(tmp_path / "proj")
    cases = [
        ([{"path": "x", "ownership": "managed", "templateVersion": 1}], "key"),
        ([{"path": "x", "ownership": "user", "templateVersion": 1, "sha256": "a" * 64}], "ownership"),
        ([{"path": "x", "ownership": "managed", "templateVersion": 1, "sha256": "zz"}], "hash"),
        ([{"path": "../x", "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64}], "path"),
        ([{"path": MANAGED_MANIFEST_PATH, "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64}], "path"),
        ([{"path": "a", "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64},
          {"path": "a", "ownership": "managed", "templateVersion": 1, "sha256": "b" * 64}], "duplicate"),
        ([{"path": "a", "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64},
          {"path": "A", "ownership": "managed", "templateVersion": 1, "sha256": "b" * 64}], "casefold"),
        ([{"path": "b", "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64},
          {"path": "a", "ownership": "managed", "templateVersion": 1, "sha256": "b" * 64}], "order"),
    ]
    for records, rule in cases:
        write_manifest_bytes(root, _manifest_with(records))
        with pytest.raises(GenerationError) as error:
            plan_for(root)
        assert error.value.code == "GENERATION_MANIFEST_INVALID"
        assert error.value.details == {"path": MANAGED_MANIFEST_PATH, "rule": rule}


def test_manifest_non_regular_file_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    path = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    path.mkdir(parents=True)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MANIFEST_INVALID"
    assert error.value.details == {"path": MANAGED_MANIFEST_PATH, "rule": "regularFile"}


# ---------------------------------------------------------------------------
# ownership classification: drift, collisions, orphans, upgrades
# ---------------------------------------------------------------------------


def test_apply_then_replan_is_all_unchanged(tmp_path):
    root = write_project(tmp_path / "proj")
    first = plan_for(root)
    result = apply_project_configuration(first)
    assert result.ok
    replan = plan_for(root)
    assert all(entry.status == "unchanged" for entry in replan.files)
    assert replan.blockers == ()
    again = plan_for(root)
    assert again.to_dict() == replan.to_dict()
    assert again.plan_id == replan.plan_id


def test_missing_managed_target_is_recreated(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    (root / "CMakeLists.txt").unlink()
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert entry.status == "update-managed"
    assert entry.before_bytes is None
    result = apply_project_configuration(plan)
    assert result.ok
    assert "CMakeLists.txt" in result.data["createdPaths"]
    assert (root / "CMakeLists.txt").read_bytes() == entry.after_bytes


def test_managed_template_upgrade_is_update_managed(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert entry.status == "update-managed"
    assert entry.before_sha256 != entry.after_sha256
    result = apply_project_configuration(plan)
    assert result.ok
    assert "CMakeLists.txt" in result.data["updatedPaths"]
    assert (root / "CMakeLists.txt").read_bytes().endswith(b"# upgraded template\n")


def test_user_drift_blocks_apply_without_writes(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    (root / "CMakeLists.txt").write_bytes(b"user edited\n")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    assert entry.status == "user-drift"
    blockers = [blocker for blocker in plan.blockers if blocker.code == "GENERATED_FILE_DRIFT"]
    assert [blocker.path for blocker in blockers] == ["CMakeLists.txt"]
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATED_FILE_DRIFT"
    assert result.details["paths"] == ("CMakeLists.txt",)
    assert (root / "CMakeLists.txt").read_bytes() == b"user edited\n"
    assert not staging_dir(root, plan.plan_id).exists()


def test_unowned_equal_collision_blocks_apply(tmp_path):
    root = write_project(tmp_path / "proj")
    proposal = plan_for(root)
    settings = next(entry for entry in proposal.files if entry.path == ".vscode/settings.json")
    (root / ".vscode").mkdir(exist_ok=True)
    (root / ".vscode/settings.json").write_bytes(settings.after_bytes)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/settings.json")
    assert entry.status == "unowned-collision"
    assert [blocker.code for blocker in plan.blockers] == ["UNOWNED_COLLISION"]
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_BLOCKED"
    assert result.details["codes"] == ("UNOWNED_COLLISION",)
    assert result.details["paths"] == (".vscode/settings.json",)
    assert (root / ".vscode/settings.json").read_bytes() == settings.after_bytes


def test_unowned_different_collision_blocks_apply(tmp_path):
    root = write_project(tmp_path / "proj")
    (root / ".vscode").mkdir(exist_ok=True)
    (root / ".vscode/settings.json").write_bytes(b"unrelated content\n")
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == ".vscode/settings.json")
    assert entry.status == "unowned-collision"
    result = apply_project_configuration(plan)
    assert result.code == "GENERATION_BLOCKED"
    assert (root / ".vscode/settings.json").read_bytes() == b"unrelated content\n"


def test_orphaned_prior_record_blocks_apply(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    write_manifest_bytes(root, _valid_manifest_bytes(root, [record("docs/notes.md", "c" * 64)]))
    plan = plan_for(root)
    assert [blocker.code for blocker in plan.blockers] == ["GENERATION_ORPHANED_MANAGED_FILE"]
    assert [blocker.path for blocker in plan.blockers] == ["docs/notes.md"]
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_BLOCKED"
    assert result.details["codes"] == ("GENERATION_ORPHANED_MANAGED_FILE",)
    assert result.details["paths"] == ("docs/notes.md",)
    assert not staging_dir(root, plan.plan_id).exists()


def test_blocker_aggregation_drift_takes_precedence(tmp_path):
    root = write_project(tmp_path / "proj")
    first = plan_for(root)
    assert apply_project_configuration(first).ok
    (root / "CMakeLists.txt").write_bytes(b"user edited\n")
    base = json.loads(first.managed_manifest_bytes.decode("utf-8"))
    base["files"] = [
        item
        for item in base["files"]
        if item["path"] != ".vscode/settings.json"
    ]
    base["files"].append(record("docs/notes.md", "c" * 64))
    base["files"].sort(key=lambda item: item["path"].encode("utf-8"))
    write_manifest_bytes(root, json.dumps(base, indent=2).encode("utf-8") + b"\n")
    plan = plan_for(root)
    codes = sorted(blocker.code for blocker in plan.blockers)
    assert codes == ["GENERATED_FILE_DRIFT", "GENERATION_ORPHANED_MANAGED_FILE", "UNOWNED_COLLISION"]
    paths = [blocker.path for blocker in plan.blockers]
    assert paths == sorted(paths)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATED_FILE_DRIFT"
    assert result.details["paths"] == ("CMakeLists.txt",)


def test_blocker_aggregation_collision_and_orphan(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    base = json.loads((root / ".stm32-toolkit/generated-files.json").read_text("utf-8"))
    base["files"] = [
        item for item in base["files"] if item["path"] != ".vscode/extensions.json"
    ]
    base["files"].append(record("docs/notes.md", "c" * 64))
    base["files"].sort(key=lambda item: item["path"].encode("utf-8"))
    write_manifest_bytes(root, json.dumps(base, indent=2).encode("utf-8") + b"\n")
    plan = plan_for(root)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_BLOCKED"
    assert result.details["codes"] == ("GENERATION_ORPHANED_MANAGED_FILE", "UNOWNED_COLLISION")
    assert result.details["paths"] == (".vscode/extensions.json", "docs/notes.md")


def test_changed_prior_manifest_blocks_apply(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    manifest_path = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    payload = json.loads(manifest_path.read_text("utf-8"))
    payload["files"][0]["sha256"] = "f" * 64
    manifest_path.write_bytes(json.dumps(payload, indent=2).encode("utf-8") + b"\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details["path"] == MANAGED_MANIFEST_PATH
    assert not staging_dir(root, plan.plan_id).exists()


def test_invalidated_prior_manifest_blocks_apply(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    write_manifest_bytes(root, b"{broken json")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details["path"] == MANAGED_MANIFEST_PATH


def test_plan_blockers_are_sorted_and_plan_is_still_deterministic(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    (root / "CMakeLists.txt").write_bytes(b"edited\n")
    first = plan_for(root)
    second = plan_for(root)
    assert first.to_dict() == second.to_dict()
    assert first.blockers == second.blockers


# ---------------------------------------------------------------------------
# apply success, atomicity, and no-op behavior
# ---------------------------------------------------------------------------


def test_apply_success_exact_paths_bytes_and_manifest(tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)
    result = apply_project_configuration(plan)
    assert result.ok
    assert result.operation == "project-configuration-apply"
    assert result.code == "OK"
    data = result.data
    assert data["planId"] == plan.plan_id
    assert data["modelSha256"] == plan.model_sha256
    assert data["templateVersion"] == 1
    assert data["managedManifestPath"] == MANAGED_MANIFEST_PATH
    assert data["managedManifestSha256"] == sha256(plan.managed_manifest_bytes)
    assert data["createdPaths"] == tuple(
        sorted([MANAGED_MANIFEST_PATH, *TARGETS], key=lambda path: path.encode("utf-8"))
    )
    assert data["updatedPaths"] == ()
    assert data["unchangedPaths"] == ()
    for entry in plan.files:
        path = root.joinpath(*entry.path.split("/"))
        assert path.read_bytes() == entry.after_bytes
        assert sha256(path.read_bytes()) == entry.after_sha256
    manifest_path = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    assert manifest_path.read_bytes() == plan.managed_manifest_bytes
    parsed = parse_managed_manifest(plan.managed_manifest_bytes)
    assert [item.path for item in parsed] == [entry.path for entry in plan.files]
    after = tree_snapshot(root)
    assert set(after) - set(before) == {
        ".stm32-toolkit",
        ".stm32-toolkit/generated-files.json",
        ".vscode",
        *[f".vscode/{name}" for name in ("c_cpp_properties.json", "extensions.json", "launch.json", "settings.json", "tasks.json")],
        "CMakeLists.txt",
        "CMakePresets.json",
        "cmake",
        "cmake/arm-none-eabi-gcc.cmake",
        "linker",
        "linker/stm32tk.ld",
    }
    for name in before:
        assert after[name] == before[name]
    assert not staging_dir(root, plan.plan_id).exists()
    assert not root.joinpath(*STAGING_ROOT.split("/")).exists()


def test_apply_second_run_is_a_noop(tmp_path):
    root = write_project(tmp_path / "proj")
    first = plan_for(root)
    assert apply_project_configuration(first).ok
    replan = plan_for(root)
    mtimes = {
        entry.path: os.lstat(root.joinpath(*entry.path.split("/"))).st_mtime_ns
        for entry in replan.files
    }
    mtimes[MANAGED_MANIFEST_PATH] = os.lstat(
        root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    ).st_mtime_ns
    result = apply_project_configuration(replan)
    assert result.ok
    assert result.data["createdPaths"] == ()
    assert result.data["updatedPaths"] == ()
    assert result.data["unchangedPaths"] == tuple(TARGETS)
    for path, mtime in mtimes.items():
        assert os.lstat(root.joinpath(*path.split("/"))).st_mtime_ns == mtime
    assert not root.joinpath(*STAGING_ROOT.split("/")).exists()


def test_apply_preserves_replacement_mode(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    cmake = root / "CMakeLists.txt"
    os.chmod(cmake, 0o640)
    mode_before = stat.S_IMODE(os.lstat(cmake).st_mode)
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    result = apply_project_configuration(plan)
    assert result.ok
    # Windows chmod only maps the read-only bit, so compare the actual
    # pre-apply mode instead of an absolute POSIX value.
    assert stat.S_IMODE(os.lstat(cmake).st_mode) == mode_before
    linker = root / "linker/stm32tk.ld"
    linker_mode_before = stat.S_IMODE(os.lstat(linker).st_mode)
    assert stat.S_IMODE(os.lstat(linker).st_mode) == linker_mode_before


def test_apply_manifest_updates_with_upgrade(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    result = apply_project_configuration(plan)
    assert result.ok
    assert MANAGED_MANIFEST_PATH in result.data["updatedPaths"]
    assert "CMakeLists.txt" in result.data["updatedPaths"]
    on_disk = manifest_on_disk(root)
    assert on_disk["files"] == json.loads(plan.managed_manifest_bytes.decode("utf-8"))["files"]


def test_apply_changed_model_is_rejected_before_writes(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    payload = standard_payload()
    payload["build"]["defines"] = ["CHANGED"]
    write_project(root, payload)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": ".stm32-project.json"}
    assert not (root / "CMakeLists.txt").exists()
    assert not (root / ".stm32-toolkit").exists()


def test_apply_changed_input_is_rejected_before_writes(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / "Src/main.c").write_bytes(b"changed\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "Src/main.c"}
    assert not (root / "CMakeLists.txt").exists()
    assert not (root / ".stm32-toolkit").exists()


def test_apply_changed_target_after_plan_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    (root / "CMakeLists.txt").write_bytes(b"edited after planning\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "CMakeLists.txt"}
    assert (root / "CMakeLists.txt").read_bytes() == b"edited after planning\n"
    assert not staging_dir(root, plan.plan_id).exists()


def test_apply_missing_target_after_plan_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    (root / "CMakeLists.txt").unlink()
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "CMakeLists.txt"}


def test_apply_creation_race_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / "CMakeLists.txt").write_bytes(b"raced in\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_TARGET_EXISTS"
    assert result.details == {"path": "CMakeLists.txt"}
    assert (root / "CMakeLists.txt").read_bytes() == b"raced in\n"
    assert not (root / ".stm32-toolkit").exists()


def test_apply_staging_collision_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    staging = staging_dir(root, plan.plan_id)
    staging.mkdir(parents=True)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_TARGET_EXISTS"
    assert result.details == {"path": f"{STAGING_ROOT}/{plan.plan_id}"}
    assert not (root / "CMakeLists.txt").exists()


def test_apply_staging_root_escape_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    outside = tmp_path / "outside-staging"
    outside.mkdir()
    _redirect_path(monkeypatch, root / ".stm32-toolkit", outside, is_dir=True)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_PATH_INVALID"
    assert result.details == {"path": f"{STAGING_ROOT}/{plan.plan_id}", "rule": "withinProjectRoot"}
    assert not any(outside.iterdir())
    assert not (root / "CMakeLists.txt").exists()


def test_apply_staging_intermediate_escape_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    outside = tmp_path / "outside-staging"
    outside.mkdir()
    (root / ".stm32-toolkit").mkdir()
    _redirect_path(monkeypatch, root / ".stm32-toolkit" / "configuration-staging", outside, is_dir=True)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_PATH_INVALID"
    assert result.details == {"path": f"{STAGING_ROOT}/{plan.plan_id}", "rule": "withinProjectRoot"}
    assert not any(outside.iterdir())
    assert not (root / "CMakeLists.txt").exists()


def test_apply_target_escape_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    outside = tmp_path / "outside-target.txt"
    outside.write_bytes(b"outside content\n")
    (root / "linker").mkdir()
    _redirect_path(monkeypatch, root / "linker" / "stm32tk.ld", outside, is_dir=False)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_PATH_INVALID"
    assert result.details == {"path": "linker/stm32tk.ld", "rule": "withinProjectRoot"}
    assert outside.read_bytes() == b"outside content\n"


def test_apply_target_turned_directory_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    (root / "CMakeLists.txt").unlink()
    (root / "CMakeLists.txt").mkdir()
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "CMakeLists.txt"}
    assert (root / "CMakeLists.txt").is_dir()


def test_apply_invalid_manifest_appearing_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    write_manifest_bytes(root, b"{broken json")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": MANAGED_MANIFEST_PATH}
    assert not (root / "CMakeLists.txt").exists()


def test_apply_invalid_report_appearing_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    write_report_bytes(root, b"not json")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": REPORT_PATH}
    assert not (root / "CMakeLists.txt").exists()


def test_apply_valid_manifest_appearing_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    write_manifest_bytes(root, _manifest_with([]))
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": MANAGED_MANIFEST_PATH}


def test_apply_leaves_unrelated_files_and_project_manifest_untouched(tmp_path):
    root = write_project(tmp_path / "proj")
    (root / "user-notes.txt").write_bytes(b"user data\n")
    (root / "Src/user.c").write_bytes(b"int user_code(void) { return 0; }\n")
    before = tree_snapshot(root)
    plan = plan_for(root)
    assert apply_project_configuration(plan).ok
    after = tree_snapshot(root)
    for name, value in before.items():
        assert after[name] == value
    assert (root / ".stm32-project.json").read_bytes() == before[".stm32-project.json"][3]


# ---------------------------------------------------------------------------
# failure injection: staging, replace, fsync, rollback
# ---------------------------------------------------------------------------


def test_apply_stage_failure_leaves_no_partial_state(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)

    def failing_stage_write(path, data, mode):
        raise OSError("injected stage failure")

    monkeypatch.setattr(configure_mod, "_stage_write", failing_stage_write)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "stage"}
    assert tree_snapshot(root) == before
    assert not (root / ".stm32-toolkit").exists()


@pytest.mark.parametrize("position", [1, 3, 5, 8, 10])
def test_apply_replace_failure_at_every_position_rolls_back(monkeypatch, tmp_path, position):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)
    fail_replace_at(monkeypatch, {position})
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "replace"}
    assert tree_snapshot(root) == before
    assert not (root / ".stm32-toolkit").exists()


def test_apply_replace_failure_rolls_back_updated_files(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    entry = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    original = entry.before_bytes
    fail_replace_at(monkeypatch, {2})  # fail the manifest replace, after CMakeLists replaced
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "replace"}
    assert (root / "CMakeLists.txt").read_bytes() == original
    assert not staging_dir(root, plan.plan_id).exists()


def test_apply_fsync_failure_rolls_back(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)
    fail_fsync_at(monkeypatch, {1})
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "fsync"}
    assert tree_snapshot(root) == before
    assert not (root / ".stm32-toolkit").exists()


def test_apply_replace_failure_after_replace_rolls_back_exactly(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    cmake_before = next(
        entry for entry in plan.files if entry.path == "CMakeLists.txt"
    ).before_bytes
    fail_replace_at(monkeypatch, {1})  # fail the CMakeLists replace (first destination)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert (root / "CMakeLists.txt").read_bytes() == cmake_before
    assert manifest_on_disk(root) == json.loads(
        (root / ".stm32-toolkit/generated-files.json").read_text("utf-8")
    )
    assert not staging_dir(root, plan.plan_id).exists()


def test_apply_rollback_failure_retains_recoverable_staging(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    first_manifest_bytes = plan_for(root).managed_manifest_bytes
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    calls = fail_replace_at(monkeypatch, {2, 3})  # fail CMakeLists replace + manifest restore
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_ROLLBACK_FAILED"
    assert result.details == {"paths": (MANAGED_MANIFEST_PATH,)}
    assert len(calls) >= 3
    staging = staging_dir(root, plan.plan_id)
    assert staging.exists()
    backup = staging / "backup" / MANAGED_MANIFEST_PATH
    assert backup.read_bytes() == first_manifest_bytes


def test_apply_success_result_is_json_serializable(tmp_path):
    root = write_project(tmp_path / "proj")
    result = apply_project_configuration(plan_for(root))
    text = json.dumps(result.to_dict())
    assert str(root) not in text
    assert result.to_dict()["operation"] == "project-configuration-apply"


# ---------------------------------------------------------------------------
# forged-plan defense
# ---------------------------------------------------------------------------


def _apply_forged(root: Path, forged) -> dict:
    result = apply_project_configuration(forged)
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    return result.details


def test_forged_plan_wrong_type_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    result = apply_project_configuration({"plan_id": "x"})  # type: ignore[arg-type]
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    assert result.details == {"rule": "type"}


def test_forged_plan_version_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert _apply_forged(root, replace(plan, plan_version=2)) == {"rule": "planVersion"}


def test_forged_plan_id_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert _apply_forged(root, replace(plan, plan_id="0" * 64)) == {"rule": "planId"}


def test_forged_model_sha256_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        model_sha256="0" * 64,
        managed_manifest_bytes=build_managed_manifest_bytes(plan.files, "0" * 64),
    )
    assert _apply_forged(root, forged) == {"rule": "modelSha256"}


def test_forged_manifest_path_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert _apply_forged(root, replace(plan, managed_manifest_path="other.json")) == {
        "rule": "manifestPath"
    }


def test_forged_file_status_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, status="unchanged") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "fileDigest"}


def test_forged_file_path_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, path="Other.txt") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "targetPath"}


def test_forged_template_name_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, template_name="vscode/other.j2")
            if entry.path == "CMakeLists.txt"
            else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "templateName"}


def test_forged_template_version_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, template_version=2) if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "templateVersion"}


def test_forged_after_bytes_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, after_bytes=b"tampered") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "fileDigest"}


def test_forged_digest_consistent_plan_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    tampered = b"digest consistent tampering\n"
    forged_files = tuple(
        replace(
            entry,
            after_bytes=tampered,
            after_sha256=sha256(tampered),
            after_size=len(tampered),
            unified_diff="",
        )
        if entry.path == "CMakeLists.txt"
        else entry
        for entry in plan.files
    )
    forged = replace(
        plan,
        files=forged_files,
        managed_manifest_bytes=build_managed_manifest_bytes(
            forged_files, plan.model_sha256
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "planId"}
    assert not (root / "CMakeLists.txt").exists()


def test_forged_before_digest_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, before_sha256="0" * 64) if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "fileDigest"}


def test_forged_unified_diff_is_rejected_by_fresh_replan(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        files=tuple(
            replace(entry, unified_diff="fake diff") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "freshPlan"}
    assert not (root / "CMakeLists.txt").exists()


def test_forged_input_digest_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(
        plan,
        inputs=tuple(
            replace(entry, sha256="zz") if entry.path == "Src/main.c" else entry
            for entry in plan.inputs
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "digestFormat"}
    digest_consistent = replace(
        plan,
        inputs=tuple(
            replace(entry, sha256="0" * 64) if entry.path == "Src/main.c" else entry
            for entry in plan.inputs
        ),
    )
    assert _apply_forged(root, digest_consistent) == {"rule": "planId"}


def test_forged_input_order_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(plan, inputs=tuple(reversed(plan.inputs)))
    assert _apply_forged(root, forged) == {"rule": "sortedOrder"}


def test_forged_duplicate_file_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(plan, files=plan.files + (plan.files[0],))
    assert _apply_forged(root, forged) == {"rule": "uniquePath"}


def test_forged_casefold_input_collision_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    extra = GenerationInput("SRC/main.c", plan.inputs[0].sha256, plan.inputs[0].size)
    forged = replace(plan, inputs=tuple(sorted(plan.inputs + (extra,), key=lambda e: e.path)))
    assert _apply_forged(root, forged) == {"rule": "casefoldCollision"}


def test_forged_manifest_bytes_are_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(plan, managed_manifest_bytes=b"tampered manifest")
    assert _apply_forged(root, forged) == {"rule": "manifestBytes"}


def test_forged_blocker_addition_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    fake = GenerationBlocker("GENERATED_FILE_DRIFT", "CMakeLists.txt", "forged")
    forged = replace(plan, blockers=(fake,))
    assert _apply_forged(root, forged) == {"rule": "planId"}


def test_forged_model_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    forged = replace(plan, model=replace(plan.model, schema_version=1))
    assert _apply_forged(root, forged) == {"rule": "modelSha256"}


def test_forged_huge_input_limit_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    huge = replace(
        plan,
        inputs=(
            GenerationInput(".stm32-project.json", "a" * 64, 64 * 1024 * 1024 + 1),
        ),
    )
    assert _apply_forged(root, huge) == {"rule": "inputLimit"}


# ---------------------------------------------------------------------------
# read-only planning and determinism
# ---------------------------------------------------------------------------


def test_planning_is_read_only(tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)
    plan_again = plan_for(root)
    assert plan.to_dict() == plan_again.to_dict()
    assert tree_snapshot(root) == before
    assert not (root / ".stm32-toolkit").exists()


def test_planning_with_blockers_is_still_read_only(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    (root / "CMakeLists.txt").write_bytes(b"edited\n")
    before = tree_snapshot(root)
    plan = plan_for(root)
    assert plan.blockers
    assert tree_snapshot(root) == before


def test_planning_after_apply_is_read_only(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    before = tree_snapshot(root)
    plan = plan_for(root)
    assert all(entry.status == "unchanged" for entry in plan.files)
    assert tree_snapshot(root) == before


def test_operation_result_failures_never_leak_host_paths(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / "Src/main.c").write_bytes(b"changed\n")
    result = apply_project_configuration(plan)
    text = json.dumps(result.to_dict())
    assert str(root) not in text
    assert "Traceback" not in text
    assert "OSError" not in text
    assert "Exception" not in text


# ---------------------------------------------------------------------------
# additional defensive branches
# ---------------------------------------------------------------------------


def test_plan_target_escape_is_path_invalid(monkeypatch, tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    outside = tmp_path / "outside-target.txt"
    outside.write_bytes(b"outside\n")
    _redirect_path(monkeypatch, root / "CMakeLists.txt", outside, is_dir=False)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_PATH_INVALID"
    assert error.value.details == {"path": "CMakeLists.txt", "rule": "withinProjectRoot"}
    assert outside.read_bytes() == b"outside\n"


def test_plan_target_directory_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    (root / "CMakeLists.txt").mkdir()
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "CMakeLists.txt", "rule": "regularFile"}


def test_plan_oversized_current_target_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "FILE_LIMIT_BYTES", 2048)
    root = write_project(tmp_path / "proj")
    (root / ".vscode").mkdir()
    (root / ".vscode/settings.json").write_bytes(b"x" * 3000)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": ".vscode/settings.json", "rule": "size"}


def test_plan_unreadable_input_is_rejected(monkeypatch, tmp_path):
    payload = standard_payload()
    payload["build"]["sources"] = ["Src/main.c"]
    root = write_project(tmp_path / "proj", payload)
    real_read = configure_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "main.c":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(configure_mod, "_read_limited", selective)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "unreadable"}


def test_plan_unreadable_report_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(root, b"{}")
    real_read = configure_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "conversion-report.json":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(configure_mod, "_read_limited", selective)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "unreadable"}


def test_plan_unreadable_prior_manifest_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    write_manifest_bytes(root, _manifest_with([]))
    real_read = configure_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "generated-files.json":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(configure_mod, "_read_limited", selective)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MANIFEST_INVALID"
    assert error.value.details == {"path": MANAGED_MANIFEST_PATH, "rule": "unreadable"}


def test_apply_unloadable_model_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / ".stm32-project.json").write_bytes(b"{broken")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": ".stm32-project.json"}


def test_apply_unreadable_input_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    real_read = configure_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "main.c":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(configure_mod, "_read_limited", selective)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "Src/main.c"}
    assert not (root / "CMakeLists.txt").exists()


def test_apply_replace_phase_creation_race_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    real_resolve = configure_mod._resolve_apply_target
    hits: dict[str, int] = {}

    def racing_resolve(path_root, path, code):
        text = path
        if Path(path).name == "CMakeLists.txt":
            count = hits.get(text, 0) + 1
            hits[text] = count
            if count >= 2:  # replace-phase revalidation call
                path_root.joinpath(*path.split("/")).write_bytes(b"raced during replace\n")
        return real_resolve(path_root, path, code)

    monkeypatch.setattr(configure_mod, "_resolve_apply_target", racing_resolve)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_TARGET_EXISTS"
    assert result.details == {"path": "CMakeLists.txt"}
    assert sum(hits.values()) >= 2
    assert (root / "CMakeLists.txt").read_bytes() == b"raced during replace\n"
    assert not (root / ".stm32-toolkit").exists()


def test_apply_replace_phase_semantic_failure_rollback_failure_retains_staging(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    first_manifest = plan_for(root).managed_manifest_bytes
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    real_resolve = configure_mod._resolve_apply_target
    hits: dict[str, int] = {}

    def selective(path_root, path, code):
        text = path
        if Path(path).name == "CMakeLists.txt":
            count = hits.get(text, 0) + 1
            hits[text] = count
            if count >= 2:  # replace-phase revalidation call
                path_root.joinpath(*path.split("/")).write_bytes(b"raced bytes\n")
        return real_resolve(path_root, path, code)

    monkeypatch.setattr(configure_mod, "_resolve_apply_target", selective)
    original_replace = os.replace

    def failing_replace(source, destination):
        if "backup" in str(source):
            raise OSError("injected rollback restore failure")
        return original_replace(source, destination)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.replace", failing_replace)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_ROLLBACK_FAILED"
    assert result.details == {"paths": (MANAGED_MANIFEST_PATH,)}
    assert sum(hits.values()) >= 2
    staging = staging_dir(root, plan.plan_id)
    assert staging.exists()
    backup = staging / "backup" / MANAGED_MANIFEST_PATH
    assert backup.read_bytes() == first_manifest


def test_apply_remove_staging_failure_rolls_back(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)

    def failing_remove(staging):
        raise OSError("injected staging removal failure")

    monkeypatch.setattr(configure_mod, "_remove_staging", failing_remove)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "stage"}
    after = tree_snapshot(root)
    for name, value in before.items():
        assert after[name] == value
    assert (root / ".stm32-toolkit").exists()


def test_apply_rollback_temp_unlink_failure(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    original = os.unlink

    def failing_unlink(path, *args, **kwargs):
        if ".stm32tk-tmp" in str(path):
            raise OSError("injected unlink failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.unlink", failing_unlink)
    fail_replace_at(monkeypatch, {1})
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_ROLLBACK_FAILED"
    assert result.details["paths"]
    assert staging_dir(root, plan.plan_id).exists()


def test_apply_rollback_created_file_unlink_failure(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    original = os.unlink

    def failing_unlink(path, *args, **kwargs):
        if ".stm32tk-tmp" not in str(path):
            raise OSError("injected unlink failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.unlink", failing_unlink)
    fail_replace_at(monkeypatch, {5})
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_ROLLBACK_FAILED"
    assert len(result.details["paths"]) == 4
    assert staging_dir(root, plan.plan_id).exists()


def test_forged_plan_container_types_are_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    assert _apply_forged(root, replace(plan, inputs=list(plan.inputs))) == {"rule": "type"}
    assert _apply_forged(root, replace(plan, files=list(plan.files))) == {"rule": "type"}
    assert _apply_forged(root, replace(plan, blockers=list(plan.blockers))) == {"rule": "type"}
    assert _apply_forged(root, replace(plan, managed_manifest_bytes="bytes")) == {"rule": "type"}


def test_forged_file_scalar_types_are_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    cmake = next(entry for entry in plan.files if entry.path == "CMakeLists.txt")
    forged = replace(
        plan,
        files=tuple(
            replace(entry, unified_diff=123) if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "type"}
    forged = replace(
        plan,
        files=tuple(
            replace(entry, before_bytes="nope") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "type"}
    forged = replace(
        plan,
        files=tuple(
            replace(entry, status="weird") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "status"}
    forged = replace(
        plan,
        files=tuple(
            replace(entry, path="../evil") if entry.path == "CMakeLists.txt" else entry
            for entry in plan.files
        ),
    )
    assert _apply_forged(root, forged) == {"rule": "portablePath"}


def test_forged_blocker_values_are_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    bad_code = (GenerationBlocker("BAD_CODE", "CMakeLists.txt", "x"),)
    assert _apply_forged(root, replace(plan, blockers=bad_code)) == {"rule": "blockerCode"}
    bad_path = (GenerationBlocker("GENERATED_FILE_DRIFT", "../x", "x"),)
    assert _apply_forged(root, replace(plan, blockers=bad_path)) == {"rule": "portablePath"}
    unsorted = (
        GenerationBlocker("UNOWNED_COLLISION", "CMakeLists.txt", "x"),
        GenerationBlocker("UNOWNED_COLLISION", ".vscode/settings.json", "x"),
    )
    assert _apply_forged(root, replace(plan, blockers=unsorted)) == {"rule": "sortedOrder"}


def test_forged_manifest_and_plan_limits_are_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    monkeypatch.setattr(configure_mod, "TOTAL_LIMIT_BYTES", 10)
    assert _apply_forged(root, plan) == {"rule": "manifestLimit"}
    monkeypatch.undo()
    monkeypatch.setattr(configure_mod, "PLAN_LIMIT_BYTES", 10)
    assert _apply_forged(root, plan) == {"rule": "planLimit"}


def test_apply_blocker_free_second_apply_has_empty_destinations(tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    plan = plan_for(root)
    result = apply_project_configuration(plan)
    assert result.ok
    assert result.data["updatedPaths"] == ()
    assert result.data["createdPaths"] == ()


# ---------------------------------------------------------------------------
# remaining defensive branches (inspection failures, races, fsync edges)
# ---------------------------------------------------------------------------


def test_aggregate_generated_and_manifest_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_mod, "TOTAL_LIMIT_BYTES", 2500)
    root = write_project(tmp_path / "proj")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_TEMPLATE_INVALID"
    assert error.value.details == {"template": "$", "rule": "aggregateLimit"}


def test_nul_project_root_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(replace(model, project_root=Path("x\x00y")))
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "directory"}


def test_resolve_failure_is_rejected_conservatively(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")

    def broken_resolve(self, strict=False):
        raise RuntimeError("resolution loop")

    monkeypatch.setattr(Path, "resolve", broken_resolve)
    with pytest.raises(GenerationError) as error:
        configure_mod._resolve_contained(root / "Src/main.c", root, "Src/main.c")
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "withinProjectRoot"}


def test_report_lstat_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    write_report_bytes(root, b"{}")
    real_lstat = os.lstat
    hits: dict[str, int] = {}

    def selective(path, *args, **kwargs):
        if Path(path).name == "conversion-report.json":
            hits["report"] = hits.get("report", 0) + 1
            raise OSError("injected lstat failure")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", selective)
    with pytest.raises(GenerationError) as error:
        configure_mod._read_conversion_report(root)
    assert error.value.code == "GENERATION_FIXED_SECTION_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "regularFile"}
    assert sum(hits.values()) >= 1


def test_collect_inputs_rejects_non_portable_model_path(tmp_path):
    from stm32_toolkit.project_model import BuildSpec

    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    forged_build = replace(
        model.build,
        sources=("C:/outside.c",),
        assembly_sources=(),
        include_paths=(),
    )
    forged = replace(model, build=forged_build)
    with pytest.raises(GenerationError) as error:
        configure_mod._collect_inputs(root, forged, None, None)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "C:/outside.c", "rule": "withinProjectRoot"}


def test_include_lstat_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)
    real_lstat = os.lstat
    hits: dict[str, int] = {}

    def selective(path, *args, **kwargs):
        if Path(path).name == "Inc":
            hits["inc"] = hits.get("inc", 0) + 1
            raise OSError("injected lstat failure")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", selective)
    with pytest.raises(GenerationError) as error:
        configure_mod._collect_inputs(root, model, None, None)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "Inc", "rule": "directory"}
    assert sum(hits.values()) >= 1


def test_current_target_lstat_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    real_lstat = os.lstat
    hits: dict[str, int] = {}

    def selective(path, *args, **kwargs):
        if Path(path).name == "CMakeLists.txt":
            hits["cmake"] = hits.get("cmake", 0) + 1
            raise OSError("injected lstat failure")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", selective)
    with pytest.raises(GenerationError) as error:
        configure_mod._read_current_target(root, "CMakeLists.txt")
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": "CMakeLists.txt", "rule": "unreadable"}
    assert sum(hits.values()) >= 1


def test_plan_unreadable_current_target_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    (root / ".vscode").mkdir()
    settings = root / ".vscode/settings.json"
    settings.write_bytes(b"unreadable target\n")
    real_read = configure_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "settings.json":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(configure_mod, "_read_limited", selective)
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": ".vscode/settings.json", "rule": "unreadable"}


def test_apply_input_inspection_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    real_lstat = os.lstat
    counts: dict[str, int] = {}

    def selective(path, *args, **kwargs):
        if Path(path).parts[-2:] == ("Src", "app.c"):
            key = "/".join(Path(path).parts[-2:])
            count = counts.get(key, 0) + 1
            counts[key] = count
            if count >= 2:
                raise OSError("injected lstat failure")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", selective)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "Src/app.c"}
    assert sum(counts.values()) >= 2
    assert not (root / "CMakeLists.txt").exists()


def test_apply_replace_phase_non_regular_race(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    real_resolve = configure_mod._resolve_apply_target
    hits: dict[str, int] = {}

    def selective(path_root, path, code):
        text = path
        if Path(path).name == "CMakeLists.txt":
            count = hits.get(text, 0) + 1
            hits[text] = count
            if count >= 2:  # replace-phase revalidation call
                target = path_root.joinpath(*path.split("/"))
                target.unlink()
                target.mkdir()
        return real_resolve(path_root, path, code)

    monkeypatch.setattr(configure_mod, "_resolve_apply_target", selective)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "CMakeLists.txt"}
    assert sum(hits.values()) >= 2
    assert (root / "CMakeLists.txt").is_dir()
    assert not staging_dir(root, plan.plan_id).exists()


def test_apply_replace_phase_bytes_race(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    first_manifest = plan_for(root).managed_manifest_bytes
    assert apply_project_configuration(plan_for(root)).ok
    upgrade_cmake_template(monkeypatch)
    plan = plan_for(root)
    real_resolve = configure_mod._resolve_apply_target
    hits: dict[str, int] = {}

    def selective(path_root, path, code):
        text = path
        if Path(path).name == "CMakeLists.txt":
            count = hits.get(text, 0) + 1
            hits[text] = count
            if count >= 2:  # replace-phase revalidation call
                path_root.joinpath(*path.split("/")).write_bytes(b"raced bytes\n")
        return real_resolve(path_root, path, code)

    monkeypatch.setattr(configure_mod, "_resolve_apply_target", selective)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert result.details == {"path": "CMakeLists.txt"}
    assert sum(hits.values()) >= 2
    assert (root / "CMakeLists.txt").read_bytes() == b"raced bytes\n"
    assert (root / ".stm32-toolkit/generated-files.json").read_bytes() == first_manifest
    assert not staging_dir(root, plan.plan_id).exists()


def test_apply_staging_path_is_a_file_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / ".stm32-toolkit").mkdir()
    (root / ".stm32-toolkit" / "configuration-staging").write_bytes(b"file in the way\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_TARGET_EXISTS"
    assert result.details == {"path": "configuration-staging"}
    assert not (root / "CMakeLists.txt").exists()
    assert (root / ".stm32-toolkit" / "configuration-staging").read_bytes() == b"file in the way\n"


def test_apply_staging_toolkit_component_is_file_is_rejected(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    (root / ".stm32-toolkit").write_bytes(b"file blocks the directory\n")
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_TARGET_EXISTS"
    assert result.details == {"path": ".stm32-toolkit"}
    assert not (root / "CMakeLists.txt").exists()
    assert (root / ".stm32-toolkit").read_bytes() == b"file blocks the directory\n"


def test_apply_staging_lstat_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    real_lstat = os.lstat
    hits: dict[str, int] = {}

    def selective(path, *args, **kwargs):
        if Path(path).name == plan.plan_id:
            hits["staging"] = hits.get("staging", 0) + 1
            raise OSError("injected lstat failure")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.lstat", selective)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_PATH_INVALID"
    assert result.details == {"path": f"{STAGING_ROOT}/{plan.plan_id}", "rule": "withinProjectRoot"}
    assert sum(hits.values()) >= 1


def test_apply_real_fsync_error_converts_to_fsync_phase(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    before = tree_snapshot(root)
    plan = plan_for(root)

    def failing_fsync(fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.fsync", failing_fsync)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details == {"phase": "fsync"}
    assert tree_snapshot(root) == before
    assert not (root / ".stm32-toolkit").exists()


def test_apply_directory_fsync_open_failure_is_ignored(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    real_open = os.open

    def selective_open(path, flags, *args, **kwargs):
        if flags & os.O_RDONLY and not flags & os.O_CREAT:
            raise OSError("injected dir open failure")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("stm32_toolkit.generation.configure.os.open", selective_open)
    result = apply_project_configuration(plan)
    assert result.ok
    assert (root / "CMakeLists.txt").exists()


def test_apply_keeps_foreign_staging_content(tmp_path):
    root = write_project(tmp_path / "proj")
    plan = plan_for(root)
    staging_root = root.joinpath(*STAGING_ROOT.split("/"))
    staging_root.mkdir(parents=True)
    foreign = staging_root / "foreign-plan"
    foreign.mkdir()
    result = apply_project_configuration(plan)
    assert result.ok
    assert foreign.exists()
    assert not staging_dir(root, plan.plan_id).exists()


def test_report_escape_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    outside = tmp_path / "outside-report"
    outside.mkdir()
    _redirect_path(monkeypatch, root / "artifacts", outside, is_dir=True)
    with pytest.raises(GenerationError) as error:
        configure_mod._read_conversion_report(root)
    assert error.value.code == "GENERATION_INPUT_INVALID"
    assert error.value.details == {"path": REPORT_PATH, "rule": "withinProjectRoot"}
    assert not any(outside.iterdir())


def test_manifest_under_file_is_treated_absent(tmp_path):
    root = write_project(tmp_path / "proj")
    (root / ".stm32-toolkit").write_bytes(b"file blocks the directory\n")
    plan = plan_for(root)
    assert not any(entry.path == MANAGED_MANIFEST_PATH for entry in plan.inputs)
    assert all(entry.status == "create" for entry in plan.files)


def test_report_under_file_is_treated_absent(tmp_path):
    root = write_project(tmp_path / "proj")
    (root / "artifacts").write_bytes(b"file blocks the directory\n")
    plan = plan_for(root)
    assert not any(entry.path == REPORT_PATH for entry in plan.inputs)


def test_model_root_resolve_failure_is_rejected(monkeypatch, tmp_path):
    root = write_project(tmp_path / "proj")
    model = load_project_model(root)

    def broken_resolve(self, strict=False):
        raise OSError("resolution unavailable")

    monkeypatch.setattr(Path, "resolve", broken_resolve)
    with pytest.raises(GenerationError) as error:
        plan_project_configuration(model)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "projectRoot", "rule": "directory"}
