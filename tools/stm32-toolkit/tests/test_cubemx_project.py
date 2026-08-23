from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.cubemx_project import (
    CubeMXNativeProjectError,
    NativeProjectModel,
    parse_native_project,
    write_native_project_manifests,
)
from stm32_toolkit.generation.creation import CreationRequest


def _native_tree(tmp_path: Path) -> Path:
    root = tmp_path / "staging"
    (root / "Core" / "Src").mkdir(parents=True)
    (root / "Core" / "Inc").mkdir(parents=True)
    (root / "Drivers" / "CMSIS").mkdir(parents=True)
    (root / "startup_stm32f429xx.s").write_text("", encoding="utf-8")
    (root / "Core" / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (root / "Core" / "Inc" / "main.h").write_text("#define APP 1\n", encoding="utf-8")
    (root / "STM32F429.ioc").write_text("Mcu.Name=STM32F429ZITx\nProjectManager.FirmwarePackage=STM32Cube_FW_F4\nProjectManager.Language=C\n", encoding="utf-8")
    (root / "CMakeLists.txt").write_text(
        """cmake_minimum_required(VERSION 3.22)\nproject(app C ASM)\n"
        "set(CMAKE_SYSTEM_PROCESSOR cortex-m4)\n"
        "set(APP_SOURCES Core/Src/main.c startup_stm32f429xx.s)\n"
        "target_include_directories(app PRIVATE Core/Inc Drivers/CMSIS)\n"
        "target_compile_definitions(app PRIVATE USE_HAL_DRIVER STM32F429xx)\n"
        "target_compile_options(app PRIVATE -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)\n"
        "set(LINKER_SCRIPT ${CMAKE_SOURCE_DIR}/STM32F429ZITx_FLASH.ld)\n""",
        encoding="utf-8",
    )
    (root / "STM32F429ZITx_FLASH.ld").write_text(
        "MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 2048K RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 256K }\n",
        encoding="utf-8",
    )
    return root


def _environment() -> SimpleNamespace:
    return SimpleNamespace(
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="1" * 64,
        package_name="STM32Cube_FW_F4",
        package_version="1.0.0",
        package_sha256="2" * 64,
        digest="3" * 64,
    )


def test_native_parser_extracts_closed_cmake_facts_and_deterministic_uuid(tmp_path: Path):
    root = _native_tree(tmp_path)
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    first = parse_native_project(root, request=request, plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    second = parse_native_project(root, request=request, plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    assert isinstance(first, NativeProjectModel)
    assert first.logical_project_id == second.logical_project_id
    assert first.target_device == "STM32F429ZITx"
    assert "Core/Src/main.c" in first.sources
    assert "Core/Inc" in first.include_paths
    assert "USE_HAL_DRIVER" in first.defines
    assert first.linker_script == "STM32F429ZITx_FLASH.ld"


def test_native_parser_rejects_unsafe_cmake_reference(tmp_path: Path):
    root = _native_tree(tmp_path)
    (root / "CMakeLists.txt").write_text("add_custom_command(COMMAND powershell -c whoami)\n", encoding="utf-8")
    with pytest.raises(CubeMXNativeProjectError) as error:
        parse_native_project(root, request=CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"), plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    assert error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"


def test_native_parser_bounds_files_and_rejects_escape(tmp_path: Path):
    root = _native_tree(tmp_path)
    (root / "CMakeLists.txt").write_text("set(APP_SOURCES ../outside.c)\n", encoding="utf-8")
    with pytest.raises(CubeMXNativeProjectError) as error:
        parse_native_project(root, request=CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"), plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    assert error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"


def test_ownership_manifest_contains_only_portable_hashes_and_bindings(tmp_path: Path):
    root = _native_tree(tmp_path)
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    model = parse_native_project(root, request=request, plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    path = write_native_project_manifests(root, model)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["planId"] == "a" * 64
    assert all(not Path(item["path"]).is_absolute() for item in payload["files"])
    assert all("\\" not in item["path"] for item in payload["files"])
    assert (root / ".stm32-project.json").is_file()
