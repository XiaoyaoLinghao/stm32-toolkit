"""Refusal boundaries for bounded integer constants and include context.

These are offline, synthetic tests for the existing Keil-migration decision
code.  They add no product behavior: every case asserts a stable failure
category on a real boundary, and neighboring controls keep the boundary
meaningful.  No compiler, probe, network or installed runtime is used.
"""

from __future__ import annotations

import contextlib
import os

import pytest

from stm32_toolkit.migration import apply_keil_conversion, plan_keil_conversion
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.constant_context import (
    MAX_EXPRESSION_CHARS,
    ConstantResolutionError,
    SourceSymbols,
    SymbolSource,
    evaluate_integer,
)

from test_migration_plan import (
    FRAMEWORK_INCLUDE,
    build_repo,
    fixture_inspection,
    snapshot_tree,
)


def _lookup(values: dict[str, str]):
    def lookup(name: str) -> str:
        if name not in values:
            raise ConstantResolutionError("undefined", f"no {name}")
        return values[name]

    return lookup


def _error_code(expression: str, values: dict[str, str] | None = None) -> str:
    with pytest.raises(ConstantResolutionError) as raised:
        evaluate_integer(expression, _lookup(dict(values or {})))
    return raised.value.code


def _write(root, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _source_symbols(root, rel: str, *, include_paths=("Main",), defines=()):
    text = (root / rel).read_text("utf-8")
    return SourceSymbols(root, rel, text, tuple(include_paths), tuple(defines))


# ---------------------------------------------------------------------------
# bounded integer expressions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("1 ? 2 : 3", "syntax"),
        ("1 == 1", "syntax"),
        ("1 && 1", "syntax"),
        ("1 2", "syntax"),
        ("1.5", "syntax"),
        ("'a'", "syntax"),
        ("", "syntax"),
        ("1uu", "non-integer"),
        ("0x10lul", "non-integer"),
        ("1e3", "non-integer"),
        ("0b101", "non-integer"),
    ],
)
def test_expression_rejects_unsupported_tokens_and_suffixes(expression, code):
    assert _error_code(expression) == code


def test_expression_accepts_standard_unsigned_and_long_suffixes():
    for expression, expected in (
        ("1u", 1),
        ("2UL", 2),
        ("3ll", 3),
        ("4ull", 4),
        ("0x10lu", 16),
        ("0XfFu", 255),
    ):
        assert evaluate_integer(expression, _lookup({})) == expected


@pytest.mark.parametrize(
    ("expression", "values", "code"),
    [
        ("-1", {}, "nonnegative"),
        ("0 - 1", {}, "nonnegative"),
        ("1 - 2", {}, "nonnegative"),
        ("0x80000000 + 0x80000000", {}, "overflow"),
        ("0xFFFFFFFF + 1", {}, "overflow"),
        ("0x10000 * 0x10000", {}, "overflow"),
        ("0xFFFFFFFF << 1", {}, "overflow"),
        ("1 % 0", {}, "syntax"),
        ("A / B", {"A": "8", "B": "0"}, "syntax"),
        ("1 % ZERO", {"ZERO": "0"}, "syntax"),
    ],
)
def test_expression_rejects_negative_intermediates_overflow_and_zero_divisors(
    expression, values, code
):
    assert _error_code(expression, values) == code


def test_expression_accepts_exact_unsigned_boundaries():
    empty = _lookup({})
    assert evaluate_integer("-0", empty) == 0
    assert evaluate_integer("+0", empty) == 0
    assert evaluate_integer("2 - 2", empty) == 0
    assert evaluate_integer("0xFFFFFFFF", empty) == 0xFFFFFFFF
    assert evaluate_integer("1 << 31", empty) == 0x80000000
    assert evaluate_integer("0xFFFFFFFF >> 31", empty) == 1
    assert evaluate_integer("0xFFFFFFFF % 0x10000", empty) == 0xFFFF


def test_parenthesis_and_expression_budget_boundaries():
    assert evaluate_integer("(" * 15 + "1" + ")" * 15, _lookup({})) == 1
    assert _error_code("(" * 16 + "1" + ")" * 16) == "limit"

    for expression in ("(", "(1", "1)", "()", "(1))", "1 +"):
        assert _error_code(expression) == "syntax", expression

    allowed = " " * (MAX_EXPRESSION_CHARS - 1) + "1"
    assert len(allowed) == MAX_EXPRESSION_CHARS
    assert evaluate_integer(allowed, _lookup({})) == 1
    assert _error_code(" " * MAX_EXPRESSION_CHARS + "1") == "limit"

    allowed_tokens = "1" + " + 1" * 255
    assert evaluate_integer(allowed_tokens, _lookup({})) == 256
    assert _error_code("1" + " + 1" * 256) == "limit"


def test_macro_expansion_depth_replacement_and_token_budgets_are_controlled():
    def chain(length: int) -> dict[str, str]:
        values = {f"M{index}": f"M{index + 1}" for index in range(length)}
        values[f"M{length}"] = "1"
        return values

    assert evaluate_integer("M0", _lookup(chain(10))) == 1
    assert _error_code("M0", chain(30)) == "limit"

    assert _error_code("A + B", {"A": "B", "B": "A"}) == "cycle"
    assert _error_code("A", {"A": "B", "B": "C", "C": "B"}) == "cycle"

    boundary_replacement = "1" + " " * (MAX_EXPRESSION_CHARS - 1)
    assert evaluate_integer("A", _lookup({"A": boundary_replacement})) == 1
    assert _error_code("A", {"A": boundary_replacement + " "}) == "limit"

    doubling = {
        f"D{index}": f"D{index + 1} + D{index + 1}" for index in range(12)
    }
    doubling["D12"] = "1"
    assert _error_code("D0", doubling) == "limit"
    assert evaluate_integer("D0", _lookup({"D0": "D1 + D1", "D1": "1"})) == 2


# ---------------------------------------------------------------------------
# macro and include context
# ---------------------------------------------------------------------------


def test_source_symbols_reports_target_define_conflicts_and_empty_values(tmp_path):
    root = tmp_path / "define-conflict"
    _write(
        root,
        "Main/main.c",
        '#include "defs.h"\nint main(void) { return 0; }\n',
    )
    _write(
        root,
        "Main/defs.h",
        "#define CONFLICT 0x20000000\n#define REAL 4\n",
    )
    symbols = _source_symbols(
        root,
        "Main/main.c",
        defines=("CONFLICT=0x20000000", "FN(x)=1", "EMPTY=", "BAD-NAME=1"),
    )

    assert symbols.evaluate("CONFLICT") == (None, "redefined")
    assert symbols.evaluate("FN") == (None, "function-like")
    assert symbols.evaluate("EMPTY") == (None, "non-integer")
    assert symbols.evaluate("BAD") == (None, "undefined")
    assert symbols.evaluate("REAL") == (4, None)


def test_source_symbols_treats_system_include_names_as_unavailable(tmp_path):
    root = tmp_path / "system-include"
    _write(
        root,
        "Main/main.c",
        "#include <stdint.h>\n#define LOCAL 9\nint main(void) { return 0; }\n",
    )
    symbols = _source_symbols(root, "Main/main.c")

    # A source-local literal remains usable; only an otherwise unknown name
    # inherits the conservative "a system header may define it" evidence.
    assert symbols.evaluate("LOCAL") == (9, None)
    assert symbols.evaluate("MISSING") == (None, "unavailable")


def test_source_symbols_rejects_unreadable_and_non_contained_include_targets(tmp_path):
    invalid_root = tmp_path / "invalid-encoding"
    _write(
        invalid_root,
        "Main/main.c",
        '#include "bad.h"\nint main(void) { return 0; }\n',
    )
    (invalid_root / "Main" / "bad.h").write_bytes(b"#define BAD 1\n\xff\n")
    assert _source_symbols(invalid_root, "Main/main.c").evaluate("BAD") == (
        None,
        "unreadable",
    )

    directory_root = tmp_path / "directory-target"
    _write(
        directory_root,
        "Main/main.c",
        '#include "dir.h"\nint main(void) { return 0; }\n',
    )
    (directory_root / "Main" / "dir.h").mkdir()
    assert _source_symbols(directory_root, "Main/main.c").evaluate("X") == (
        None,
        "unreadable",
    )

    absolute_root = tmp_path / "absolute-include"
    _write(
        absolute_root,
        "Main/main.c",
        '#include "C:/outside.h"\nint main(void) { return 0; }\n',
    )
    assert _source_symbols(absolute_root, "Main/main.c").evaluate("X") == (
        None,
        "escape",
    )

    backslash_root = tmp_path / "backslash-include"
    _write(
        backslash_root,
        "Main/main.c",
        '#include "Main\\bad.h"\nint main(void) { return 0; }\n',
    )
    assert _source_symbols(backslash_root, "Main/main.c").evaluate("X") == (
        None,
        "escape",
    )


def test_source_symbols_bounds_include_depth_and_component_count(tmp_path):
    component_root = tmp_path / "component-budget"
    components = "/".join(["d"] * 17)
    _write(
        component_root,
        "Main/main.c",
        f'#include "{components}/leaf.h"\nint main(void) {{ return 0; }}\n',
    )
    assert _source_symbols(component_root, "Main/main.c").evaluate("LEAF") == (
        None,
        "limit",
    )

    depth_root = tmp_path / "depth-budget"
    _write(
        depth_root,
        "Main/main.c",
        '#include "d0.h"\nint main(void) { return 0; }\n',
    )
    for index in range(8):
        _write(
            depth_root,
            f"Main/d{index}.h",
            f'#include "d{index + 1}.h"\n',
        )
    _write(depth_root, "Main/d8.h", "#define LEAF 1\n")
    assert _source_symbols(depth_root, "Main/main.c").evaluate("LEAF") == (
        None,
        "limit",
    )


def test_case_ambiguous_include_is_a_controlled_refusal(tmp_path, monkeypatch):
    """The ambiguity is injected at the OS directory-listing boundary.

    This host's case-insensitive filesystem cannot physically hold two names
    that differ only by case.  The injected listing adds one deterministic
    case variant; the resolver's own case-folded ambiguity decision is the
    code under test and is left unchanged.
    """
    import stm32_toolkit.migration.constant_context as context

    root = tmp_path / "ambiguous-include"
    _write(
        root,
        "Main/main.c",
        '#include "Board.h"\nint main(void) { return 0; }\n',
    )
    _write(root, "Main/Board.h", "#define AMBIGUOUS 1\n")
    target = root / "Main"
    real_scandir = os.scandir

    class _NamedEntry:
        def __init__(self, name: str) -> None:
            self.name = name

    @contextlib.contextmanager
    def injected_scandir(path):
        with real_scandir(path) as iterator:
            names = [entry.name for entry in iterator]
        if os.path.normcase(str(path)) == os.path.normcase(str(target)):
            names.append("board.h")
        yield iter([_NamedEntry(name) for name in names])

    monkeypatch.setattr(context.os, "scandir", injected_scandir)

    symbols = _source_symbols(root, "Main/main.c")
    assert symbols.evaluate("AMBIGUOUS") == (None, "ambiguous")
    assert symbols.dependencies() == ()


def test_scan_sources_keeps_bytes_when_include_context_is_unreadable(tmp_path):
    root = tmp_path / "scan-unreadable"
    text = (
        '#include "bad.h"\n'
        "__at(PLACED) volatile unsigned int pinned;\n"
        "int main(void) { return (int)pinned; }\n"
    )
    _write(root, "Main/main.c", text)
    (root / "Main" / "bad.h").write_bytes(b"#define PLACED 0x20000000\n\xff\n")
    raw = (root / "Main" / "main.c").read_bytes()
    symbols = SymbolSource(root, ("Main",), ())

    scan = rules.scan_sources([("Main/main.c", raw, "c")], symbols=symbols)[0]

    assert scan.after == raw
    assert scan.fixed_sections == ()
    placement = [
        blocker
        for blocker in scan.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    ]
    assert len(placement) == 1
    assert placement[0].line == 2
    assert "__at(PLACED)" in placement[0].evidence
    assert "(unreadable)" in placement[0].message


def test_blocked_redefined_constant_plan_preserves_project_and_writes_nothing(
    tmp_path,
):
    repo = build_repo(
        tmp_path,
        name="redefined-constant",
        files={
            "Main/main.c": (
                '#include "defs.h"\n'
                "__at(PLACED) volatile unsigned int pinned;\n"
                "int main(void) { return (int)pinned; }\n"
            ),
            "Main/defs.h": (
                "#ifndef DEFS_H\n"
                "#define DEFS_H\n"
                "#define PLACED 0x20000000\n"
                "#endif\n"
            ),
        },
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
            "defines": "USE_STDPERIPH_DRIVER,PLACED=0x20000000",
        },
    )
    before = snapshot_tree(repo)

    plan = plan_keil_conversion(repo, fixture_inspection(repo))
    placement = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED"
    ]
    assert len(placement) == 1
    assert placement[0].path == "Main/main.c"
    assert "(redefined)" in placement[0].message
    assert plan.fixed_sections == ()
    assert not any(
        patch.path == "Main/main.c" and b".stm32tk.abs." in patch.after_bytes
        for patch in plan.patches
    )

    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED" in result.details["blockerCodes"]
    assert snapshot_tree(repo) == before
    assert not (repo / ".stm32-project.json").exists()
    assert not (repo / "artifacts").exists()
    assert (repo / "Main" / "defs.h").is_file()
