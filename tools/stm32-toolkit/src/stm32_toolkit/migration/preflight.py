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

from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.migration import git_guard
from stm32_toolkit.migration.model import MigrationPlanError, inspection_sha256_for
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
    except MigrationPlanError as error:
        state["repository"] = {
            "available": False,
            "projectRootIsToplevel": None,
            "error": _error_evidence(error),
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
    except MigrationPlanError as error:
        state["head"] = {
            "available": False,
            "commit": None,
            "status": "unavailable",
            "reason": "No committed HEAD is available for the Git-bound plan.",
            "error": _error_evidence(error),
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
    except MigrationPlanError as error:
        state["worktree"] = {
            "status": "unavailable",
            "dirtyPaths": [],
            "reason": "Git worktree status is unavailable.",
            "error": _error_evidence(error),
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


def _plan_readiness(
    git: dict[str, object], blocker_total: int
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
        next_steps.append(
            "Call stm32_keil_convert (CLI: keil convert --dry-run) with the same uvprojx and targetName and no planId; the read-only PLAN response returns the exact identifier as data.plan_id and the complete diff as data.patches[].unified_diff."
        )
        next_steps.append(
            "Review that plan, then pass its exact data.plan_id as the apply request's planId together with authorized=true only after explicit user authorization."
        )
    return {
        "ready": ready,
        "status": "ready-for-plan" if ready else "blocked",
        "planId": None,
        "requiresReviewedPlan": True,
        "prerequisites": prerequisites,
        "nextSteps": next_steps,
    }


def _apply_readiness(plan_readiness: dict[str, object]) -> dict[str, object]:
    """Apply is never ready from preflight, regardless of plan prerequisites."""
    prerequisites = plan_readiness["prerequisites"]
    assert isinstance(prerequisites, (list, tuple))
    unmet = [
        str(item["id"])
        for item in prerequisites
        if isinstance(item, dict) and item.get("satisfied") is not True
    ]
    if plan_readiness["ready"] is True:
        next_steps = [
            "Call stm32_keil_convert with the same uvprojx and targetName and no planId to obtain the read-only PLAN response; read data.plan_id and data.patches[].unified_diff.",
            "Only after reviewing that exact plan and obtaining explicit user authorization, call stm32_keil_convert with planId set to the reviewed data.plan_id and authorized=true.",
        ]
    else:
        blockers = (
            " Resolve these unmet planReadiness prerequisites first: "
            + ", ".join(unmet)
            + ". See data.analysis.blockers and each prerequisite's nextStep, and inspect the reported data.git evidence."
        )
        next_steps = [
            blockers.strip(),
            "After planReadiness.status becomes ready-for-plan, call stm32_keil_convert with the same uvprojx and targetName and no planId to obtain the read-only PLAN response; read data.plan_id and data.patches[].unified_diff.",
            "Only after reviewing that exact plan and obtaining explicit user authorization, call stm32_keil_convert with planId set to the reviewed data.plan_id and authorized=true.",
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


def preflight_keil_conversion(
    root: Path, inspection: KeilInspection
) -> dict[str, object]:
    """Analyze one inspected Keil target without Git and without mutation.

    Stable ``MigrationPlanError`` failures are raised for invalid/unreadable
    or ambiguous input; technical blockers are returned in a successful
    result, independently of apply readiness.
    """
    analysis = analyze_keil_conversion(root, inspection)
    git = _git_state(analysis.project_root)

    by_code: dict[str, int] = {}
    for blocker in analysis.blockers:
        by_code[blocker.code] = by_code.get(blocker.code, 0) + 1

    fresh = analysis.inspection
    plan_readiness = _plan_readiness(git, len(analysis.blockers))
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
            "blockers": [blocker.to_dict() for blocker in analysis.blockers],
            "blockerSummary": {
                "total": len(analysis.blockers),
                "byCode": dict(sorted(by_code.items())),
            },
            "fixedSections": [
                section.to_dict() for section in analysis.fixed_sections
            ],
        },
        "git": git,
        "planReadiness": plan_readiness,
        "applyReadiness": _apply_readiness(plan_readiness),
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > _PREFLIGHT_OUTPUT_LIMIT_BYTES:
        raise MigrationPlanError(
            "MIGRATION_LIMIT_EXCEEDED",
            "preflight output exceeds the limit",
            {"scope": "preflight", "limitBytes": _PREFLIGHT_OUTPUT_LIMIT_BYTES},
        )
    return payload


__all__ = ["preflight_keil_conversion"]
