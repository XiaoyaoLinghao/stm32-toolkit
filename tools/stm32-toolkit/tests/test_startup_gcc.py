"""STARTUP-GCC recognizer, option, plan, preflight and apply tests.

All projects are disposable synthetic Git repositories.  No vendor startup
source is copied; the fixture is authored for this grammar contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import stm32_toolkit.migration.startup as startup_mod
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    StartupOptions,
    apply_keil_conversion,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.migration.model import MigrationPlanError
from stm32_toolkit.workflows import convert_keil_workflow, preflight_keil_workflow

from startup_gcc_fixture import (
    GENERATED_SOURCE,
    MAIN_C,
    STARTUP_SOURCE,
    SYNTHETIC_STARTUP,
    TARGET,
    UVPROJX,
    cpu_setting,
    git_init,
    snapshot_tree,
    startup_repo,
    two_assembly_repo,
)
from test_migration_plan import build_repo


def parse(text: str, core: str = "Cortex-M4"):
    return startup_mod._Parser(
        STARTUP_SOURCE,
        startup_mod._logical_lines(text),
        startup_mod.normalize_startup_core(core),
    ).run()


def codes(parsed) -> set[str]:
    return {diagnostic.code for diagnostic in parsed.diagnostics}


def mutate(old: str, new: str, text: str = SYNTHETIC_STARTUP) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# whole-grammar acceptance
# ---------------------------------------------------------------------------


def test_synthetic_startup_is_fully_recognized_with_vectors_and_sizes():
    parsed = parse(SYNTHETIC_STARTUP)

    assert parsed.status == "ready"
    assert parsed.diagnostics == ()
    assert parsed.core == "cortex-m4"
    assert parsed.stack_size == 4096
    assert parsed.heap_size == 1024
    assert len(parsed.vectors) == 24
    assert parsed.reserved_count == 5
    assert parsed.vectors[0].symbol == "__initial_sp"
    assert parsed.vectors[1].symbol == "Reset_Handler"
    assert [entry.index for entry in parsed.vectors if entry.reserved] == [7, 8, 9, 10, 13]
    assert all(entry.reserved is False for entry in parsed.vectors if entry.index not in (7, 8, 9, 10, 13))

    kinds = {handler.name: handler.kind for handler in parsed.handlers}
    assert kinds["Reset_Handler"] == "reset"
    reset_handler = next(
        handler for handler in parsed.handlers if handler.name == "Reset_Handler"
    )
    assert reset_handler.line == (
        SYNTHETIC_STARTUP[: SYNTHETIC_STARTUP.index("Reset_Handler    PROC")].count("\n")
        + 1
    )
    for name in (
        "NMI_Handler",
        "HardFault_Handler",
        "MemManage_Handler",
        "BusFault_Handler",
        "UsageFault_Handler",
        "SVC_Handler",
        "DebugMon_Handler",
        "PendSV_Handler",
        "SysTick_Handler",
    ):
        assert kinds[name] == "individual"
    for name in (
        "ADC1_IRQHandler",
        "TIM2_IRQHandler",
        "USART1_IRQHandler",
        "EXTI0_IRQHandler",
        "DMA1_Stream0_IRQHandler",
        "SPI1_IRQHandler",
        "I2C1_EV_IRQHandler",
        "WWDG_IRQHandler",
    ):
        assert kinds[name] == "default-alias"


def test_physical_line_continuation_maps_to_the_starting_line():
    parsed = parse(SYNTHETIC_STARTUP)
    hard_fault = next(handler for handler in parsed.handlers if handler.name == "HardFault_Handler")
    expected_line = SYNTHETIC_STARTUP[: SYNTHETIC_STARTUP.index("HardFault_Handler\\")].count("\n") + 1
    assert hard_fault.line == expected_line
    assert hard_fault.kind == "individual"


def test_generated_startup_is_deterministic_and_preserves_the_vector_order():
    parsed = parse(SYNTHETIC_STARTUP)
    first = startup_mod.render_startup(
        source_path=STARTUP_SOURCE,
        source_sha256=hashlib.sha256(SYNTHETIC_STARTUP.encode()).hexdigest(),
        parsed=parsed,
    )
    second = startup_mod.render_startup(
        source_path=STARTUP_SOURCE,
        source_sha256=hashlib.sha256(SYNTHETIC_STARTUP.encode()).hexdigest(),
        parsed=parsed,
    )
    text = first.decode("utf-8")

    assert first == second
    assert text.endswith("\n")
    assert "  .cpu cortex-m4\n" in text
    assert text.count("  .word 0\n") == 5
    assert "  .word __initial_sp\n  .word Reset_Handler\n  .word NMI_Handler\n" in text
    assert "  .weak WWDG_IRQHandler\n  .thumb_set WWDG_IRQHandler, Default_Handler\n" in text
    assert "  bl SystemInit\n" in text
    assert "  ldr r0, =_sidata\n" in text
    assert "  ldr r1, =_sbss\n" in text
    assert "  bl __libc_init_array\n" in text
    assert "  bl main\n" in text
    assert "Reset_Handler:\n" in text
    assert "  .weak _init\n" in text
    assert "  .weak _fini\n" in text
    assert "  .word __Vectors_End" not in text
    # Vector table boundary comes after all 24 preserved words.
    vector_section = text.split("__Vectors:", 1)[1].split("__Vectors_End:", 1)[0]
    assert vector_section.count(".word ") == 24


def test_rendered_source_metadata_cannot_escape_the_assembly_comment():
    """Pure synthetic input: no unsafe host filename is ever created."""
    parsed = parse(SYNTHETIC_STARTUP)
    hostile_paths = (
        "Startup/evil*/handler.s",
        "Startup/line\nbreak.s",
        "Startup/tab\tname.s",
        "Startup/back\\slash.s",
    )
    for hostile in hostile_paths:
        rendered = startup_mod.render_startup(
            source_path=hostile,
            source_sha256=hashlib.sha256(SYNTHETIC_STARTUP.encode()).hexdigest(),
            parsed=parsed,
        ).decode("utf-8")
        source_lines = [
            line for line in rendered.splitlines() if line.startswith("/* Source: ")
        ]
        assert len(source_lines) == 1
        source_line = source_lines[0]
        opener, terminator = "/* Source: ", " */"
        assert source_line.startswith(opener)
        assert source_line.endswith(terminator)
        # Only the template's own opener and terminator carry comment syntax;
        # the interpolated payload can never close the comment or inject raw
        # assembly, control or separator bytes.
        payload = source_line[len(opener) : -len(terminator)]
        assert "*" not in payload
        assert "*/" not in payload
        assert "\n" not in payload and "\t" not in payload
        assert all(0x20 <= ord(character) <= 0x7E for character in payload), payload
    escaped_terminator = startup_mod.render_startup(
        source_path="Startup/evil*/handler.s",
        source_sha256="0" * 64,
        parsed=parsed,
    ).decode("utf-8")
    assert "evil\\x2a/handler.s" in escaped_terminator
    escaped_newline = startup_mod.render_startup(
        source_path="Startup/line\nbreak.s",
        source_sha256="0" * 64,
        parsed=parsed,
    ).decode("utf-8")
    assert "line\\x0abreak.s" in escaped_newline


# ---------------------------------------------------------------------------
# rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            mutate(
                "                 END\n",
                "                ADD R0, R1, R2\n                 END\n",
            ),
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
        ),
        (
            mutate(
                "                 BLX     R0\n",
                "                 BLX     R0\n                 MOV R5, R5\n",
            ),
            "MIGRATION_STARTUP_RESET_UNSUPPORTED",
        ),
        (
            mutate(
                "                 END\n",
                "__Vectors       DCD     __initial_sp\n                 END\n",
            ),
            "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        ),
        (
            mutate("DCD     ADC1_IRQHandler", "DCD     ADC1_IRQHandler + 4"),
            "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        ),
        (
            mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 0x00001004"),
            "MIGRATION_STARTUP_SIZE_INVALID",
        ),
        (
            mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 0x00000000"),
            "MIGRATION_STARTUP_SIZE_INVALID",
        ),
        (
            mutate("Heap_Size       EQU     0x00000400", "Heap_Size EQU 0x100000000"),
            "MIGRATION_STARTUP_SIZE_INVALID",
        ),
        (
            mutate(
                "Stack_Size      EQU     0x00001000",
                "Stack_Size EQU 0x00001000\nStack_Size EQU 0x00001000",
            ),
            "MIGRATION_STARTUP_DUPLICATE_LABEL",
        ),
        (
            mutate(
                "                EXPORT  ADC1_IRQHandler            [WEAK]\n",
                "                EXPORT  ADC1_IRQHandler            [WEAK]\n"
                "                EXPORT  ADC1_IRQHandler            [WEAK]\n",
            ),
            "MIGRATION_STARTUP_DUPLICATE_EXPORT",
        ),
        (
            mutate("DCD     WWDG_IRQHandler", "DCD     MISSING_IRQHandler"),
            "MIGRATION_STARTUP_UNDECLARED_HANDLER",
        ),
        (
            mutate(
                "ADC1_IRQHandler\nTIM2_IRQHandler\n",
                "ADC1_IRQHandler\n                MOV R0, R0\nTIM2_IRQHandler\n",
            ),
            "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
        ),
        (
            mutate(
                "                EXPORT  NMI_Handler                [WEAK]",
                "                EXPORT  NMI_Handler",
            ),
            "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
        ),
        (
            mutate(
                "                 IF      :DEF:__MICROLIB",
                "                 IF      :DEF:OTHER",
            ),
            "MIGRATION_STARTUP_CONDITIONAL_UNSUPPORTED",
        ),
        (
            mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU Stack_Mem + 4"),
            "MIGRATION_STARTUP_SIZE_INVALID",
        ),
        (
            mutate(
                "                 EXPORT  Reset_Handler             [WEAK]",
                "                 EXPORT  Reset_Handler",
            ),
            "MIGRATION_STARTUP_RESET_UNSUPPORTED",
        ),
        (
            mutate(
                "                EXPORT  ADC1_IRQHandler            [WEAK]\n",
                "",
            ),
            "MIGRATION_STARTUP_HANDLER_EXPORT_UNSUPPORTED",
        ),
        (
            mutate(
                "                EXPORT  ADC1_IRQHandler            [WEAK]",
                "                EXPORT  ADC1_IRQHandler",
            ),
            "MIGRATION_STARTUP_HANDLER_EXPORT_UNSUPPORTED",
        ),
        (
            mutate(
                "                EXPORT  NMI_Handler                [WEAK]\n",
                "",
            ),
            "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
        ),
        (
            mutate(
                "                 LDR     R2, = (Heap_Mem +  Heap_Size)\n",
                "",
            ),
            "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        ),
        (
            mutate(
                "                 LDR     R1, =(Stack_Mem + Stack_Size)\n",
                "                 LDR     R1, =(Stack_Mem + Stack_Size)\n"
                "                 LDR     R0, =  Heap_Mem\n",
            ),
            "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        ),
        (
            mutate(
                "                 LDR     R0, =  Heap_Mem\n"
                "                 LDR     R1, =(Stack_Mem + Stack_Size)\n",
                "                 LDR     R1, =(Stack_Mem + Stack_Size)\n"
                "                 LDR     R0, =  Heap_Mem\n",
            ),
            "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        ),
    ],
)
def test_unsupported_and_custom_constructs_are_rejected(text: str, expected: str):
    parsed = parse(text)
    assert parsed.status == "unsupported"
    assert expected in codes(parsed)


def test_missing_or_incomplete_reset_handler_is_rejected():
    reset_block = (
        "Reset_Handler    PROC\n"
        "                 EXPORT  Reset_Handler             [WEAK]\n"
        "        IMPORT  SystemInit\n"
        "        IMPORT  __main\n"
        "\n"
        "                 LDR     R0, =SystemInit\n"
        "                 BLX     R0\n"
        "                 LDR     R0, =__main\n"
        "                 BX      R0\n"
        "                 ENDP\n"
    )
    missing = parse(SYNTHETIC_STARTUP.replace(reset_block, "", 1))
    assert missing.status == "unsupported"
    assert "MIGRATION_STARTUP_RESET_UNSUPPORTED" in codes(missing)

    incomplete_text = SYNTHETIC_STARTUP.replace(
        "                 ENDP\n"
        "\n"
        "NMI_Handler     PROC\n",
        "\n"
        "NMI_Handler     PROC\n",
        1,
    )
    incomplete = parse(incomplete_text)
    assert incomplete.status == "unsupported"
    assert "MIGRATION_STARTUP_RESET_UNSUPPORTED" in codes(incomplete)

    # Completed reset evidence is required separately from the weak
    # individual handler PROCs; the valid fixture still reports it once.
    ready = parse(SYNTHETIC_STARTUP)
    assert ready.status == "ready"
    assert [
        handler.name for handler in ready.handlers if handler.kind == "reset"
    ] == ["Reset_Handler"]


def test_microlib_block_is_only_recognized_inside_the_code_area():
    """Active code is never normalized silently from a non-code AREA."""
    block_start = SYNTHETIC_STARTUP.index("                 IF      :DEF:__MICROLIB")
    block_end = SYNTHETIC_STARTUP.index("                 ENDIF\n") + len(
        "                 ENDIF\n"
    )
    block = SYNTHETIC_STARTUP[block_start:block_end]
    assert block.startswith("                 IF      :DEF:__MICROLIB\n")
    without = SYNTHETIC_STARTUP[:block_start] + SYNTHETIC_STARTUP[block_end:]
    assert block not in without

    # The same, otherwise valid block moved after __heap_limit stays in HEAP.
    heap_variant = without.replace(
        "                PRESERVE8\n",
        block + "                PRESERVE8\n",
        1,
    )
    # ... and moved directly after the RESET AREA stays in RESET.
    reset_variant = without.replace(
        "                AREA    RESET, DATA, READONLY\n",
        "                AREA    RESET, DATA, READONLY\n" + block,
        1,
    )
    # ... or moved inside a recognized handler PROC.
    proc_variant = without.replace(
        "Reset_Handler    PROC\n",
        "Reset_Handler    PROC\n" + block,
        1,
    )
    for text in (heap_variant, reset_variant, proc_variant):
        parsed = parse(text)
        assert parsed.status == "unsupported"
        assert "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED" in codes(parsed), [
            diagnostic.to_dict() for diagnostic in parsed.diagnostics
        ]

    # The supported text-area grammar is unchanged.
    assert parse(SYNTHETIC_STARTUP).status == "ready"


def test_numeric_sizes_accept_leading_zeros_and_reject_oversized_literals():
    leading_zero_decimal = parse(
        mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 000004096")
    )
    assert leading_zero_decimal.status == "ready", [
        diagnostic.to_dict() for diagnostic in leading_zero_decimal.diagnostics
    ]
    assert leading_zero_decimal.stack_size == 4096

    leading_zero_hex = parse(
        mutate("Heap_Size       EQU     0x00000400", "Heap_Size EQU 0x000000000400")
    )
    assert leading_zero_hex.status == "ready"
    assert leading_zero_hex.heap_size == 1024

    zero_heap_decimal = parse(
        mutate("Heap_Size       EQU     0x00000400", "Heap_Size EQU 0000000000")
    )
    assert zero_heap_decimal.status == "ready"
    assert zero_heap_decimal.heap_size == 0

    huge_decimal = parse(
        mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU " + "9" * 5000)
    )
    assert huge_decimal.status == "unsupported"
    assert "MIGRATION_STARTUP_SIZE_INVALID" in codes(huge_decimal)
    assert huge_decimal.stack_size is not None
    assert huge_decimal.stack_size > 0xFFFFFFFF

    huge_hex = parse(
        mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 0x" + "f" * 5000)
    )
    assert huge_hex.status == "unsupported"
    assert "MIGRATION_STARTUP_SIZE_INVALID" in codes(huge_hex)
    assert huge_hex.stack_size is not None
    assert huge_hex.stack_size > 0xFFFFFFFF

    decimal_overflow = parse(
        mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 4294967296")
    )
    assert decimal_overflow.status == "unsupported"
    assert "MIGRATION_STARTUP_SIZE_INVALID" in codes(decimal_overflow)

    hex_overflow = parse(
        mutate(
            "Heap_Size       EQU     0x00000400",
            "Heap_Size EQU 0x0000000100000000",
        )
    )
    assert hex_overflow.status == "unsupported"
    assert "MIGRATION_STARTUP_SIZE_INVALID" in codes(hex_overflow)

    unaligned = parse(
        mutate("Stack_Size      EQU     0x00001000", "Stack_Size EQU 4294967295")
    )
    assert unaligned.status == "unsupported"
    assert "MIGRATION_STARTUP_SIZE_INVALID" in codes(unaligned)


def test_zero_heap_is_permitted_and_represented_consistently():
    parsed = parse(
        mutate("Heap_Size       EQU     0x00000400", "Heap_Size EQU 0x00000000")
    )
    assert parsed.status == "ready"
    assert parsed.heap_size == 0
    rendered = startup_mod.render_startup(
        source_path=STARTUP_SOURCE,
        source_sha256="0" * 64,
        parsed=parsed,
    ).decode("utf-8")
    assert "Heap Size: 0x00000000 bytes" in rendered


def test_unsupported_core_is_a_structured_diagnostic():
    parsed = parse(SYNTHETIC_STARTUP, core="Cortex-M0")
    assert parsed.core is None
    assert parsed.status == "unsupported"
    assert "MIGRATION_STARTUP_CORE_UNSUPPORTED" in codes(parsed)
    assert parse(SYNTHETIC_STARTUP, core="Cortex-M3").core == "cortex-m3"
    assert parse(SYNTHETIC_STARTUP, core="Cortex-M7").core == "cortex-m7"


def test_unterminated_continuation_is_rejected():
    parsed = parse(SYNTHETIC_STARTUP + "Broken\\")
    assert "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED" in codes(parsed)


def test_vector_limit_is_bounded(monkeypatch):
    monkeypatch.setattr(startup_mod, "STARTUP_VECTOR_LIMIT", 4)
    parsed = parse(SYNTHETIC_STARTUP)
    assert "MIGRATION_STARTUP_VECTOR_LIMIT_EXCEEDED" in codes(parsed)


def test_non_utf8_startup_is_rejected_without_decoding_guesswork(tmp_path):
    repo = startup_repo(tmp_path)
    (repo / STARTUP_SOURCE).write_bytes(b"\xff\xfe\x00startup\n")
    git_init(repo)
    inspection = inspect_keil(repo)
    options = StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE)
    plan = plan_keil_conversion(repo, inspection, startup_options=options)
    assert "MIGRATION_STARTUP_ENCODING_UNSUPPORTED" in {b.code for b in plan.blockers}


# ---------------------------------------------------------------------------
# option normalization and selection
# ---------------------------------------------------------------------------


def test_option_normalization_is_exact_and_portable():
    assert startup_mod.normalize_startup_options(None, None) is None

    with pytest.raises(MigrationPlanError) as error:
        startup_mod.normalize_startup_options(None, STARTUP_SOURCE)
    assert error.value.code == "MIGRATION_STARTUP_OPTIONS_INVALID"
    assert error.value.details == {"field": "startupSource", "rule": "requiresStrategy"}

    with pytest.raises(MigrationPlanError) as error:
        startup_mod.normalize_startup_options("translate-anything", None)
    assert error.value.code == "MIGRATION_STARTUP_STRATEGY_UNSUPPORTED"
    assert error.value.details == {"field": "startupStrategy", "rule": "unsupported"}

    with pytest.raises(MigrationPlanError) as error:
        startup_mod.normalize_startup_options("generate-cmsis-gcc", "../startup.s")
    assert error.value.code == "MIGRATION_STARTUP_OPTIONS_INVALID"
    assert error.value.details["field"] == "startupSource"

    with pytest.raises(MigrationPlanError) as error:
        startup_mod.normalize_startup_options("generate-cmsis-gcc", "Startup\\startup.s")
    assert error.value.code == "MIGRATION_STARTUP_OPTIONS_INVALID"
    assert error.value.details["rule"] == "portablePath"


def test_single_candidate_is_resolved_and_ambiguous_selection_returns_choices(tmp_path):
    repo = startup_repo(tmp_path, name="single")
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", None),
    )
    assert plan.startup is not None
    assert plan.startup.source_path == STARTUP_SOURCE
    assert plan.startup.status == "ready"

    ambiguous = two_assembly_repo(tmp_path, name="ambiguous")
    ambiguous_inspection = inspect_keil(ambiguous)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(
            ambiguous,
            ambiguous_inspection,
            startup_options=StartupOptions("generate-cmsis-gcc", None),
        )
    assert error.value.code == "MIGRATION_STARTUP_SELECTION_REQUIRED"
    assert error.value.details == {
        "candidates": ["DSP/filter.s", STARTUP_SOURCE],
    }


def test_zero_candidates_and_invalid_source_are_structured(tmp_path):
    from test_migration_plan import build_repo

    repo = build_repo(
        tmp_path,
        name="no-assembly",
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={
            "fpu": None,
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    inspection = inspect_keil(repo)
    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(
            repo,
            inspection,
            startup_options=StartupOptions("generate-cmsis-gcc", None),
        )
    assert error.value.code == "MIGRATION_STARTUP_SOURCE_NOT_FOUND"
    assert error.value.details == {"candidates": []}

    with pytest.raises(MigrationPlanError) as error:
        plan_keil_conversion(
            repo,
            inspection,
            startup_options=StartupOptions("generate-cmsis-gcc", "Missing/startup.s"),
        )
    assert error.value.code == "MIGRATION_STARTUP_SOURCE_INVALID"
    assert error.value.details == {"path": "Missing/startup.s", "rule": "notIncludedAssembly"}


# ---------------------------------------------------------------------------
# plan evidence and immutability
# ---------------------------------------------------------------------------


def test_default_plan_keeps_the_existing_assembly_blocker_and_no_startup_fields(tmp_path):
    repo = startup_repo(tmp_path)
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(repo, inspection)
    data = plan.to_dict()

    assert "startup" not in data
    assert "startup_options" not in data
    assert any(b.code == "ARMCC_ASSEMBLY_UNSUPPORTED" for b in plan.blockers)
    assert not any(patch.path == GENERATED_SOURCE for patch in plan.patches)
    manifest = next(p for p in plan.patches if p.path == ".stm32-project.json")
    payload = json.loads(manifest.after_bytes)
    assert payload["build"]["assemblySources"] == [STARTUP_SOURCE]
    assert "stackSize" not in payload["memory"]
    assert "runtimeInitialization" not in payload["generation"]


def test_generated_plan_binds_source_options_hashes_vectors_and_manifest(tmp_path):
    repo = startup_repo(tmp_path)
    inspection = inspect_keil(repo)
    options = StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE)
    plan = plan_keil_conversion(repo, inspection, startup_options=options)
    data = plan.to_dict()
    startup = data["startup"]

    assert data["startup_options"] == {"strategy": "generate-cmsis-gcc", "source": STARTUP_SOURCE}
    assert startup["status"] == "ready"
    assert startup["source_path"] == STARTUP_SOURCE
    assert startup["source_sha256"] == hashlib.sha256(SYNTHETIC_STARTUP.encode()).hexdigest()
    assert startup["stack_size"] == 4096
    assert startup["heap_size"] == 1024
    assert startup["vector_count"] == 24
    assert startup["reserved_count"] == 5
    assert startup["generated_path"] == GENERATED_SOURCE
    assert len(startup["generated_sha256"]) == 64
    assert len(startup["warnings"]) == 3
    assert startup["diagnostics"] == []
    assert not any(
        b.code == "ARMCC_ASSEMBLY_UNSUPPORTED" and b.path == STARTUP_SOURCE
        for b in plan.blockers
    )

    generated = next(p for p in plan.patches if p.path == GENERATED_SOURCE)
    assert generated.before_bytes is None
    assert hashlib.sha256(generated.after_bytes).hexdigest() == startup["generated_sha256"]

    manifest = json.loads(next(p for p in plan.patches if p.path == ".stm32-project.json").after_bytes)
    assert manifest["build"]["assemblySources"] == [GENERATED_SOURCE]
    assert manifest["memory"]["stackSize"] == 4096
    assert manifest["memory"]["heapSize"] == 1024
    assert manifest["generation"]["runtimeInitialization"] == "cmsis-gcc-v1"

    defaults = plan_keil_conversion(repo, inspection)
    assert defaults.plan_id != plan.plan_id
    auto = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", None),
    )
    assert auto.startup is not None
    assert auto.startup.source_path == STARTUP_SOURCE
    assert auto.plan_id != plan.plan_id


def test_other_assembly_sources_remain_blocked(tmp_path):
    repo = two_assembly_repo(tmp_path)
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assembly = [b for b in plan.blockers if b.code == "ARMCC_ASSEMBLY_UNSUPPORTED"]
    assert [b.path for b in assembly] == ["DSP/filter.s"]


def test_plan_is_read_only_with_startup_options(tmp_path):
    repo = startup_repo(tmp_path)
    inspection = inspect_keil(repo)
    before = snapshot_tree(repo)
    plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert snapshot_tree(repo) == before


# ---------------------------------------------------------------------------
# preflight and apply
# ---------------------------------------------------------------------------


def test_preflight_returns_startup_evidence_without_mutation(tmp_path):
    repo = startup_repo(tmp_path)
    inspection = inspect_keil(repo)
    before = snapshot_tree(repo)
    data = preflight_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert snapshot_tree(repo) == before
    assert data["analysis"]["startup"]["status"] == "ready"
    assert data["analysis"]["startup"]["vector_count"] == 24
    assert data["applyReadiness"]["ready"] is False
    assert data["planReadiness"]["planId"] is None

    apply_steps = " ".join(data["applyReadiness"]["nextSteps"])
    assert "startupStrategy=generate-cmsis-gcc" in apply_steps
    assert f"startupSource={STARTUP_SOURCE}" in apply_steps
    plan_steps = " ".join(data["planReadiness"]["nextSteps"])
    if data["planReadiness"]["ready"]:
        assert "startupStrategy=generate-cmsis-gcc" in plan_steps
        assert f"startupSource={STARTUP_SOURCE}" in plan_steps

    default_data = preflight_keil_conversion(repo, inspection)
    assert "startupStrategy" not in " ".join(
        default_data["planReadiness"]["nextSteps"]
    )
    assert "startupStrategy" not in " ".join(
        default_data["applyReadiness"]["nextSteps"]
    )


def test_apply_generates_only_the_new_assembly_and_records_model_fields(tmp_path):
    repo = startup_repo(tmp_path)
    source_bytes = (repo / STARTUP_SOURCE).read_bytes()
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    result = apply_keil_conversion(plan)

    assert result.ok is True
    assert (repo / GENERATED_SOURCE).is_file()
    assert (repo / STARTUP_SOURCE).read_bytes() == source_bytes
    manifest = json.loads((repo / ".stm32-project.json").read_text("utf-8"))
    assert manifest["build"]["assemblySources"] == [GENERATED_SOURCE]
    assert manifest["memory"]["stackSize"] == 4096
    assert manifest["memory"]["heapSize"] == 1024
    assert manifest["generation"]["runtimeInitialization"] == "cmsis-gcc-v1"
    report = json.loads(
        (repo / "artifacts/migration/conversion-report.json").read_text("utf-8")
    )
    assert report["startup"]["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["startup"]["generated_sha256"] == hashlib.sha256(
        (repo / GENERATED_SOURCE).read_bytes()
    ).hexdigest()


def test_existing_different_generated_target_is_a_blocked_collision(tmp_path):
    repo = startup_repo(tmp_path)
    generated = repo / GENERATED_SOURCE
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"/* user owned file */\n")
    git_init(repo)
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert any(b.code == "MIGRATION_STARTUP_TARGET_COLLISION" for b in plan.blockers)
    assert not any(patch.path == GENERATED_SOURCE for patch in plan.patches)
    before = snapshot_tree(repo)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert snapshot_tree(repo) == before
    assert generated.read_bytes() == b"/* user owned file */\n"


def test_file_occupying_the_generated_parent_is_a_blocked_collision(tmp_path):
    source = "Config/startup_synthetic.s"
    repo = build_repo(
        tmp_path,
        name="startup-parent-file",
        files={"Main/main.c": MAIN_C, source: SYNTHETIC_STARTUP},
        uvprojx_kwargs={
            "cpu": cpu_setting(),
            "fpu": None,
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Config", (("startup_synthetic.s", "2", source),)),
            ),
            "includes": "Main;Libraries/STM32F4xx_StdPeriph_Driver",
        },
        commit=False,
    )
    # A regular file, not a directory, occupies Startup/ where the generated
    # target's parent would be.  Analysis must classify this as a collision
    # instead of a writable missing destination.
    (repo / "Startup").write_text("user owned file\n", encoding="utf-8")
    git_init(repo)
    inspection = inspect_keil(repo)

    plan = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", source),
    )
    assert any(
        blocker.code == "MIGRATION_STARTUP_TARGET_COLLISION"
        for blocker in plan.blockers
    )
    assert not any(patch.path == GENERATED_SOURCE for patch in plan.patches)

    before = snapshot_tree(repo)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert snapshot_tree(repo) == before
    assert (repo / "Startup").read_text("utf-8") == "user owned file\n"
    assert not (repo / "Startup" / "stm32tk_startup_gcc.S").exists()


def test_existing_identical_generated_target_is_reused_without_overwrite(tmp_path):
    repo = startup_repo(tmp_path)
    inspection = inspect_keil(repo)
    first = plan_keil_conversion(
        repo,
        inspection,
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    generated_bytes = next(
        patch for patch in first.patches if patch.path == GENERATED_SOURCE
    ).after_bytes
    target = repo / GENERATED_SOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(generated_bytes)
    git_init(repo)

    second = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert not any(patch.path == GENERATED_SOURCE for patch in second.patches)
    assert any(entry.path == GENERATED_SOURCE for entry in second.inputs)
    assert second.startup is not None and second.startup.status == "ready"
    assert second.startup.generated_sha256 == hashlib.sha256(generated_bytes).hexdigest()

    result = apply_keil_conversion(second)
    assert result.ok is True
    assert target.read_bytes() == generated_bytes


# ---------------------------------------------------------------------------
# workflow option routing and apply replanning
# ---------------------------------------------------------------------------


def test_workflow_preflight_plan_and_apply_use_the_same_options(tmp_path):
    repo = startup_repo(tmp_path)
    preflight = preflight_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert preflight.ok is True
    assert preflight.data["analysis"]["startup"]["source_path"] == STARTUP_SOURCE

    planned = convert_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert planned.ok is True
    assert planned.data["startup"]["status"] == "ready"
    plan_id = planned.data["plan_id"]

    applied = convert_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        plan_id=plan_id,
        authorized=True,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert applied.ok is True
    assert (repo / GENERATED_SOURCE).is_file()


def test_apply_with_a_caller_edited_source_or_omitted_options_is_rejected(tmp_path):
    repo = two_assembly_repo(tmp_path)
    planned = convert_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        startup_strategy="generate-cmsis-gcc",
        startup_source=STARTUP_SOURCE,
    )
    assert planned.ok is True
    plan_id = planned.data["plan_id"]
    before = snapshot_tree(repo)

    edited = convert_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        plan_id=plan_id,
        authorized=True,
        startup_strategy="generate-cmsis-gcc",
        startup_source="DSP/filter.s",
    )
    assert edited.ok is False
    assert edited.code == "PLAN_CHANGED"
    assert snapshot_tree(repo) == before

    omitted = convert_keil_workflow(
        repo,
        uvprojx=UVPROJX,
        target_name=TARGET,
        plan_id=plan_id,
        authorized=True,
    )
    assert omitted.ok is False
    assert omitted.code == "PLAN_CHANGED"
    assert snapshot_tree(repo) == before


def test_forged_plan_startup_options_fail_plan_id_validation(tmp_path):
    repo = startup_repo(tmp_path)
    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    forged = replace(
        plan,
        startup_options=StartupOptions("generate-cmsis-gcc", "DSP/filter.s"),
    )
    result = apply_keil_conversion(forged)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details == {"rule": "planId"}


# ---------------------------------------------------------------------------
# read-only original-file recognizer evidence
# ---------------------------------------------------------------------------


def test_original_f429_startup_is_recognized_read_only(monkeypatch):
    """Grammar evidence only: this does not build, migrate or modify the project."""

    original = Path(
        "D:/WorkSpace/mobile-robot-controller/Startup_config/startup_stm32f429_439xx.s"
    )
    if not original.is_file():
        pytest.skip("supplied original startup evidence path is not present on this host")
    data = original.read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "3265ff864ce96074f384e178b35acdbbd33ebdffe45716ccba8d55544b9db0ae"
    )
    parsed = startup_mod._Parser(
        "startup_stm32f429_439xx.s",
        startup_mod._logical_lines(data.decode("utf-8")),
        startup_mod.normalize_startup_core("Cortex-M4"),
    ).run()
    assert parsed.status == "ready", [d.to_dict() for d in parsed.diagnostics]
    assert parsed.stack_size == 4096
    assert parsed.heap_size == 1024
    assert len(parsed.vectors) == 107
    assert parsed.vectors[0].symbol == "__initial_sp"
    assert parsed.vectors[1].symbol == "Reset_Handler"
    assert sum(1 for entry in parsed.vectors if entry.reserved) == 5
    assert original.read_bytes() == data
