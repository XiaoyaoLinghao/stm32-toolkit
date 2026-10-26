"""Offline AI invocation guidance: route separation and preflight remediation.

These tests exercise the accepted AI-CALL-GUIDANCE slice as behavior, not as
prose: configured and unconfigured context reporting, the managed/imported
route split, complete failure diagnostics, preflight-only blocker
classification, and inventory-real tool/skill references.  Every repository
and data root is disposable; sentinels prove context performs no probe,
import, admission, or backend effect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import stm32_toolkit.external_firmware as external_firmware
import stm32_toolkit.mcp_server as mcp_mod
import stm32_toolkit.migration.preflight as preflight_mod
import stm32_toolkit.probe.flash as probe_flash
from stm32_toolkit.context import build_project_context
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import plan_keil_conversion
from stm32_toolkit.migration.model import MigrationBlocker
from stm32_toolkit.migration.planner import analyze_keil_conversion
from stm32_toolkit.migration.preflight import preflight_keil_conversion
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.public_inventory import MCP_TOOL_NAMES, SKILL_NAMES

from test_build_snapshot import snapshot_build
from test_memory_layout_migration import multi_ram_repo
from test_migration_plan import COMMON_C, MAIN_C, build_repo


REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_MCP_TOOLS = frozenset(MCP_TOOL_NAMES.values())
REAL_SKILLS = frozenset(SKILL_NAMES)


def forbid_external_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail if pure context evaluation touches firmware or hardware."""

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "project context must not read firmware or perform a probe/backend effect"
        )

    for name in (
        "tool_probe_list_for_request",
        "tool_flash_for_request",
        "tool_firmware_import_for_request",
        "tool_firmware_admit_for_request",
        "tool_flash_imported_for_request",
    ):
        monkeypatch.setattr(mcp_mod, name, forbidden)
    for name in (
        "analyze_import",
        "firmware_import_workflow",
        "firmware_admit_workflow",
        "flash_imported_firmware",
    ):
        monkeypatch.setattr(external_firmware, name, forbidden)
    monkeypatch.setattr(probe_flash, "flash_firmware", forbidden)


def routes_of(payload: dict) -> tuple[dict, dict]:
    data = payload["data"]
    return data["firmwareRoutes"]["managed"], data["firmwareRoutes"]["imported"]


def assert_imported_not_evaluated(imported: dict) -> None:
    assert imported["status"] == "not-evaluated"
    assert imported["requiresGit"] is False
    assert imported["requiresManagedModel"] is False
    assert imported["selection"] == "explicit"
    assert imported["tools"] == [
        "stm32_firmware_import",
        "stm32_firmware_admit",
        "stm32_flash_imported",
    ]
    reason = imported["reason"]
    assert "no firmware" in reason or "does not read or evaluate" in reason
    assert "Tool availability is not image readiness" in reason
    assert set(imported["tools"]) <= REAL_MCP_TOOLS


# ---------------------------------------------------------------------------
# context routes
# ---------------------------------------------------------------------------


def test_configured_no_build_context_separates_routes_without_side_effects(
    configured_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forbid_external_effects(monkeypatch)
    result = build_project_context(
        configured_project, tmp_path.parent / f"data-{tmp_path.name}", "session-a"
    )

    payload = result.to_dict()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["project"]["kind"] == "configured"
    assert data["build"]["elfFresh"] is False
    assert data["build"]["buildId"] is None

    managed, imported = routes_of(payload)
    flash = data["capabilityDetails"]["flash"]
    assert flash["status"] == "not-evaluated"
    assert managed["status"] == flash["status"]
    assert managed["reason"] == flash["reason"]
    assert managed["nextSteps"] == flash["nextSteps"]
    assert managed["identity"] == ["buildId", "elfSha256"]
    assert managed["requiresGit"] is True
    assert managed["requiresManagedModel"] is True
    assert set(managed["tools"]) <= REAL_MCP_TOOLS
    assert "stm32_flash" in managed["tools"]
    assert "managed flash entry covers only stm32_flash" in managed["reason"]
    assert_imported_not_evaluated(imported)


def test_unconfigured_keil_context_reports_routes_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_repo(tmp_path, name="keil-no-git", commit=False)
    assert not (root / ".git").exists()
    forbid_external_effects(monkeypatch)

    result = build_project_context(root, tmp_path / "data", "session-a")

    payload = result.to_dict()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["project"]["kind"] == "keil"
    assert data["workspace"] is None
    assert data["capabilities"]["keilPreflight"] is True
    assert data["hardware"] == {"probe": None, "state": "unavailable"}
    # Keil delivery guidance is available without Git and names the actual
    # independent-destination fields instead of an in-place default.
    convert = data["capabilityDetails"]["keilConvert"]
    assert convert["status"] == "available"
    convert_text = " ".join([convert["reason"], *convert["nextSteps"]])
    for field in (
        "destination",
        "data.planId",
        "data.outputs[]",
        "data.sourcePatches[]",
        "outputRoot",
    ):
        assert field in convert_text, field

    managed, imported = routes_of(payload)
    assert managed["status"] == "not-evaluated"
    assert "Git-shaped managed firmware provenance" in managed["reason"]
    assert any("committed HEAD" in step for step in managed["nextSteps"])
    assert_imported_not_evaluated(imported)


def test_snapshot_only_context_blocks_managed_flash_but_not_import_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch, name="snapshot")
    forbid_external_effects(monkeypatch)

    payload = build_project_context(root, tmp_path / "data", "session-a").to_dict()

    assert payload["ok"] is True
    data = payload["data"]
    details = data["capabilityDetails"]
    managed, imported = routes_of(payload)
    assert managed["status"] == "blocked"
    assert "FIRMWARE_PROVENANCE_UNSUPPORTED" in managed["reason"]
    assert details["flash"]["status"] == managed["status"]
    # Only managed flash may describe the separate imported route.
    flash_text = " ".join([details["flash"]["reason"], *details["flash"]["nextSteps"]])
    assert "stm32_firmware_import" in flash_text
    for key in ("targetTest", "monitor", "breakpointDebug"):
        assert details[key]["status"] == "blocked"
        text = " ".join([details[key]["reason"], *details[key]["nextSteps"]]).lower()
        assert "import" not in text, key
    # The imported route is never selected, admitted, or made ready by a block.
    assert_imported_not_evaluated(imported)


# ---------------------------------------------------------------------------
# failure diagnostics remain complete
# ---------------------------------------------------------------------------


def test_context_invalid_data_root_preserves_exact_failure_and_has_no_data(
    configured_project: Path,
) -> None:
    result = build_project_context(
        configured_project, configured_project / "data-inside", "session-a"
    )

    payload = result.to_dict()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["code"] == "PROJECT_CONTEXT_INVALID"
    assert payload["message"] == "Project context parameters are invalid"
    assert payload["details"] == {
        "field": "dataRoot",
        "path": str((configured_project / "data-inside").resolve(strict=False)),
    }


def test_context_model_failure_preserves_exact_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "bad-model"
    root.mkdir()
    (root / ".stm32-project.json").write_text(
        json.dumps({"schemaVersion": 1}) + "\n", encoding="utf-8"
    )

    try:
        ProjectManifest.load(root)
    except ProjectManifestError as error:
        expected_code = error.code
        expected_message = error.message
        expected_details = dict(error.details)
    else:  # pragma: no cover - fixture contract
        raise AssertionError("fixture manifest must fail to load")

    payload = build_project_context(
        root, tmp_path / "data", "session-a"
    ).to_dict()

    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["operation"] == "project.context"
    assert payload["code"] == expected_code
    assert payload["message"] == expected_message
    assert payload["details"] == expected_details


# ---------------------------------------------------------------------------
# preflight remediation
# ---------------------------------------------------------------------------


def _removals(blockers: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {key: value for key, value in blocker.items() if key != "remediation"}
        for blocker in blockers
    ]


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value)
        for item in value.values():
            keys |= _all_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys |= _all_keys(item)
    return keys


def _blocker(
    data: dict[str, object], code: str
) -> dict[str, object]:
    analysis = data["analysis"]
    assert isinstance(analysis, dict)
    return next(
        blocker for blocker in analysis["blockers"] if blocker["code"] == code
    )


def test_preflight_remediation_classifies_known_and_unknown_without_changing_blockers(
    tmp_path: Path,
) -> None:
    root = multi_ram_repo(tmp_path)
    inspection = inspect_keil(root)
    analysis = analyze_keil_conversion(root, inspection)
    plan_before = plan_keil_conversion(root, inspection)
    data = preflight_keil_conversion(root, inspection)
    plan_after = plan_keil_conversion(root, inspection)

    blockers = data["analysis"]["blockers"]
    # Every original blocker field, order, and value is unchanged.
    assert _removals(blockers) == [blocker.to_dict() for blocker in analysis.blockers]
    summary = data["analysis"]["blockerSummary"]
    assert summary["total"] == len(analysis.blockers)
    assert sum(summary["byCode"].values()) == summary["total"]
    categories = [blocker["remediation"]["category"] for blocker in blockers]
    assert summary["byRemediation"] == {
        "needs-user-input": categories.count("needs-user-input"),
        "unsupported": categories.count("unsupported"),
    }

    layout = _blocker(data, "MEMORY_LAYOUT_REQUIRED")["remediation"]
    assert layout["category"] == "needs-user-input"
    assert layout["tool"] == "stm32_keil_preflight"
    assert layout["tool"] in REAL_MCP_TOOLS
    assert layout["requiredInputs"] == ["memoryLayout"]
    assert "skill" not in layout

    assembly = _blocker(data, "ARMCC_ASSEMBLY_UNSUPPORTED")["remediation"]
    assert assembly["category"] == "unsupported"
    assert assembly["tool"] == "stm32_keil_preflight"
    assert assembly["requiredInputs"] == []

    # Classification is preflight presentation only: a plan taken before and
    # after preflight is byte-for-byte identical, so review presentation
    # cannot alter the plan identity/digest.  The plan also gains no
    # remediation key and keeps every original blocker field.
    plan_payload = plan_after.to_dict()
    assert plan_after.to_dict() == plan_before.to_dict()
    assert plan_after.plan_id == plan_before.plan_id
    assert list(plan_payload["blockers"]) == _removals(blockers)
    assert "remediation" not in _all_keys(plan_payload)
    assert data["planReadiness"]["planId"] is None
    assert data["applyReadiness"]["ready"] is False


def test_preflight_encoding_remediation_is_conditional_and_skill_not_tool(
    tmp_path: Path,
) -> None:
    root = build_repo(
        tmp_path,
        name="encoding",
        files={"Main/main.c": MAIN_C, "Common/common.c": COMMON_C},
    )
    (root / "Common" / "common.c").write_bytes(b"\xff\xfe not utf-8\n")

    data = preflight_keil_conversion(root, inspect_keil(root))
    remediation = _blocker(data, "ARMCC_SOURCE_ENCODING_UNSUPPORTED")["remediation"]

    assert remediation["category"] == "needs-user-input"
    assert remediation["skill"] == "normalize-source-comments"
    assert remediation["skill"] in REAL_SKILLS
    assert "tool" not in remediation
    summary = remediation["summary"]
    assert "explicitly declared" in summary
    assert "comment-only" in summary
    assert "Other byte sequences or non-comment content remain unsupported" in summary
    assert remediation["requiredInputs"] == []


def test_fpu_abi_framework_and_option_remediation_preserves_semantics() -> None:
    codes = (
        "MIGRATION_FRAMEWORK_SELECTION_REQUIRED",
        "MIGRATION_FPU_UNSUPPORTED",
        "MIGRATION_FPU_SELECTION_UNSUPPORTED",
        "MIGRATION_FLOAT_ABI_REQUIRED",
        "MIGRATION_FLOAT_ABI_REQUIRES_FPU",
        "MIGRATION_FLOAT_ABI_UNSUPPORTED",
        "ARMCC_OPTION_UNSUPPORTED",
    )
    for code in codes:
        remediation = preflight_mod._remediation_for(
            MigrationBlocker(code, "rule", "Main/main.c", 1, 1, "evidence", "message")
        )
        assert remediation["category"] == "unsupported", code
        assert "tool" not in remediation and "skill" not in remediation, code
        assert remediation["requiredInputs"] == [], code
        summary = remediation["summary"].lower()
        # Preserve the real evidence and semantics instead of editing it to
        # clear the blocker; there is no override parameter to advertise.
        assert "inspect" in summary, code
        assert "retain" in summary, code
        assert "project-owned port" in summary, code
        assert "correct the" not in summary, code
        assert "remove or" not in summary, code


def test_unknown_and_startup_remediation_remain_unsupported() -> None:
    unknown = preflight_mod._remediation_for(
        MigrationBlocker("FUTURE_UNKNOWN_CODE", "rule", "x", 1, 1, "ev", "msg")
    )
    assert unknown == {
        "category": "unsupported",
        "summary": preflight_mod._UNKNOWN_REMEDIATION_SUMMARY,
        "requiredInputs": [],
    }

    startup = preflight_mod._remediation_for(
        MigrationBlocker(
            "MIGRATION_STARTUP_SELECTION_REQUIRED", "rule", "x", 1, 1, "ev", "msg"
        )
    )
    assert startup == {
        "category": "unsupported",
        "summary": preflight_mod._STARTUP_REMEDIATION_SUMMARY,
        "requiredInputs": [],
    }


def test_every_known_remediation_reference_exists_in_the_public_inventory() -> None:
    seen_references: set[str] = set()
    for code, (category, summary, tool, skill, required_inputs) in (
        preflight_mod._KNOWN_REMEDIATION.items()
    ):
        assert code and isinstance(code, str)
        assert summary
        assert category in {"needs-user-input", "unsupported"}
        assert isinstance(required_inputs, tuple)
        assert not (tool is not None and skill is not None), code
        if tool is not None:
            assert tool in REAL_MCP_TOOLS, code
            seen_references.add(tool)
        if skill is not None:
            assert skill in REAL_SKILLS, code
            seen_references.add(skill)
    assert "stm32_keil_preflight" in seen_references
    assert "normalize-source-comments" in seen_references


def test_context_route_tools_and_skill_names_are_public() -> None:
    # The route descriptors embed tool names as data; verify them without
    # requiring a configured project or any backend.
    for tool in (
        "stm32_probe_list",
        "stm32_flash",
        "stm32_firmware_import",
        "stm32_firmware_admit",
        "stm32_flash_imported",
    ):
        assert tool in REAL_MCP_TOOLS
    assert "normalize-source-comments" in REAL_SKILLS


def test_documentation_keeps_route_and_authorization_contracts() -> None:
    """Documentation behavior: no model gate on discovery/import, two writes."""
    flash = (REPO_ROOT / "skills" / "flash-firmware" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert flash.index("**Discovery-only request.**") < flash.index(
        "Call `stm32_project_context`"
    )
    assert "do not require a model" in flash
    # A normal not-evaluated context is not a refusal of managed flash.
    assert "it is not a refusal" in flash
    assert (
        "known `blocked` status or a missing/stale current managed build identity"
        in flash
    )

    guide = (REPO_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    assert 'managed.status == "blocked"' in guide
    assert 'managed.status != "available"' not in guide
    assert "not-evaluated 表示 context 未检查硬件，并非拒绝" in guide
    assert "不要用旧 capabilities 布尔值判断就绪" in guide
    # Managed and imported examples are independent branches; imported needs
    # no managed context/model but root/binding errors stay authoritative.
    assert "两条路线是独立分支" in guide
    assert "不需要 stm32_project_context" in guide
    assert "无效工程根、无效绑定" in guide
    # PLAN and ADMIT are read-only; only APPLY and flash are write boundaries.
    assert "ADMIT 是只读的" in guide
    assert "没有 authorized 参数" in guide
    assert "写授权只有两个边界" in guide
    assert "三次独立授权" not in guide
    assert "admit.data.offlineReady" in guide
    # JSON region sample is decimal and labelled as a reviewed example.
    assert '{"start": 134217728, "length": 1048576}' in guide
    assert "审阅示例，非默认" in guide


def test_documentation_covers_pyocd_evidence_and_vscode_guidance() -> None:
    """Both evidence forms and the derived guidance must be documented."""
    guide = (REPO_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    for field in (
        "data.tools.pyocd",
        "data.probeCore.dependencies.pyocd",
        "data.probeCore.pyocdResolution",
        "runtime-package-present",
        "runtime-package-unconfirmed",
        "distribution-metadata",
        "hardwareVerified=false",
        "PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT",
        "PYOCD_RUNTIME_PACKAGE_UNCONFIRMED",
        "data.vscodeGuidance",
        "bindingMode",
        "requiredUserSettings",
        "userSettingsChecked=false",
        "preservedPaths",
        "VSCODE_EXECUTABLE_SETTINGS_REQUIRED",
        "VSCODE_TASKS_PRESERVED",
    ):
        assert field in guide, field
    # The guide must not present global pip or PATH edits as the fix.
    pyocd_paragraph = guide[guide.index("PyOCD 两条证据必须分开读") :]
    pyocd_paragraph = pyocd_paragraph[: pyocd_paragraph.index("\n")]
    assert "setup-stm32-env.ps1 -Mode Check" in pyocd_paragraph
    assert "不要把全局 pip 安装或 PATH 编辑当作默认修复" in pyocd_paragraph
    assert "不导入 pyOCD" in pyocd_paragraph

    setup = (REPO_ROOT / "skills" / "setup-stm32-env" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for field in (
        "data.tools.pyocd",
        "data.probeCore.pyocdResolution",
        "runtime-package-present",
        "runtime-package-unconfirmed",
        "PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT",
        "PYOCD_RUNTIME_PACKAGE_UNCONFIRMED",
        "never treat a global pip install or PATH edit as the default remedy",
    ):
        assert field in setup, field

    configure = (
        REPO_ROOT / "skills" / "configure-stm32-project" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for field in (
        "data.vscodeGuidance",
        "userSettingsChecked=false",
        "VSCODE_EXECUTABLE_SETTINGS_REQUIRED",
        "VSCODE_TASKS_PRESERVED",
        "preservedPaths",
        "never imply that PATH installation is required",
    ):
        assert field in configure, field


def test_documentation_describes_independent_delivery_and_root_rebinding() -> None:
    """AI guidance names the actual destination-delivery public fields.

    Both the migration Skill and the user guide must describe the explicit
    destination, the camelCase delivery plan/result fields, the no-in-place
    boundary and the explicit output-root handoff.  The flash Skill must not
    reduce the unpublished snapshot firmware limitation to one route.
    """
    migrate = (REPO_ROOT / "skills" / "migrate-keil" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    flash = (REPO_ROOT / "skills" / "flash-firmware" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    guide = (REPO_ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")

    for text in (migrate, guide):
        assert "DELIVERY_DESTINATION_REQUIRED" in text
        assert "data.planId" in text
        assert "data.outputs[]" in text
        assert "data.sourcePatches[]" in text
        assert "outputRoot" in text
        assert "PLAN_CHANGED" in text
    assert "authorized=true" in migrate
    # No silent in-place fallback and no stale Git baseline prerequisite.
    assert "in-place" in migrate
    assert "Git baseline" not in migrate
    # The user guide owns the detailed unpublished/local limitation and the
    # explicit (never automatic) rebinding of the delivered project root.
    assert "keil convert --destination" in guide
    assert "本地未发布" in guide
    assert "原地 `keil convert`" in guide
    assert "把 `data.outputRoot` 绑定为 VS Code workspace" in guide
    assert "不要偷偷改现有服务器绑定" in guide
    # The managed firmware-provenance limitation affects more than flash.
    assert "Git-shaped provenance" in guide
    assert "debug handoff" in guide
    assert "Target 测试" in guide
    assert "Monitor" in guide
    # Flash guidance must not call managed flash the only Git dependency.
    assert "only current Git dependency" not in flash
    assert "debug handoff" in flash
    assert "Target tests" in flash
    assert "Monitor" in flash
