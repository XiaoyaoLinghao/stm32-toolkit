"""ARMCC directive recognition behind same-line block-comment trivia.

Governing design: ``docs/superpowers/specs/2026-10-26-armcc-directive-prefix-design.md``
at accepted base ``41925c6e915a8af41c350bd08113e82bed41d1ed``.  GNU CPP
initial processing replaces comments with whitespace before directives are
interpreted, so a block comment before ``#`` must not hide a real ARMCC
pragma from either scanner.

This file began as the frozen reproduction at accepted base
``41925c6e915a8af41c350bd08113e82bed41d1ed``: the comment-prefix cases failed
there because both scanners treated any raw non-whitespace before ``#`` as
ordinary code, while the neighbouring controls passed.  The bounded lexical
correction now implements the contract, and the extended cases below cover
multiple/multiline trivia (including macro and comment bodies), spliced
lines, C++ raw-literal prefixes, BOM/CRLF, capped evidence and false-positive
controls.  Do not weaken an assertion to match any historical output.

Fixtures are synthetic, disposable repositories built by the shared
``test_migration_plan`` helpers; nothing here runs a probe or the installed
Toolkit runtime.  The single compiler-backed oracle reuses the existing
``test_startup_gcc_compiler`` helpers and the supplied offline ARM GNU
toolchain to substantiate the preprocessing logical-line rule independently
of the product scanners.
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


def _repo_cpp(tmp_path: Path, name: str, source: str) -> Path:
    """C++ repository; the deliberately unknown FileType defers to ``.cpp``.

    ``uvprojx._language_for`` maps FileType ``1``/``2`` to C/asm, so a numeric
    type would hide the C++ raw-string path under test.
    """
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.cpp": source},
        uvprojx_kwargs={
            "groups": (("Main", (("main.cpp", "9", "Main/main.cpp"),)),),
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


# ---------------------------------------------------------------------------
# extended lexical prefix: multiple/multiline trivia and spliced lines
# ---------------------------------------------------------------------------


def test_scan_accepts_multiple_and_multiline_comment_prefixes():
    cases = (
        (
            f"/* a */ /* b */ {SUPPORTED}\n{MAIN_BODY}",
            f"/* a */ /* b */ \n{MAIN_BODY}",
        ),
        (
            f"/* first\n   second */ {SUPPORTED}\n{MAIN_BODY}",
            f"/* first\n   second */ \n{MAIN_BODY}",
        ),
    )
    for text, expected in cases:
        scan = _scan(text)
        assert scan.blockers == (), text
        assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",), text
        assert scan.link_specs == ("nosys.specs",), text
        assert scan.after.decode("utf-8") == expected, text


def test_scan_keeps_code_before_a_spliced_line_ordinary():
    text = f"int sentinel; \\\n{SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == text


def test_scan_accepts_splice_only_prefix_and_preserves_crlf():
    lf_text = f"   \\\n{SUPPORTED}\n{MAIN_BODY}"
    lf = _scan(lf_text)
    assert lf.blockers == ()
    assert lf.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",)
    assert lf.link_specs == ("nosys.specs",)
    assert lf.after.decode("utf-8") == f"   \\\n\n{MAIN_BODY}"

    crlf_text = (
        f"   \\\r\n{SUPPORTED}\r\n"
        "int main(void) { return 0; }\r\n"
    )
    crlf = _scan(crlf_text)
    assert crlf.blockers == ()
    assert crlf.link_specs == ("nosys.specs",)
    assert crlf.after.decode("utf-8") == (
        "   \\\r\n\r\nint main(void) { return 0; }\r\n"
    )


def test_macro_continuation_pragma_stays_inert_in_both_scanners(tmp_path):
    text = f"#define KEEP \\\n{SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(text)

    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == text

    repo = _repo(tmp_path, "macro-continuation", text)
    report = inspect_keil(repo)
    assert not any(
        finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        for finding in report.findings
    )


def test_scan_cxx_comment_prefix_is_supported_and_unknown_stays_blocked():
    supported = f"/* note */ {SUPPORTED}\n{MAIN_BODY}"
    scan = _scan(supported, language="cxx")
    assert scan.blockers == ()
    assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",)
    assert scan.link_specs == ("nosys.specs",)
    assert scan.after.decode("utf-8") == f"/* note */ \n{MAIN_BODY}"

    unknown = (
        "/* note */ #pragma import(__use_no_semihosting_extra)\n"
        + MAIN_BODY
    )
    blocked = _scan(unknown, language="cxx")
    assert any(
        blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
        for blocker in blocked.blockers
    )
    assert blocked.after.decode("utf-8") == unknown


def test_scan_comment_prefixed_pragma_preserves_a_utf8_bom():
    raw = b"\xef\xbb\xbf" + f"/* note */ {SUPPORTED}\n{MAIN_BODY}".encode(
        "utf-8"
    )
    scan = rules.scan_sources([("Main/main.c", raw, "c")])[0]

    assert scan.blockers == ()
    assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",)
    assert scan.link_specs == ("nosys.specs",)
    assert scan.after == b"\xef\xbb\xbf" + f"/* note */ \n{MAIN_BODY}".encode(
        "utf-8"
    )


def test_scan_raw_string_and_spliced_line_comment_hide_pragmas():
    raw_string = (
        'const char *msg = R"tag(a"b\n'
        "#pragma import(__use_no_semihosting_extra)\n"
        ')tag";\n' + MAIN_BODY
    )
    cpp = _scan(raw_string, language="cxx")
    assert cpp.blockers == ()
    assert cpp.rule_ids == ()
    assert cpp.after.decode("utf-8") == raw_string

    spliced = f"// note \\\n{SUPPORTED}\n{MAIN_BODY}"
    comment = _scan(spliced)
    assert comment.blockers == ()
    assert comment.rule_ids == ()
    assert comment.link_specs == ()
    assert comment.after.decode("utf-8") == spliced


def test_inspection_reports_multiline_comment_prefixed_unsupported_pragma(
    tmp_path,
):
    directive = "#pragma import(__use_no_semihosting_extra)"
    line_two = f"   second */ {directive}"
    repo = _repo(
        tmp_path, "multiline-inspection", f"/* first\n{line_two}\n{MAIN_BODY}"
    )

    report = inspect_keil(repo)
    found = [
        finding
        for finding in report.findings
        if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
    ]
    assert len(found) == 1, report.findings
    finding = found[0]
    assert (finding.path, finding.line, finding.column) == (
        "Main/main.c",
        2,
        14,
    )
    assert directive in finding.evidence
    assert finding.evidence in line_two


def test_inspection_spliced_line_comment_and_raw_string_stay_inert(tmp_path):
    spliced = f"// note \\\n{SUPPORTED}\n{MAIN_BODY}"
    repo = _repo(tmp_path, "spliced-inspection", spliced)
    report = inspect_keil(repo)
    assert not any(
        finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        for finding in report.findings
    )

    raw_string = (
        'const char *msg = R"tag(a"b\n'
        "#pragma import(__use_no_semihosting_extra)\n"
        ')tag";\n' + MAIN_BODY
    )
    cpp_repo = _repo_cpp(tmp_path, "raw-inspection", raw_string)
    cpp_report = inspect_keil(cpp_repo)
    assert not any(
        finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        for finding in cpp_report.findings
    )


def test_public_flow_applies_multiple_comment_prefixes(tmp_path):
    main_c = f"/* a */ /* b */ {SUPPORTED}\n\n{MAIN_BODY}"
    repo = _repo(tmp_path, "prefixed-multi-flow", main_c)
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
    assert patch.after_bytes.decode("utf-8") == f"/* a */ /* b */ \n\n{MAIN_BODY}"

    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    assert (repo / "Main" / "main.c").read_bytes() == patch.after_bytes


def test_public_flow_reconciles_a_capped_trailing_comment_after_prefix(
    tmp_path,
):
    comment = "/* " + "keep-comment " * 20 + "*/"
    assert len(comment) > 200
    main_c = f"/* note */ {SUPPORTED} {comment}\n{MAIN_BODY}"
    repo = _repo(tmp_path, "prefixed-long", main_c)
    inspection = fixture_inspection(repo)

    found = [
        finding
        for finding in inspection.findings
        if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
    ]
    assert len(found) == 1, inspection.findings
    assert len(found[0].evidence) <= 200

    plan = plan_keil_conversion(repo, inspection)
    assert plan.blockers == ()
    patch = next(
        (item for item in plan.patches if item.path == "Main/main.c"), None
    )
    assert patch is not None
    after = patch.after_bytes.decode("utf-8")
    assert "#pragma import" not in after
    assert comment in after
    assert after.startswith("/* note */  ")


# ---------------------------------------------------------------------------
# logical-line state through multiline comments
# ---------------------------------------------------------------------------


def test_code_before_multiline_comment_keeps_hash_ordinary(tmp_path):
    prefix = "int sentinel; /* first\nsecond */ "
    extra = f"{prefix}#pragma import(__use_no_semihosting_extra)\n{MAIN_BODY}"
    scan = _scan(extra)
    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == extra

    supported = f"{prefix}{SUPPORTED}\n{MAIN_BODY}"
    supported_scan = _scan(supported)
    assert supported_scan.blockers == ()
    assert supported_scan.rule_ids == ()
    assert supported_scan.link_specs == ()
    assert supported_scan.after.decode("utf-8") == supported

    repo = _repo(tmp_path, "code-before-multiline", extra)
    report = inspect_keil(repo)
    assert not any(
        finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        for finding in report.findings
    )


def test_multiline_comment_inside_macro_body_never_becomes_a_directive():
    for ending in ("\n", "\r\n"):
        text = (
            f"#define KEEP /* first{ending}"
            f"{SUPPORTED}{ending}"
            f"*/ 1{ending}"
            f"{SUPPORTED}{ending}"
            f"int main(void) {{ return 0; }}{ending}"
        )
        expected = (
            f"#define KEEP /* first{ending}"
            f"{SUPPORTED}{ending}"
            f"*/ 1{ending}"
            f"{ending}"
            f"int main(void) {{ return 0; }}{ending}"
        )
        scan = _scan(text)
        assert scan.blockers == (), ending
        assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",), ending
        assert scan.link_specs == ("nosys.specs",), ending
        assert scan.after.decode("utf-8") == expected, ending


def test_macro_comment_fake_pragma_is_inert_and_real_one_is_processed(
    tmp_path,
):
    for index, ending in enumerate(("\n", "\r\n")):
        main_c = (
            f"#define KEEP /* first{ending}"
            f"{SUPPORTED}{ending}"
            f"*/ 1{ending}"
            f"{SUPPORTED}{ending}"
            f"int main(void) {{ return 0; }}{ending}"
        )
        expected = (
            f"#define KEEP /* first{ending}"
            f"{SUPPORTED}{ending}"
            f"*/ 1{ending}"
            f"{ending}"
            f"int main(void) {{ return 0; }}{ending}"
        )
        repo = _repo(tmp_path, f"macro-comment-flow-{index}", main_c)
        inspection = fixture_inspection(repo)

        found = [
            finding
            for finding in inspection.findings
            if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        ]
        assert [(finding.line, finding.column) for finding in found] == [
            (4, 1)
        ], ending

        preflight = preflight_keil_conversion(repo, inspection)
        assert preflight["analysis"]["blockers"] == [], ending
        changes = {
            change["path"]: change
            for change in preflight["analysis"].get("sourceChanges", [])
        }
        assert changes.get("Main/main.c", {}).get("ruleIds") == [
            "ARMCC_NO_SEMIHOSTING_PRAGMA"
        ], ending

        plan = plan_keil_conversion(repo, inspection)
        assert plan.blockers == (), ending
        patch = next(
            (item for item in plan.patches if item.path == "Main/main.c"),
            None,
        )
        assert patch is not None
        assert patch.after_bytes.decode("utf-8") == expected, ending
        applied = apply_keil_conversion(plan)
        assert applied.ok is True, applied.to_dict()


def test_macro_comment_fake_unknown_pragma_stays_inert_but_real_one_blocks(
    tmp_path,
):
    directive = "#pragma import(__use_no_semihosting_extra)"
    for index, ending in enumerate(("\n", "\r\n")):
        main_c = (
            f"#define KEEP /* first{ending}"
            f"{directive}{ending}"
            f"*/ 1{ending}"
            f"{directive}{ending}"
            f"int main(void) {{ return 0; }}{ending}"
        )
        repo = _repo(tmp_path, f"macro-comment-blocked-{index}", main_c)
        inspection = fixture_inspection(repo)

        found = [
            finding
            for finding in inspection.findings
            if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        ]
        assert [(finding.line, finding.column) for finding in found] == [
            (4, 1)
        ], ending

        preflight = preflight_keil_conversion(repo, inspection)
        reported = [
            blocker
            for blocker in preflight["analysis"]["blockers"]
            if blocker["code"] == "ARMCC_PRAGMA_UNSUPPORTED"
        ]
        assert len(reported) == 1, ending
        assert (reported[0]["line"], reported[0]["column"]) == (4, 1)

        plan = plan_keil_conversion(repo, inspection)
        plan_blockers = [
            blocker
            for blocker in plan.blockers
            if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
        ]
        assert len(plan_blockers) == 1, ending
        assert (plan_blockers[0].line, plan_blockers[0].column) == (4, 1)
        assert not any(
            b"nosys.specs" in item.after_bytes for item in plan.patches
        )
        assert all(
            item.after_bytes.decode("utf-8") == main_c
            for item in plan.patches
            if item.path == "Main/main.c"
        )


# ---------------------------------------------------------------------------
# quoted macro text continued by backslash-LF/CRLF
# ---------------------------------------------------------------------------


def _spliced_string_macro(ending: str, inner: str, real: str) -> str:
    """Macro whose string literal is continued by a backslash newline.

    ``inner`` is text inside the literal on the continuation line and ``real``
    is a genuine standalone directive on the following line.
    """
    return (
        f'#define TEXT "first \\{ending}'
        f'{inner} second"{ending}'
        f"{real}{ending}"
        f"int main(void) {{ return 0; }}{ending}"
    )


def _spliced_string_macro_after(ending: str, inner: str) -> str:
    return (
        f'#define TEXT "first \\{ending}'
        f'{inner} second"{ending}'
        f"{ending}"
        f"int main(void) {{ return 0; }}{ending}"
    )


def test_spliced_string_macro_text_hides_fake_pragma():
    for ending in ("\n", "\r\n"):
        supported = _spliced_string_macro(ending, SUPPORTED, SUPPORTED)
        scan = _scan(supported)
        assert scan.blockers == (), ending
        assert scan.rule_ids == ("ARMCC_NO_SEMIHOSTING_PRAGMA",), ending
        assert scan.link_specs == ("nosys.specs",), ending
        assert scan.after.decode("utf-8") == _spliced_string_macro_after(
            ending, SUPPORTED
        ), ending

        extra = "#pragma import(__use_no_semihosting_extra)"
        blocked_text = _spliced_string_macro(ending, SUPPORTED, extra)
        blocked = _scan(blocked_text)
        assert blocked.rule_ids == (), ending
        assert blocked.link_specs == (), ending
        assert blocked.after.decode("utf-8") == blocked_text, ending
        blockers = [
            blocker
            for blocker in blocked.blockers
            if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
        ]
        assert len(blockers) == 1, ending
        assert (blockers[0].line, blockers[0].column) == (3, 1), ending


def test_spliced_string_macro_fake_pragma_is_inert_and_real_one_processed(
    tmp_path,
):
    for index, ending in enumerate(("\n", "\r\n")):
        main_c = _spliced_string_macro(ending, SUPPORTED, SUPPORTED)
        expected = _spliced_string_macro_after(ending, SUPPORTED)
        repo = _repo(tmp_path, f"spliced-string-flow-{index}", main_c)
        inspection = fixture_inspection(repo)

        found = [
            finding
            for finding in inspection.findings
            if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        ]
        assert [(finding.line, finding.column) for finding in found] == [
            (3, 1)
        ], ending

        preflight = preflight_keil_conversion(repo, inspection)
        assert preflight["analysis"]["blockers"] == [], ending
        changes = {
            change["path"]: change
            for change in preflight["analysis"].get("sourceChanges", [])
        }
        assert changes.get("Main/main.c", {}).get("ruleIds") == [
            "ARMCC_NO_SEMIHOSTING_PRAGMA"
        ], ending

        plan = plan_keil_conversion(repo, inspection)
        assert plan.blockers == (), ending
        patch = next(
            (item for item in plan.patches if item.path == "Main/main.c"),
            None,
        )
        assert patch is not None
        assert patch.after_bytes.decode("utf-8") == expected, ending
        applied = apply_keil_conversion(plan)
        assert applied.ok is True, applied.to_dict()


def test_spliced_string_macro_fake_supported_pragma_never_rewrites_and_real_blocks(
    tmp_path,
):
    extra = "#pragma import(__use_no_semihosting_extra)"
    for index, ending in enumerate(("\n", "\r\n")):
        main_c = _spliced_string_macro(ending, SUPPORTED, extra)
        repo = _repo(tmp_path, f"spliced-string-blocked-{index}", main_c)
        inspection = fixture_inspection(repo)

        found = [
            finding
            for finding in inspection.findings
            if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        ]
        assert [(finding.line, finding.column) for finding in found] == [
            (3, 1)
        ], ending

        preflight = preflight_keil_conversion(repo, inspection)
        reported = [
            blocker
            for blocker in preflight["analysis"]["blockers"]
            if blocker["code"] == "ARMCC_PRAGMA_UNSUPPORTED"
        ]
        assert len(reported) == 1, ending
        assert (reported[0]["line"], reported[0]["column"]) == (3, 1)

        plan = plan_keil_conversion(repo, inspection)
        plan_blockers = [
            blocker
            for blocker in plan.blockers
            if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
        ]
        assert len(plan_blockers) == 1, ending
        assert (plan_blockers[0].line, plan_blockers[0].column) == (3, 1)
        assert not any(
            b"nosys.specs" in item.after_bytes for item in plan.patches
        )
        assert all(
            item.after_bytes.decode("utf-8") == main_c
            for item in plan.patches
            if item.path == "Main/main.c"
        )


# ---------------------------------------------------------------------------
# C++ raw-literal encoding prefixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["u8R", "uR", "UR", "LR", "R"])
def test_scan_cxx_raw_literal_prefixes_hide_pragma_text(prefix):
    text = (
        f'const char *msg = {prefix}"tag(a"b\n'
        "#pragma import(__use_no_semihosting_extra)\n"
        ')tag";\n' + MAIN_BODY
    )
    scan = _scan(text, language="cxx")

    assert scan.blockers == ()
    assert scan.rule_ids == ()
    assert scan.after.decode("utf-8") == text


@pytest.mark.parametrize("prefix", ["u8R", "uR", "UR", "LR", "R"])
def test_inspection_cxx_raw_literal_prefixes_stay_inert(tmp_path, prefix):
    source = (
        f'const char *msg = {prefix}"tag(a"b\n'
        "#pragma import(__use_no_semihosting_extra)\n"
        ')tag";\n' + MAIN_BODY
    )
    repo = _repo_cpp(tmp_path, f"raw-{prefix}", source)
    report = inspect_keil(repo)

    assert not any(
        finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
        for finding in report.findings
    )


# ---------------------------------------------------------------------------
# capped evidence must never suppress a real blocker
# ---------------------------------------------------------------------------


def test_capped_evidence_does_not_suppress_prefixed_trailing_token(tmp_path):
    directive_prefix = f"{SUPPORTED} "
    comment = "/*" + "x" * (200 - len(directive_prefix) - 4) + "*/"
    # The 200-codepoint evidence cap ends exactly after a supported-looking
    # directive plus its complete trailing comment; only the full verified line
    # reveals the extra trailing token.
    assert len(directive_prefix) + len(comment) == 200
    line = f"/* note */ {SUPPORTED} {comment} extra_token"
    main_c = f"{line}\n{MAIN_BODY}"

    scan = _scan(main_c)
    rules_blockers = [
        blocker
        for blocker in scan.blockers
        if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert len(rules_blockers) == 1
    assert scan.rule_ids == ()
    assert scan.link_specs == ()
    assert scan.after.decode("utf-8") == main_c

    repo = _repo(tmp_path, "capped-extra", main_c)
    inspection = fixture_inspection(repo)
    found = [
        finding
        for finding in inspection.findings
        if finding.rule_id == "ARMCC_UNSUPPORTED_PRAGMA"
    ]
    assert len(found) == 1
    assert len(found[0].evidence) == 200
    assert found[0].evidence == f"{SUPPORTED} {comment}"

    preflight = preflight_keil_conversion(repo, inspection)
    reported = [
        blocker
        for blocker in preflight["analysis"]["blockers"]
        if blocker["code"] == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert len(reported) == 1
    assert reported[0]["line"] == 1

    plan = plan_keil_conversion(repo, inspection)
    plan_blockers = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "ARMCC_PRAGMA_UNSUPPORTED"
    ]
    assert len(plan_blockers) == 1
    assert not any(
        b"nosys.specs" in item.after_bytes for item in plan.patches
    )
    assert all(
        item.after_bytes.decode("utf-8") == main_c
        for item in plan.patches
        if item.path == "Main/main.c"
    )


# ---------------------------------------------------------------------------
# independent compiler oracle for the logical-line rule
# ---------------------------------------------------------------------------


def test_gcc_oracle_confirms_multiline_comment_logical_line(tmp_path):
    """Independent GCC preprocessing oracle, not product evidence.

    The oracle reads successful preprocessing output instead of diagnostic
    text, so a source excerpt echoed by GCC cannot masquerade as a recognised
    directive.  The offline ARM GNU compiler is expected on this host; a
    missing tool or arbitrary compiler failure is a test failure, matching the
    existing compiler-test contract.
    """
    from test_startup_gcc_compiler import _run as gcc_run
    from test_startup_gcc_compiler import _tool as gcc_tool

    gcc = gcc_tool("arm-none-eabi-gcc")

    def preprocessed(name: str, text: str) -> str:
        source = tmp_path / name
        source.write_text(text, encoding="utf-8")
        result = gcc_run([gcc, "-E", "-P", str(source)], cwd=tmp_path)
        return result.stdout

    # A trivia-only multiline comment prefix keeps '#' a directive.
    accepted = preprocessed(
        "trivia.c",
        "/* first\nsecond */ #define ORACLE_MARK 1\n"
        "int oracle_use = ORACLE_MARK;\n",
    )
    assert "int oracle_use = 1;" in accepted
    assert "ORACLE_MARK" not in accepted

    # A real code token before the same comment keeps '#' ordinary, so the
    # macro is never defined and the use site keeps the identifier.
    preceded = preprocessed(
        "preceded.c",
        "int sentinel; /* first\nsecond */ #define ORACLE_MARK 1\n"
        "int oracle_use = ORACLE_MARK;\n",
    )
    assert "int oracle_use = ORACLE_MARK;" in preceded
    assert "int oracle_use = 1;" not in preceded

    # The same macro/comment body text is inert, not a nested directive.
    macro_comment = preprocessed(
        "macro.c",
        "#define KEEP /* first\n#define ORACLE_MARK 1\n*/ 1\n"
        "int oracle_use = ORACLE_MARK;\n",
    )
    assert "int oracle_use = ORACLE_MARK;" in macro_comment
    assert "int oracle_use = 1;" not in macro_comment
