"""Bounded quoted-header encoding discovery regressions.

Public ``discover_header_encodings`` behavior is exercised against real
temporary files: quoted edges, refusals, comment/string controls,
deterministic ordering, read-only behavior and every explicit budget.  Two
integration checks keep the raw reader and the scanner/preflight layers
honest: the exact invalid bytes stay readable without ever being decoded, and
an encoding-clean guarded header still resolves the reported ARMCC shapes.
Nothing here transcodes, edits product files, or uses a compiler, probe or
network.
"""

from __future__ import annotations

from pathlib import Path

from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import header_encoding, rules
from stm32_toolkit.migration.constant_context import (
    SourceSymbols,
    SymbolSource,
    _MacroIndex,
)
from stm32_toolkit.migration.header_encoding import discover_header_encodings
from stm32_toolkit.migration.preflight import preflight_keil_conversion

from test_migration_plan import build_repo, snapshot_tree

#: A GBK comment makes a file undecodable as strict UTF-8 while its ASCII
#: directives are unchanged beneath it; no byte or encoding may be guessed.
GBK_COMMENT = b"/* \xd6\xd0\xce\xc4 */\n"


def _write(root: Path, rel: str, content: str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))
    return path


def _inventory(
    root: Path,
    sources: tuple[str, ...] = ("Main/main.c",),
    include_paths: tuple[str, ...] = (),
    expected: dict[str, tuple[str, int]] | None = None,
) -> dict[str, object]:
    return discover_header_encodings(
        root, sources, include_paths, expected or {}
    )


#: The reported declaration shapes: three ``__align(4)`` arrays plus four
#: absolute placements.  The include occupies line 1.
DECLARATIONS = (
    '#include "malloc.h"\n'
    "__align(4) u8 mem1base[MEM1_MAX_SIZE];\n"
    "__align(4) u8 mem2base[MEM2_MAX_SIZE] __attribute__((at(0x68000000)));\n"
    "__align(4) u8 mem3base[MEM3_MAX_SIZE] __attribute__((at(0x10000000)));\n"
    "u16 mem2mapbase[MEM2_ALLOC_TABLE_SIZE] "
    "__attribute__((at(0X68000000+MEM2_MAX_SIZE)));\n"
    "u16 mem3mapbase[MEM3_ALLOC_TABLE_SIZE] "
    "__attribute__((at(0X10000000+MEM3_MAX_SIZE)));\n"
)

#: The audited ``MALLOC/malloc.h`` shape: a whole-file ``#ifndef`` guard with an
#: independent, balanced ``#ifndef NULL`` block ahead of the constants.
GUARDED_MALLOC_H = (
    "#ifndef MALLOC_H\n"
    "#define MALLOC_H\n"
    "\n"
    "#ifndef NULL\n"
    "#define NULL ((void *)0)\n"
    "#endif\n"
    "\n"
    "#define MEM1_MAX_SIZE 110*1024\n"
    "#define MEM2_MAX_SIZE 200*1024\n"
    "#define MEM3_MAX_SIZE 60*1024\n"
    "#define MEM1_BLOCK_SIZE 32\n"
    "#define MEM2_BLOCK_SIZE 32\n"
    "#define MEM3_BLOCK_SIZE 32\n"
    "#define MEM1_ALLOC_TABLE_SIZE MEM1_MAX_SIZE/MEM1_BLOCK_SIZE\n"
    "#define MEM2_ALLOC_TABLE_SIZE MEM2_MAX_SIZE/MEM2_BLOCK_SIZE\n"
    "#define MEM3_ALLOC_TABLE_SIZE MEM3_MAX_SIZE/MEM3_BLOCK_SIZE\n"
    "#endif\n"
)


# ---------------------------------------------------------------------------
# scanner integration: the reported shapes still convert with a guarded header
# ---------------------------------------------------------------------------


def test_guarded_header_resolves_reported_alignment_and_placements(tmp_path):
    root = tmp_path / "guarded"
    _write(root, "Main/malloc.c", DECLARATIONS)
    _write(root, "Main/malloc.h", GUARDED_MALLOC_H)

    raw = (root / "Main" / "malloc.c").read_bytes()
    symbols = SymbolSource(root, ("Main",), ())
    scan = rules.scan_sources([("Main/malloc.c", raw, "c")], symbols=symbols)[0]

    assert scan.blockers == ()
    assert set(scan.rule_ids) == {
        "ARMCC_ALIGN_ATTRIBUTE",
        "ARMCC_ABSOLUTE_PLACEMENT",
    }
    after = scan.after.decode("utf-8")
    assert after.count("__attribute__((aligned(4)))") == 3
    assert '__attribute__((section(".stm32tk.abs.68000000"), used))' in after
    assert '__attribute__((section(".stm32tk.abs.10000000"), used))' in after
    assert '__attribute__((section(".stm32tk.abs.68032000"), used))' in after
    assert '__attribute__((section(".stm32tk.abs.1000f000"), used))' in after

    sections = {section.symbol: section.address for section in scan.fixed_sections}
    assert sections == {
        "mem2base": 0x68000000,
        "mem3base": 0x10000000,
        "mem2mapbase": 0x68000000 + 200 * 1024,
        "mem3mapbase": 0x10000000 + 60 * 1024,
    }


# ---------------------------------------------------------------------------
# the contained raw reader never decodes what semantic resolution refuses
# ---------------------------------------------------------------------------


def test_raw_reader_returns_invalid_bytes_while_source_symbols_refuse(tmp_path):
    root = tmp_path / "raw-reader"
    gbk = GBK_COMMENT + b"#define MEM1_MAX_SIZE 110*1024\n"
    _write(root, "Main/malloc.h", gbk)
    text = '#include "malloc.h"\n__align(4) u8 pool[MEM1_MAX_SIZE];\n'
    _write(root, "Main/main.c", text)

    index = _MacroIndex(
        root=root,
        source_path="",
        include_paths=("Main",),
        target_defines=(),
        source_text="",
    )
    located = index.resolve_include_bytes("Main/main.c", "malloc.h")
    assert located is not None
    rel, _fingerprint, payload = located
    assert rel == "Main/malloc.h"
    # Exact bytes, still invalid UTF-8: no decode, no replacement characters.
    assert payload == gbk
    assert b"\xd6\xd0" in payload
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:  # pragma: no cover - the fixture must stay undecodable
        raise AssertionError("fixture unexpectedly decoded as UTF-8")

    symbols = SourceSymbols(root, "Main/main.c", text, ("Main",), ())
    assert symbols.evaluate("MEM1_MAX_SIZE") == (None, "unreadable")
    assert symbols.failure_context() == 'quoted include "Main/malloc.h" is not UTF-8'


# ---------------------------------------------------------------------------
# real sibling and transitive invalid headers behind invalid comments
# ---------------------------------------------------------------------------


def test_sibling_and_transitive_invalid_headers_are_all_discovered(tmp_path):
    root = tmp_path / "siblings"
    _write(root, "Main/main.c", b'/* \xd6\xd0 */\n#include "a.h"\n#include "b.h"\n')
    _write(root, "Main/a.h", b'/* \xd6\xd0 */\n#include "leaf.h"\n')
    _write(root, "Main/b.h", b"// \xd6\xd0\n#include \"c.h\"\n")
    _write(root, "Main/leaf.h", "#define LEAF 1\n")
    _write(root, "Main/c.h", b"/* \xd6 */\n#define C 1\n")

    inventory = _inventory(root)

    assert inventory["complete"] is True
    assert inventory["diagnostics"] == []
    assert [entry["path"] for entry in inventory["headers"]] == [
        "Main/a.h",
        "Main/b.h",
        "Main/c.h",
        "Main/leaf.h",
    ]
    flags = {entry["path"]: entry["utf8"] for entry in inventory["headers"]}
    assert flags == {
        "Main/a.h": False,
        "Main/b.h": False,
        "Main/c.h": False,
        "Main/leaf.h": True,
    }
    assert inventory["nonUtf8Headers"] == ["Main/a.h", "Main/b.h", "Main/c.h"]
    assert inventory["counts"]["files"] == 5


def test_cycles_and_duplicate_edges_are_stable_and_read_only(tmp_path):
    root = tmp_path / "cycles"
    _write(root, "Main/main.c", '#include "a.h"\n#include "b.h"\n')
    _write(root, "Main/a.h", '#include "b.h"\n#define A 1\n')
    _write(root, "Main/b.h", '#include "a.h"\n#define B 2\n')

    before = snapshot_tree(root)
    first = _inventory(root)
    second = _inventory(root)

    assert snapshot_tree(root) == before
    assert first == second
    assert first["complete"] is True
    assert first["diagnostics"] == []
    assert [entry["path"] for entry in first["headers"]] == [
        "Main/a.h",
        "Main/b.h",
    ]
    # Every discovered path appears exactly once, and files charges the seed.
    assert first["counts"]["files"] == 3


# ---------------------------------------------------------------------------
# comments, strings and phase-2 splices never invent an include
# ---------------------------------------------------------------------------


def test_comments_strings_and_splices_never_invent_includes(tmp_path):
    root = tmp_path / "controls"
    _write(root, "Main/spliced.h", "#define SPLICED 1\n")
    _write(
        root,
        "Main/main.c",
        '// #include "line-comment.h"\n'
        '/* #include "block-comment.h"\n'
        '   #include "block-continued.h" */\n'
        'const char *text = "#include \\"string-literal.h\\"";\n'
        "/* a spliced comment \\\n"
        '#include "spliced-comment.h"\n'
        "*/\n"
        '#inc\\\n'
        'lude "spliced.h"\n',
    )

    inventory = _inventory(root)

    # The only real edge is the one a phase-2 splice legitimately forms.
    assert inventory["complete"] is True
    assert inventory["diagnostics"] == []
    assert [entry["path"] for entry in inventory["headers"]] == ["Main/spliced.h"]


def test_system_includes_are_ignored_without_lookup(tmp_path):
    root = tmp_path / "system"
    _write(root, "Main/local.h", "\n")
    _write(root, "Main/main.c", '#include <stdio.h>\n#include "local.h"\n')

    inventory = _inventory(root)

    assert inventory["complete"] is True
    assert inventory["diagnostics"] == []
    assert [entry["path"] for entry in inventory["headers"]] == ["Main/local.h"]


# ---------------------------------------------------------------------------
# non-literal, malformed and unproven operands never guess a filename
# ---------------------------------------------------------------------------


def test_non_ascii_dynamic_and_malformed_operands_are_incomplete(tmp_path):
    root = tmp_path / "operands"
    _write(
        root,
        "Main/main.c",
        b"#include MEM_H\n"
        b'#include "back\\slash.h"\n'
        b'#include "trailing.h" extra\n'
        b'#include "\xd6\xd0.h"\n'
        b"#include\n"
        b'#include "unterminated.h\n'
        b"#include <unterminated\n",
    )

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert inventory["headers"] == []
    diagnostics = inventory["diagnostics"]
    assert len(diagnostics) == 7
    assert {item["code"] for item in diagnostics} == {
        "dynamic",
        "malformed",
        "non-ascii",
    }
    # No diagnostic carries a guessed filename; the raw operand is evidence.
    assert {item["operand"] for item in diagnostics} == {
        "MEM_H",
        '"back\\slash.h"',
        '"trailing.h" extra',
        '"\xd6\xd0.h"',
        "",
        '"unterminated.h',
        "<unterminated",
    }


def test_unproven_raw_strings_hide_every_edge_in_their_file(tmp_path):
    cases = {
        "spanning": (
            'const char *s = R"(alpha\nbeta)";\n#include "real.h"\n',
            "raw string literal spans multiple lines",
        ),
        "unterminated": (
            'const char *s = R"(never closed\n',
            "raw string literal is not terminated",
        ),
    }
    for name, (source, message) in cases.items():
        root = tmp_path / name
        _write(root, "Main/unit.c", source)
        _write(root, "Main/real.h", "#define REAL 1\n")

        inventory = _inventory(root, sources=("Main/unit.c",))

        assert inventory["complete"] is False, name
        assert inventory["headers"] == [], name
        assert [
            (item["code"], item["message"])
            for item in inventory["diagnostics"]
        ] == [("raw-string", message)], name


def test_include_next_and_import_are_incomplete_and_never_looked_up(tmp_path):
    root = tmp_path / "unsupported"
    _write(
        root,
        "Main/main.c",
        '#include_next "next.h"\n#import "imported.h"\n#include "ordinary.h"\n',
    )
    _write(root, "Main/next.h", "#define NEXT 1\n")
    _write(root, "Main/imported.h", "#define IMPORTED 1\n")
    _write(root, "Main/ordinary.h", "#define ORDINARY 1\n")

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert [item["code"] for item in inventory["diagnostics"]] == [
        "unsupported-directive",
        "unsupported-directive",
    ]
    assert {item["operand"] for item in inventory["diagnostics"]} == {
        '"next.h"',
        '"imported.h"',
    }
    # Existing files with different directive semantics are never followed.
    assert [entry["path"] for entry in inventory["headers"]] == [
        "Main/ordinary.h"
    ]


# ---------------------------------------------------------------------------
# refusals: missing, path escape and bound-input digest mismatch
# ---------------------------------------------------------------------------


def test_missing_escape_and_digest_mismatch_are_incomplete(tmp_path):
    root = tmp_path / "refusals"
    _write(
        root,
        "Main/main.c",
        '#include "missing.h"\n#include "../outside.h"\n#include "good.h"\n',
    )
    (tmp_path / "outside.h").write_bytes(b"#define OUTSIDE 1\n")
    _write(root, "Main/good.h", "#define GOOD 1\n")
    good = (root / "Main/good.h").read_bytes()
    expected = {"Main/good.h": ("0" * 64, len(good))}

    inventory = _inventory(root, expected=expected)

    assert inventory["complete"] is False
    codes = {item["code"] for item in inventory["diagnostics"]}
    assert codes == {"missing", "escape", "changed"}
    # The trusted sibling is still reported even though its digest is wrong.
    assert [entry["path"] for entry in inventory["headers"]] == ["Main/good.h"]


def test_seed_digest_mismatch_marks_the_inventory_incomplete(tmp_path):
    root = tmp_path / "seed-digest"
    _write(root, "Main/main.c", "int main(void) { return 0; }\n")

    inventory = _inventory(
        root, expected={"Main/main.c": ("0" * 64, 99)}
    )

    assert inventory["complete"] is False
    assert inventory["headers"] == []
    assert [item["code"] for item in inventory["diagnostics"]] == ["changed"]


# ---------------------------------------------------------------------------
# explicit bounds: depth, bytes, lookups, directories and files
# ---------------------------------------------------------------------------


def test_depth_limit_is_enforced_before_any_header_read(tmp_path, monkeypatch):
    root = tmp_path / "depth"
    _write(root, "Main/main.c", '#include "present.h"\n')
    _write(root, "Main/present.h", "#define PRESENT 1\n")

    calls: list[tuple[str, str]] = []
    real = _MacroIndex.resolve_include_bytes

    def spy(self, including: str, name: str):
        calls.append((including, name))
        return real(self, including, name)

    monkeypatch.setattr(_MacroIndex, "resolve_include_bytes", spy)
    monkeypatch.setattr(header_encoding, "MAX_INVENTORY_DEPTH", 0)

    inventory = _inventory(root)

    # Only the seed was read; the existing header was never opened.
    assert calls == [("", "Main/main.c")]
    assert inventory["complete"] is False
    assert inventory["headers"] == []
    assert [
        (item["code"], item["message"]) for item in inventory["diagnostics"]
    ] == [("limit", "include depth budget exceeded")]


def test_byte_budget_stops_and_charges_every_successful_read(tmp_path, monkeypatch):
    root = tmp_path / "byte-budget"
    main = '#include "p1.h"\n#include "p2.h"\n'
    p1 = '#include "shared.h"\n'
    p2 = '#include "shared.h"\n#include "third.h"\n'
    shared = "int shared_value;\n"
    third = "int third_value;\n"
    _write(root, "Main/main.c", main)
    _write(root, "Main/p1.h", p1)
    _write(root, "Main/p2.h", p2)
    _write(root, "Main/shared.h", shared)
    _write(root, "Main/third.h", third)

    # One shared.h read fits; the diamond's second read plus third.h does not.
    budget = len(main) + len(p1) + len(p2) + 2 * len(shared) + len(third) - 1
    monkeypatch.setattr(header_encoding, "MAX_INVENTORY_BYTES", budget)

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert inventory["counts"]["bytes"] == budget + 1
    # shared.h is charged once per successful read, even when already known.
    charged = inventory["counts"]["bytes"] - (
        len(main) + len(p1) + len(p2) + len(third)
    )
    assert charged == 2 * len(shared)
    assert [
        (item["including"], item["operand"], item["code"])
        for item in inventory["diagnostics"]
    ] == [("Main/p2.h", "third.h", "limit")]
    assert [entry["path"] for entry in inventory["headers"]] == [
        "Main/p1.h",
        "Main/p2.h",
        "Main/shared.h",
    ]


def test_lookup_budget_stops_before_resolving_more_edges(tmp_path, monkeypatch):
    root = tmp_path / "lookup-budget"
    _write(root, "Main/main.c", '#include "a.h"\n')
    _write(root, "Main/a.h", "#define A 1\n")

    calls: list[tuple[str, str]] = []
    real = _MacroIndex.resolve_include_bytes

    def spy(self, including: str, name: str):
        calls.append((including, name))
        return real(self, including, name)

    monkeypatch.setattr(_MacroIndex, "resolve_include_bytes", spy)
    monkeypatch.setattr(header_encoding, "MAX_INVENTORY_LOOKUPS", 1)

    inventory = _inventory(root)

    assert calls == [("", "Main/main.c")]
    assert inventory["complete"] is False
    assert inventory["headers"] == []
    assert inventory["counts"]["files"] == 1
    assert [
        (item["including"], item["operand"], item["code"])
        for item in inventory["diagnostics"]
    ] == [("Main/main.c", "a.h", "limit")]


def test_file_budget_stops_before_inventorying_another_header(tmp_path, monkeypatch):
    root = tmp_path / "file-budget"
    _write(root, "Main/main.c", '#include "a.h"\n')
    _write(root, "Main/a.h", "#define A 1\n")
    monkeypatch.setattr(header_encoding, "MAX_INVENTORY_FILES", 1)

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert inventory["headers"] == []
    assert inventory["counts"]["files"] == 1
    assert [
        (item["including"], item["operand"], item["code"])
        for item in inventory["diagnostics"]
    ] == [("Main/main.c", "a.h", "limit")]


def test_directory_budget_stops_without_further_reads(tmp_path, monkeypatch):
    root = tmp_path / "directory-budget"
    _write(root, "Main/main.c", '#include "a.h"\n')
    _write(root, "Main/a.h", "#define A 1\n")
    monkeypatch.setattr(header_encoding, "MAX_INVENTORY_DIRECTORIES", 0)

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert inventory["headers"] == []
    assert [item["code"] for item in inventory["diagnostics"]] == ["limit"]
    assert "directory budget exceeded" in inventory["diagnostics"][0]["message"]


def test_independent_unresolved_sibling_does_not_stop_the_next_edge(tmp_path):
    root = tmp_path / "siblings-continue"
    _write(root, "Main/main.c", '#include "missing.h"\n#include "good.h"\n')
    _write(root, "Main/good.h", "#define GOOD 1\n")

    inventory = _inventory(root)

    assert inventory["complete"] is False
    assert [item["code"] for item in inventory["diagnostics"]] == ["missing"]
    assert [entry["path"] for entry in inventory["headers"]] == ["Main/good.h"]


# ---------------------------------------------------------------------------
# preflight integration: discovered encodings gate readiness, metadata does not
# ---------------------------------------------------------------------------


def test_preflight_reports_every_invalid_sibling_and_blocks_plan_readiness(tmp_path):
    repo = build_repo(
        tmp_path,
        name="header-encoding-preflight",
        files={
            "Main/main.c": (
                '#include "a.h"\n'
                '#include "b.h"\n'
                "int main(void) { return 0; }\n"
            ),
            "Common/common.c": "int common_value;\n",
        },
    )
    # Invalid comment bytes ahead of plain ASCII directives in both siblings.
    (repo / "Main" / "a.h").write_bytes(
        GBK_COMMENT + b'#include "b.h"\n#define A 1\n'
    )
    (repo / "Main" / "b.h").write_bytes(GBK_COMMENT + b"#define B 2\n")

    data = preflight_keil_conversion(repo, inspect_keil(repo))
    analysis = data["analysis"]

    blockers = [
        blocker
        for blocker in analysis["blockers"]
        if blocker["code"] == "ARMCC_HEADER_ENCODING_UNSUPPORTED"
    ]
    assert {blocker["path"] for blocker in blockers} == {"Main/a.h", "Main/b.h"}
    for blocker in blockers:
        assert blocker["rule_id"] == "keil.header-encoding/1"
        assert blocker["line"] == 0
        assert blocker["column"] == 0
        assert blocker["remediation"]["category"] == "needs-user-input"
    assert analysis["blockerSummary"]["byCode"][
        "ARMCC_HEADER_ENCODING_UNSUPPORTED"
    ] == 2
    # Even with no original semantic blocker, the encoding evidence alone keeps
    # plan readiness closed and grants no plan or apply authorization.
    assert data["planReadiness"]["ready"] is False
    assert data["planReadiness"]["status"] == "blocked"

    discovery = analysis["encodingDiscovery"]
    assert discovery["complete"] is True
    assert discovery["nonUtf8Headers"] == ["Main/a.h", "Main/b.h"]
    assert [entry["path"] for entry in discovery["headers"]] == [
        "Main/a.h",
        "Main/b.h",
    ]


def test_missing_optional_edge_is_metadata_only_for_literal_sources(tmp_path):
    repo = build_repo(
        tmp_path,
        name="missing-optional",
        files={
            "Main/main.c": (
                '#include "optional.h"\nint main(void) { return 0; }\n'
            ),
            "Common/common.c": "int common_value;\n",
        },
    )

    data = preflight_keil_conversion(repo, inspect_keil(repo))
    analysis = data["analysis"]

    assert analysis["blockers"] == []
    discovery = analysis["encodingDiscovery"]
    assert discovery["complete"] is False
    assert discovery["headers"] == []
    assert [item["code"] for item in discovery["diagnostics"]] == ["missing"]
    # Incomplete discovery is evidence only: literal-only semantics keep their
    # original plan readiness.
    assert data["planReadiness"]["ready"] is True
    assert data["planReadiness"]["status"] == "ready-for-plan"


def test_unreferenced_bad_header_never_blocks_literal_sources(tmp_path):
    repo = build_repo(
        tmp_path,
        name="unreferenced-bad",
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": "int common_value;\n",
        },
    )
    (repo / "Main" / "unrelated.h").write_bytes(
        GBK_COMMENT + b"#define UNRELATED 1\n"
    )

    data = preflight_keil_conversion(repo, inspect_keil(repo))
    analysis = data["analysis"]

    assert analysis["blockers"] == []
    discovery = analysis["encodingDiscovery"]
    assert discovery["complete"] is True
    assert discovery["headers"] == []
    assert discovery["nonUtf8Headers"] == []
    assert data["planReadiness"]["ready"] is True
