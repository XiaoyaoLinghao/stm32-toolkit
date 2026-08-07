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


def test_context_reports_the_shipped_migration_action_for_keil_projects(
    tmp_path: Path,
):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    payload = build_project_context(
        tmp_path, tmp_path.parent / "plugin-data", "session-a"
    ).to_dict()

    assert payload["data"]["project"]["recommendedAction"] == MIGRATE_ACTION
    assert payload["data"]["recommendedActions"] == [MIGRATE_ACTION]
    assert not MIGRATE_ACTION["id"].startswith("/")


def test_mcp_detection_reports_the_same_migration_action(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    runtime = ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")

    payload = tool_project_detect(runtime)

    assert payload["data"]["recommended_action"] == MIGRATE_ACTION
    assert not MIGRATE_ACTION["id"].startswith("/")
