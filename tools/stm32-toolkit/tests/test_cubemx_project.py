from __future__ import annotations

import json
import shutil
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
from stm32_toolkit.generation.configure import plan_project_configuration
from stm32_toolkit.generation.managed_files import GENERATED_TARGETS
from stm32_toolkit.project_model import load_project_model


def _native_tree(tmp_path: Path) -> Path:
    return _fixture_tree(tmp_path, "global-f4")


def _environment() -> SimpleNamespace:
    return SimpleNamespace(
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="1" * 64,
        package_name="STM32Cube_FW_F4",
        package_version="1.0.0",
        package_sha256="2" * 64,
        digest="3" * 64,
    )


def _fixture_tree(tmp_path: Path, name: str) -> Path:
    source = Path(__file__).parent / "fixtures" / "cubemx-6.18" / name
    destination = tmp_path / name
    shutil.copytree(source, destination)
    return destination


def _fixture_environment(name: str) -> SimpleNamespace:
    package = "STM32Cube_FW_H7" if "h7" in name else "STM32Cube_FW_F4"
    return SimpleNamespace(
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="1" * 64,
        package_name=package,
        package_version="1.0.0",
        package_sha256="2" * 64,
        digest="3" * 64,
    )


def _fixture_request(name: str) -> CreationRequest:
    device = "STM32H743ZITx" if "h7" in name else "STM32F429ZITx"
    return CreationRequest.from_mcu(device, "generated", framework="hal", language="c")


def _seed_managed_manifest(root: Path) -> None:
    managed = root / ".stm32-toolkit" / "generated-files.json"
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "tool": "stm32-toolkit",
                "toolVersion": "0.5.0",
                "templateVersion": 1,
                "projectManifestSha256": "0" * 64,
                "files": [
                    {"path": path, "ownership": "managed", "templateVersion": 1, "sha256": "0" * 64}
                    for path in sorted(GENERATED_TARGETS)
                ],
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _nested_native_tree(tmp_path: Path, *, core: str, fpu: str, float_abi: str, name: str) -> Path:
    fixture = "global-h7" if core == "cortex-m7" else "global-f4"
    root = _fixture_tree(tmp_path, fixture)
    text = (root / "CMakeLists.txt").read_text(encoding="utf-8").replace(
        "GlobalH7" if fixture == "global-h7" else "GlobalF4", name
    )
    (root / "CMakeLists.txt").write_text(text, encoding="utf-8")
    return root


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
    model = parse_native_project(
        root,
        request=request,
        plan_id="a" * 64,
        action_digest="b" * 64,
        environment=_environment(),
    )
    path = write_native_project_manifests(root, model)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["planId"] == "a" * 64
    assert all(not Path(item["path"]).is_absolute() for item in payload["files"])
    assert all("\\" not in item["path"] for item in payload["files"])
    assert (root / ".stm32-project.json").is_file()


@pytest.mark.parametrize(
    "core,fpu,float_abi,name",
    [
        ("cortex-m4", "fpv4-sp-d16", "hard", "F4App"),
        ("cortex-m7", "fpv5-d16", "hard", "H7App"),
    ],
)
def test_native_parser_extracts_literal_nested_cubemx_cmake_and_toolchain_facts(
    tmp_path: Path, core: str, fpu: str, float_abi: str, name: str
):
    root = _nested_native_tree(tmp_path, core=core, fpu=fpu, float_abi=float_abi, name=name)
    request = CreationRequest.from_mcu("STM32H743ZITx" if core == "cortex-m7" else "STM32F429ZITx", "generated", framework="hal", language="c")
    model = parse_native_project(
        root,
        request=request,
        plan_id="a" * 64,
        action_digest="b" * 64,
        environment=_fixture_environment("global-h7" if core == "cortex-m7" else "global-f4"),
    )
    assert model.project_name == name
    assert model.core == core
    assert model.fpu == fpu
    assert model.float_abi == float_abi
    assert model.sources == ("Core/Src/main.c", "Drivers/Src/stm32_hal.c")
    assert model.include_paths == ("Core/Inc", "Drivers/CMSIS")
    assert model.linker_script.endswith("_FLASH.ld")
    write_native_project_manifests(root, model)
    manifest = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    assert manifest["target"]["fpu"] == fpu
    assert manifest["target"]["floatAbi"] == float_abi
    managed = root / ".stm32-toolkit" / "generated-files.json"
    managed.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "tool": "stm32-toolkit",
                "toolVersion": "0.5.0",
                "templateVersion": 1,
                "projectManifestSha256": "0" * 64,
                "files": [
                    {"path": path, "ownership": "managed", "templateVersion": 1, "sha256": "0" * 64}
                    for path in sorted(GENERATED_TARGETS)
                ],
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    configured = plan_project_configuration(load_project_model(root))
    assert configured.files
    assert configured.model.target.fpu == fpu


def test_native_parser_rejects_nested_template_without_toolchain_cpu_fpu_or_abi(tmp_path: Path):
    root = _nested_native_tree(tmp_path, core="cortex-m4", fpu="fpv4-sp-d16", float_abi="hard", name="Broken")
    toolchain = root / "cmake" / "gcc-arm-none-eabi.cmake"
    toolchain.write_text("set(CMAKE_SYSTEM_PROCESSOR cortex-m4)\n", encoding="utf-8")
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    with pytest.raises(CubeMXNativeProjectError) as error:
        parse_native_project(root, request=request, plan_id="a" * 64, action_digest="b" * 64, environment=_environment())
    assert error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "fixture,core,fpu,float_abi",
    [
        ("global-f4", "cortex-m4", "fpv4-sp-d16", "hard"),
        ("global-h7", "cortex-m7", "fpv5-d16", "hard"),
        ("context-f4", "cortex-m4", "fpv4-sp-d16", "hard"),
        ("context-h7", "cortex-m7", "fpv5-d16", "hard"),
    ],
)
def test_native_parser_accepts_literal_618_global_and_context_dialects(
    tmp_path: Path, fixture: str, core: str, fpu: str, float_abi: str
):
    root = _fixture_tree(tmp_path, fixture)
    model = parse_native_project(
        root,
        request=_fixture_request(fixture),
        plan_id="a" * 64,
        action_digest="b" * 64,
        environment=_fixture_environment(fixture),
    )
    assert model.core == core
    assert model.fpu == fpu
    assert model.float_abi == float_abi
    assert model.project_name in {"GlobalF4", "GlobalH7", "ContextF4", "ContextH7"}
    assert model.sources == ("Core/Src/main.c", "Drivers/Src/stm32_hal.c")
    assert model.include_paths == ("Core/Inc", "Drivers/CMSIS")
    assert model.linker_script.endswith("_FLASH.ld")


@pytest.mark.parametrize("fixture", ["global-f4", "context-h7"])
def test_native_parser_model_loads_and_plans_debug_release_from_618_fixture(tmp_path: Path, fixture: str):
    root = _fixture_tree(tmp_path, fixture)
    model = parse_native_project(
        root,
        request=_fixture_request(fixture),
        plan_id="a" * 64,
        action_digest="b" * 64,
        environment=_fixture_environment(fixture),
    )
    write_native_project_manifests(root, model)
    _seed_managed_manifest(root)
    loaded = load_project_model(root)
    debug = plan_project_configuration(loaded)
    release = plan_project_configuration(loaded)
    assert debug.files and release.files


def test_native_parser_rejects_missing_preset_or_mixed_cmake_dialects(tmp_path: Path):
    global_root = _fixture_tree(tmp_path, "global-f4")
    (global_root / "CMakePresets.json").unlink()
    with pytest.raises(CubeMXNativeProjectError) as missing:
        parse_native_project(
            global_root,
            request=_fixture_request("global-f4"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment=_fixture_environment("global-f4"),
        )
    assert missing.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"

    mixed_root = _fixture_tree(tmp_path, "context-h7")
    (mixed_root / "CMakeLists.txt").write_text(
        (mixed_root / "CMakeLists.txt").read_text(encoding="utf-8")
        + "\nadd_subdirectory(cmake/stm32cubemx)\n",
        encoding="utf-8",
    )
    with pytest.raises(CubeMXNativeProjectError) as mixed:
        parse_native_project(
            mixed_root,
            request=_fixture_request("context-h7"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment=_fixture_environment("context-h7"),
        )
    assert mixed.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"


def test_native_parser_rejects_project_name_or_include_contract_drift(tmp_path: Path):
    root = _fixture_tree(tmp_path, "global-f4")
    text = (root / "CMakeLists.txt").read_text(encoding="utf-8").replace("project(${CMAKE_PROJECT_NAME})", "project(GlobalF4)")
    (root / "CMakeLists.txt").write_text(text, encoding="utf-8")
    with pytest.raises(CubeMXNativeProjectError) as project_error:
        parse_native_project(
            root,
            request=_fixture_request("global-f4"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment=_fixture_environment("global-f4"),
        )
    assert project_error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"

    context = _fixture_tree(tmp_path, "context-f4")
    context_text = (context / "CMakeLists.txt").read_text(encoding="utf-8").replace(
        'include("mx-generated.cmake")', 'include("other.cmake")'
    )
    (context / "CMakeLists.txt").write_text(context_text, encoding="utf-8")
    with pytest.raises(CubeMXNativeProjectError) as include_error:
        parse_native_project(
            context,
            request=_fixture_request("context-f4"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment=_fixture_environment("context-f4"),
        )
    assert include_error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"
