"""Read-only Keil migration preflight.

Preflight runs the exact technical analysis used by conversion planning but
does not require Git.  Missing Git, an unborn HEAD, and dirty/untracked work
are reported as apply prerequisites instead of analysis failures.  A
completed preflight may contain blockers: analysis completion is deliberately
separate from permission to apply.  No plan ID is produced, no patch is
applied, and no file or Git state is modified.
"""

from __future__ import annotations

import json
from pathlib import Path

from stm32_toolkit.debug_configuration import post_migration_debug_configuration
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.memory_layout import MemoryLayout
from stm32_toolkit.migration import git_guard
from stm32_toolkit.migration.model import (
    MigrationBlocker,
    MigrationPlanError,
    StartupOptions,
    inspection_sha256_for,
)
from stm32_toolkit.migration.planner import analyze_keil_conversion

_ANALYSIS_RULESET = "keil-conversion-technical/1"
#: Same public output bound as a serialized conversion plan.
_PREFLIGHT_OUTPUT_LIMIT_BYTES = 64 * 1024 * 1024


def _error_evidence(error: MigrationPlanError) -> dict[str, object]:
    """Return only stable, bounded error metadata (never exception text)."""
    evidence: dict[str, object] = {"code": error.code}
    rule = error.details.get("rule")
    if isinstance(rule, str) and rule:
        evidence["rule"] = rule
    return evidence


def _git_error_evidence(error: BaseException, rule: str) -> dict[str, object]:
    """Map stable Git errors and OS launch/read failures to safe metadata.

    ``git_guard`` normally raises ``MigrationPlanError``, but an OS policy can
    deny launching or reading Git and raise ``OSError``/``PermissionError``.
    Neither exception text nor host paths may enter the public result.
    """
    if isinstance(error, MigrationPlanError):
        evidence = _error_evidence(error)
        evidence.setdefault("rule", rule)
        return evidence
    return {"code": "MIGRATION_GIT_UNAVAILABLE", "rule": rule}


def _head_not_evaluated(reason: str) -> dict[str, object]:
    return {
        "available": False,
        "commit": None,
        "status": "not-evaluated",
        "reason": reason,
        "error": None,
    }


def _worktree_not_evaluated(reason: str) -> dict[str, object]:
    return {
        "status": "not-evaluated",
        "dirtyPaths": [],
        "reason": reason,
        "error": None,
    }


def _git_state(canonical: Path) -> dict[str, object]:
    """Collect read-only Git evidence without making analysis depend on it."""
    state: dict[str, object] = {
        "analysisRequiresGit": False,
        "repository": {
            "available": False,
            "projectRootIsToplevel": None,
            "error": None,
        },
        "head": _head_not_evaluated("HEAD has not been evaluated."),
        "worktree": _worktree_not_evaluated("Worktree state has not been evaluated."),
    }
    try:
        toplevel = git_guard.git_toplevel(canonical)
    except (MigrationPlanError, OSError) as error:
        state["repository"] = {
            "available": False,
            "projectRootIsToplevel": None,
            "error": _git_error_evidence(error, "repository"),
        }
        state["head"] = _head_not_evaluated(
            "HEAD is not inspected because no readable Git repository is available."
        )
        state["worktree"] = _worktree_not_evaluated(
            "Worktree state is not inspected because no readable Git repository is available."
        )
        return state

    matches = toplevel == canonical
    state["repository"] = {
        "available": True,
        "projectRootIsToplevel": matches,
        "error": None,
    }
    if not matches:
        state["head"] = _head_not_evaluated(
            "HEAD is not inspected because the project root is not the Git worktree toplevel."
        )
        state["worktree"] = _worktree_not_evaluated(
            "Worktree state is not inspected because the project root is not the Git worktree toplevel."
        )
        return state

    try:
        head = git_guard.git_head(canonical)
    except (MigrationPlanError, OSError) as error:
        state["head"] = {
            "available": False,
            "commit": None,
            "status": "unavailable",
            "reason": "No committed HEAD is available for the Git-bound plan.",
            "error": _git_error_evidence(error, "head"),
        }
    else:
        state["head"] = {
            "available": True,
            "commit": head,
            "status": "available",
            "reason": None,
            "error": None,
        }

    try:
        status = git_guard.porcelain_status(canonical)
        entries = git_guard.dirty_paths(status)
    except (MigrationPlanError, OSError) as error:
        state["worktree"] = {
            "status": "unavailable",
            "dirtyPaths": [],
            "reason": "Git worktree status is unavailable.",
            "error": _git_error_evidence(error, "status"),
        }
    else:
        state["worktree"] = {
            "status": "dirty" if entries else "clean",
            "dirtyPaths": [
                {"path": path, "category": category} for category, path in entries
            ],
            "reason": None,
            "error": None,
        }
    return state


def _prerequisite(
    identifier: str,
    satisfied: bool,
    description: str,
    next_step: str,
) -> dict[str, object]:
    return {
        "id": identifier,
        "satisfied": satisfied,
        "description": description,
        "nextStep": next_step,
    }


def _startup_option_guidance(options: StartupOptions | None) -> str:
    """Return the exact startup choice the reviewed plan/apply must retain."""
    if options is None:
        return ""
    if options.source is not None:
        return (
            " Retain startupStrategy=generate-cmsis-gcc and "
            f"startupSource={options.source} for the PLAN and apply requests; "
            "omitting or changing either value is never accepted against this plan."
        )
    return (
        " Retain startupStrategy=generate-cmsis-gcc and the same startupSource "
        "selection for the PLAN and apply requests (startupSource may be omitted "
        "only while exactly one included ARMCC assembly candidate remains); "
        "omitting or changing either value is never accepted against this plan."
    )


def _memory_layout_option_guidance(layout: MemoryLayout | None) -> str:
    """Return the exact reviewed layout choice the plan/apply must retain."""
    if layout is None:
        return ""
    return (
        " Retain memoryLayout="
        + json.dumps(layout.to_dict(), sort_keys=True, separators=(",", ":"))
        + " for the PLAN and apply requests; a different or omitted mapping is "
        "a different reviewed choice and is never accepted against this plan."
    )


def _extra_regions_option_guidance(
    extra_regions: tuple[ExtraRegion, ...],
) -> str:
    """Return the exact reviewed extra-region request to retain."""
    if not extra_regions:
        return ""
    return (
        " Retain extraRegions="
        + json.dumps(
            [region.to_dict() for region in extra_regions],
            sort_keys=True,
            separators=(",", ":"),
        )
        + " for the PLAN and apply requests; omitting or changing any entry is "
        "a different reviewed request and is never accepted against this plan."
    )


def _plan_readiness(
    git: dict[str, object],
    blocker_total: int,
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
    extra_regions: tuple[ExtraRegion, ...] = (),
) -> dict[str, object]:
    """Whether the technical/Git prerequisites for obtaining a plan are met.

    This is deliberately not apply readiness.  Even when every prerequisite is
    satisfied, no plan exists yet and no authorization has been granted.
    """
    repository = git["repository"]
    head = git["head"]
    worktree = git["worktree"]
    assert isinstance(repository, dict)
    assert isinstance(head, dict)
    assert isinstance(worktree, dict)

    repository_available = repository["available"] is True
    toplevel_match = repository["projectRootIsToplevel"] is True
    head_available = head["available"] is True
    worktree_clean = worktree["status"] == "clean"

    prerequisites = [
        _prerequisite(
            "technical-blockers",
            blocker_total == 0,
            f"{blocker_total} technical migration blocker(s) remain.",
            "Resolve every reported blocker; preflight does not edit files or bypass rules.",
        ),
        _prerequisite(
            "git-repository",
            repository_available,
            "The project root must be inside a readable Git repository.",
            "Inspect data.git.repository.error (code/rule) and confirm Git installation plus repository readability/access. Only if the owner confirms no repository exists, establish a Git worktree as an explicit project-owner decision; preflight never runs git init.",
        ),
        _prerequisite(
            "git-project-root-is-toplevel",
            repository_available and toplevel_match,
            "The project root must be the canonical Git worktree toplevel.",
            "Inspect data.git.repository.projectRootIsToplevel and run conversion from the worktree toplevel, or establish a separate owner-approved Git baseline; preflight does not rewrite Git ownership.",
        ),
        _prerequisite(
            "git-committed-head",
            head_available,
            "A committed HEAD is required for the Git-bound conversion plan.",
            "Inspect data.git.head.error/status. If the repository is confirmed unborn, the owner may create its first commit as an explicit baseline decision; otherwise restore repository access. Preflight never commits.",
        ),
        _prerequisite(
            "git-clean-worktree",
            worktree_clean,
            "Index, tracked, and untracked changes must be resolved by the project owner.",
            "Inspect data.git.worktree.status, dirtyPaths, and error. Resolve actual local changes as the owner; Toolkit never stashes, discards, deletes, or ignores them.",
        ),
    ]
    ready = all(item["satisfied"] is True for item in prerequisites)
    next_steps: list[str] = []
    if blocker_total:
        next_steps.append(
            "Resolve the reported technical blockers. Preflight is analysis only: it does not transcode sources, replace startup code, or write a manifest."
        )
    if not repository_available:
        next_steps.append(
            "Inspect data.git.repository.error (code/rule) and confirm Git availability and repository readability/access. If the owner confirms no baseline exists, establish a Git worktree as an explicit project-owner decision; preflight and Toolkit never run git init."
        )
    elif not toplevel_match:
        next_steps.append(
            "Inspect data.git.repository.projectRootIsToplevel; use the Git worktree toplevel as the project root, or establish a separate owner-approved Git baseline. Do not move Git state implicitly."
        )
    if repository_available and toplevel_match and not head_available:
        next_steps.append(
            "Inspect data.git.head.error/status. If the repository is confirmed unborn, the owner may create its first commit as an explicit baseline decision; otherwise restore repository access. Toolkit never commits automatically."
        )
    worktree_status = worktree["status"]
    if repository_available and toplevel_match and worktree_status == "dirty":
        next_steps.append(
            "Commit or intentionally preserve the reported local changes; Toolkit will not stash, discard, or delete them."
        )
    elif repository_available and toplevel_match and worktree_status == "unavailable":
        next_steps.append(
            "Inspect data.git.worktree.error and confirm Git status access; do not assume the worktree is dirty or clean."
        )
    if ready:
        guidance = (
            _startup_option_guidance(startup_options)
            + _memory_layout_option_guidance(memory_layout)
            + _extra_regions_option_guidance(extra_regions)
        )
        next_steps.append(
            "Call stm32_keil_convert (CLI: keil convert --dry-run) with the same uvprojx and targetName and no planId; the read-only PLAN response returns the exact identifier as data.plan_id and the complete diff as data.patches[].unified_diff."
            + guidance
        )
        next_steps.append(
            "Review that plan, then pass its exact data.plan_id as the apply request's planId together with authorized=true only after explicit user authorization."
            + guidance
        )
    return {
        "ready": ready,
        "status": "ready-for-plan" if ready else "blocked",
        "planId": None,
        "requiresReviewedPlan": True,
        "prerequisites": prerequisites,
        "nextSteps": next_steps,
    }


def _apply_readiness(
    plan_readiness: dict[str, object],
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
    extra_regions: tuple[ExtraRegion, ...] = (),
) -> dict[str, object]:
    """Apply is never ready from preflight, regardless of plan prerequisites."""
    prerequisites = plan_readiness["prerequisites"]
    assert isinstance(prerequisites, (list, tuple))
    unmet = [
        str(item["id"])
        for item in prerequisites
        if isinstance(item, dict) and item.get("satisfied") is not True
    ]
    guidance = (
        _startup_option_guidance(startup_options)
        + _memory_layout_option_guidance(memory_layout)
        + _extra_regions_option_guidance(extra_regions)
    )
    if plan_readiness["ready"] is True:
        next_steps = [
            "Call stm32_keil_convert with the same uvprojx and targetName and no planId to obtain the read-only PLAN response; read data.plan_id and data.patches[].unified_diff."
            + guidance,
            "Only after reviewing that exact plan and obtaining explicit user authorization, call stm32_keil_convert with planId set to the reviewed data.plan_id and authorized=true."
            + guidance,
        ]
    else:
        blockers = (
            " Resolve these unmet planReadiness prerequisites first: "
            + ", ".join(unmet)
            + ". See data.analysis.blockers and each prerequisite's nextStep, and inspect the reported data.git evidence."
        )
        next_steps = [
            blockers.strip(),
            "After planReadiness.status becomes ready-for-plan, call stm32_keil_convert with the same uvprojx and targetName and no planId to obtain the read-only PLAN response; read data.plan_id and data.patches[].unified_diff."
            + guidance,
            "Only after reviewing that exact plan and obtaining explicit user authorization, call stm32_keil_convert with planId set to the reviewed data.plan_id and authorized=true."
            + guidance,
        ]
    return {
        "ready": False,
        "status": "requires-reviewed-plan",
        "planId": None,
        "planReadinessStatus": plan_readiness["status"],
        "reason": (
            "Preflight has produced no applicable plan and grants no apply "
            "authorization. A current Git-bound conversion plan must be "
            "obtained, reviewed, and explicitly authorized separately."
        ),
        "nextSteps": next_steps,
    }


_NEEDS_USER_INPUT = "needs-user-input"
_UNSUPPORTED = "unsupported"

#: Known blocker classifications:
#: ``(category, summary, tool, skill, requiredInputs)``.
#: ``tool`` may name only a real MCP tool; the comment-copy helper is the
#: separate ``normalize-source-comments`` Skill, reported in ``skill``.
#: Every entry names only inputs that the current preflight actually accepts
#: (``memoryLayout``); framework, FPU, and ABI overrides are deliberately
#: absent because no such preflight parameter exists.
_KNOWN_REMEDIATION: dict[
    str, tuple[str, str, str | None, str | None, tuple[str, ...]]
] = {
    "MEMORY_LAYOUT_REQUIRED": (
        _NEEDS_USER_INPUT,
        "Choose exactly one existing region for each of flash, data, bss, heap,"
        " and stack from data.analysis.memoryLayout.candidates, then pass that"
        " same memoryLayout object to preflight, the PLAN call, and apply.",
        "stm32_keil_preflight",
        None,
        ("memoryLayout",),
    ),
    "ARMCC_SOURCE_ENCODING_UNSUPPORTED": (
        _NEEDS_USER_INPUT,
        "Only when every affected file's charset is explicitly declared and"
        " the reviewed change is comment-only, the normalize-source-comments"
        " Skill can prepare a reviewed UTF-8 copy outside the project; verify"
        " the bytes, then rerun inspect and preflight. Other byte sequences or"
        " non-comment content remain unsupported, and Toolkit never transcodes"
        " the original file.",
        None,
        "normalize-source-comments",
        (),
    ),
    "MIGRATION_MANIFEST_EXISTS": (
        _NEEDS_USER_INPUT,
        "Review the existing .stm32-project.json conflict as the project owner"
        " and decide whether that file or the migration tree should change;"
        " preflight never edits, overwrites, or deletes it.",
        None,
        None,
        (),
    ),
    "MIGRATION_MEMORY_INCOMPLETE": (
        _UNSUPPORTED,
        "The Keil project must declare at least one executable and one"
        " writable memory region. Preflight does not synthesize missing"
        " regions, and memoryLayout may only name declared regions.",
        None,
        None,
        (),
    ),
    "MIGRATION_COMPILER_UNSUPPORTED": (
        _UNSUPPORTED,
        "Only an ARM Compiler 5 project is analyzed. Preflight has no"
        " parameter to select another compiler or translate this toolchain.",
        None,
        None,
        (),
    ),
    "MIGRATION_FRAMEWORK_SELECTION_REQUIRED": (
        _UNSUPPORTED,
        "Preflight has no framework selection parameter. Inspect the actual"
        " project configuration and toolchain/build evidence, retain the"
        " existing framework intent, and use a separately reviewed"
        " project-owned port if the target toolchain requires a different"
        " framework. Never remove framework controls merely to clear this"
        " blocker.",
        None,
        None,
        (),
    ),
    "MIGRATION_FPU_UNSUPPORTED": (
        _UNSUPPORTED,
        "Preflight has no FPU override. Inspect the Keil FPU evidence together"
        " with the actual toolchain and build configuration, retain that"
        " evidence, and use a separately reviewed project-owned port if the"
        " target toolchain needs a different FPU setting. Do not alter the"
        " evidence or invent an FPU fact merely to clear this blocker.",
        None,
        None,
        (),
    ),
    "MIGRATION_FPU_SELECTION_UNSUPPORTED": (
        _UNSUPPORTED,
        "Preflight has no FPU hardware-selection override. Inspect the selected"
        " target's ArmAdsMisc/RvdsVP together with the actual toolchain and"
        " build configuration, retain that evidence, and use a separately"
        " reviewed project-owned port if the selection must change. Do not"
        " alter the selector or an ABI declaration merely to clear this"
        " blocker.",
        None,
        None,
        (),
    ),
    "MIGRATION_FLOAT_ABI_REQUIRED": (
        _UNSUPPORTED,
        "Preflight has no float-ABI selection parameter. Inspect the actual"
        " Keil and toolchain/build evidence, retain its current semantics, and"
        " use a separately reviewed project-owned port if the float ABI must"
        " change. Do not invent an ABI fact or alter the evidence merely to"
        " clear this blocker.",
        None,
        None,
        (),
    ),
    "MIGRATION_FLOAT_ABI_REQUIRES_FPU": (
        _UNSUPPORTED,
        "The Keil float-ABI evidence requires matching FPU evidence. Preflight"
        " cannot supply either value; inspect and retain the actual"
        " toolchain/build evidence and use a separately reviewed"
        " project-owned port if those settings must change. Do not change one"
        " fact merely to satisfy this cross-check.",
        None,
        None,
        (),
    ),
    "MIGRATION_FLOAT_ABI_UNSUPPORTED": (
        _UNSUPPORTED,
        "Preflight has no float-ABI override. Inspect and retain the actual"
        " Keil and toolchain/build evidence, and use a separately reviewed"
        " project-owned port if a different float ABI is required. Do not"
        " relabel unsupported evidence as supported merely to clear this"
        " blocker.",
        None,
        None,
        (),
    ),
    "ARMCC_ASSEMBLY_UNSUPPORTED": (
        _UNSUPPORTED,
        "Review the included ARMCC assembly. A conventional ST/CMSIS"
        " Cortex-M3/M4/M7 startup file may be reviewed through the optional"
        " startupStrategy=generate-cmsis-gcc route and its analysis.startup"
        " diagnostics; arbitrary or unknown assembly is never promised or"
        " translated automatically.",
        "stm32_keil_preflight",
        None,
        (),
    ),
    "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED": (
        _UNSUPPORTED,
        "This absolute-placement grammar is not supported and is never"
        " rewritten. Keep it project-owned and resolve it explicitly outside"
        " the conversion.",
        None,
        None,
        (),
    ),
    "ARMCC_ALIGN_UNSUPPORTED": (
        _UNSUPPORTED,
        "This __align form, bound, or declaration grammar is not supported and"
        " is never rewritten. Keep it project-owned and resolve it explicitly"
        " outside the conversion; Toolkit never carries an unresolved __align"
        " into GNU source.",
        None,
        None,
        (),
    ),
    "MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY": (
        _NEEDS_USER_INPUT,
        "A fixed placement address lies outside every declared memory region."
        " Review the actual memory map and, when the project owner confirms a"
        " writable RAM region such as external SRAM, pass its exact name,"
        " origin, byte length and rw-/rwx attributes as extraRegions. Preflight"
        " never guesses a length, invents an external region, or changes the"
        " inspected Keil base regions.",
        "stm32_keil_preflight",
        None,
        ("extraRegions",),
    ),
    "ARMCC_OPTION_UNSUPPORTED": (
        _UNSUPPORTED,
        "Scoped or target ARMCC compiler options are not representable."
        " Inspect the option evidence, retain its intended semantics, and use"
        " a separately reviewed project-owned port; preflight has no option"
        " override, and controls must not be removed merely to clear this"
        " blocker.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_PATH_MISSING": (
        _UNSUPPORTED,
        "The scoped include directory does not exist. Inspect the group/file"
        " IncludePath evidence, retain the intended scope, and resolve the"
        " missing directory or scope as a project-owned change; Toolkit never"
        " invents, creates, or silently drops a search directory.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_PATH_NOT_DIRECTORY": (
        _UNSUPPORTED,
        "The scoped include path is not a directory. Inspect the group/file"
        " IncludePath evidence, retain the intended scope, and resolve the"
        " path as a project-owned change; Toolkit never substitutes a"
        " directory or drops the scope.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_PATH_ESCAPES": (
        _UNSUPPORTED,
        "The scoped include path leaves the canonical project root. Inspect"
        " the group/file IncludePath evidence and keep every search directory"
        " inside the project as a project-owned change; Toolkit never follows"
        " an out-of-root search path.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_PATH_UNREADABLE": (
        _UNSUPPORTED,
        "The scoped include directory or its inventory cannot be read."
        " Inspect the actual filesystem access, retain the intended scope, and"
        " resolve readability as a project-owned change; Toolkit never"
        " assumes an unreadable directory is empty.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_REDIRECT_UNSUPPORTED": (
        _UNSUPPORTED,
        "A symlink or reparse entry is involved in the scoped include path or"
        " its inventory. Inspect the actual redirect target, retain the"
        " intended scope, and use a project-owned directory layout; Toolkit"
        " does not follow redirects when deciding header conflicts.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_LIMIT_EXCEEDED": (
        _UNSUPPORTED,
        "The scoped include inventory exceeds the aggregate bounded traversal"
        " or hash budget. Inspect the actual directory contents and reduce or"
        " relocate the scope as a project-owned change; Toolkit never samples"
        " a partial inventory for a conflict decision.",
        None,
        None,
        (),
    ),
    "MIGRATION_INCLUDE_COLLISION": (
        _UNSUPPORTED,
        "One case-insensitive include-relative key resolves to different"
        " files in two search directories, so translated header resolution"
        " would be ambiguous. Inspect the reported key and files, decide which"
        " header the build must use, and remove the ambiguity as a"
        " project-owned change; Toolkit never guesses precedence or edits"
        " headers. Overlapping directories that expose the same physical files"
        " are not a conflict.",
        None,
        None,
        (),
    ),
    "ARMCC_PRAGMA_UNSUPPORTED": (
        _UNSUPPORTED,
        "This ARMCC pragma has no supported automatic translation. Review the"
        " reported evidence and handle it as a project-owned source change.",
        None,
        None,
        (),
    ),
    "ARMCC_FINDING_UNSUPPORTED": (
        _UNSUPPORTED,
        "This inspection finding has no supported automatic translation."
        " Review the reported evidence and handle it as a project-owned"
        " change.",
        None,
        None,
        (),
    ),
    "ARMCC_LINKER_CONFIGURATION_UNSUPPORTED": (
        _UNSUPPORTED,
        "The linker or scatter configuration requires project-owned"
        " translation and is never rewritten automatically. Review the"
        " reported evidence outside preflight.",
        None,
        None,
        (),
    ),
}

_STARTUP_REMEDIATION_SUMMARY = (
    "Review analysis.startup and its diagnostics. The reviewed"
    " startupStrategy=generate-cmsis-gcc route covers only the conventional"
    " ST/CMSIS Cortex-M3/M4/M7 pattern and does not promise support for this"
    " startup diagnostic."
)
_UNKNOWN_REMEDIATION_SUMMARY = (
    "No supported remediation is defined for this blocker code in the current"
    " preflight. Review the returned code, rule_id, path, line, column,"
    " evidence, and message; Toolkit does not auto-fix, suppress, or bypass"
    " it."
)


def _remediation(
    category: str,
    summary: str,
    tool: str | None = None,
    skill: str | None = None,
    required_inputs: tuple[str, ...] = (),
) -> dict[str, object]:
    value: dict[str, object] = {
        "category": category,
        "summary": summary,
        "requiredInputs": list(required_inputs),
    }
    if tool is not None:
        value["tool"] = tool
    if skill is not None:
        value["skill"] = skill
    return value


def _remediation_for(blocker: MigrationBlocker) -> dict[str, object]:
    """Classify one blocker without changing the blocker or conversion plan."""
    known = _KNOWN_REMEDIATION.get(blocker.code)
    if known is not None:
        category, summary, tool, skill, required_inputs = known
        return _remediation(
            category,
            summary,
            tool=tool,
            skill=skill,
            required_inputs=required_inputs,
        )
    if blocker.code.startswith("MIGRATION_STARTUP_"):
        return _remediation(_UNSUPPORTED, _STARTUP_REMEDIATION_SUMMARY)
    return _remediation(_UNSUPPORTED, _UNKNOWN_REMEDIATION_SUMMARY)


def preflight_keil_conversion(
    root: Path,
    inspection: KeilInspection,
    *,
    startup_options: StartupOptions | None = None,
    memory_layout: MemoryLayout | None = None,
    extra_regions: tuple[ExtraRegion, ...] | None = None,
) -> dict[str, object]:
    """Analyze one inspected Keil target without Git and without mutation.

    Stable ``MigrationPlanError`` failures are raised for invalid/unreadable
    or ambiguous input; technical blockers are returned in a successful
    result, independently of apply readiness.
    """
    analysis = analyze_keil_conversion(
        root,
        inspection,
        startup_options=startup_options,
        memory_layout=memory_layout,
        extra_regions=extra_regions,
    )
    extras = analysis.extra_regions
    git = _git_state(analysis.project_root)

    by_code: dict[str, int] = {}
    by_remediation = {_NEEDS_USER_INPUT: 0, _UNSUPPORTED: 0}
    blockers: list[dict[str, object]] = []
    for blocker in analysis.blockers:
        by_code[blocker.code] = by_code.get(blocker.code, 0) + 1
        remediation = _remediation_for(blocker)
        category = remediation["category"]
        assert isinstance(category, str)
        by_remediation[category] += 1
        blockers.append({**blocker.to_dict(), "remediation": remediation})

    fresh = analysis.inspection
    plan_readiness = _plan_readiness(
        git, len(analysis.blockers), startup_options, memory_layout, extras
    )
    payload = {
        "analysis": {
            "complete": True,
            "status": "complete",
            "requiresGit": False,
            "mutating": False,
            "ruleset": _ANALYSIS_RULESET,
            "selection": {
                "projectFile": fresh.project_file,
                "targetName": fresh.target_name,
                "device": fresh.device,
                "compiler": fresh.compiler,
                "framework": fresh.framework,
                "projectSha256": fresh.project_sha256,
                "inspectionSha256": inspection_sha256_for(fresh),
            },
            "inputs": [entry.to_dict() for entry in analysis.inputs],
            "blockers": blockers,
            "blockerSummary": {
                "total": len(analysis.blockers),
                "byCode": dict(sorted(by_code.items())),
                "byRemediation": dict(sorted(by_remediation.items())),
            },
            "fixedSections": [
                section.to_dict() for section in analysis.fixed_sections
            ],
            "memoryLayout": (
                analysis.memory_layout.to_dict()
                if analysis.memory_layout is not None
                else None
            ),
            # Same deterministic evidence object as the PLAN and conversion
            # report; derived from the fresh inspection, never caller-supplied.
            "floatAbi": analysis.float_abi,
        },
        "git": git,
        "planReadiness": plan_readiness,
        "applyReadiness": _apply_readiness(
            plan_readiness, startup_options, memory_layout, extras
        ),
        # Additive post-migration prerequisite, never a technical blocker or
        # planReadiness item: an ordinary conversion writes ``debug: {}`` and
        # remains valid for build-only use.
        "debugConfiguration": post_migration_debug_configuration(),
    }
    if analysis.startup is not None:
        payload["analysis"]["startup"] = analysis.startup.to_dict()
    if extras:
        # Additive reviewed evidence; absent for the historical no-extra
        # request so preflight bytes stay unchanged.
        payload["analysis"]["extraRegions"] = [
            region.to_dict() for region in extras
        ]
    if analysis.include_merges:
        # Additive reviewed evidence: absent when no include-only scope was
        # analyzed, so historical preflight payloads are unchanged.
        payload["analysis"]["includeMerges"] = [
            merge.to_report_dict() for merge in analysis.include_merges
        ]
    # Concise supported-change evidence: exact rule IDs and the same digests
    # the PLAN patches carry, so a reviewer can distinguish proposed supported
    # changes from blockers without reading the full diff.  PLAN keeps the
    # complete unified diffs; this is presentation only and grants nothing.
    source_changes = [
        {
            "path": patch.path,
            "ruleIds": list(patch.rule_ids),
            "beforeSha256": patch.before_sha256,
            "afterSha256": patch.after_sha256,
        }
        for patch in analysis.patches
    ]
    if source_changes:
        payload["analysis"]["sourceChanges"] = source_changes
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > _PREFLIGHT_OUTPUT_LIMIT_BYTES:
        raise MigrationPlanError(
            "MIGRATION_LIMIT_EXCEEDED",
            "preflight output exceeds the limit",
            {"scope": "preflight", "limitBytes": _PREFLIGHT_OUTPUT_LIMIT_BYTES},
        )
    return payload


__all__ = ["preflight_keil_conversion"]
