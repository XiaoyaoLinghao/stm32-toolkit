"""ARMCC-COMMON-SYNTAX unit and public-flow tests.

The fixtures here are synthetic and disposable.  Real compiler (GNU Arm)
evidence lives in ``test_armcc_common_compiler.py``; this module never runs a
compiler, a probe, or the installed Toolkit runtime.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.migration import (
    apply_keil_conversion,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.constant_context import (
    ConstantResolutionError,
    SourceSymbols,
    evaluate_integer,
)
from stm32_toolkit.project_model import load_project_model

from test_migration_plan import FRAMEWORK_INCLUDE, build_repo, fixture_inspection

BOARD_H = (
    "/* synthetic board constants */\n"
    "#ifndef BOARD_H\n"
    "#define BOARD_H\n"
    "\n"
    "#define BASE 0x20000000u\n"
    "#define OFFSET 0x100\n"
    "#define SIZE 64\n"
    "#define REG_ADDR (BASE + 0x400)\n"
    "#define ALIGN_BYTES 16\n"
    "\n"
    "#endif /* BOARD_H */\n"
)

MAIN_C = (
    "/* synthetic ARMCC source: no vendor code */\n"
    '#include "board.h"\n'
    "\n"
    "#pragma import(__use_no_semihosting) /* keep */\n"
    "\n"
    "__asm void wait_wfi(void)\n"
    "{\n"
    "    WFI\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__asm void irq_off(void)\n"
    "{\n"
    "    CPSID I\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__asm void irq_on(void)\n"
    "{\n"
    "    CPSIE I\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__asm void set_stack(unsigned int top)\n"
    "{\n"
    "    MSR MSP, R0\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__align(32) unsigned char pool[SIZE] __attribute__((at(BASE + OFFSET)));\n"
    "__at(REG_ADDR) volatile unsigned int reg;\n"
    "__align(ALIGN_BYTES) static unsigned char aligned_buf[8];\n"
    "\n"
    "int main(void) { return (int)reg + pool[0] + aligned_buf[0]; }\n"
)

# ---------------------------------------------------------------------------
# expression evaluation
# ---------------------------------------------------------------------------


def _map(values: dict[str, str]):
    def lookup(name: str) -> str:
        if name not in values:
            raise ConstantResolutionError("undefined")
        return values[name]

    return lookup


def test_expression_expands_macros_textually_preserving_precedence():
    assert evaluate_integer("A * 4", _map({"A": "1 + 2"})) == 9
    assert evaluate_integer("(A) * 4", _map({"A": "1 + 2"})) == 12
    assert evaluate_integer(
        "BASE + OFFSET", _map({"BASE": "0x20000000u", "OFFSET": "0x100UL"})
    ) == 0x20000100
    assert evaluate_integer("1 << 4", _map({})) == 16


def test_expression_rejects_octal_overflow_divergence_and_type_dependent_forms():
    for expression in ("010", "~1", "1 / 0", "1 << 32", "0x100000000", "0x1p3"):
        with pytest.raises(ConstantResolutionError):
            evaluate_integer(expression, _map({}))
    with pytest.raises(ConstantResolutionError):
        evaluate_integer("1" * 70, _map({}))


def test_deeply_expanded_unary_nesting_is_a_controlled_limit_error():
    with pytest.raises(ConstantResolutionError) as error:
        evaluate_integer("DEEP", _map({"DEEP": "-" * 40 + "0"}))
    assert error.value.code == "limit"


def test_expression_cycles_and_function_like_usage_fail_closed():
    with pytest.raises(ConstantResolutionError) as error:
        evaluate_integer("A + 1", _map({"A": "B", "B": "A"}))
    assert error.value.code == "cycle"
    with pytest.raises(ConstantResolutionError):
        evaluate_integer("FN(1)", _map({"FN": "2"}))
    with pytest.raises(ConstantResolutionError):
        evaluate_integer("A", _map({"A": ""}))


# ---------------------------------------------------------------------------
# macro / include resolution
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _resolve(root: Path, source: str, name: str, include_paths=("Main",)):
    source_path = root / source
    text = source_path.read_text("utf-8")
    symbols = SourceSymbols(root, source, text, tuple(include_paths), ())
    return symbols.evaluate(name)


def test_nested_guarded_include_chain_resolves_and_binds_dependency_bytes(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/main.c",
        '#include "cfg/memory.h"\nint main(void) { return 0; }\n',
    )
    _write(
        root,
        "Main/cfg/memory.h",
        "#ifndef MEMORY_H\n"
        "#define MEMORY_H\n"
        '#include "base.h"\n'
        "#define REG (BASE + OFFSET)\n"
        "#endif\n",
    )
    _write(
        root,
        "Main/cfg/base.h",
        "#ifndef BASE_H\n"
        "#define BASE_H\n"
        "#define BASE 0x20000000\n"
        "#define OFFSET 0x40\n"
        "#endif\n",
    )
    value, error = _resolve(root, "Main/main.c", "REG")
    assert error is None
    assert value == 0x20000040

    source_text = (root / "Main" / "main.c").read_text("utf-8")
    symbols = SourceSymbols(root, "Main/main.c", source_text, ("Main",), ())
    assert symbols.evaluate("REG") == (0x20000040, None)
    dependencies = {path for path, _digest, _size in symbols.dependencies()}
    assert dependencies == {"Main/cfg/memory.h", "Main/cfg/base.h"}
    for path, digest, size in symbols.dependencies():
        data = (root / path).read_bytes()
        assert digest == hashlib.sha256(data).hexdigest()
        assert size == len(data)


def test_conditional_include_and_conditional_definition_are_unsupported(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/main.c",
        '#include "plain.h"\n'
        "#if 0\n"
        '#include "conditional.h"\n'
        "#endif\n"
        "int main(void) { return 0; }\n",
    )
    _write(root, "Main/plain.h", "#define SAFE 1\n")
    _write(root, "Main/conditional.h", "#define CONDITIONAL 2\n")
    value, error = _resolve(root, "Main/main.c", "CONDITIONAL")
    assert value is None
    assert error == "conditional"
    assert _resolve(root, "Main/main.c", "SAFE") == (1, None)

    _write(
        root,
        "Main/guarded.h",
        "#ifdef CONFIG_ENABLED\n#define MAYBE 3\n#endif\n",
    )
    _write(root, "Main/main2.c", '#include "guarded.h"\nint f(void){return 0;}\n')
    assert _resolve(root, "Main/main2.c", "MAYBE") == (None, "conditional")


def test_plain_ifndef_with_later_define_is_not_a_proven_guard(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/not_a_guard.h",
        "#ifndef CONFIG\n/* no immediate empty define */\n#define VALUE 7\n#endif\n",
    )
    _write(root, "Main/main.c", '#include "not_a_guard.h"\nint main(void){return 0;}\n')
    assert _resolve(root, "Main/main.c", "VALUE") == (None, "conditional")

    _write(
        root,
        "Main/nonempty_guard.h",
        "#ifndef NONEMPTY\n#define NONEMPTY 1\n#define INNER 8\n#endif\n",
    )
    _write(root, "Main/main2.c", '#include "nonempty_guard.h"\nint f(void){return 0;}\n')
    assert _resolve(root, "Main/main2.c", "INNER") == (None, "conditional")


def test_fake_directives_in_comments_and_strings_are_not_macros(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/header.h",
        "// #define COMMENTED 1\n"
        "/*\n"
        "#define BLOCKED 2\n"
        "*/\n"
        'const char *text = "#define IN_STRING 3";\n'
        "#define REAL 4\n",
    )
    _write(root, "Main/main.c", '#include "header.h"\nint main(void){return 0;}\n')
    assert _resolve(root, "Main/main.c", "REAL") == (4, None)
    for name in ("COMMENTED", "BLOCKED", "IN_STRING"):
        value, error = _resolve(root, "Main/main.c", name)
        assert value is None
        assert error in ("undefined", "unavailable")


def test_redefined_undef_function_like_and_unavailable_evidence_fail_closed(tmp_path):
    root = tmp_path / "proj"
    _write(root, "Main/a.h", "#define DUP 1\n#define UND 1\n#define FN(x) ((x) + 1)\n")
    _write(root, "Main/b.h", "#define DUP 2\n#undef UND\n")
    _write(
        root,
        "Main/main.c",
        '#include "a.h"\n#include "b.h"\nint main(void){return 0;}\n',
    )
    assert _resolve(root, "Main/main.c", "DUP") == (None, "redefined")
    assert _resolve(root, "Main/main.c", "UND") == (None, "undef")
    assert _resolve(root, "Main/main.c", "FN") == (None, "function-like")

    _write(root, "Main/missing.c", '#include "missing.h"\n#define KNOWN 5\n')
    assert _resolve(root, "Main/missing.c", "KNOWN") == (None, "unavailable")


def test_guard_name_defined_elsewhere_makes_the_body_conditional(tmp_path):
    root = tmp_path / "proj"
    _write(root, "Main/first.h", "#ifndef SHARED_H\n#define SHARED_H\n#define FIRST 1\n#endif\n")
    _write(root, "Main/second.h", "#ifndef SHARED_H\n#define SHARED_H\n#define SECOND 2\n#endif\n")
    _write(
        root,
        "Main/main.c",
        '#include "first.h"\n#include "second.h"\nint main(void){return 0;}\n',
    )
    assert _resolve(root, "Main/main.c", "FIRST") == (1, None)
    assert _resolve(root, "Main/main.c", "SECOND") == (None, "conditional")


def test_literal_only_values_do_not_read_headers_or_bind_dependencies(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/main.c",
        '#include "missing.h"\nint main(void){return 0;}\n',
    )
    source_text = (root / "Main" / "main.c").read_text("utf-8")
    symbols = SourceSymbols(root, "Main/main.c", source_text, ("Main",), ())
    assert symbols.evaluate("(1 << 5)") == (32, None)
    assert symbols.dependencies() == ()


def test_nested_escape_is_rejected(tmp_path):
    root = tmp_path / "proj"
    outside = tmp_path / "outside.h"
    outside.write_text("#define ESCAPED 1\n", encoding="utf-8")
    _write(root, "Main/main.c", '#include "../outside.h"\nint main(void){return 0;}\n')
    assert _resolve(root, "Main/main.c", "ESCAPED") == (None, "escape")


def test_include_search_base_parent_redirect_is_rejected(tmp_path, monkeypatch):
    import stm32_toolkit.migration.constant_context as context

    root = tmp_path / "proj"
    _write(root, "Main/main.c", '#include "base.h"\nint main(void){return 0;}\n')
    _write(root, "cfg/inc/base.h", "#define BASE_REDIRECT 1\n")
    redirected = root / "cfg"
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if os.path.normcase(str(path)) == os.path.normcase(str(redirected)):
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return result

    monkeypatch.setattr(context.os, "lstat", fake_lstat)
    value, error = _resolve(
        root, "Main/main.c", "BASE_REDIRECT", include_paths=("cfg/inc",)
    )
    assert value is None
    assert error == "redirect"


def test_line_spliced_comment_owns_fake_rules_in_constant_context(tmp_path):
    root = tmp_path / "proj"
    _write(
        root,
        "Main/header.h",
        "// #define FAKE 1 \\\n"
        "#define ALSO_FAKE 2\n"
        "#define REAL 3\n",
    )
    _write(root, "Main/main.c", '#include "header.h"\nint main(void){return 0;}\n')
    assert _resolve(root, "Main/main.c", "REAL") == (3, None)
    assert _resolve(root, "Main/main.c", "FAKE") == (None, "undefined")
    assert _resolve(root, "Main/main.c", "ALSO_FAKE") == (None, "undefined")


def test_parent_redirect_is_rejected_before_traversal(tmp_path, monkeypatch):
    import stm32_toolkit.migration.constant_context as context

    root = tmp_path / "proj"
    _write(root, "Main/cfg/base.h", "#define REDIRECTED 1\n")
    _write(root, "Main/main.c", '#include "cfg/base.h"\nint main(void){return 0;}\n')
    redirected = root / "Main" / "cfg"
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if os.path.normcase(str(path)) == os.path.normcase(str(redirected)):
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return result

    monkeypatch.setattr(context.os, "lstat", fake_lstat)
    assert _resolve(root, "Main/main.c", "REDIRECTED") == (None, "redirect")


# ---------------------------------------------------------------------------
# rules: naked assembly, alignment, placement, pragma
# ---------------------------------------------------------------------------


class _StubProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def evaluate(self, expression: str):
        try:
            return evaluate_integer(expression, _map(self.values)), None
        except ConstantResolutionError as error:
            return None, error.code

    def dependencies(self):
        return ()


class _StubSymbols:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def for_source(self, path: str, text: str) -> _StubProvider:
        return _StubProvider(self.values)


def _scan(text: str, language: str = "c", values: dict[str, str] | None = None):
    symbols = _StubSymbols(values or {}) if values is not None else None
    return rules.scan_sources([("Main/main.c", text.encode("utf-8"), language)], symbols=symbols)[0]


def test_supported_naked_assembly_wrappers_and_comment_preservation():
    text = (
        "__asm void wait_wfi(void)\n"
        "{\n"
        "    WFI /* wait */\n"
        "    BX LR\n"
        "}\n"
        "\n"
        "__asm void irq_off(void) { CPSID I BX LR }\n"
        "\n"
        "__asm void irq_on(void) { CPSIE I BX R14 }\n"
        "\n"
        "__asm void set_stack(uint32_t top)\n"
        "{\n"
        "    MSR MSP, R0\n"
        "    BX LR\n"
        "}\n"
    )
    scan = _scan(text)
    assert scan.blockers == ()
    assert scan.rule_ids == ("ARMCC_NAKED_ASM_FUNCTION",)
    after = scan.after.decode("utf-8")
    assert after.startswith(
        "__attribute__((naked)) void wait_wfi(void)\n"
        "{\n"
        '    __asm volatile ("wfi\\n\\tbx lr");\n'
        "    /* wait */\n"
        "}"
    )
    assert '__asm volatile ("cpsid i\\n\\tbx lr");' in after
    assert '__asm volatile ("cpsie i\\n\\tbx lr");' in after
    assert '__asm volatile ("msr msp, r0\\n\\tbx lr");' in after
    assert "cpsid i" in after and "cpsie i" in after


def test_naked_assembly_crlf_is_preserved():
    text = (
        "__asm void wait_wfi(void)\r\n"
        "{\r\n"
        "    WFI\r\n"
        "    BX LR\r\n"
        "}\r\n"
    )
    scan = _scan(text)
    assert scan.blockers == ()
    after = scan.after.decode("utf-8")
    assert "\r\n" in after
    assert "\n" not in after.replace("\r\n", "")


def test_naked_assembly_negative_forms_remain_blocked():
    cases = (
        "__asm void missing_bx(void) { WFI }\n",
        "__asm void extra(void) { WFI BX LR NOP }\n",
        "__asm void wrong_param(double top) { MSR MSP, R0 BX LR }\n",
        "__asm void pointer_param(unsigned int *top) { MSR MSP, R0 BX LR }\n",
        "__asm void two_params(uint32_t a, uint32_t b) { MSR MSP, R0 BX LR }\n",
        "__asm /* ambiguous */ void commented(void) { WFI BX LR }\n",
        "__asm void wfi_param(uint32_t top) { WFI BX LR }\n",
        "__asm void msp_no_param(void) { MSR MSP, R0 BX LR }\n",
    )
    for case in cases:
        scan = _scan(case)
        assert any(
            blocker.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"
            for blocker in scan.blockers
        ), case
        assert scan.after.decode("utf-8") == case

    cpp = _scan("__asm void wait_wfi(void) { WFI BX LR }\n", language="cxx")
    assert any(
        blocker.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED" for blocker in cpp.blockers
    )


def test_alignment_and_placement_composition_with_macros():
    text = (
        "__align(32) unsigned char pool[SIZE] __attribute__((at(BASE + OFFSET)));\n"
        "__at(REG_ADDR) volatile unsigned int reg;\n"
        "__align(ALIGN_BYTES) static unsigned char aligned_buf[8];\n"
        "int main(void) { return 0; }\n"
    )
    scan = _scan(
        text,
        values={
            "BASE": "0x20000000u",
            "OFFSET": "0x100",
            "SIZE": "64",
            "REG_ADDR": "(BASE + 0x400)",
            "ALIGN_BYTES": "16",
        },
    )
    assert scan.blockers == ()
    after = scan.after.decode("utf-8")
    assert after.startswith(
        '__attribute__((aligned(32))) unsigned char pool[SIZE] '
        '__attribute__((section(".stm32tk.abs.20000100"), used));\n'
    )
    assert (
        '__attribute__((section(".stm32tk.abs.20000400"), used)) '
        "volatile unsigned int reg;" in after
    )
    assert '__attribute__((aligned(16))) static unsigned char aligned_buf[8];' in after
    sections = {section.symbol: section for section in scan.fixed_sections}
    assert sections["pool"].address == 0x20000100
    assert sections["reg"].address == 0x20000400


def test_alignment_must_divide_the_fixed_address():
    mismatches = (
        ("__align(32) unsigned char pool[16] __attribute__((at(0x20000104)));\n", None),
        (
            "__align(ALIGN_BYTES) unsigned char pool[16] __at(0x20000104);\n",
            {"ALIGN_BYTES": "32"},
        ),
    )
    for case, values in mismatches:
        scan = _scan(case, values=values)
        placement = [
            blocker
            for blocker in scan.blockers
            if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
        ]
        assert len(placement) == 1, case
        assert "0x20000104 does not satisfy __align(32)" in placement[0].message, case
        assert scan.fixed_sections == (), case
        after = scan.after.decode("utf-8")
        assert "0x20000104" in after, case
        assert ".stm32tk.abs.20000104" not in after, case
        assert "__align" not in after, case

    supported = _scan(
        "__align(ALIGN_BYTES) unsigned char pool[16] __at(0x20000100);\n",
        values={"ALIGN_BYTES": "32"},
    )
    assert supported.blockers == ()
    assert [section.address for section in supported.fixed_sections] == [0x20000100]


def test_placement_literal_overflow_keeps_generic_message():
    scan = _scan("__at(0x100000000) int pinned;\n")
    placement = [
        blocker
        for blocker in scan.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    ]
    assert len(placement) == 1
    assert placement[0].message == "unsupported ARMCC absolute placement grammar"

    undefined = _scan("__at(UNDEFINED_ADDR) int pinned;\n")
    reported = next(
        blocker
        for blocker in undefined.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    )
    assert "(undefined)" in reported.message


def test_unresolved_symbolic_alignment_reports_its_reason():
    scan = _scan("__align(UNKNOWN_ALIGN) unsigned char pool[8] __at(0x20000100);\n")
    align = [
        blocker
        for blocker in scan.blockers
        if blocker.code == "ARMCC_ALIGN_UNSUPPORTED"
    ]
    assert len(align) == 1
    assert "(undefined)" in align[0].message


def test_alignment_and_placement_negative_forms_remain_blocked():
    align_cases = (
        "__align(3) int x;\n",
        "__align(0) int x;\n",
        "__align(8192) int x;\n",
        "__align(UNKNOWN_LIMIT) int x;\n",
        "__align(4) extern int x;\n",
        "__align(4) typedef int value;\n",
        "__align(4) int a, b;\n",
        "__align(4) int empty[0];\n",
        "__align(4) __attribute__((packed)) int x;\n",
    )
    for case in align_cases:
        scan = _scan(case)
        assert any(
            blocker.code == "ARMCC_ALIGN_UNSUPPORTED" for blocker in scan.blockers
        ), case
        assert scan.after.decode("utf-8") == case

    placement_cases = (
        "__at(0x20000000) int *pointer;\n",
        "__at(0x20000000) extern int external;\n",
        "__at(0x20000000) typedef int alias;\n",
        "__at(0x20000000) int zero[0];\n",
        "__at(0x20000000) int value = 1;\n",
        "__attribute__((at(0x20000000), used)) int mixed;\n",
    )
    for case in placement_cases:
        scan = _scan(case)
        assert any(
            blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
            for blocker in scan.blockers
        ), case
        assert scan.after.decode("utf-8") == case


def test_alignment_suffix_form_and_cxx_gating():
    suffix = _scan("__at(0x20000000) int pinned __align(8);\n")
    assert suffix.blockers == ()
    assert (
        suffix.after.decode("utf-8")
        == '__attribute__((section(".stm32tk.abs.20000000"), used)) int pinned '
        "__attribute__((aligned(8)));\n"
    )

    cpp_align = _scan("__align(8) int x;\n", language="cxx")
    assert any(
        blocker.code == "ARMCC_ALIGN_UNSUPPORTED" for blocker in cpp_align.blockers
    )
    assert cpp_align.after.decode("utf-8") == "__align(8) int x;\n"

    # Historically reviewed numeric C++ placement stays supported.
    cpp_placement = _scan("__at(0x20000000) int pinned;\n", language="cxx")
    assert cpp_placement.blockers == ()
    assert (
        cpp_placement.after.decode("utf-8")
        == '__attribute__((section(".stm32tk.abs.20000000"), used)) int pinned;\n'
    )


def test_no_semihosting_pragma_is_removed_without_eating_crlf_or_comment():
    text = (
        "#pragma import(__use_no_semihosting) /* keep */\r\n"
        "int main(void) { return 0; }\r\n"
    )
    scan = _scan(text)
    assert scan.blockers == ()
    assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",)
    assert scan.link_specs == ("nosys.specs",)
    assert scan.after.decode("utf-8") == " /* keep */\r\nint main(void) { return 0; }\r\n"


def test_line_spliced_comment_owns_fake_armcc_constructs():
    text = (
        "// fake placement owned by this spliced comment \\\n"
        "__at(0x60000000) int fake_placed;\n"
        "// fake assembly owned by this spliced comment \\\n"
        "__asm void fake_asm(void) { WFI BX LR }\n"
        "__at(0x20000000) int real_placed;\n"
        "int main(void) { return 0; }\n"
    )
    scan = _scan(text)
    assert scan.blockers == ()
    after = scan.after.decode("utf-8")
    assert ".stm32tk.abs.20000000" in after
    assert ".stm32tk.abs.60000000" not in after
    assert "__at(0x60000000) int fake_placed;" in after
    assert "__asm void fake_asm(void)" in after


def test_unknown_import_and_pragma_forms_keep_blockers():
    cases = (
        "#pragma import(__use_no_semihosting_extra)\n",
        "#pragma import(__use_no_semihosting)\\\n\n",
        '#pragma arm section code=".x"\n',
        "#pragma O3\n",
    )
    for case in cases:
        scan = _scan(case + "int main(void) { return 0; }\n")
        assert any(
            blocker.code == "ARMCC_PRAGMA_UNSUPPORTED" for blocker in scan.blockers
        ), case


# ---------------------------------------------------------------------------
# public preflight -> PLAN -> apply -> configure flow
# ---------------------------------------------------------------------------


def _syntax_repo(tmp_path: Path, name: str = "syntax") -> Path:
    return build_repo(
        tmp_path,
        name=name,
        files={
            "Main/main.c": MAIN_C,
            "Main/board.h": BOARD_H,
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


def test_public_flow_produces_supported_changes_and_nosys_specs(tmp_path):
    repo = _syntax_repo(tmp_path)
    inspection = fixture_inspection(repo)

    preflight = preflight_keil_conversion(repo, inspection)
    assert preflight["analysis"]["blockers"] == []
    changes = preflight["analysis"]["sourceChanges"]
    by_path = {change["path"]: change for change in changes}
    main_change = by_path["Main/main.c"]
    assert "ARMCC_NO_SEMIHOSTING_PRAGMA" in main_change["ruleIds"]
    assert "ARMCC_NAKED_ASM_FUNCTION" in main_change["ruleIds"]
    assert "ARMCC_ALIGN_ATTRIBUTE" in main_change["ruleIds"]
    assert "ARMCC_ABSOLUTE_PLACEMENT" in main_change["ruleIds"]
    assert by_path[".stm32-project.json"]["ruleIds"] == ["MIGRATION_MANIFEST"]
    for change in changes:
        assert set(change) == {"path", "ruleIds", "beforeSha256", "afterSha256"}

    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    after = patch.after_bytes.decode("utf-8")
    assert "#pragma import" not in after
    assert "/* keep */" in after
    assert "__asm void" not in after
    assert "__align" not in after
    assert "__at(" not in after
    assert '__asm volatile ("wfi\\n\\tbx lr");' in after
    assert "__attribute__((aligned(32))) unsigned char pool[SIZE]" in after
    assert '__attribute__((section(".stm32tk.abs.20000100"), used));' in after

    manifest_patch = next(
        p for p in plan.patches if p.path == ".stm32-project.json"
    )
    manifest = manifest_patch.after_bytes.decode("utf-8")
    assert '"newlibSpecs": [\n      "nosys.specs"\n    ]' in manifest

    dependency_inputs = {entry.path: entry for entry in plan.inputs}
    header_bytes = (repo / "Main" / "board.h").read_bytes()
    assert dependency_inputs["Main/board.h"].sha256 == hashlib.sha256(
        header_bytes
    ).hexdigest()

    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    assert (repo / "artifacts/migration/conversion-report.json").is_file()

    configuration = plan_project_configuration(load_project_model(repo))
    assert configuration.blockers == ()
    cmake = next(
        entry
        for entry in configuration.files
        if entry.path == "CMakeLists.txt"
    ).after_bytes.decode("utf-8")
    assert cmake.count('"--specs=nosys.specs"') == 1
    assert '"--specs=nano.specs"' not in cmake
    linker = next(
        entry for entry in configuration.files if entry.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert ".stm32tk.abs.20000100" in linker
    assert ".stm32tk.abs.20000400" in linker


def test_public_flow_blocks_stale_symbol_dependency_before_writing(tmp_path):
    repo = _syntax_repo(tmp_path, name="stale")
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert plan.blockers == ()

    header = repo / "Main" / "board.h"
    header.write_bytes(header.read_bytes().replace(b"0x100", b"0x200"))
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_INPUT_CHANGED"


def test_apply_refuses_a_new_source_adjacent_shadowing_header(tmp_path):
    repo = build_repo(
        tmp_path,
        name="shadow",
        files={
            "Main/main.c": (
                '#include "board.h"\n'
                "__at(PLACED) volatile unsigned int pinned;\n"
                "int main(void) { return (int)pinned; }\n"
            ),
            "Inc/board.h": (
                "#ifndef BOARD_H\n"
                "#define BOARD_H\n"
                "#define PLACED 0x20000000\n"
                "#endif\n"
            ),
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;Inc;{FRAMEWORK_INCLUDE}",
        },
        # The new shadowing header is intentionally Git-ignored so only the
        # fresh-plan include-resolution boundary, not a dirty-worktree check,
        # is exercised.
        gitignore="Main/board.h\n",
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    assert plan.blockers == ()
    assert any(entry.path == "Inc/board.h" for entry in plan.inputs)
    original_main = (repo / "Main" / "main.c").read_bytes()

    # A new, ignored, source-adjacent header wins the include search order.
    (repo / "Main" / "board.h").write_bytes(
        b"#ifndef BOARD_H\n#define BOARD_H\n#define PLACED 0x20000400\n#endif\n"
    )
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details.get("rule") == "freshPlan"
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts").exists()
    assert (repo / "Main" / "main.c").read_bytes() == original_main
    assert (repo / "Main" / "board.h").is_file()


def test_public_flow_reports_out_of_memory_placement_as_needs_user_input(tmp_path):
    repo = build_repo(
        tmp_path,
        name="outside",
        files={
            "Main/main.c": (
                "__at(0x60000000) int external_buffer;\n"
                "int main(void) { return 0; }\n"
            )
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    outside = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY"
    ]
    assert len(outside) == 1
    assert outside[0].path == "Main/main.c"
    preflight = preflight_keil_conversion(repo, inspection)
    reported = next(
        blocker
        for blocker in preflight["analysis"]["blockers"]
        if blocker["code"] == "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY"
    )
    assert reported["remediation"]["category"] == "needs-user-input"


def test_public_flow_keeps_unknown_and_conflicting_macros_blocked(tmp_path):
    repo = build_repo(
        tmp_path,
        name="conflict",
        files={
            "Main/main.c": (
                '#include "first.h"\n'
                '#include "second.h"\n'
                "__at(CONFLICT) int pinned;\n"
                "__at(UNKNOWN_ADDR) int other;\n"
                "int main(void) { return 0; }\n"
            ),
            "Main/first.h": "#define CONFLICT 0x20000000\n",
            "Main/second.h": "#define CONFLICT 0x20000000\n",
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    placement = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    ]
    assert len(placement) == 2
    assert plan.fixed_sections == ()
    assert not any(p.path == "Main/main.c" and b"section(" in p.after_bytes for p in plan.patches)


def test_public_flow_blocks_incompatible_alignment_and_fixed_address(tmp_path):
    repo = build_repo(
        tmp_path,
        name="misaligned",
        files={
            "Main/main.c": (
                '#include "board.h"\n'
                "__align(ALIGN) unsigned char pool[16] __at(PLACED);\n"
                "int main(void) { return (int)pool[0]; }\n"
            ),
            "Main/board.h": (
                "#ifndef BOARD_H\n"
                "#define BOARD_H\n"
                "#define ALIGN 32\n"
                "#define PLACED 0x20000104\n"
                "#endif\n"
            ),
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    inspection = fixture_inspection(repo)
    plan = plan_keil_conversion(repo, inspection)
    placement = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    ]
    assert len(placement) == 1
    assert placement[0].path == "Main/main.c"
    assert "0x20000104 does not satisfy __align(32)" in placement[0].message
    assert plan.fixed_sections == ()
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    after = patch.after_bytes.decode("utf-8")
    assert "__at(PLACED)" in after
    assert ".stm32tk.abs.20000104" not in after

    preflight = preflight_keil_conversion(repo, inspection)
    reported = next(
        blocker
        for blocker in preflight["analysis"]["blockers"]
        if blocker["code"] == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    )
    assert "0x20000104 does not satisfy __align(32)" in reported["message"]
    changes = {
        change["path"]: change for change in preflight["analysis"]["sourceChanges"]
    }
    assert "ARMCC_ABSOLUTE_PLACEMENT" not in changes["Main/main.c"]["ruleIds"]
    assert "ARMCC_ALIGN_ATTRIBUTE" in changes["Main/main.c"]["ruleIds"]


def test_public_flow_surfaces_symbolic_placement_resolution_reason(tmp_path):
    cases = (
        (
            "conditional",
            {
                "Main/main.c": (
                    '#include "config.h"\n'
                    "__at(PLACED) int pinned;\n"
                    "int main(void) { return (int)pinned; }\n"
                ),
                "Main/config.h": (
                    "#ifdef FEATURE\n#define PLACED 0x20000100\n#endif\n"
                ),
            },
            "conditional",
        ),
        (
            "undefined",
            {
                "Main/main.c": (
                    "__at(UNDEFINED_ADDR) int pinned;\n"
                    "int main(void) { return (int)pinned; }\n"
                ),
            },
            "undefined",
        ),
    )
    for name, files, reason in cases:
        repo = build_repo(
            tmp_path,
            name=name,
            files=files,
            uvprojx_kwargs={
                "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            },
        )
        preflight = preflight_keil_conversion(repo, fixture_inspection(repo))
        blocker = next(
            blocker
            for blocker in preflight["analysis"]["blockers"]
            if blocker["code"] == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
        )
        assert f"({reason})" in blocker["message"]


def test_public_flow_supports_pragma_with_long_trailing_comment(tmp_path):
    comment = "/* " + "keep-comment " * 20 + "*/"
    assert len(comment) > 200
    repo = build_repo(
        tmp_path,
        name="longpragma",
        files={
            "Main/main.c": (
                f"#pragma import(__use_no_semihosting) {comment}\n"
                "int main(void) { return 0; }\n"
            )
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    inspection = fixture_inspection(repo)
    preflight = preflight_keil_conversion(repo, inspection)
    assert preflight["analysis"]["blockers"] == []
    changes = {
        change["path"]: change for change in preflight["analysis"]["sourceChanges"]
    }
    assert changes["Main/main.c"]["ruleIds"] == ["ARMCC_NO_SEMIHOSTING_PRAGMA"]

    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patch = next(p for p in plan.patches if p.path == "Main/main.c")
    after = patch.after_bytes.decode("utf-8")
    assert "#pragma import" not in after
    assert comment in after
    manifest = next(
        p for p in plan.patches if p.path == ".stm32-project.json"
    ).after_bytes.decode("utf-8")
    assert '"newlibSpecs": [\n      "nosys.specs"\n    ]' in manifest


def test_public_flow_keeps_long_unknown_import_blocked(tmp_path):
    comment = "/* " + "keep-going " * 20 + "*/"
    repo = build_repo(
        tmp_path,
        name="longunknown",
        files={
            "Main/main.c": (
                f"#pragma import(__use_no_semihosting_extra) {comment}\n"
                "int main(void) { return 0; }\n"
            )
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
        },
    )
    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    blockers = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert blockers
    assert not any(
        b"nosys.specs" in patch.after_bytes for patch in plan.patches
    )
