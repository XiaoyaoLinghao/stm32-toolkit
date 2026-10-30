from pathlib import Path

from stm32_toolkit.context import build_project_context
from stm32_toolkit.mcp_server import ServerRuntime, tool_project_detect


MIGRATE_ACTION = {
    "id": "migrate-keil",
    "available": True,
    "explanation": (
        "Inspect the Keil project and convert ARMCC sources to GCC "
        "with a read-only plan and explicit authorization."
    ),
}

PREFLIGHT_ACTION = {
    "id": "keil-preflight",
    "available": True,
    "explanation": (
        "Run stm32_keil_preflight with the selected project-relative uvprojx "
        "and exact targetName. It is read-only, requires no Git, may return "
        "blockers, and does not authorize conversion; the PLAN also needs a "
        "separate absolute new output directory."
    ),
}


def test_context_reports_the_shipped_migration_action_for_keil_projects(
    tmp_path: Path,
):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    payload = build_project_context(
        tmp_path, tmp_path.parent / "plugin-data", "session-a"
    ).to_dict()

    assert payload["data"]["project"]["recommendedAction"] == MIGRATE_ACTION
    assert payload["data"]["recommendedActions"] == [MIGRATE_ACTION, PREFLIGHT_ACTION]
    assert not MIGRATE_ACTION["id"].startswith("/")
    assert payload["data"]["capabilities"]["keilPreflight"] is True
    assert (
        payload["data"]["capabilityDetails"]["keilPreflight"]["status"]
        == "available"
    )


def test_mcp_detection_reports_the_same_migration_action(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    runtime = ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")

    payload = tool_project_detect(runtime)

    assert payload["data"]["recommended_action"] == MIGRATE_ACTION
    assert not MIGRATE_ACTION["id"].startswith("/")
