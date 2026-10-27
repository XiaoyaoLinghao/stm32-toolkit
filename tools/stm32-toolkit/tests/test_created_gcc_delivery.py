"""Offline new-project GCC development journey with a synthetic vendor boundary.

Scope and honesty boundary
--------------------------
The *only* synthetic part of this journey is the external STM32CubeMX
generation/environment fact set: this host has no offline Cube firmware
package, so the test injects ``discover_creation_environment`` (exactly that
one seam) and supplies a clearly labelled :class:`_SyntheticCubeMXAdapter`
that copies the tracked, sanitized ``cubemx-6.18/native-f429`` fixture into
the authorized staging child and reshapes only that temporary copy into a
minimal real Cortex-M4 GCC image.  This is **not** vendor-generation evidence
and must never be reported as a real CubeMX PASS.

Everything downstream of that boundary is genuine and unmocked:

* the public ``CreationPlanWorkflowRequest`` plan/prepare/apply path with its
  real one-time authorization store,
* the real native-output parser, manifest writer, ownership seeding and
  managed configuration apply,
* real ARM GNU GCC / CMake / Ninja debug and release builds through the
  normal Toolkit build workflow, with fresh content identities and no Git,
* relocation of the delivered output to an independent root and a real
  ``clean`` rebuild there,
* the normal public ``flash_workflow`` with its default implementation,
  real lease/supervisor/client/receipt path and only the documented
  in-memory backend seam (``run_managed_flash``); simulated memory starts
  empty and is populated from the ELF that is actually programmed.

No original project, tracked fixture, installed source, hardware, network,
installation or remote Git is touched.  Tools are required: a missing local
verified GNU/CMake/Ninja toolchain fails the test instead of skipping.
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.creation_workflows as creation_workflows
from stm32_toolkit.build.model import SOURCE_BASELINE_INPUT_SNAPSHOT
from stm32_toolkit.creation_authorization import CreationAuthorizationStore
from stm32_toolkit.creation_workflows import (
    CreationPlanWorkflowRequest,
    apply_creation_workflow,
    plan_creation_workflow,
    prepare_creation_workflow,
)
from stm32_toolkit.tool_support import ToolFact, ToolSupportProfile
from stm32_toolkit.workflows import build_firmware_workflow, configure_project_workflow

from gcc_delivery_integration_helpers import (
    SIM_LOG_ENV,
    SIM_MODE_ENV,
    apply_toolchain_path,
    assert_no_git_metadata,
    copy_output_only,
    elf_entry_and_symbols,
    event_names,
    pt_load_segments,
    run_managed_flash,
    sha256_bytes,
    tree_inventory,
)
from test_cubemx_project import _real_native_environment

FIXTURE = Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429"

MCU = "STM32F429ZITx"
DESTINATION = "generated"
SESSION = "creation1"
DEBUG_TARGET = "stm32f429zitx"
STACK_POINTER = 0x20030000
FLASH_VECTOR_ADDRESS = 0x08000000

#: Minimal CubeMX-style generated source list.  Only the source lists change;
#: every other fixture file (vendor/library/license content) is preserved.
GENERATED_CMAKE = """\
cmake_minimum_required(VERSION 3.22)
enable_language(C ASM)
set(MX_Defines_Syms
    USE_HAL_DRIVER
    STM32F429xx
    $<$<CONFIG:Debug>:DEBUG>
)
set(MX_Include_Dirs
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/STM32F4xx_HAL_Driver/Inc
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/STM32F4xx_HAL_Driver/Inc/Legacy
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/CMSIS/Device/ST/STM32F4xx/Include
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Drivers/CMSIS/Include
)
set(MX_Application_Src
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Src/startup_min.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../../Core/Src/main.c
)
set(STM32_Drivers_Src)
set(MX_LINK_DIRS)
set(MX_LINK_LIBS STM32_Drivers ${TOOLCHAIN_LINK_LIBRARIES})
add_library(stm32cubemx INTERFACE)
target_include_directories(stm32cubemx INTERFACE ${MX_Include_Dirs})
target_compile_definitions(stm32cubemx INTERFACE ${MX_Defines_Syms})
add_library(STM32_Drivers OBJECT)
target_sources(STM32_Drivers PRIVATE ${STM32_Drivers_Src})
target_link_libraries(STM32_Drivers PUBLIC stm32cubemx)
target_sources(${CMAKE_PROJECT_NAME} PRIVATE ${MX_Application_Src})
target_link_libraries(${CMAKE_PROJECT_NAME} ${MX_LINK_LIBS})
"""

#: Real GNU ld script: internal-Flash vector/text load plus RAM .data/.bss.
LINKER_SCRIPT = """\
ENTRY(Reset_Handler)

MEMORY
{
  RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 192K
  CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = 64K
  FLASH (rx) : ORIGIN = 0x8000000, LENGTH = 2048K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);
__stack = _estack;
_stack = _estack;
__StackTop = _estack;

SECTIONS
{
  .isr_vector :
  {
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  } > FLASH

  .text :
  {
    . = ALIGN(4);
    *(.text*)
    *(.rodata*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)
    KEEP(*(.init))
    KEEP(*(.fini))
    . = ALIGN(4);
    _etext = .;
    __etext = .;
  } > FLASH

  .ARM.extab :
  {
    *(.ARM.extab* .gnu.linkonce.armextab.*)
  } > FLASH

  .ARM.exidx :
  {
    __exidx_start = .;
    *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    __exidx_end = .;
  } > FLASH

  .preinit_array :
  {
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > FLASH

  .init_array :
  {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > FLASH

  .fini_array :
  {
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*)))
    KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > FLASH

  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    __data_start__ = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
    __data_end__ = .;
  } > RAM AT> FLASH

  _sidata = LOADADDR(.data);
  __data_load_start__ = LOADADDR(.data);
  __data_load_start = LOADADDR(.data);

  .bss (NOLOAD) :
  {
    . = ALIGN(4);
    _sbss = .;
    __bss_start__ = .;
    __bss_start = .;
    _bss_start = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = .;
    __bss_end = .;
    _bss_end = .;
  } > RAM

  end = .;
  _end = .;
}
"""

STARTUP_C = """\
/* Minimal real Cortex-M4 startup and vector table for this synthetic copy. */
typedef void (*vector_fn)(void);

extern int main(void);
extern unsigned int _sidata;
extern unsigned int _sdata;
extern unsigned int _edata;
extern unsigned int _sbss;
extern unsigned int _ebss;

void Reset_Handler(void);

__attribute__((section(".isr_vector"), used))
static vector_fn const g_vectors[16] = {
    (vector_fn)0x20030000u,
    Reset_Handler,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
    (vector_fn)0,
};

void Reset_Handler(void)
{
    unsigned int *source = &_sidata;
    unsigned int *target = &_sdata;
    while (target < &_edata)
    {
        *target++ = *source++;
    }
    for (target = &_sbss; target < &_ebss; ++target)
    {
        *target = 0u;
    }
    (void)main();
    for (;;)
    {
    }
}
"""

MAIN_C = """\
/* Minimal application: one initialized word in .data, one buffer in .bss. */
volatile unsigned int g_accumulator = 1u;
volatile unsigned int g_samples[4];

int main(void)
{
    for (;;)
    {
        g_samples[0] = g_accumulator;
    }
}
"""


def _shape_minimal_cortex_m4_image(child: Path) -> None:
    """Reshape only the temporary native copy into a minimal valid image."""

    (child / "cmake" / "stm32cubemx" / "CMakeLists.txt").write_text(
        GENERATED_CMAKE, encoding="utf-8", newline="\n"
    )
    (child / "Core" / "Src" / "main.c").write_text(
        MAIN_C, encoding="utf-8", newline="\n"
    )
    (child / "Core" / "Src" / "startup_min.c").write_text(
        STARTUP_C, encoding="utf-8", newline="\n"
    )
    (child / "STM32F429xx_FLASH.ld").write_text(
        LINKER_SCRIPT, encoding="utf-8", newline="\n"
    )


class _SyntheticCubeMXAdapter:
    """SYNTHETIC offline generation seam -- never vendor-generation evidence.

    It copies the tracked sanitized CubeMX fixture into the apply-owned child
    directory named after the authorized destination leaf and reshapes only
    that temporary copy's project source/startup/linker into a minimal real
    Cortex-M4 GCC image.  It is used once; the adapter invocation count is
    asserted by the journey.
    """

    def __init__(self, fixture: Path) -> None:
        self._fixture = fixture
        self.calls = 0

    def generate(self, capability, staging):
        self.calls += 1
        leaf = capability.request.destination.replace("\\", "/").split("/")[-1]
        child = staging.staging_dir / leaf
        assert not child.exists()
        shutil.copytree(self._fixture, child)
        _shape_minimal_cortex_m4_image(child)
        return SimpleNamespace(invocations=1, project_root=child)


def _tool_fact(name: str, path: str) -> ToolFact:
    executable = Path(path).resolve()
    return ToolFact(
        name,
        executable,
        "unknown",
        "explicit",
        sha256_bytes(executable.read_bytes()),
    )


def _support_profile(tmp_path: Path, gcc: str, cmake: str, ninja: str) -> ToolSupportProfile:
    # Synthetic external CubeMX fact is local-fixture-only; compiler tools are
    # the real verified executables whose paths/hashes enter the profile.
    synthetic_cubemx = tmp_path / "synthetic-cubemx" / "STM32CubeMX.stub.exe"
    synthetic_cubemx.parent.mkdir(parents=True, exist_ok=True)
    synthetic_cubemx.write_bytes(b"synthetic-cubemx-contract-fact\n")
    return ToolSupportProfile(
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ToolFact(
            "cubeMx",
            synthetic_cubemx.resolve(),
            "synthetic",
            "explicit",
            sha256_bytes(synthetic_cubemx.read_bytes()),
        ),
        Path(gcc).resolve().parents[2],
        _tool_fact("gcc", gcc),
        _tool_fact("cmake", cmake),
        _tool_fact("ninja", ninja),
        None,
        (),
        (),
    )


def test_offline_creation_journey_reaches_independent_gcc_build_and_managed_flash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    gcc, cmake, ninja = apply_toolchain_path(monkeypatch)
    support = _support_profile(tmp_path, gcc, cmake, ninja)
    environment = _real_native_environment()
    monkeypatch.setattr(
        creation_workflows,
        "discover_creation_environment",
        lambda *args, **kwargs: environment,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_root = tmp_path / "data"
    request = CreationPlanWorkflowRequest(
        workspace, data_root, SESSION, "mcu", MCU, DESTINATION, "hal", "c"
    )
    destination = workspace / DESTINATION
    store = CreationAuthorizationStore(data_root)
    before = tree_inventory(workspace)
    fixture_before = tree_inventory(FIXTURE)

    planned = plan_creation_workflow(request, support_profile=support)
    assert planned.ok is True, planned.to_dict()
    assert planned.data["mutated"] is False
    assert not planned.data["blockers"]
    prepared = prepare_creation_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        support_profile=support,
        store=store,
    )
    assert prepared.ok is True, prepared.to_dict()
    assert prepared.data["mutated"] is False
    assert prepared.data["authorizationDigest"]
    # PLAN/PREPARE never create the destination and never touch the workspace.
    assert not destination.exists()
    assert tree_inventory(workspace) == before
    record = store.authorization_root / f"{prepared.data['authorizationDigest']}.json"
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "prepared"
    assert_no_git_metadata(workspace)

    adapter = _SyntheticCubeMXAdapter(FIXTURE)
    applied = apply_creation_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        store=store,
        adapter=adapter,
        environment=environment,
        support_profile=support,
    )
    assert applied.ok is True, applied.to_dict()
    assert applied.data["mutated"] is True
    assert adapter.calls == 1
    assert destination.is_dir()
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "consumed"
    assert not list(workspace.glob(".stm32tk-*"))
    assert not any(path.name.endswith(".script") for path in destination.rglob("*"))
    assert_no_git_metadata(workspace, destination)
    # The adapter copied the tracked fixture and reshaped only that disposable
    # copy: the tracked fixture input inventory is byte-identical afterwards.
    assert tree_inventory(FIXTURE) == fixture_before

    # Genuine debug and release builds ran inside apply before activation, and
    # the ownership manifest is the real literal CubeMX ownership record.
    assert applied.data["debug"]["ok"] is True
    assert applied.data["release"]["ok"] is True
    ownership_rel = applied.data["ownershipManifestPath"]
    assert ownership_rel == ".stm32-toolkit/cubemx-ownership.json"
    ownership_path = destination.joinpath(*ownership_rel.split("/"))
    assert sha256_bytes(ownership_path.read_bytes()) == applied.data["ownershipManifestSha256"]
    for preset in ("arm-debug", "arm-release"):
        assert (destination / "build" / preset / "STM32F429ZITx.elf").is_file()
        identity_path = destination / "build" / preset / "firmware-identity.json"
        staged_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        assert staged_identity["schemaVersion"] == 2
        assert staged_identity["gitHead"] is None
        assert staged_identity["gitDirty"] is None

    # Explicit supported debug configuration through the normal PLAN/APPLY.
    # The activated project still carries the generation-time build caches,
    # whose CMake cache records the pre-activation source directory; those
    # moved caches are deliberately not reused.  The supported fresh path is
    # the output-only copy below, rebuilt clean in an independent root.
    config_plan = configure_project_workflow(
        destination, authorized=False, debug_backend="pyocd", debug_target=DEBUG_TARGET
    )
    assert config_plan.ok is True, config_plan.to_dict()
    configured = configure_project_workflow(
        destination,
        plan_id=config_plan.data["plan_id"],
        authorized=True,
        debug_backend="pyocd",
        debug_target=DEBUG_TARGET,
    )
    assert configured.ok is True, configured.to_dict()
    manifest = json.loads((destination / ".stm32-project.json").read_text(encoding="utf-8"))
    assert manifest["debug"] == {"backend": "pyocd", "target": DEBUG_TARGET}

    # Independent relocated output: no carried build cache, real clean rebuild.
    relocated = copy_output_only(tmp_path, destination, tmp_path / "relocated")
    assert not (relocated / "build").exists()
    assert_no_git_metadata(relocated)

    # Independence also means the original delivered path must not exist while
    # the relocated copy is rebuilt, so the build cannot silently reuse the
    # pre-activation cache or fall back to the original tree.  The delivered
    # workspace is a disposable test-owned tree: it is renamed reversibly here
    # and restored below -- never deleted or modified -- so every later
    # "no reference to the original" check still compares the real old
    # workspace/destination paths.  Nothing about the build is caught or
    # downgraded: if the normal ``clean`` build cannot stand on its own, this
    # test fails.
    parked_workspace = tmp_path / "workspace-parked"
    assert not parked_workspace.exists()
    workspace.rename(parked_workspace)
    try:
        assert not workspace.exists()
        assert not destination.exists()
        rebuilt = build_firmware_workflow(
            relocated, preset="arm-debug", clean=True, authorized=True
        )
    finally:
        parked_workspace.rename(workspace)
    assert workspace.is_dir()
    assert rebuilt.ok is True, rebuilt.to_dict()
    relocated_identity = json.loads(
        (relocated / "build" / "arm-debug" / "firmware-identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert relocated_identity["schemaVersion"] == 2
    assert relocated_identity["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert relocated_identity["gitHead"] is None
    assert relocated_identity["gitDirty"] is None
    assert relocated_identity["gitEvidence"]["status"] == "unavailable"
    result_doc = json.loads(
        (relocated / "artifacts" / "migration" / "build-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result_doc["schemaVersion"] == 2
    assert result_doc["status"] == "success"

    # Declared build inputs stay portable and independent of the original
    # workspace/staging boundary.
    relocated_manifest = json.loads(
        (relocated / ".stm32-project.json").read_text(encoding="utf-8")
    )
    declared = list(relocated_manifest["build"]["sources"])
    declared += list(relocated_manifest["build"]["assemblySources"])
    declared += list(relocated_manifest["build"]["includePaths"])
    declared.append(relocated_manifest["build"]["elf"])
    declared.append(relocated_manifest["generation"]["nativeLinkerScript"])
    forbidden = (str(destination), str(workspace), ".stm32tk-")
    for value in declared:
        assert value
        assert "\\" not in value
        assert not value.startswith("/")
        for marker in forbidden:
            assert marker not in value
        assert (relocated.joinpath(*value.split("/"))).resolve().is_relative_to(
            relocated.resolve()
        )
    for generated in ("CMakeLists.txt", "CMakePresets.json"):
        text = (relocated / generated).read_text(encoding="utf-8")
        assert str(destination) not in text
        assert ".stm32tk-" not in text

    # The CMake cache proves the real verified compiler was used.
    cache = (relocated / "build" / "arm-debug" / "CMakeCache.txt").read_text(
        encoding="utf-8"
    )
    compiler_line = next(
        line for line in cache.splitlines() if line.startswith("CMAKE_C_COMPILER:")
    )
    compiler = Path(compiler_line.split("=", 1)[1].strip()).resolve()
    assert compiler.is_file()
    assert compiler == Path(gcc).resolve()
    assert str(destination) not in cache
    assert str(workspace) not in cache

    # Real ELF: entry is the reset handler and the first PT_LOAD begins with
    # the live vector table at the internal-Flash origin.
    elf_path = relocated.joinpath(*relocated_identity["elfPath"].split("/"))
    elf_bytes = elf_path.read_bytes()
    entry, symbols = elf_entry_and_symbols(elf_bytes)
    assert entry == symbols["Reset_Handler"]
    assert entry & 1 == 1
    assert relocated_identity["entryPoint"] == entry
    assert relocated_identity["vectorAddress"] == FLASH_VECTOR_ADDRESS
    assert relocated_identity["resetHandlerAddress"] == entry
    assert relocated_identity["elfSha256"] == sha256_bytes(elf_bytes)
    segments = pt_load_segments(elf_bytes)
    assert segments
    assert segments[0][0] == FLASH_VECTOR_ADDRESS
    stored_stack, stored_reset = struct.unpack("<II", segments[0][1][:8])
    assert stored_stack == STACK_POINTER
    assert stored_reset == entry

    # Normal managed flash through the public workflow and the real
    # lease/supervisor/client/receipt path; only the backend is a test seam.
    monkeypatch.setenv(SIM_MODE_ENV, "ok")
    monkeypatch.setenv(SIM_LOG_ENV, str(tmp_path / "probe-events.jsonl"))

    denied = run_managed_flash(
        relocated,
        data_root,
        SESSION,
        build_id=relocated_identity["buildId"],
        elf_sha256=relocated_identity["elfSha256"],
        authorized=False,
    )
    assert denied.result.ok is False
    assert denied.result.code == "AUTHORIZATION_REQUIRED"
    assert event_names(list(denied.events)) == []

    main_source = relocated / "Core" / "Src" / "main.c"
    original_source = main_source.read_bytes()
    main_source.write_bytes(original_source + b"\n/* changed declared input */\n")
    try:
        changed = run_managed_flash(
            relocated,
            data_root,
            SESSION,
            build_id=relocated_identity["buildId"],
            elf_sha256=relocated_identity["elfSha256"],
            authorized=True,
        )
        assert changed.result.ok is False
        assert changed.result.code == "FIRMWARE_INPUT_CHANGED"
        changed_names = event_names(list(changed.events))
        assert "flash_elf" not in changed_names
        assert "program_segment" not in changed_names
    finally:
        main_source.write_bytes(original_source)

    flashed = run_managed_flash(
        relocated,
        data_root,
        SESSION,
        build_id=relocated_identity["buildId"],
        elf_sha256=relocated_identity["elfSha256"],
        authorized=True,
    )
    assert flashed.result.ok is True, flashed.result.to_dict()
    names = event_names(list(flashed.events))
    assert names.count("flash_elf") == 1
    assert "flash_imported_elf" not in names
    assert "flash_file" not in names
    programmed = [
        (event["address"], event["length"])
        for event in flashed.events
        if event["event"] == "program_segment"
    ]
    assert programmed == [(address, len(payload)) for address, payload in segments]
    total_payload = sum(len(payload) for _, payload in segments)
    read_back = sum(
        event["bytes"] for event in flashed.events if event["event"] == "read_memory"
    )
    assert read_back >= total_payload
    assert flashed.result.data.verified_bytes == total_payload

    receipt_path = relocated / "artifacts" / "migration" / "flash-result.json"
    assert flashed.receipt_path == receipt_path
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schemaVersion"] == 2
    assert receipt["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert receipt["buildId"] == relocated_identity["buildId"]
    assert receipt["inputSnapshotSha256"] == relocated_identity["inputSnapshotSha256"]
    assert receipt["elfSha256"] == sha256_bytes(elf_bytes)
    assert receipt["gitHead"] is None
    assert receipt["gitDirty"] is None
    assert receipt["verifiedBytes"] == total_payload
    assert "importId" not in receipt
    assert receipt["operationLevel"] == "modify"
    assert receipt["authorized"] is True
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "consumed"
