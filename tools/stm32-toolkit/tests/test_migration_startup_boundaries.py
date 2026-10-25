"""Whole-grammar refusal boundaries for CMSIS startup recognition.

Every fixture is the authored synthetic startup from ``startup_gcc_fixture``;
no vendor or user startup source is copied.  The tests drive the exported
``analyze_startup`` analysis and the public PLAN/APPLY flow, and add no
product behavior.  Neighboring accepted controls keep each refusal a real
grammar boundary rather than a globally disabled feature.
"""

from __future__ import annotations

import pytest

from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    StartupOptions,
    apply_keil_conversion,
    plan_keil_conversion,
)
from stm32_toolkit.migration.startup import analyze_startup

from startup_gcc_fixture import (
    GENERATED_SOURCE,
    STARTUP_SOURCE,
    SYNTHETIC_STARTUP,
    git_init,
    snapshot_tree,
    startup_repo,
)

STACK_AREA = "                AREA    STACK, NOINIT, READWRITE, ALIGN=3\n"
HEAP_AREA = "                AREA    HEAP, NOINIT, READWRITE, ALIGN=3\n"
RESET_AREA = "                AREA    RESET, DATA, READONLY\n"
PRESERVE8_LINE = "                PRESERVE8\n"
THUMB_LINE = "                THUMB\n"

MICROLIB_IF = "                 IF      :DEF:__MICROLIB\n"
MICROLIB_ELSE = "                 ELSE\n"
MICROLIB_ENDIF = "                 ENDIF\n"
MICROLIB_BX_LR = "                 BX      LR\n"
MICROLIB_IMPORT = "                 IMPORT  __use_two_region_memory\n"
MICROLIB_HEAP_EXPORT = "                 EXPORT  __heap_base\n"


def _mutate(old: str, new: str) -> str:
    assert old in SYNTHETIC_STARTUP, old
    return SYNTHETIC_STARTUP.replace(old, new, 1)


def _line_of(text: str, stripped_line: str, occurrence: int = 0) -> int:
    hits = [
        index + 1
        for index, line in enumerate(text.splitlines())
        if line.strip() == stripped_line
    ]
    assert len(hits) > occurrence, (stripped_line, hits)
    return hits[occurrence]


def _analyze(tmp_path, text: str):
    repo = startup_repo(tmp_path)
    (repo / STARTUP_SOURCE).write_bytes(text.encode("utf-8"))
    inspection = inspect_keil(repo)
    data = (repo / STARTUP_SOURCE).read_bytes()
    outcome = analyze_startup(
        repo,
        inspection,
        StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
        {STARTUP_SOURCE: data},
    )
    return repo, outcome


def _assert_refusal(
    tmp_path,
    text: str,
    code: str,
    anchor: str | None,
    occurrence: int,
    fragment: str,
) -> None:
    repo, outcome = _analyze(tmp_path, text)
    analysis = outcome.analysis
    assert analysis.status == "unsupported"
    assert outcome.generated_bytes is None
    assert analysis.generated_path is None
    assert analysis.source_path == STARTUP_SOURCE

    expected_line = 0 if anchor is None else _line_of(text, anchor, occurrence)
    matches = [item for item in analysis.diagnostics if item.code == code]
    assert matches, [item.to_dict() for item in analysis.diagnostics]
    assert any(
        item.line == expected_line and fragment in item.message for item in matches
    ), [(item.line, item.message) for item in matches]

    # Analysis never rewrites the selected ARMCC source.
    assert (repo / STARTUP_SOURCE).read_bytes() == text.encode("utf-8")


def _missing_microlib_block() -> str:
    start = SYNTHETIC_STARTUP.index(MICROLIB_IF)
    end = SYNTHETIC_STARTUP.index(MICROLIB_ENDIF) + len(MICROLIB_ENDIF)
    return SYNTHETIC_STARTUP[:start] + SYNTHETIC_STARTUP[end:]


def _missing_stack_area() -> str:
    block = (
        STACK_AREA
        + "Stack_Mem       SPACE   Stack_Size\n"
        + "__initial_sp\n"
        + "\n"
    )
    return _mutate(block, "")


def _missing_vector_end() -> str:
    return SYNTHETIC_STARTUP.replace(
        "__Vectors_End\n\n__Vectors_Size", "__Vectors_Size", 1
    )


def _one_vector_word() -> str:
    start = SYNTHETIC_STARTUP.index("__Vectors       DCD     __initial_sp\n")
    end = SYNTHETIC_STARTUP.index("\n__Vectors_End\n", start) + 1
    first_line = SYNTHETIC_STARTUP[start : SYNTHETIC_STARTUP.index("\n", start) + 1]
    return SYNTHETIC_STARTUP[:start] + first_line + SYNTHETIC_STARTUP[end:]


_SPARE_HANDLER_PROC = (
    "Spare_Handler   PROC\n"
    "                EXPORT  Spare_Handler              [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
)
_DEFAULT_ALIAS_TAIL = "WWDG_IRQHandler\n                B       .\n"
_VECTOR_TAIL = "                DCD     WWDG_IRQHandler\n\n__Vectors_End\n"


MICROLIB_CASES = [
    (
        "if-unsupported-statement",
        _mutate(MICROLIB_IF, MICROLIB_IF + "                 NOP\n"),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "NOP",
        0,
        "IF :DEF:__MICROLIB branch",
    ),
    (
        "missing-else",
        _mutate(MICROLIB_ELSE, ""),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "ENDIF",
        0,
        "missing its ELSE branch",
    ),
    (
        "if-exports-incomplete",
        _mutate(MICROLIB_HEAP_EXPORT, ""),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "ELSE",
        0,
        "must export __initial_sp",
    ),
    (
        "else-wrong-import",
        _mutate(MICROLIB_IMPORT, "                 IMPORT  other_symbol\n"),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "IMPORT  other_symbol",
        0,
        "Microlib ELSE branch",
    ),
    (
        "else-wrong-bx",
        _mutate(MICROLIB_BX_LR, "                 BX      R7\n"),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "BX      R7",
        0,
        "Microlib ELSE branch",
    ),
    (
        "else-incomplete-bx",
        _mutate(MICROLIB_BX_LR, ""),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        "ENDIF",
        0,
        "incomplete",
    ),
    (
        "duplicate-if-export",
        _mutate(
            MICROLIB_HEAP_EXPORT,
            MICROLIB_HEAP_EXPORT + MICROLIB_HEAP_EXPORT,
        ),
        "MIGRATION_STARTUP_DUPLICATE_EXPORT",
        "EXPORT  __heap_base",
        1,
        "duplicate",
    ),
    (
        "missing-block",
        _missing_microlib_block(),
        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
        None,
        0,
        "is required",
    ),
]


STACK_HEAP_AREA_CASES = [
    (
        "unsupported-area-attributes",
        _mutate(STACK_AREA, "                AREA    STACK, NOINIT, READWRITE\n"),
        "MIGRATION_STARTUP_AREA_UNSUPPORTED",
        "AREA    STACK, NOINIT, READWRITE",
        0,
        "unsupported startup AREA",
    ),
    (
        "duplicate-stack-area",
        _mutate(STACK_AREA, STACK_AREA + STACK_AREA),
        "MIGRATION_STARTUP_AREA_UNSUPPORTED",
        "AREA    STACK, NOINIT, READWRITE, ALIGN=3",
        1,
        "duplicate startup AREA",
    ),
    (
        "wrong-stack-reservation",
        _mutate(
            "Stack_Mem       SPACE   Stack_Size\n",
            "Other_Mem       SPACE   Stack_Size\n",
        ),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        "Other_Mem       SPACE   Stack_Size",
        0,
        "unexpected STACK reservation",
    ),
    (
        "missing-initial-sp",
        _mutate("__initial_sp\n", ""),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        "AREA    STACK, NOINIT, READWRITE, ALIGN=3",
        0,
        "STACK area is incomplete",
    ),
    (
        "missing-heap-limit",
        _mutate("__heap_limit\n\n" + PRESERVE8_LINE, "\n" + PRESERVE8_LINE),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        "AREA    HEAP, NOINIT, READWRITE, ALIGN=3",
        0,
        "HEAP area is incomplete",
    ),
    (
        "space-outside-stack-or-heap",
        _mutate(
            RESET_AREA,
            RESET_AREA + "Foreign_Mem     SPACE   Some_Size\n",
        ),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        "Foreign_Mem     SPACE   Some_Size",
        0,
        "SPACE is only recognized",
    ),
    (
        "missing-stack-area",
        _missing_stack_area(),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        None,
        0,
        "STACK area is required",
    ),
    (
        "missing-preserve8",
        _mutate(PRESERVE8_LINE, ""),
        "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
        None,
        0,
        "PRESERVE8 is required",
    ),
]


VECTOR_HANDLER_CASES = [
    (
        "first-vector-not-initial-sp",
        _mutate(
            "__Vectors       DCD     __initial_sp\n",
            "__Vectors       DCD     Reset_Handler\n",
        ),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        "__Vectors       DCD     Reset_Handler",
        0,
        "first vector word",
    ),
    (
        "second-vector-reserved",
        _mutate(
            "                DCD     Reset_Handler\n",
            "                DCD     0\n",
        ),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        "DCD     0",
        0,
        "second vector word",
    ),
    (
        "initial-sp-not-first",
        _mutate(
            _VECTOR_TAIL,
            "                DCD     WWDG_IRQHandler\n"
            "                DCD     __initial_sp\n\n__Vectors_End\n",
        ),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        "DCD     __initial_sp",
        0,
        "__initial_sp is only recognized as the first vector word",
    ),
    (
        "reset-handler-not-second",
        _mutate(
            _VECTOR_TAIL,
            "                DCD     WWDG_IRQHandler\n"
            "                DCD     Reset_Handler\n\n__Vectors_End\n",
        ),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        "DCD     Reset_Handler",
        1,
        "Reset_Handler is only recognized as the second vector word",
    ),
    (
        "missing-vector-end",
        _missing_vector_end(),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        None,
        0,
        "vector table has no end",
    ),
    (
        "vector-table-too-short",
        _one_vector_word(),
        "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
        "__Vectors       DCD     __initial_sp",
        0,
        "at least the initial SP and reset handler",
    ),
    (
        "unreferenced-individual-handler",
        _mutate("\nDefault_Handler PROC\n", "\n" + _SPARE_HANDLER_PROC + "\nDefault_Handler PROC\n"),
        "MIGRATION_STARTUP_UNREFERENCED_HANDLER",
        "Spare_Handler   PROC",
        0,
        "handler PROC is not referenced",
    ),
    (
        "unreferenced-default-alias",
        _mutate(
            _DEFAULT_ALIAS_TAIL,
            "WWDG_IRQHandler\nSPARE_IRQHandler\n                B       .\n",
        ),
        "MIGRATION_STARTUP_UNREFERENCED_HANDLER",
        "SPARE_IRQHandler",
        0,
        "Default_Handler alias is not referenced",
    ),
    (
        "default-export-without-alias",
        _mutate(
            _DEFAULT_ALIAS_TAIL,
            "WWDG_IRQHandler\n"
            "                EXPORT  SPARE_IRQHandler            [WEAK]\n"
            "                B       .\n",
        ),
        "MIGRATION_STARTUP_UNREFERENCED_HANDLER",
        "EXPORT  SPARE_IRQHandler            [WEAK]",
        0,
        "weak Default_Handler export is not a bare alias label or vector target",
    ),
    (
        "endp-without-proc",
        _mutate(THUMB_LINE, THUMB_LINE + "                ENDP\n"),
        "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
        "ENDP",
        0,
        "ENDP without an open PROC",
    ),
]


@pytest.mark.parametrize(
    ("text", "code", "anchor", "occurrence", "fragment"),
    [case[1:] for case in MICROLIB_CASES],
    ids=[case[0] for case in MICROLIB_CASES],
)
def test_microlib_boilerplate_refusals(tmp_path, text, code, anchor, occurrence, fragment):
    _assert_refusal(tmp_path, text, code, anchor, occurrence, fragment)


@pytest.mark.parametrize(
    ("text", "code", "anchor", "occurrence", "fragment"),
    [case[1:] for case in STACK_HEAP_AREA_CASES],
    ids=[case[0] for case in STACK_HEAP_AREA_CASES],
)
def test_stack_heap_and_area_stage_refusals(
    tmp_path, text, code, anchor, occurrence, fragment
):
    _assert_refusal(tmp_path, text, code, anchor, occurrence, fragment)


@pytest.mark.parametrize(
    ("text", "code", "anchor", "occurrence", "fragment"),
    [case[1:] for case in VECTOR_HANDLER_CASES],
    ids=[case[0] for case in VECTOR_HANDLER_CASES],
)
def test_vector_and_handler_boundary_refusals(
    tmp_path, text, code, anchor, occurrence, fragment
):
    _assert_refusal(tmp_path, text, code, anchor, occurrence, fragment)


def test_referenced_additional_default_alias_is_accepted(tmp_path):
    text = SYNTHETIC_STARTUP.replace(
        _DEFAULT_ALIAS_TAIL,
        "WWDG_IRQHandler\n"
        "                EXPORT  SPARE_IRQHandler            [WEAK]\n"
        "SPARE_IRQHandler\n"
        "                B       .\n",
        1,
    )
    text = text.replace(
        _VECTOR_TAIL,
        "                DCD     WWDG_IRQHandler\n"
        "                DCD     SPARE_IRQHandler\n\n__Vectors_End\n",
        1,
    )
    assert text != SYNTHETIC_STARTUP

    repo, outcome = _analyze(tmp_path, text)
    analysis = outcome.analysis
    assert analysis.status == "ready", [
        item.to_dict() for item in analysis.diagnostics
    ]
    assert outcome.generated_bytes is not None
    assert analysis.generated_path == GENERATED_SOURCE
    assert analysis.vector_count == 25
    assert analysis.reserved_count == 5
    kinds = {handler.name: handler.kind for handler in analysis.handlers}
    assert kinds["SPARE_IRQHandler"] == "default-alias"
    assert b".thumb_set SPARE_IRQHandler, Default_Handler" in outcome.generated_bytes
    assert (repo / STARTUP_SOURCE).read_bytes() == text.encode("utf-8")


def test_blocked_microlib_startup_preserves_source_and_writes_no_output(tmp_path):
    text = _mutate(MICROLIB_BX_LR, "")
    repo = startup_repo(tmp_path)
    source = repo / STARTUP_SOURCE
    source.write_bytes(text.encode("utf-8"))
    git_init(repo)

    plan = plan_keil_conversion(
        repo,
        inspect_keil(repo),
        startup_options=StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE),
    )
    assert plan.startup is not None
    assert plan.startup.status == "unsupported"
    assert plan.startup.generated_path is None
    assert any(
        diagnostic.code == "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED"
        and "incomplete" in diagnostic.message
        for diagnostic in plan.startup.diagnostics
    )
    assert not any(patch.path == GENERATED_SOURCE for patch in plan.patches)

    before = snapshot_tree(repo)
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED" in result.details["blockerCodes"]
    assert snapshot_tree(repo) == before
    assert source.read_bytes() == text.encode("utf-8")
    assert not (repo / GENERATED_SOURCE).exists()
