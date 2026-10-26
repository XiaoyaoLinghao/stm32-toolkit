"""Offline diagnostics for the reported v1.3.2 retest cases.

Synthetic projects only: the supplied declaration shapes, a quoted header that
is not UTF-8 (with a source that already is), transitive/missing/cyclic
dependencies, and embedded assembly functions without an explicit return.  The
tests assert bounded, project-relative diagnostics, unchanged source bytes and
every existing semantic guard.  No compiler, probe, network, installed runtime
or real firmware project is used.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.constant_context import SourceSymbols, SymbolSource
from stm32_toolkit.migration.model import (
    BLOCKER_HINT_DEPENDENCY_ENCODING,
    BLOCKER_HINT_DEPENDENCY_PATH,
)
from stm32_toolkit.migration.preflight import preflight_keil_conversion

from test_migration_plan import build_repo

#: The reported declaration shapes, with the quoted include a real ARMCC
#: source uses.  The include occupies line 1, so declarations start at line 2.
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

MALLOC_H = (
    "#ifndef MALLOC_H\n"
    "#define MALLOC_H\n"
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

#: A GBK comment makes the header undecodable as strict UTF-8 while its ASCII
#: macro text is unchanged beneath it; no byte or encoding may be guessed.
GBK_MALLOC_H = b"/* \xd6\xd0\xce\xc4 */\n" + MALLOC_H.encode("utf-8")


def _project(tmp_path, header: bytes):
    root = tmp_path / "retest"
    (root / "Main").mkdir(parents=True)
    (root / "Main" / "malloc.c").write_text(DECLARATIONS, encoding="utf-8")
    (root / "Main" / "malloc.h").write_bytes(header)
    return root


def _scan(root, path: str = "Main/malloc.c"):
    raw = (root / path).read_bytes()
    symbols = SymbolSource(root, ("Main",), ())
    return rules.scan_sources([(path, raw, "c")], symbols=symbols)[0]


def _blockers(scan, code: str):
    return [blocker for blocker in scan.blockers if blocker.code == code]


def _messages(scan) -> str:
    return "\n".join(blocker.message for blocker in scan.blockers)


# ---------------------------------------------------------------------------
# a strict UTF-8 guarded header keeps resolving through the existing rules
# ---------------------------------------------------------------------------


def test_utf8_header_resolves_alignment_and_macro_addresses(tmp_path):
    root = _project(tmp_path, MALLOC_H.encode("utf-8"))
    scan = _scan(root)

    assert scan.blockers == ()
    assert set(scan.rule_ids) == {"ARMCC_ALIGN_ATTRIBUTE", "ARMCC_ABSOLUTE_PLACEMENT"}
    after = scan.after.decode("utf-8")
    assert after.count("__attribute__((aligned(4)))") == 3
    assert '__attribute__((section(".stm32tk.abs.68000000"), used))' in after
    assert '__attribute__((section(".stm32tk.abs.1000f000"), used))' in after

    sections = {section.symbol: section.address for section in scan.fixed_sections}
    assert sections == {
        "mem2base": 0x68000000,
        "mem3base": 0x10000000,
        "mem2mapbase": 0x68000000 + 200 * 1024,
        "mem3mapbase": 0x10000000 + 60 * 1024,
    }

    header = (root / "Main" / "malloc.h").read_bytes()
    assert scan.dependencies == (
        ("Main/malloc.h", hashlib.sha256(header).hexdigest(), len(header)),
    )

    # The bounded evaluator resolves the reported macro arithmetic directly.
    symbols = SourceSymbols(root, "Main/malloc.c", DECLARATIONS, ("Main",), ())
    assert symbols.evaluate("MEM2_MAX_SIZE") == (200 * 1024, None)
    assert symbols.evaluate("MEM2_ALLOC_TABLE_SIZE") == (200 * 1024 // 32, None)
    assert symbols.failure_context() is None


# ---------------------------------------------------------------------------
# a non-UTF-8 quoted header: bounded cause, relative dependency, no rewrite
# ---------------------------------------------------------------------------


def test_non_utf8_header_names_relative_dependency_and_preserves_bytes(tmp_path):
    root = _project(tmp_path, GBK_MALLOC_H)
    raw = (root / "Main" / "malloc.c").read_bytes()
    scan = _scan(root)

    assert scan.after == raw
    assert scan.rule_ids == ()
    assert scan.fixed_sections == ()
    # A failed dependency contributes no digest: it is never read partially.
    assert scan.dependencies == ()

    align = _blockers(scan, "ARMCC_ALIGN_UNSUPPORTED")
    placement = _blockers(scan, "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED")
    assert len(align) == 3
    assert len(placement) == 4
    assert all(blocker.rule_id == blocker.code for blocker in scan.blockers)
    # The trusted structured cause, not message text, drives remediation.
    assert all(
        blocker.diagnostic == BLOCKER_HINT_DEPENDENCY_ENCODING
        for blocker in scan.blockers
    )

    messages = _messages(scan)
    assert 'quoted include "Main/malloc.h" is not UTF-8' in messages
    # The dependency name is project-relative, never the host path.
    assert str(root) not in json.dumps(
        [blocker.to_dict() for blocker in scan.blockers], ensure_ascii=False
    )

    by_line = {blocker.line: blocker for blocker in align}
    assert "array bound 'MEM1_MAX_SIZE' could not be resolved (unreadable)" in (
        by_line[2].message
    )
    assert "array bound 'MEM2_MAX_SIZE' could not be resolved (unreadable)" in (
        by_line[3].message
    )
    assert "array bound 'MEM3_MAX_SIZE' could not be resolved (unreadable)" in (
        by_line[4].message
    )
    for line in (2, 3, 4):
        assert 'quoted include "Main/malloc.h" is not UTF-8' in by_line[line].message
    # Only array bounds reach the declaration parser here; the shape itself is
    # plain and supported, so it must not be reported as grammar.
    assert "unsupported __align declaration grammar" not in messages

    placed = {blocker.line: blocker for blocker in placement}
    assert "array bound 'MEM2_MAX_SIZE' could not be resolved (unreadable)" in (
        placed[3].message
    )
    assert "array bound 'MEM3_MAX_SIZE' could not be resolved (unreadable)" in (
        placed[4].message
    )
    # The source expression is already the blocker evidence; the message only
    # has to carry the stable reason and dependency context.
    assert "MEM2_MAX_SIZE" in placed[5].evidence
    assert "address expression could not be resolved (unreadable)" in (
        placed[5].message
    )
    assert 'quoted include "Main/malloc.h" is not UTF-8' in placed[5].message
    assert "MEM3_MAX_SIZE" in placed[6].evidence
    assert "address expression could not be resolved (unreadable)" in (
        placed[6].message
    )
    assert 'quoted include "Main/malloc.h" is not UTF-8' in placed[6].message
    assert "no placement rewrite was applied for this file" in placed[3].message


def test_transitive_non_utf8_header_is_named_without_host_path(tmp_path):
    root = tmp_path / "transitive"
    (root / "Main" / "cfg").mkdir(parents=True)
    (root / "Main" / "malloc.c").write_text(
        '#include "wrapper.h"\n__align(4) u8 pool[MEM2_MAX_SIZE];\n',
        encoding="utf-8",
    )
    # Real chain: the UTF-8 wrapper includes the non-UTF-8 leaf.
    (root / "Main" / "wrapper.h").write_text(
        '#include "cfg/mem.h"\n', encoding="utf-8"
    )
    (root / "Main" / "cfg" / "mem.h").write_bytes(b"#define MEM2_MAX_SIZE 1\n\xff\n")

    raw = (root / "Main" / "malloc.c").read_bytes()
    scan = _scan(root)

    assert scan.after == raw
    blocker = _blockers(scan, "ARMCC_ALIGN_UNSUPPORTED")[0]
    assert "array bound 'MEM2_MAX_SIZE' could not be resolved (unreadable)" in (
        blocker.message
    )
    assert 'quoted include "Main/cfg/mem.h" is not UTF-8' in blocker.message
    assert str(root) not in blocker.message
    assert blocker.diagnostic == BLOCKER_HINT_DEPENDENCY_ENCODING


def test_missing_quoted_header_is_named_and_stays_unavailable(tmp_path):
    root = tmp_path / "missing"
    (root / "Main").mkdir(parents=True)
    (root / "Main" / "malloc.c").write_text(
        '#include "missing.h"\n__align(4) u8 pool[NEEDED_SIZE];\n',
        encoding="utf-8",
    )

    scan = _scan(root)

    blocker = _blockers(scan, "ARMCC_ALIGN_UNSUPPORTED")[0]
    assert "array bound 'NEEDED_SIZE' could not be resolved (unavailable)" in (
        blocker.message
    )
    assert 'quoted include "missing.h" was not found' in blocker.message
    # Missing paths are a distinct trusted cause from a non-UTF-8 header.
    assert blocker.diagnostic == BLOCKER_HINT_DEPENDENCY_PATH


def test_cyclic_macro_keeps_bounded_reason_without_dependency_context(tmp_path):
    root = tmp_path / "cycle"
    (root / "Main").mkdir(parents=True)
    (root / "Main" / "malloc.c").write_text(
        '#include "defs.h"\n__align(4) u8 pool[A];\n', encoding="utf-8"
    )
    (root / "Main" / "defs.h").write_text(
        "#define A B\n#define B A\n", encoding="utf-8"
    )

    scan = _scan(root)

    blocker = _blockers(scan, "ARMCC_ALIGN_UNSUPPORTED")[0]
    assert "array bound 'A' could not be resolved (cycle)" in blocker.message
    assert "quoted include" not in blocker.message
    assert str(root) not in blocker.message
    # A cyclic macro is a real resolution cause, not a dependency-hint case.
    assert blocker.diagnostic is None


def test_literal_address_alone_reads_no_header_but_a_macro_bound_does(tmp_path):
    root = tmp_path / "literal-vs-bound"
    (root / "Main").mkdir(parents=True)
    (root / "Main" / "malloc.h").write_bytes(GBK_MALLOC_H)

    literal = "__align(4) u8 buf[16] __attribute__((at(0x68000000)));\n"
    (root / "Main" / "main.c").write_text(literal, encoding="utf-8")
    literal_scan = _scan(root, "Main/main.c")
    assert literal_scan.blockers == ()
    assert literal_scan.dependencies == ()
    assert [section.address for section in literal_scan.fixed_sections] == [
        0x68000000
    ]

    # Same literal address, but the declaration's array bound is symbolic, so
    # the dependency is loaded and its non-UTF-8 bytes stop the rewrite.
    mixed = (
        '#include "malloc.h"\n'
        "__align(4) u8 mem2base[MEM2_MAX_SIZE] "
        "__attribute__((at(0x68000000)));\n"
    )
    (root / "Main" / "main.c").write_text(mixed, encoding="utf-8")
    mixed_scan = _scan(root, "Main/main.c")
    assert _blockers(mixed_scan, "ARMCC_ALIGN_UNSUPPORTED")
    assert _blockers(mixed_scan, "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED")
    assert 'quoted include "Main/malloc.h" is not UTF-8' in _messages(mixed_scan)
    assert all(
        blocker.diagnostic == BLOCKER_HINT_DEPENDENCY_ENCODING
        for blocker in mixed_scan.blockers
    )


# ---------------------------------------------------------------------------
# embedded assembly without an explicit return
# ---------------------------------------------------------------------------


def test_missing_return_assembly_keeps_blocker_with_fall_through_diagnostic():
    text = (
        "__asm void WFI_SET(void) { WFI; }\n"
        "\n"
        "__asm void INTX_DISABLE(void) { CPSID I; }\n"
    )
    scan = rules.scan_sources([("Main/sys.c", text.encode("utf-8"), "c")])[0]

    assert scan.after.decode("utf-8") == text
    assert scan.rule_ids == ()
    blockers = _blockers(scan, "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED")
    assert len(blockers) == 2
    assert "WFI_SET" in blockers[0].message
    assert "'WFI'" in blockers[0].message
    assert "INTX_DISABLE" in blockers[1].message
    assert "'CPSID I'" in blockers[1].message
    for blocker in blockers:
        assert "no explicit return" in blocker.message
        assert "fall through" in blocker.message
        assert "armcc User Guide" in blocker.message
        assert "section 7.30" in blocker.message
        # The source-intent decision no longer demands a Keil disassembly/AXF
        # baseline, and no return instruction is invented.
        assert "does not require a Keil disassembly/control-flow baseline" in (
            blocker.message
        )
        assert "project-owned source port" in blocker.message
        assert "BX LR" in blocker.message
    # The plain WFI-only wrapper names the exact opt-in and its normal body.
    assert 'wfiReturns=[{"path": "Main/sys.c", "function": "WFI_SET"}]' in (
        blockers[0].message
    )
    assert '__asm volatile ("wfi" ::: "memory")' in blockers[0].message
    assert "not binary equivalence" in blockers[0].message
    # CPSID I is not eligible for the WFI normal-return choice.
    assert "'CPSID I' is not eligible" in blockers[1].message
    # No invented return was written anywhere in the source.
    assert "bx lr" not in scan.after.decode("utf-8").lower()


def test_explicit_return_wrapper_still_rewrites_and_unknown_asm_stays_generic():
    text = (
        "__asm void wait_ok(void)\n"
        "{\n"
        "    WFI\n"
        "    BX LR\n"
        "}\n"
        "\n"
        "__asm void unknown(void) { LDR R0, [R1] BX LR }\n"
    )
    scan = rules.scan_sources([("Main/sys.c", text.encode("utf-8"), "c")])[0]

    after = scan.after.decode("utf-8")
    assert '__asm volatile ("wfi\\n\\tbx lr");' in after
    assert scan.rule_ids == ("ARMCC_NAKED_ASM_FUNCTION",)
    assert len(scan.blockers) == 1
    unknown = scan.blockers[0]
    assert unknown.line == 7
    assert unknown.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"
    # Unknown assembly is never described as a missing return.
    assert unknown.message == "ARMCC __asm function declaration or body"


@pytest.mark.parametrize(
    "body",
    ["WFI", "WFI;", "CPSID I", "CPSID I;", "CPSIE I;"],
)
def test_missing_return_diagnostic_covers_only_recognised_bodies(body):
    text = f"__asm void f(void) {{ {body} }}\n"
    scan = rules.scan_sources([("Main/sys.c", text.encode("utf-8"), "c")])[0]

    assert scan.after.decode("utf-8") == text
    assert len(_blockers(scan, "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED")) == 1
    assert "no explicit return" in _messages(scan)


def test_missing_return_msp_setter_is_named_without_rewriting():
    text = "__asm void set_msp(unsigned int top) { MSR MSP, R0; }\n"
    scan = rules.scan_sources([("Main/sys.c", text.encode("utf-8"), "c")])[0]

    assert scan.after.decode("utf-8") == text
    blocker = _blockers(scan, "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED")[0]
    assert "'MSR MSP, R0'" in blocker.message
    assert "no explicit return" in blocker.message


# ---------------------------------------------------------------------------
# preflight remediation classification at real preflight output
# ---------------------------------------------------------------------------

_DEPENDENCY_CODES = {
    "ARMCC_ALIGN_UNSUPPORTED",
    "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
}


def _dependency_blockers(repo):
    data = preflight_keil_conversion(repo, inspect_keil(repo))
    blockers = [
        blocker
        for blocker in data["analysis"]["blockers"]
        if blocker["code"] in _DEPENDENCY_CODES
    ]
    return blockers


def test_preflight_classifies_non_utf8_dependency_as_supported_preparation(tmp_path):
    repo = build_repo(
        tmp_path,
        name="encoding-hint",
        files={
            "Main/main.c": (
                '#include "malloc.h"\n'
                "__align(4) u8 mem2base[MEM2_MAX_SIZE] "
                "__attribute__((at(0x68000000)));\n"
                "int main(void) { return 0; }\n"
            ),
            "Common/common.c": "int common_value;\n",
        },
    )
    (repo / "Main" / "malloc.h").write_bytes(GBK_MALLOC_H)

    blockers = _dependency_blockers(repo)
    assert len(blockers) == 2
    for blocker in blockers:
        # The public blocker contract and plan identity stay unchanged.
        assert "diagnostic" not in blocker
        assert "Main/malloc.h" in blocker["message"]
        assert "is not UTF-8" in blocker["message"]
        remediation = blocker["remediation"]
        assert remediation["category"] == "needs-user-input"
        assert remediation["skill"] == "normalize-source-comments"
        assert remediation["requiredInputs"] == [
            "declaredCharset",
            "reviewedPlanId",
        ]
        assert "tool" not in remediation


def test_preflight_keeps_unsupported_grammar_unsupported(tmp_path):
    repo = build_repo(
        tmp_path,
        name="grammar-hint",
        files={
            "Main/main.c": (
                "__align(4) int a, b;\n"
                "__at(0x20000000) int *pointer;\n"
                "int main(void) { return 0; }\n"
            ),
            "Common/common.c": "int common_value;\n",
        },
    )

    blockers = _dependency_blockers(repo)
    assert len(blockers) == 2
    for blocker in blockers:
        assert "diagnostic" not in blocker
        remediation = blocker["remediation"]
        assert remediation["category"] == "unsupported"
        assert "skill" not in remediation
        assert remediation["requiredInputs"] == []


def test_preflight_classifies_missing_dependency_as_path_evidence(tmp_path):
    repo = build_repo(
        tmp_path,
        name="path-hint",
        files={
            "Main/main.c": (
                '#include "is not UTF-8.h"\n'
                "__align(4) u8 pool[NEEDED_SIZE];\n"
                "int main(void) { return 0; }\n"
            ),
            "Common/common.c": "int common_value;\n",
        },
    )

    blockers = _dependency_blockers(repo)
    assert len(blockers) == 1
    blocker = blockers[0]
    # A human-readable name cannot spoof the trusted encoding cause: the file
    # is missing, so the structured hint stays path evidence and no charset
    # skill is attached.
    assert 'quoted include "is not UTF-8.h" was not found' in blocker["message"]
    assert "diagnostic" not in blocker
    remediation = blocker["remediation"]
    assert remediation["category"] == "needs-user-input"
    assert "skill" not in remediation
    assert remediation["requiredInputs"] == ["includePathEvidence"]
    assert "not an encoding problem" in remediation["summary"]
    assert "read-only evidence" in remediation["summary"]
    assert "normalize-source-comments" not in remediation["summary"]


def test_preflight_dependency_evidence_does_not_claim_syntax_support(tmp_path):
    repo = build_repo(
        tmp_path,
        name="unproven-syntax",
        files={
            "Main/main.c": (
                '#include "flags.h"\n'
                "__at(BASE) int *pointer;\n"
                "int main(void) { return 0; }\n"
            ),
            "Common/common.c": "int common_value;\n",
        },
    )
    (repo / "Main" / "flags.h").write_bytes(
        b"/* \xd6\xd0\xce\xc4 */\n#define BASE 0x20000000\n"
    )

    blockers = _dependency_blockers(repo)
    assert len(blockers) == 1
    blocker = blockers[0]
    # Address evaluation stopped before declaration validation, so the message
    # must not claim the declaration is supported or call it grammar.
    assert blocker["message"].startswith("ARMCC absolute placement: ")
    assert "grammar" not in blocker["message"]
    assert "address expression could not be resolved (unreadable)" in (
        blocker["message"]
    )
    assert "Main/flags.h" in blocker["message"]
    remediation = blocker["remediation"]
    assert remediation["category"] == "needs-user-input"
    assert remediation["skill"] == "normalize-source-comments"
    # Preparing the dependency is not syntax acceptance; rerun may still block.
    assert "does not prove" in remediation["summary"]
    assert "remaining syntax can still block" in remediation["summary"]
