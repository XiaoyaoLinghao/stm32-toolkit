"""v1.3.4 structural include-guard regressions.

Synthetic ``SourceSymbols``-only tests for the whole-file include guard in the
audited ``MALLOC/malloc.h`` shape: a balanced nested ``#ifndef NULL`` block
ahead of the unconditional ``MEM*_BLOCK_SIZE`` constants.  Only the guard's own
opening and closing directives may be exempt from conditional depth; every
definition inside a nested group keeps conditional provenance.  No compiler,
probe, network, installed runtime or project fixture participates.
"""

from __future__ import annotations

from pathlib import Path

from stm32_toolkit.migration.constant_context import SourceSymbols


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _symbols_for_header(root: Path, header: str) -> SourceSymbols:
    _write(
        root,
        "Main/main.c",
        '#include "candidate.h"\nint main(void) { return 0; }\n',
    )
    _write(root, "Main/candidate.h", header)
    text = (root / "Main" / "main.c").read_text("utf-8")
    return SourceSymbols(root, "Main/main.c", text, ("Main",), ())


def _dependencies(symbols: SourceSymbols) -> set[str]:
    return {path for path, _digest, _size in symbols.dependencies()}


# ---------------------------------------------------------------------------
# structural guard with balanced nested conditionals
# ---------------------------------------------------------------------------


def test_nested_null_guard_keeps_mem_constants_resolvable(tmp_path):
    symbols = _symbols_for_header(
        tmp_path / "nested-null",
        "#ifndef __MALLOC_H\n"
        "#define __MALLOC_H\n"
        "\n"
        "#ifndef NULL\n"
        "#define NULL ((void *)0)\n"
        "#endif\n"
        "\n"
        "#define MEM1_BLOCK_SIZE 110\n"
        "#define MEM2_BLOCK_SIZE 200\n"
        "#define MEM3_BLOCK_SIZE (60 * 1024)\n"
        "\n"
        "#endif\n",
    )

    assert symbols.evaluate("MEM1_BLOCK_SIZE") == (110, None)
    assert symbols.evaluate("MEM2_BLOCK_SIZE") == (200, None)
    assert symbols.evaluate("MEM3_BLOCK_SIZE") == (60 * 1024, None)
    # The nested block is still a real conditional region.
    assert symbols.evaluate("NULL") == (None, "conditional")
    assert _dependencies(symbols) == {"Main/candidate.h"}


def test_simple_guard_without_nesting_still_resolves(tmp_path):
    symbols = _symbols_for_header(
        tmp_path / "simple-guard",
        "#ifndef PLAIN_H\n#define PLAIN_H\n#define VALUE 3\n#endif\n",
    )
    assert symbols.evaluate("VALUE") == (3, None)


def test_nested_groups_pair_by_depth_not_by_directive_count(tmp_path):
    symbols = _symbols_for_header(
        tmp_path / "depth-two",
        "#ifndef DEEP_H\n"
        "#define DEEP_H\n"
        "#if ENABLED_A\n"
        "#if ENABLED_B\n"
        "#define INNER 1\n"
        "#endif\n"
        "#endif\n"
        "#define OUTER 2\n"
        "#endif\n",
    )
    assert symbols.evaluate("INNER") == (None, "conditional")
    assert symbols.evaluate("OUTER") == (2, None)


def test_nested_conditional_macros_and_includes_stay_conditional(tmp_path):
    root = tmp_path / "nested-conditional"
    _write(
        root,
        "Main/extra.h",
        "#ifndef EXTRA_H\n#define EXTRA_H\n#define EXTRA 9\n#endif\n",
    )
    symbols = _symbols_for_header(
        root,
        "#ifndef CFG_H\n"
        "#define CFG_H\n"
        "#if defined(NEEDED)\n"
        "#define MAYBE 5\n"
        '#include "extra.h"\n'
        "#endif\n"
        "#define ALWAYS 7\n"
        "#endif\n",
    )
    assert symbols.evaluate("MAYBE") == (None, "conditional")
    assert symbols.evaluate("EXTRA") == (None, "conditional")
    assert symbols.evaluate("ALWAYS") == (7, None)


def test_inner_branches_are_permitted_inside_a_nested_group(tmp_path):
    symbols = _symbols_for_header(
        tmp_path / "inner-else",
        "#ifndef INNER_ELSE_H\n"
        "#define INNER_ELSE_H\n"
        "#if defined(SELECTED)\n"
        "#define PRIMARY 1\n"
        "#else\n"
        "#define FALLBACK 2\n"
        "#endif\n"
        "#define OUTER 3\n"
        "#endif\n",
    )
    assert symbols.evaluate("PRIMARY") == (None, "conditional")
    assert symbols.evaluate("FALLBACK") == (None, "conditional")
    assert symbols.evaluate("OUTER") == (3, None)


# ---------------------------------------------------------------------------
# negative controls: no structural guard is proven
# ---------------------------------------------------------------------------


def test_guard_level_branch_directives_leave_values_conditional(tmp_path):
    cases = (
        (
            "outer-else",
            "#ifndef ONLY_ELSE_H\n"
            "#define ONLY_ELSE_H\n"
            "#define VALUE 1\n"
            "#else\n"
            "#define OTHER 2\n"
            "#endif\n",
        ),
        (
            "outer-elif",
            "#ifndef ONLY_ELIF_H\n"
            "#define ONLY_ELIF_H\n"
            "#define VALUE 1\n"
            "#elif defined(CONFIGURE)\n"
            "#define OTHER 2\n"
            "#endif\n",
        ),
    )
    for name, header in cases:
        symbols = _symbols_for_header(tmp_path / name, header)
        assert symbols.evaluate("VALUE") == (None, "conditional"), name
        assert symbols.evaluate("OTHER") == (None, "conditional"), name


def test_malformed_or_nonmatching_guard_names_leave_values_conditional(tmp_path):
    cases = (
        (
            "trailing-token",
            "#ifndef TRAILING H\n#define TRAILING\n#define VALUE 1\n#endif\n",
        ),
        ("missing-name", "#ifndef\n#define NAMELESS\n#define VALUE 1\n#endif\n"),
        (
            "unrelated-define",
            "#ifndef GUARD_H\n#define OTHER_H\n#define VALUE 1\n#endif\n",
        ),
        (
            "nonempty-define",
            "#ifndef NONEMPTY_H\n#define NONEMPTY_H 1\n#define VALUE 1\n#endif\n",
        ),
        (
            "late-define",
            "#ifndef LATE_H\n#define VALUE 1\n#define LATE_H\n#endif\n",
        ),
        (
            "function-like-define",
            "#ifndef FN_H\n#define FN_H(x) 1\n#define VALUE 1\n#endif\n",
        ),
    )
    for name, header in cases:
        symbols = _symbols_for_header(tmp_path / name, header)
        assert symbols.evaluate("VALUE") == (None, "conditional"), name


def test_unbalanced_guard_endings_leave_values_conditional(tmp_path):
    cases = (
        (
            "premature-close",
            "#ifndef EARLY_H\n"
            "#define EARLY_H\n"
            "#define VALUE 1\n"
            "#endif\n"
            "#define TAIL 2\n"
            "#endif\n",
            ("VALUE",),
            (("TAIL", 2),),
        ),
        (
            "extra-final-endif",
            "#ifndef EXTRA_END_H\n#define EXTRA_END_H\n#define VALUE 1\n#endif\n#endif\n",
            ("VALUE",),
            (),
        ),
        (
            "unclosed-nested-open",
            "#ifndef UNCLOSED_H\n"
            "#define UNCLOSED_H\n"
            "#if ENABLED\n"
            "#define VALUE 1\n"
            "#define TAIL 2\n"
            "#endif\n",
            ("VALUE", "TAIL"),
            (),
        ),
        (
            "torn-open",
            "#ifndef TORN_H\n#define TORN_H\n#if ENABLED\n#define VALUE 1\n",
            ("VALUE",),
            (),
        ),
    )
    for name, header, conditionals, resolvable in cases:
        symbols = _symbols_for_header(tmp_path / name, header)
        for macro in conditionals:
            assert symbols.evaluate(macro) == (None, "conditional"), (name, macro)
        # A premature close leaves later directives at outer level, which is
        # exactly why such a file is never reported as a proven guard.
        for macro, value in resolvable:
            assert symbols.evaluate(macro) == (value, None), (name, macro)


def test_duplicate_guard_names_still_leave_the_second_body_conditional(tmp_path):
    root = tmp_path / "duplicate-guard"
    _write(
        root,
        "Main/first.h",
        "#ifndef SHARED_H\n#define SHARED_H\n#define FIRST 1\n#endif\n",
    )
    _write(
        root,
        "Main/second.h",
        "#ifndef SHARED_H\n#define SHARED_H\n#define SECOND 2\n#endif\n",
    )
    _write(
        root,
        "Main/main.c",
        '#include "first.h"\n#include "second.h"\nint main(void) { return 0; }\n',
    )
    text = (root / "Main" / "main.c").read_text("utf-8")
    symbols = SourceSymbols(root, "Main/main.c", text, ("Main",), ())

    assert symbols.evaluate("FIRST") == (1, None)
    assert symbols.evaluate("SECOND") == (None, "conditional")


def test_structural_guard_does_not_bypass_undef_refusal(tmp_path):
    symbols = _symbols_for_header(
        tmp_path / "guard-undef",
        "#ifndef UNDEF_H\n#define UNDEF_H\n#define GONE 1\n#undef GONE\n#endif\n",
    )
    assert symbols.evaluate("GONE") == (None, "undef")
