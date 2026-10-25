"""ARMCC directive recognition behind same-line block-comment trivia.

Governing design: ``docs/superpowers/specs/2026-10-26-armcc-directive-prefix-design.md``
at accepted base ``41925c6e915a8af41c350bd08113e82bed41d1ed``.  GNU CPP
initial processing replaces comments with whitespace before directives are
interpreted, so a block comment before ``#`` must not hide a real ARMCC
pragma from either scanner.

This file is a reproduction only: it contains no product change and is
written against the approved contract.  On the accepted base the
comment-prefix cases are expected to fail (both scanners currently treat any
raw non-whitespace before ``#`` as ordinary code), while the neighbouring
controls are expected to pass before and after the fix.  Do not weaken an
assertion to match pre-fix output.

Fixtures are synthetic, disposable repositories built by the shared
``test_migration_plan`` helpers; nothing here runs a compiler, probe, or the
installed Toolkit runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    apply_keil_conversion,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.migration import rules

from test_migration_plan import FRAMEWORK_INCLUDE, build_repo, fixture_inspection

MAIN_BODY = "int main(void) { return 0; }\n"
SUPPORTED = "#pragma import(__use_no_semihosting)"
SUPPORTED_AFTER = "/* note */ \n"


def _scan(text: str, language: str = "c"):
    return rules.scan_sources(
        [("Main/main.c", text.encode("utf-8"), language)]
    )[0]


def _repo(tmp_path: Path, name: str, main_c: str) -> Path:
    """One-target synthetic repository using the existing migration helpers."""
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.c": main_c},
        uvprojx_kwargs={
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


# ---------------------------------------------------------------------------
# token-aware migration scan
# ---------------------------------------------------------------------------


def test_scan_rewrites_supported_pragma_after_block_comment_prefix():
    text = f"/* note */ {SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",)
    assert scan.link_specs == ("nosys.specs",)
    assert scan.after.decode("utf-8") == SUPPORTED_AFTER + MAIN_BODY


def test_scan_comment_prefixed_pragma_preserves_crlf_bytes():
    text = (
        f"/* note */ {SUPPORTED}\r\n"
        "int main(void) { return 0; }\r\n"
    )
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.link_specs == ("nosys.specs",)
    after = scan.after.decode("utf-8")
    assert after == f"/* note */ \r\nint main(void) {{ return 0; }}\r\n"
    assert "\n" not in after.replace("\r\n", "")


@pytest.mark.parametrize(
    "directive",
    [
        "#pragma import(__use_no_semihosting_extra)",
        '#pragma arm section code=".x"',
        "#pragma O3",
    ],
)
def test_scan_keeps_unknown_prefixed_pragma_blocked(directive):
    text = f"/* note */ {directive}\n{MAIN_BODY}"
    scan = _scan(text)

    blockers = [
        blocker
        for blocker in scan.blockers
        if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert len(blockers) == 1, scan.blockers
    blocker = blockers[0]
    assert (blocker.path, blocker.line, blocker.column) == (
        "Main/main.c",
        1,
        12,
    )
    assert blocker.evidence == f"/* note */ {directive}"
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == text


# ---------------------------------------------------------------------------
# neighbouring controls: comments, strings and ordinary mid-code '#'
# ---------------------------------------------------------------------------


def test_scan_leaves_comment_string_and_macro_occurrences_untouched():
    cases = (
        f"/* {SUPPORTED} */\n{MAIN_BODY}",
        f'const char *msg = "{SUPPORTED}";\n{MAIN_BODY}',
        f"#define KEEP /* c */ {SUPPORTED}\n{MAIN_BODY}",
    )
    for text in cases:
        scan = _scan(text)
        assert scan.blockers == (), text
        assert scan.rule_ids == (), text
        assert scan.link_specs == (), text
        assert scan.after.decode("utf-8") == text, text


def test_scan_comment_prefix_does_not_expose_a_line_comment_pragma():
    text = f"/* note */ // {SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == text


def test_scan_code_prefix_keeps_hash_ordinary():
    text = f"int sentinel; /* note */ {SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == text


# ---------------------------------------------------------------------------
# real Keil inspection scan
# ---------------------------------------------------------------------------


def test_inspection_reports_comment_prefixed_unsupported_pragma(tmp_path):
    directive = "#pragma import(__use_no_semihosting_extra)"
    line = f"/* note */ {directive}"
    repo = _repo(tmp_path, "prefixed-inspection", f"{line}\n{MAIN_BODY}")

    report = inspect_keil(repo)
    found = [
        finding
        for finding in report.findings
        if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
    ]
    assert len(found) == 1, report.findings
    finding = found[0]
    assert finding.severity == "blocker"
    assert (finding.path, finding.line, finding.column) == (
        "Main/main.c",
        1,
        12,
    )
    # Evidence stays original source text: either the whole stripped line or
    # the directive span itself, never a normalised or synthesized string.
    assert directive in finding.evidence
    assert finding.evidence in line


def test_prefixed_supported_pragma_is_not_blocked_by_its_comment_prefix(tmp_path):
    main_c = f"/* note */ {SUPPORTED}\n\n{MAIN_BODY}"
    repo = _repo(tmp_path, "prefixed-supported", main_c)
    inspection = fixture_inspection(repo)

    found = [
        finding
        for finding in inspection.findings
        if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
    ]
    assert len(found) == 1, inspection.findings
    assert (found[0].line, found[0].column) == (1, 12)
    assert SUPPORTED in found[0].evidence

    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patch = next(
        (item for item in plan.patches if item.path == "Main/main.c"), None
    )
    assert patch is not None
    assert patch.after_bytes.decode("utf-8") == f"/* note */ \n\n{MAIN_BODY}"
    manifest = next(
        (
            item
            for item in plan.patches
            if item.path == ".stm32-project.json"
        ),
        None,
    )
    assert manifest is not None
    assert '"nosys.specs"' in manifest.after_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# public preflight / PLAN / apply paths
# ---------------------------------------------------------------------------


def test_public_flow_rewrites_comment_prefixed_no_semihosting_pragma(tmp_path):
    main_c = f"/* note */ {SUPPORTED}\n\n{MAIN_BODY}"
    repo = _repo(tmp_path, "prefixed-flow", main_c)
    inspection = fixture_inspection(repo)

    preflight = preflight_keil_conversion(repo, inspection)
    assert preflight["analysis"]["blockers"] == []
    changes = {
        change["path"]: change
        for change in preflight["analysis"].get("sourceChanges", [])
    }
    assert changes.get("Main/main.c", {}).get("ruleIds") == [
        "ARMCC_NO_SEMIHOSTING_PRAGMA"
    ]

    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patch = next(
        (item for item in plan.patches if item.path == "Main/main.c"), None
    )
    assert patch is not None
    assert patch.after_bytes.decode("utf-8") == f"/* note */ \n\n{MAIN_BODY}"

    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    assert (repo / "Main" / "main.c").read_bytes() == patch.after_bytes
    assert (repo / "artifacts/migration/conversion-report.json").is_file()


def test_public_flow_keeps_comment_prefixed_unknown_import_blocked(tmp_path):
    directive = "#pragma import(__use_no_semihosting_extra)"
    line = f"/* note */ {directive}"
    main_c = f"{line}\n\n{MAIN_BODY}"
    repo = _repo(tmp_path, "prefixed-unknown", main_c)
    inspection = fixture_inspection(repo)

    preflight = preflight_keil_conversion(repo, inspection)
    reported = [
        blocker
        for blocker in preflight["analysis"]["blockers"]
        if blocker["code"] == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert len(reported) == 1, preflight["analysis"]["blockers"]
    assert (reported[0]["path"], reported[0]["line"], reported[0]["column"]) == (
        "Main/main.c",
        1,
        12,
    )
    assert directive in reported[0]["evidence"]
    assert reported[0]["evidence"] in line

    plan = plan_keil_conversion(repo, inspection)
    plan_blockers = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert plan_blockers
    assert not any(
        b"nosys.specs" in item.after_bytes for item in plan.patches
    )
    assert all(
        item.after_bytes.decode("utf-8") == main_c
        for item in plan.patches
        if item.path == "Main/main.c"
    )
