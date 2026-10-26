"""Bounded explicit WFI normal-return source-intent tests (M3a).

Every repository is a disposable synthetic fixture below pytest's temporary
directory; the real user project is never touched.  Planning, preflight and
selection tests use no compiler, probe, network, or hardware.  The final test
compiles the delivered WFI function with the coordinator's offline ARM GNU
toolchain and inspects only the generated object; a missing tool is an
explicit failure, never a silent skip and never a fake binary.

The choice records requested source behaviour (WFI followed by a normal C
return), not binary equivalence, and never requires a Keil disassembly/AXF
baseline.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import stm32_toolkit.migration.model as model_mod
import stm32_toolkit.migration.preflight as preflight_mod
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    apply_keil_delivery,
    plan_keil_delivery,
    plan_keil_conversion,
    preflight_keil_conversion,
)
from stm32_toolkit.migration import rules
from stm32_toolkit.migration.model import (
    MigrationBlocker,
    MigrationPlanError,
    WfiReturn,
)
from stm32_toolkit.migration.source_intent import (
    MAX_WFI_RETURNS,
    WFI_NORMAL_BODY,
    WFI_RETURN_RULE_ID,
    normalize_wfi_returns,
)

from test_migration_delivery import (
    GNU_BIN,
    REPORT_PATH,
    _require_tool,
    make_repo,
    output_parent,
    tree_digest,
)
from test_migration_plan import FRAMEWORK_INCLUDE, build_repo, fixture_inspection

WFI_ONLY = "__asm void WFI_SET(void) { WFI; }\n"
WFI_WITH_INTERRUPT = (
    "/* wait helpers */\n"
    "__asm void WFI_SET(void) { WFI; }\n"
    "\n"
    "__asm void INTX_DISABLE(void) { CPSID I; }\n"
)
WFI_AFTER = (
    "/* wait helpers */\n"
    "void WFI_SET(void)\n"
    "{\n"
    f'    {WFI_NORMAL_BODY}\n'
    "}\n"
    "\n"
    "__asm void INTX_DISABLE(void) { CPSID I; }\n"
)
EXPECTED_WFI_AFTER = (
    "void WFI_SET(void)\n"
    "{\n"
    f'    {WFI_NORMAL_BODY}\n'
    "}\n"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def choose(
    path: str = "Common/common.c", function: str = "WFI_SET"
) -> WfiReturn:
    return WfiReturn(path, function)


def scan(
    text: bytes | str,
    *,
    wfi_returns: tuple[WfiReturn, ...] | None = None,
    path: str = "Common/common.c",
    language: str = "c",
):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return rules.scan_sources(
        [(path, data, language)], wfi_returns=wfi_returns
    )[0]


def wfi_repo(
    tmp_path: Path,
    *,
    name: str = "wfi",
    source: str = WFI_ONLY,
) -> Path:
    return build_repo(
        tmp_path,
        name=name,
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": source,
        },
        commit=False,
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Common", (("common.c", "1", "Common/common.c"),)),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
    )


def _asm_blockers(scan_result) -> list:
    return [
        blocker
        for blocker in scan_result.blockers
        if blocker.code == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"
    ]


def apply_authorized(plan):
    return apply_keil_delivery(
        plan, authorized=True, plan_id=plan.plan_id
    )


# ---------------------------------------------------------------------------
# no selection: actionable decision, no disassembly prerequisite
# ---------------------------------------------------------------------------


def test_no_selection_keeps_actionable_wfi_decision() -> None:
    result = scan(WFI_ONLY)

    assert result.after.decode("utf-8") == WFI_ONLY
    assert result.rule_ids == ()
    blockers = _asm_blockers(result)
    assert len(blockers) == 1
    message = blockers[0].message
    assert "no explicit return" in message
    assert "fall through" in message
    assert "does not require a Keil disassembly/control-flow baseline" in message
    # The exact path/function and a concrete normal-return choice are named.
    assert 'wfiReturns=[{"path": "Common/common.c", "function": "WFI_SET"}]' in (
        message
    )
    assert WFI_NORMAL_BODY in message
    assert "not binary equivalence" in message
    assert "project-owned source port" in message
    # Toolkit never invents a return instruction or a CMSIS call.
    assert "bx lr" not in result.after.decode("utf-8").lower()


def test_no_selection_preflight_names_opt_in_without_new_shape(
    tmp_path: Path,
) -> None:
    repo = wfi_repo(tmp_path)
    data = preflight_keil_conversion(repo, inspect_keil(repo))

    blockers = [
        blocker
        for blocker in data["analysis"]["blockers"]
        if blocker["code"] == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"
    ]
    assert len(blockers) == 1
    assert "wfiReturns" not in data["analysis"]
    remediation = blockers[0]["remediation"]
    assert remediation["category"] == "needs-user-input"
    assert remediation["requiredInputs"] == ["wfiReturns"]
    assert remediation["tool"] == "stm32_keil_preflight"
    assert "plain" in remediation["summary"]
    assert "No Keil disassembly/AXF baseline" in remediation["summary"]
    assert data["planReadiness"]["status"] == "blocked"

    with pytest.raises(MigrationPlanError) as caught:
        plan_keil_delivery(
            repo,
            output_parent(tmp_path, "blocked-output") / "project",
            inspect_keil(repo),
        )
    assert caught.value.code == "DELIVERY_BLOCKED"
    assert "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED" in (
        caught.value.details["blockerCodes"]
    )


#: Every embedded-assembly shape that cannot use the wfiReturns choice.
_INELIGIBLE_ASM_SOURCES = [
    ("unknown-asm", "__asm void unknown(void) { LDR R0, [R1] BX LR }\n"),
    ("cpsid-missing-return", "__asm void INTX_DISABLE(void) { CPSID I; }\n"),
    (
        "msp-missing-return",
        "__asm void set_msp(unsigned int top) { MSR MSP, R0; }\n",
    ),
    (
        "conditional-wfi",
        "#if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    ),
    (
        "spliced-comment-wfi",
        "#/\\\n**/if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    ),
    ("punctuation-wfi", "__asm void WFI_SET(void) { WFI;; }\n"),
]


def test_missing_return_hint_is_set_only_for_plain_eligible_wfi() -> None:
    eligible = _asm_blockers(scan(WFI_ONLY))
    assert len(eligible) == 1
    # The scanner's trusted internal classification, not the message text.
    assert eligible[0].diagnostic == model_mod.BLOCKER_HINT_WFI_MISSING_RETURN
    assert "diagnostic" not in eligible[0].to_dict()

    for _name, source in _INELIGIBLE_ASM_SOURCES:
        blockers = _asm_blockers(scan(source))
        assert len(blockers) == 1
        assert blockers[0].diagnostic is None
        assert "wfiReturns=[" not in blockers[0].message


@pytest.mark.parametrize(("name", "source"), _INELIGIBLE_ASM_SOURCES)
def test_preflight_offers_wfi_option_only_for_the_plain_candidate(
    tmp_path: Path, name: str, source: str
) -> None:
    repo = wfi_repo(tmp_path, name=name, source=source)
    data = preflight_keil_conversion(repo, inspect_keil(repo))

    blockers = [
        blocker
        for blocker in data["analysis"]["blockers"]
        if blocker["code"] == "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED"
    ]
    assert len(blockers) == 1
    blocker = blockers[0]
    # The hint is trusted internal state and never changes the public shape.
    assert "diagnostic" not in blocker
    remediation = blocker["remediation"]
    assert remediation["category"] == "unsupported"
    assert remediation["requiredInputs"] == []
    assert "skill" not in remediation
    # No concrete opt-in is advertised anywhere for an ineligible body.
    assert "wfiReturns" not in json.dumps(remediation)
    assert "wfiReturns=[" not in blocker["message"]
    assert "No Keil disassembly/AXF baseline" in remediation["summary"]
    assert data["planReadiness"]["status"] == "blocked"


def test_remediation_hint_is_the_only_source_of_the_wfi_option() -> None:
    trusted = MigrationBlocker(
        "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
        "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
        "Common/common.c",
        1,
        1,
        "__asm void WFI_SET(void) { WFI; }",
        "ARMCC __asm function 'WFI_SET' ends after 'WFI' with no explicit"
        " return",
        model_mod.BLOCKER_HINT_WFI_MISSING_RETURN,
    )
    remediation = preflight_mod._remediation_for(trusted)
    assert remediation["category"] == "needs-user-input"
    assert remediation["tool"] == "stm32_keil_preflight"
    assert "skill" not in remediation
    assert remediation["requiredInputs"] == ["wfiReturns"]
    assert "No Keil disassembly/AXF baseline" in remediation["summary"]


def test_remediation_never_infers_the_wfi_option_from_path_or_message() -> None:
    # A path, evidence, or message that merely looks like the opt-in cannot
    # spoof the trusted hint: only the scanner's classification may.
    misleading = MigrationBlocker(
        "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
        "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
        "Common/wfiReturns.c",
        1,
        1,
        'wfiReturns=[{"path": "Common/wfiReturns.c", "function": "WFI_SET"}]',
        'Select wfiReturns=[{"path": "Common/wfiReturns.c", "function": '
        '"WFI_SET"}] for this plain unconditional file-scope WFI-only wrapper.',
    )
    remediation = preflight_mod._remediation_for(misleading)
    assert remediation["category"] == "unsupported"
    assert remediation["requiredInputs"] == []
    assert "skill" not in remediation
    assert "wfiReturns" not in json.dumps(remediation)
    assert "No Keil disassembly/AXF baseline" in remediation["summary"]
    assert "diagnostic" not in misleading.to_dict()


def test_no_selection_preserves_legacy_option_and_plan_shapes(
    tmp_path: Path,
) -> None:
    # A source without unsupported assembly keeps every historical shape.
    repo = make_repo(tmp_path)
    delivery = plan_keil_delivery(
        repo,
        output_parent(tmp_path, "legacy-output") / "project",
        inspect_keil(repo),
    )
    preview = delivery.to_dict()
    assert set(preview["options"]) == {
        "startupOptions",
        "memoryLayout",
        "extraRegions",
    }
    assert "wfiReturns" not in json.dumps(preview["options"])

    preflight = preflight_keil_conversion(repo, inspect_keil(repo))
    assert "wfiReturns" not in preflight["analysis"]
    assert "wfiReturns" not in " ".join(
        preflight["planReadiness"]["nextSteps"]
    )

    git_repo = build_repo(
        tmp_path,
        name="legacy-plan",
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": "int common_value;\n",
        },
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Common", (("common.c", "1", "Common/common.c"),)),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
    )
    plan = plan_keil_conversion(git_repo, fixture_inspection(git_repo))
    # The historical in-place plan is not extended with the new choice: the
    # legacy apply path cannot replay it, so neither the model, its public
    # payload, nor its identity payload carries a wfi_returns field.
    assert not hasattr(plan, "wfi_returns")
    assert "wfi_returns" not in plan.to_dict()
    assert "wfi_returns" not in model_mod._plan_id_payload(plan)


# ---------------------------------------------------------------------------
# exact opt-in: source rewrite, comments, newline/BOM, adjacent function
# ---------------------------------------------------------------------------


def test_selection_rewrites_only_the_plain_wfi_wrapper() -> None:
    result = scan(WFI_WITH_INTERRUPT, wfi_returns=(choose(),))

    assert result.after.decode("utf-8") == WFI_AFTER
    assert result.rule_ids == (WFI_RETURN_RULE_ID,)
    blockers = _asm_blockers(result)
    assert len(blockers) == 1
    assert "INTX_DISABLE" in blockers[0].message
    assert "'CPSID I' is not eligible" in blockers[0].message
    assert "__attribute__((naked))" not in result.after.decode("utf-8")
    assert "bx lr" not in result.after.decode("utf-8").lower()


def test_selection_preserves_crlf_bom_and_body_comment() -> None:
    raw = b"\xef\xbb\xbf" + (
        "__asm void WFI_SET(void)\r\n"
        "{\r\n"
        "    WFI /* wait */\r\n"
        "}\r\n"
        "__asm void INTX_DISABLE(void) { CPSID I; }\r\n"
    ).encode("utf-8")
    result = scan(raw, wfi_returns=(choose(),))

    after = result.after
    assert after.startswith(b"\xef\xbb\xbf")
    text = after.decode("utf-8-sig")
    assert "\n" not in text.replace("\r\n", "")
    assert (
        "void WFI_SET(void)\r\n"
        "{\r\n"
        f'    {WFI_NORMAL_BODY}\r\n'
        "    /* wait */\r\n"
        "}\r\n"
    ) in text
    assert "__asm void INTX_DISABLE(void) { CPSID I; }" in text
    assert len(_asm_blockers(result)) == 1


@pytest.mark.parametrize(
    ("source", "expected_prototype"),
    [
        ("__asm void wait_wfi() { WFI; }\n", "void wait_wfi()"),
        ("__asm void wait_wfi( void ) { WFI; }\n", "void wait_wfi(void)"),
    ],
)
def test_selection_preserves_the_zero_argument_prototype(
    source: str, expected_prototype: str
) -> None:
    result = scan(source, wfi_returns=(choose(function="wait_wfi"),))

    assert result.blockers == ()
    after = result.after.decode("utf-8")
    assert after.startswith(expected_prototype + "\n{\n")
    assert WFI_NORMAL_BODY in after


def test_prototype_plus_definition_is_not_a_duplicate() -> None:
    text = (
        "__asm void WFI_SET(void);\n"
        "__asm void WFI_SET(void) { WFI; }\n"
    )
    # The bare declaration still has no supported translation of its own, but
    # it must not make the selected definition look ambiguous.
    result = scan(text, wfi_returns=(choose(),))

    assert result.rule_ids == (WFI_RETURN_RULE_ID,)
    assert len(_asm_blockers(result)) == 1
    assert result.after.decode("utf-8").startswith(
        "__asm void WFI_SET(void);\nvoid WFI_SET(void)\n"
    )


# ---------------------------------------------------------------------------
# bounded transport validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        (["Common/common.c:WFI_SET"], "type"),
        (("Common/common.c", "WFI_SET"), "type"),
        ((WfiReturn("../outside.c", "WFI_SET"),), "path"),
        ((WfiReturn("C:/outside.c", "WFI_SET"),), "path"),
        ((WfiReturn("Common\\common.c", "WFI_SET"),), "path"),
        ((WfiReturn("Common/common.h", "WFI_SET"),), "path"),
        ((WfiReturn("Common/common.c", ""),), "function"),
        ((WfiReturn("Common/common.c", "1bad"),), "function"),
        ((WfiReturn("Common/common.c", "bad-name"),), "function"),
        ((WfiReturn("Common/common.c", "a" * 129),), "function"),
        ((WfiReturn("Common/common.c", "WFI_SET"),) * 2, "duplicate"),
    ],
)
def test_wfi_transport_validation_rejects_malformed_requests(
    value: object, rule: str
) -> None:
    with pytest.raises(MigrationPlanError) as caught:
        normalize_wfi_returns(value)
    assert caught.value.code == "WFI_RETURNS_INVALID"
    assert caught.value.details["field"] == "wfiReturns"
    assert caught.value.details["rule"] == rule


def test_wfi_transport_validation_bounds_count_and_orders_choices() -> None:
    too_many = tuple(
        WfiReturn(f"Common/f{index}.c", f"f{index}")
        for index in range(MAX_WFI_RETURNS + 1)
    )
    with pytest.raises(MigrationPlanError) as caught:
        normalize_wfi_returns(too_many)
    assert caught.value.details["rule"] == "limit"

    unsorted = (
        WfiReturn("Common/z.c", "z"),
        WfiReturn("Common/a.c", "b"),
        WfiReturn("Common/a.c", "a"),
    )
    normalized = normalize_wfi_returns(unsorted)
    assert normalized == (
        WfiReturn("Common/a.c", "a"),
        WfiReturn("Common/a.c", "b"),
        WfiReturn("Common/z.c", "z"),
    )
    assert normalize_wfi_returns(normalized) == normalized


def test_invalid_transport_fails_through_the_scanner() -> None:
    with pytest.raises(MigrationPlanError) as caught:
        rules.scan_sources(
            [("Common/common.c", WFI_ONLY.encode("utf-8"), "c")],
            wfi_returns=["Common/common.c:WFI_SET"],
        )
    assert caught.value.code == "WFI_RETURNS_INVALID"


# ---------------------------------------------------------------------------
# unmatched and ambiguous selections fail instead of silently succeeding
# ---------------------------------------------------------------------------


def test_unmatched_function_and_path_are_refused() -> None:
    with pytest.raises(MigrationPlanError) as missing_function:
        scan(WFI_ONLY, wfi_returns=(choose(function="OTHER"),))
    assert missing_function.value.code == "WFI_RETURN_UNUSED"
    assert missing_function.value.details["rule"] == "unused"

    with pytest.raises(MigrationPlanError) as missing_path:
        scan(
            WFI_ONLY,
            path="Main/main.c",
            wfi_returns=(choose(path="Common/common.c"),),
        )
    assert missing_path.value.code == "WFI_RETURN_UNUSED"


def test_macro_generated_and_comment_prefixed_forms_are_not_definitions() -> None:
    with pytest.raises(MigrationPlanError) as macro:
        scan(
            "#define WFI_FUNC __asm void WFI_SET(void) { WFI; }\nWFI_FUNC\n",
            wfi_returns=(choose(),),
        )
    assert macro.value.code == "WFI_RETURN_UNUSED"

    with pytest.raises(MigrationPlanError) as commented:
        scan(
            "__asm /* prototype ambiguity */ void WFI_SET(void) { WFI; }\n",
            wfi_returns=(choose(),),
        )
    assert commented.value.code == "WFI_RETURN_UNUSED"


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            "void outer(void)\n{\n    __asm void WFI_SET(void) { WFI; }\n}\n",
            "nested",
        ),
        ("static __asm void WFI_SET(void) { WFI; }\n", "prefix"),
        ("static\n__asm void WFI_SET(void) { WFI; }\n", "prefix"),
        (
            "__attribute__((section(\".x\")))\n"
            "__asm void WFI_SET(void) { WFI; }\n",
            "prefix",
        ),
        ("#if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n", "conditional"),
        (
            "#ifdef WAIT\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
            "conditional",
        ),
        (
            "__asm void WFI_SET(void) { WFI; }\n"
            "__asm void WFI_SET(void) { WFI; }\n",
            "duplicateDefinition",
        ),
        ("__asm void WFI_SET(unsigned int top) { WFI; }\n", "unsupported"),
        ("__asm void WFI_SET(void) { WFI; NOP; }\n", "unsupported"),
        # The legacy explicit-return grammar takes no semicolons, so this form
        # stays an unsupported refusal rather than a rewritten wrapper.
        ("__asm void WFI_SET(void) { WFI; BX LR; }\n", "unsupported"),
        (
            "__asm void WFI_SET(void)\n"
            "{\n"
            "    WFI\n"
            "    BX LR\n"
            "}\n",
            "explicitReturn",
        ),
        (
            "__asm void WFI_SET(unsigned int top) { MSR MSP, R0; }\n",
            "nonWfi",
        ),
        ("__asm void WFI_SET(void) { CPSID I; }\n", "nonWfi"),
    ],
)
def test_ambiguous_selections_are_refused(source: str, rule: str) -> None:
    with pytest.raises(MigrationPlanError) as caught:
        scan(source, wfi_returns=(choose(),))
    assert caught.value.code == "WFI_RETURN_AMBIGUOUS"
    assert caught.value.details["rule"] == rule
    assert caught.value.details["path"] == "Common/common.c"
    assert caught.value.details["function"] == "WFI_SET"


# ---------------------------------------------------------------------------
# preprocessor trivia cannot hide a real conditional from the choice
# ---------------------------------------------------------------------------

#: ``#``-to-keyword trivia a preprocessor would normalize into one logical
#: directive: comments, LF/CRLF line splices, and splices inside the keyword.
_CONDITIONAL_TRIVIA_FORMS = [
    "#/**/if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    "#/* multi\nline */if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    "#\\\nif 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    "#\\\r\nif 1\r\n__asm void WFI_SET(void) { WFI; }\r\n#endif\r\n",
    "#i\\\nf 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    "#i\\\r\nf 1\r\n__asm void WFI_SET(void) { WFI; }\r\n#endif\r\n",
    # A phase-2 splice can create the comment open: ``#/`` + splice + ``**/if``
    # is the real logical directive ``#/**/if 1``, never a null directive.
    "#/\\\n**/if 1\n__asm void WFI_SET(void) { WFI; }\n#endif\n",
    "#/\\\r\n**/if 1\r\n__asm void WFI_SET(void) { WFI; }\r\n#endif\r\n",
]


@pytest.mark.parametrize("source", _CONDITIONAL_TRIVIA_FORMS)
def test_selection_never_infers_unconditional_from_trivia_directive(
    source: str,
) -> None:
    with pytest.raises(MigrationPlanError) as caught:
        scan(source, wfi_returns=(choose(),))
    assert caught.value.code == "WFI_RETURN_AMBIGUOUS"
    assert caught.value.details["rule"] == "conditional"


@pytest.mark.parametrize("source", _CONDITIONAL_TRIVIA_FORMS)
def test_no_choice_trivia_directive_keeps_legacy_blocker(source: str) -> None:
    result = scan(source)

    assert result.after.decode("utf-8") == source
    assert result.rule_ids == ()
    blockers = _asm_blockers(result)
    assert len(blockers) == 1
    assert "no explicit return" in blockers[0].message
    assert "fall through" in blockers[0].message
    assert "not plain (conditional)" in blockers[0].message
    # No concrete opt-in is offered for a definition inside a conditional.
    assert "wfiReturns=[" not in blockers[0].message


def test_hashes_inside_literals_comments_and_macros_are_not_directives() -> None:
    source = (
        "/* #if 0 */\n"
        'const char *marker = "#ifdef FAKE";\n'
        "#define FAKE_DIRECTIVE #if 0\n"
        "__asm void WFI_SET(void) { WFI; }\n"
    )
    result = scan(source, wfi_returns=(choose(),))

    assert result.blockers == ()
    assert result.rule_ids == (WFI_RETURN_RULE_ID,)
    after = result.after.decode("utf-8")
    assert 'const char *marker = "#ifdef FAKE";' in after
    assert "#define FAKE_DIRECTIVE #if 0" in after
    assert "void WFI_SET(void)" in after


@pytest.mark.parametrize(
    "prefix",
    [
        "#\n",
        "#\r\n",
        "#   \n",
        "# /* null */\n",
        "#/**/\r\n",
    ],
)
def test_genuine_null_directive_keeps_plain_candidate_selectable(
    prefix: str,
) -> None:
    # Only trivia then end of logical line is a real null directive; it hides
    # no conditional, so an otherwise plain WFI wrapper stays selectable.
    source = prefix + "__asm void WFI_SET(void) { WFI; }\n"
    result = scan(source, wfi_returns=(choose(),))

    assert result.blockers == ()
    assert result.rule_ids == (WFI_RETURN_RULE_ID,)


@pytest.mark.parametrize(
    "source",
    [
        # Unrecognised non-trivia punctuation after ``#`` can never be proven
        # to be a null directive.
        "#@\n__asm void WFI_SET(void) { WFI; }\n",
        "#/ not-a-comment\n__asm void WFI_SET(void) { WFI; }\n",
    ],
)
def test_unrecognised_directive_prefix_never_admits_a_conditional(
    source: str,
) -> None:
    with pytest.raises(MigrationPlanError) as caught:
        scan(source, wfi_returns=(choose(),))
    assert caught.value.code == "WFI_RETURN_AMBIGUOUS"
    assert caught.value.details["rule"] == "conditional"


# ---------------------------------------------------------------------------
# the selected body contract is exactly one WFI plus one optional semicolon
# ---------------------------------------------------------------------------

_NON_CONTRACT_WFI_BODIES = ["WFI,", ",WFI", "WFI;;", "WFI; ;", "WFI ,", "WFI; ,"]


@pytest.mark.parametrize("body", _NON_CONTRACT_WFI_BODIES)
def test_selection_refuses_bodies_outside_the_single_wfi_contract(
    body: str,
) -> None:
    source = f"__asm void WFI_SET(void) {{ {body} }}\n"
    with pytest.raises(MigrationPlanError) as caught:
        scan(source, wfi_returns=(choose(),))
    assert caught.value.code == "WFI_RETURN_AMBIGUOUS"
    assert caught.value.details["rule"] == "body"


@pytest.mark.parametrize("body", _NON_CONTRACT_WFI_BODIES)
def test_no_choice_non_contract_bodies_never_rewrite(body: str) -> None:
    source = f"__asm void WFI_SET(void) {{ {body} }}\n"
    result = scan(source)

    assert result.after.decode("utf-8") == source
    assert result.rule_ids == ()
    blockers = _asm_blockers(result)
    assert len(blockers) == 1
    assert "no explicit return" in blockers[0].message
    assert "project-owned source port" in blockers[0].message
    # The single-WFI opt-in is never advertised for another body.
    assert "wfiReturns=[" not in blockers[0].message


@pytest.mark.parametrize(
    ("body", "comments"),
    [
        ("WFI", ()),
        ("WFI;", ()),
        ("WFI /* wait */", ("/* wait */",)),
        ("WFI; /* wait */", ("/* wait */",)),
        ("\n    WFI; // wait\n", ("// wait",)),
        ("WFI /* a */ ;", ("/* a */",)),
    ],
)
def test_selection_accepts_single_wfi_with_optional_semicolon_and_comments(
    body: str, comments: tuple[str, ...]
) -> None:
    source = f"/* wait helpers */\n__asm void WFI_SET(void) {{ {body} }}\n"
    result = scan(source, wfi_returns=(choose(),))

    assert result.blockers == ()
    assert result.rule_ids == (WFI_RETURN_RULE_ID,)
    after = result.after.decode("utf-8")
    assert "void WFI_SET(void)\n{\n" in after
    assert WFI_NORMAL_BODY in after
    for comment in comments:
        assert comment in after


def test_selection_fails_preflight_and_delivery_planning(tmp_path: Path) -> None:
    repo = build_repo(
        tmp_path,
        name="ambiguous",
        files={
            "Main/main.c": "int main(void) { return 0; }\n",
            "Common/common.c": (
                "static __asm void WFI_SET(void) { WFI; }\n"
            ),
        },
        commit=False,
        uvprojx_kwargs={
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Common", (("common.c", "1", "Common/common.c"),)),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
    )
    inspection = inspect_keil(repo)
    with pytest.raises(MigrationPlanError) as preflight:
        preflight_keil_conversion(
            repo, inspection, wfi_returns=(choose(),)
        )
    assert preflight.value.code == "WFI_RETURN_AMBIGUOUS"

    with pytest.raises(MigrationPlanError) as delivery:
        plan_keil_delivery(
            repo,
            output_parent(tmp_path, "ambiguous-output") / "project",
            inspection,
            wfi_returns=(choose(function="OTHER"),),
        )
    assert delivery.value.code == "WFI_RETURN_UNUSED"


# ---------------------------------------------------------------------------
# delivery binding: plan, preview, report, apply, drift
# ---------------------------------------------------------------------------


def test_selection_binds_plan_preview_report_and_apply(tmp_path: Path) -> None:
    repo = wfi_repo(tmp_path)
    original = (repo / "Common" / "common.c").read_bytes()
    before_tree = tree_digest(repo)
    destination = output_parent(tmp_path, "delivery") / "gcc-project"

    plan = plan_keil_delivery(
        repo,
        destination,
        inspect_keil(repo),
        wfi_returns=(choose(),),
    )
    assert plan.wfi_returns == (choose(),)
    preview = plan.to_dict()
    assert preview["options"]["wfiReturns"] == [
        {"path": "Common/common.c", "function": "WFI_SET"}
    ]
    source_patch = next(
        patch
        for patch in preview["sourcePatches"]
        if patch["path"] == "Common/common.c"
    )
    assert source_patch["rule_ids"] == [WFI_RETURN_RULE_ID]
    assert source_patch["before_sha256"] == sha256(original)
    expected_after = EXPECTED_WFI_AFTER.encode("utf-8")
    assert source_patch["after_sha256"] == sha256(expected_after)
    assert "-__asm void WFI_SET(void) { WFI; }" in (
        source_patch["unified_diff"]
    )
    assert "+void WFI_SET(void)" in source_patch["unified_diff"]
    assert f'+    {WFI_NORMAL_BODY}' in source_patch["unified_diff"]
    output = next(
        entry
        for entry in preview["outputs"]
        if entry["path"] == "Common/common.c"
    )
    assert output["kind"] == "replaced"
    assert output["sha256"] == sha256(expected_after)
    assert output["binary"] is False
    assert plan.plan_id != plan.content_id

    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()
    assert (destination / "Common" / "common.c").read_bytes() == expected_after
    # The original source is never modified by planning or apply.
    assert (repo / "Common" / "common.c").read_bytes() == original
    assert tree_digest(repo) == before_tree

    report = json.loads(
        (destination / REPORT_PATH).read_text(encoding="utf-8")
    )
    assert report["schemaVersion"] == 2
    assert report["sourceSnapshotSha256"] == plan.source_snapshot_sha256
    assert report["wfiReturns"] == [
        {
            "path": "Common/common.c",
            "function": "WFI_SET",
            "sourceSha256": sha256(original),
            "convertedSha256": sha256(expected_after),
            "requestedBehavior": "normal-return",
            "binaryEquivalent": False,
        }
    ]
    # The planned output snapshot binds the rewritten file and its report.
    assert plan.output_snapshot_sha256 == result.data["outputSnapshotSha256"]


def test_selection_is_bound_into_preflight_evidence(tmp_path: Path) -> None:
    repo = wfi_repo(tmp_path, name="preflight-evidence")
    original = (repo / "Common" / "common.c").read_bytes()

    data = preflight_keil_conversion(
        repo, inspect_keil(repo), wfi_returns=(choose(),)
    )
    assert data["analysis"]["blockers"] == []
    assert data["planReadiness"]["status"] == "ready-for-plan"
    evidence = data["analysis"]["wfiReturns"]
    assert evidence == [
        {
            "path": "Common/common.c",
            "function": "WFI_SET",
            "sourceSha256": sha256(original),
            "convertedSha256": sha256(
                EXPECTED_WFI_AFTER.encode("utf-8")
            ),
            "requestedBehavior": "normal-return",
            "binaryEquivalent": False,
        }
    ]
    changes = {
        change["path"]: change
        for change in data["analysis"]["sourceChanges"]
    }
    assert changes["Common/common.c"]["ruleIds"] == [WFI_RETURN_RULE_ID]
    guidance = " ".join(data["planReadiness"]["nextSteps"])
    assert "wfiReturns=" in guidance
    assert '"function":"WFI_SET"' in guidance


def test_selection_option_drift_is_refused_before_writing(
    tmp_path: Path,
) -> None:
    repo = wfi_repo(tmp_path, name="drift")
    destination = output_parent(tmp_path, "drift-output") / "project"
    plan = plan_keil_delivery(
        repo,
        destination,
        inspect_keil(repo),
        wfi_returns=(choose(),),
    )

    omitted = apply_authorized(replace(plan, wfi_returns=()))
    assert omitted.ok is False
    assert omitted.code == "DELIVERY_BLOCKED"
    assert not destination.exists()

    wrong = apply_authorized(
        replace(
            plan,
            wfi_returns=(WfiReturn("Common/common.c", "OTHER"),),
        )
    )
    assert wrong.ok is False
    assert wrong.code == "WFI_RETURN_UNUSED"
    assert not destination.exists()

    mutable = apply_authorized(
        replace(plan, wfi_returns=[choose()])
    )
    assert mutable.ok is False
    assert mutable.code == "DELIVERY_PLAN_INVALID"
    assert mutable.details["rule"] == "wfiReturns"
    assert not destination.exists()


def test_selection_source_drift_is_refused_before_writing(
    tmp_path: Path,
) -> None:
    repo = wfi_repo(tmp_path, name="source-drift")
    destination = output_parent(tmp_path, "source-drift-output") / "project"
    plan = plan_keil_delivery(
        repo,
        destination,
        inspect_keil(repo),
        wfi_returns=(choose(),),
    )

    changed = WFI_ONLY + "/* concurrent edit */\n"
    (repo / "Common" / "common.c").write_bytes(changed.encode("utf-8"))
    result = apply_authorized(plan)
    assert result.ok is False
    assert result.code == "DELIVERY_SOURCE_CHANGED"
    assert not destination.exists()
    assert (repo / "Common" / "common.c").read_text(
        encoding="utf-8"
    ) == changed


def test_selection_order_is_deterministic(tmp_path: Path) -> None:
    repo = wfi_repo(tmp_path, name="order")
    inspection = inspect_keil(repo)
    parent = output_parent(tmp_path, "order-output")
    first = plan_keil_delivery(
        repo, parent / "first", inspection, wfi_returns=(choose(),)
    )
    second = plan_keil_delivery(
        repo, parent / "second", inspection, wfi_returns=(choose(),)
    )
    assert first.wfi_returns == second.wfi_returns == (choose(),)
    assert first.source_snapshot_sha256 == second.source_snapshot_sha256
    # The destination-bound content identity differs, but the selected intent
    # and its source patch bytes do not.
    assert first.content_id != second.content_id
    assert first.source_patches == second.source_patches


# ---------------------------------------------------------------------------
# real ARM GNU evidence: generated object only, no Keil baseline
# ---------------------------------------------------------------------------


def test_real_gcc_emits_wfi_then_normal_return_without_interrupt_disable(
    tmp_path: Path,
) -> None:
    gcc = _require_tool(GNU_BIN, "arm-none-eabi-gcc")
    objdump = _require_tool(GNU_BIN, "arm-none-eabi-objdump")

    repo = wfi_repo(tmp_path, name="gcc-evidence")
    destination = output_parent(tmp_path, "gcc-output") / "project"
    plan = plan_keil_delivery(
        repo,
        destination,
        inspect_keil(repo),
        wfi_returns=(choose(),),
    )
    result = apply_authorized(plan)
    assert result.ok is True, result.to_dict()

    source = destination / "Common" / "common.c"
    delivered = source.read_text(encoding="utf-8")
    assert WFI_NORMAL_BODY in delivered
    assert "__attribute__((naked))" not in delivered
    assert "__asm void" not in delivered

    obj = tmp_path / "wfi.o"
    compiled = subprocess.run(
        [
            gcc,
            "-c",
            "-mcpu=cortex-m4",
            "-mthumb",
            "-O2",
            "-ffreestanding",
            "-o",
            str(obj),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert compiled.returncode == 0, (
        compiled.stdout + "\n" + compiled.stderr
    )

    disassembly = subprocess.run(
        [objdump, "-d", str(obj)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert disassembly.returncode == 0, disassembly.stderr
    text = disassembly.stdout.lower()
    # The selected function waits and returns normally; it never disables
    # interrupts and never depends on a Keil AXF/disassembly baseline.
    assert re.search(r"\bwfi\b", text) is not None
    assert re.search(r"\bcpsid\b", text) is None
    assert (
        re.search(r"\bbx\s+lr\b", text) is not None
        or re.search(r"\bpop\s*\{[^}]*\bpc\b", text) is not None
    )
