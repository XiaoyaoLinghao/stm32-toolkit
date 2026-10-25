"""STARTUP-GCC manifest, model and generated linker contract tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import stm32_toolkit.generation.configure as configure_mod
from stm32_toolkit.generation import GenerationError, plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import StartupOptions, apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.project_model import ProjectManifestError, load_project_model

from startup_gcc_fixture import GENERATED_SOURCE, STARTUP_SOURCE, startup_repo
from test_generation import EXPECTED_LINKER, plan_for, standard_payload, write_project

REPO_ROOT = Path(__file__).resolve().parents[3]
UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"


def v3_payload(**overrides):
    payload = {
        "schemaVersion": 3,
        "logicalProjectId": UUID,
        "generatedBy": {"tool": "stm32-toolkit", "version": "1.3.1"},
        "project": {"name": "firmware", "origin": "keil-migration"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["Src/main.c"],
            "includePaths": ["Inc"],
            "defines": ["USE_STDPERIPH_DRIVER"],
            "compileOptions": [],
            "assemblySources": [GENERATED_SOURCE],
            "presets": ["arm-debug", "arm-release"],
            "elf": "build/arm-debug/firmware.elf",
        },
        "memory": {
            "source": "keil",
            "regions": [
                {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
                {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
            ],
            "stackSize": 4096,
            "heapSize": 1024,
        },
        "debug": {},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
            "runtimeInitialization": "cmsis-gcc-v1",
        },
    }
    payload.update(overrides)
    return payload


def linker_bytes(plan) -> bytes:
    return next(file for file in plan.files if file.path == "linker/stm32tk.ld").after_bytes


def test_absent_optional_fields_keep_the_default_linker_bytes_exactly(tmp_path):
    root = write_project(tmp_path / "default", standard_payload())
    generated = linker_bytes(plan_for(root))
    assert generated == EXPECTED_LINKER.encode("utf-8")
    text = generated.decode("utf-8")
    assert ".preinit_array" not in text
    assert ".init_array" not in text
    assert "__initial_sp = __StackTop;" not in text
    assert "ASSERT((" not in text
    assert "  .data :\n  {\n    _sdata = .;" in text
    assert "  .bss :\n  {\n    _sbss = .;" in text


def test_runtime_contract_emits_exact_sizes_constructor_sections_and_aliases(tmp_path):
    root = write_project(tmp_path / "runtime", v3_payload())
    plan = plan_for(root)
    text = linker_bytes(plan).decode("utf-8")

    assert "_Min_Heap_Size = 0x400;" in text
    assert "_Min_Stack_Size = 0x1000;" in text
    assert "_Min_Heap_Size = 4K;" not in text
    assert "_Min_Stack_Size = 1K;" not in text
    for section in (".preinit_array", ".init_array", ".fini_array"):
        assert section in text
    assert "PROVIDE_HIDDEN(__init_array_start = .);" in text
    assert "PROVIDE_HIDDEN(__init_array_end = .);" in text
    assert "KEEP(*(SORT(.init_array.*)))" in text
    assert "__initial_sp = __StackTop;" in text
    assert "__heap_base = __HeapBase;" in text
    assert "__heap_limit = __HeapLimit;" in text

    # The generated startup copies/zeroes whole words, so the runtime contract
    # must align both ends of .data/.bss and the .data load address.
    assert "  .data :\n  {\n    . = ALIGN(4);\n    _sdata = .;" in text
    assert "  .bss :\n  {\n    . = ALIGN(4);\n    _sbss = .;" in text
    for symbol in ("_sidata", "_sdata", "_edata", "_sbss", "_ebss"):
        assert f"ASSERT(({symbol} & 3) == 0" in text
    # Endpoint alignment alone is insufficient: an unaligned RAM origin makes
    # ld pad the start of .data, so LOADADDR(.data) would no longer match
    # _sdata.  The runtime contract refuses that layout instead of copying it.
    assert 'ASSERT(ADDR(.data) == _sdata, "cmsis-gcc-v1 requires the .data copy source to start at _sdata")' in text
    assert 'ASSERT(SIZEOF(.data) == _edata - _sdata, "cmsis-gcc-v1 requires the .data copy size to match _sdata.._edata")' in text


def test_zero_heap_is_rendered_as_an_exact_zero_byte_reservation(tmp_path):
    payload = v3_payload()
    payload["memory"]["heapSize"] = 0
    root = write_project(tmp_path / "zero-heap", payload)
    text = linker_bytes(plan_for(root)).decode("utf-8")
    assert "_Min_Heap_Size = 0x0;" in text
    assert "_Min_Stack_Size = 0x1000;" in text


def test_sizes_without_runtime_contract_still_use_exact_values(tmp_path):
    payload = v3_payload()
    payload["generation"].pop("runtimeInitialization")
    root = write_project(tmp_path / "sizes-only", payload)
    text = linker_bytes(plan_for(root)).decode("utf-8")
    assert "_Min_Heap_Size = 0x400;" in text
    assert "_Min_Stack_Size = 0x1000;" in text
    assert ".init_array" not in text


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda p: p["memory"].__setitem__("stackSize", 0), "memory.stackSize"),
        (lambda p: p["memory"].__setitem__("stackSize", 1001), "memory.stackSize"),
        (lambda p: p["memory"].__setitem__("stackSize", "4096"), "memory.stackSize"),
        (lambda p: p["memory"].__setitem__("stackSize", True), "memory.stackSize"),
        (lambda p: p["memory"].__setitem__("stackSize", 0x100000000), "memory.stackSize"),
        (lambda p: p["memory"].__setitem__("heapSize", -8), "memory.heapSize"),
        (lambda p: p["memory"].__setitem__("heapSize", 1023), "memory.heapSize"),
        (
            lambda p: p["generation"].__setitem__("runtimeInitialization", "other"),
            "generation.runtimeInitialization",
        ),
    ],
)
def test_schema_rejects_unsafe_optional_values(tmp_path, mutation, field):
    payload = v3_payload()
    mutation(payload)
    root = write_project(tmp_path / "invalid", payload)
    with pytest.raises(ProjectManifestError) as error:
        load_project_model(root)
    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details["field"] == field


def test_model_layer_repeats_size_validation(tmp_path):
    root = write_project(tmp_path / "model", v3_payload())
    model = load_project_model(root)
    bad = replace(model, memory=replace(model.memory, stack_size=1001))
    with pytest.raises(GenerationError) as error:
        configure_mod._validate_memory(bad)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {"field": "memory.stackSize", "rule": "size"}

    bad_heap = replace(model, memory=replace(model.memory, heap_size=-8))
    with pytest.raises(GenerationError) as error:
        configure_mod._validate_memory(bad_heap)
    assert error.value.details == {"field": "memory.heapSize", "rule": "size"}


def test_runtime_contract_is_never_silently_ignored_for_a_native_linker(tmp_path):
    payload = v3_payload()
    payload["generation"]["nativeLinkerScript"] = "linker/native.ld"
    root = write_project(tmp_path / "native", payload)
    (root / "linker").mkdir(parents=True, exist_ok=True)
    (root / "linker" / "native.ld").write_text("ENTRY(Reset_Handler)\n", encoding="utf-8")
    with pytest.raises(GenerationError) as error:
        plan_for(root)
    assert error.value.code == "GENERATION_MODEL_INVALID"
    assert error.value.details == {
        "field": "generation.runtimeInitialization",
        "rule": "managedLinker",
    }


def test_schema_copies_are_identical_and_contain_the_bounded_optional_fields():
    root_schema = REPO_ROOT / "schemas" / "stm32-project.schema.json"
    packaged_schema = (
        REPO_ROOT
        / "tools"
        / "stm32-toolkit"
        / "src"
        / "stm32_toolkit"
        / "schemas"
        / "stm32-project.schema.json"
    )
    assert root_schema.read_bytes() == packaged_schema.read_bytes()
    schema = json.loads(root_schema.read_text("utf-8"))
    assert schema["properties"]["memory"]["properties"]["stackSize"]["multipleOf"] == 8
    assert schema["properties"]["memory"]["properties"]["heapSize"]["minimum"] == 0
    assert schema["properties"]["generation"]["properties"]["runtimeInitialization"] == {
        "enum": ["cmsis-gcc-v1"]
    }


def test_migrated_project_configures_with_recorded_memory_and_generated_assembly(tmp_path):
    repo = startup_repo(tmp_path, name="configured")
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert apply_keil_conversion(plan).ok is True

    model = load_project_model(repo)
    assert model.memory.stack_size == 4096
    assert model.memory.heap_size == 1024
    assert model.generation.runtime_initialization == "cmsis-gcc-v1"
    assert model.build.assembly_sources == (GENERATED_SOURCE,)

    configuration = plan_project_configuration(model)
    assert configuration.blockers == ()
    cmake = next(file for file in configuration.files if file.path == "CMakeLists.txt")
    assert GENERATED_SOURCE.encode() in cmake.after_bytes
    linker = linker_bytes(configuration)
    assert b"_Min_Stack_Size = 0x1000;" in linker
    assert b"_Min_Heap_Size = 0x400;" in linker
    assert b".init_array" in linker
    # The generated startup is project input, not a managed generation target.
    managed = configuration.managed_manifest_bytes.decode("utf-8")
    assert GENERATED_SOURCE not in managed
