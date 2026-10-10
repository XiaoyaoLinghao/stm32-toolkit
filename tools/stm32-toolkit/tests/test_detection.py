import os
from pathlib import Path

import pytest

from stm32_toolkit.detection import PlannedAction, ProjectDetection, detect_project
from stm32_toolkit.keil.model import KeilInspectionError
import stm32_toolkit.keil.uvprojx as uvprojx_mod

MIGRATE_EXPLANATION = (
    "Inspect the Keil project and convert ARMCC sources to GCC "
    "with a read-only plan and explicit authorization."
)
CONFIGURE_EXPLANATION = (
    "Generate managed GCC/CMake and VS Code configuration "
    "with a read-only plan and explicit authorization."
)
CONFIGURE_PREREQUISITE = (
    "Project configuration requires a valid supported .stm32-project.json manifest."
)
CREATE_EXPLANATION = (
    "Project creation is planned but unavailable in this foundation release."
)


def _assert_available(result: ProjectDetection, action_id: str) -> None:
    assert result.recommended_action.id == action_id
    assert result.recommended_action.available is True


def _assert_unavailable(result: ProjectDetection, action_id: str) -> None:
    assert result.recommended_action.id == action_id
    assert result.recommended_action.available is False


def test_manifest_wins_over_other_markers(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "board.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "configured"
    assert result.files == (".stm32-project.json",)
    _assert_available(result, "configure-project")
    assert result.recommended_action.explanation == CONFIGURE_EXPLANATION


def test_keil_project_recommends_available_migration_and_sorts_marker_names(
    tmp_path: Path,
):
    (tmp_path / "zeta.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "alpha.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("alpha.uvprojx", "zeta.uvprojx")
    _assert_available(result, "migrate-keil")
    assert result.recommended_action.explanation == MIGRATE_EXPLANATION


def test_cubemx_wins_over_cmake_and_reports_the_configuration_prerequisite(
    tmp_path: Path,
):
    (tmp_path / "zeta.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "alpha.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cubemx"
    assert result.files == ("alpha.ioc", "zeta.ioc")
    _assert_unavailable(result, "configure-project")
    assert result.recommended_action.explanation == CONFIGURE_PREREQUISITE


def test_cmake_project_without_manifest_reports_the_configuration_prerequisite(
    tmp_path: Path,
):
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cmake"
    assert result.files == ("CMakeLists.txt",)
    _assert_unavailable(result, "configure-project")
    assert result.recommended_action.explanation == CONFIGURE_PREREQUISITE


def test_unknown_project_recommends_unavailable_creation(tmp_path: Path):
    (tmp_path / "README.md").write_text("empty", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "unknown"
    assert result.files == ()
    _assert_unavailable(result, "create-project")
    assert result.recommended_action.explanation == CREATE_EXPLANATION


def test_detection_is_immutable_and_serializes_json_style_values(tmp_path: Path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.to_dict() == {
        "kind": "keil",
        "files": ["legacy.uvprojx"],
        "recommended_action": {
            "id": "migrate-keil",
            "available": True,
            "explanation": MIGRATE_EXPLANATION,
        },
    }
    with pytest.raises(AttributeError):
        result.kind = "unknown"


def test_detection_does_not_mutate_project_root(tmp_path: Path):
    marker = tmp_path / "legacy.uvprojx"
    marker.write_text("<Project/>", encoding="utf-8")
    before = {path.name: (path.is_file(), path.read_bytes()) for path in tmp_path.iterdir()}

    detect_project(tmp_path)

    after = {path.name: (path.is_file(), path.read_bytes()) for path in tmp_path.iterdir()}
    assert after == before


def test_project_detection_is_frozen():
    detection = ProjectDetection(
        kind="unknown",
        files=(),
        recommended_action=PlannedAction(
            id="create-project",
            available=False,
            explanation=CREATE_EXPLANATION,
        ),
    )

    with pytest.raises(AttributeError):
        detection.files = ("unexpected",)


@pytest.mark.parametrize("root_name", ["missing", "not-a-directory"])
def test_missing_or_non_directory_root_is_unknown(tmp_path: Path, root_name: str):
    project_root = tmp_path / root_name
    if root_name == "not-a-directory":
        project_root.write_text("not a project root", encoding="utf-8")

    result = detect_project(project_root)

    assert result.kind == "unknown"
    assert result.files == ()
    _assert_unavailable(result, "create-project")


def test_marker_shaped_directories_are_ignored_in_precedence(tmp_path: Path):
    (tmp_path / ".stm32-project.json").mkdir()
    (tmp_path / "legacy.uvprojx").mkdir()
    (tmp_path / "board.ioc").mkdir()
    (tmp_path / "CMakeLists.txt").mkdir()
    (tmp_path / "actual.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("actual.uvprojx",)
    _assert_available(result, "migrate-keil")


def test_directory_only_markers_are_unknown(tmp_path: Path):
    for name in (".stm32-project.json", "legacy.uvprojx", "board.ioc", "CMakeLists.txt"):
        (tmp_path / name).mkdir()

    result = detect_project(tmp_path)

    assert result.kind == "unknown"
    assert result.files == ()
    _assert_unavailable(result, "create-project")


def test_nested_keil_discovery_is_sorted_and_skips_generated_directories(tmp_path: Path):
    for relative in ("Project/Zeta.uvprojx", "Project/sub/alpha.uvprojx"):
        marker = tmp_path / relative
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("<Project/>", encoding="utf-8")
    for directory in (
        ".GIT", ".stm32-toolkit", "BUILD", "build-debug", "cmake-build-debug",
        "node_modules", ".venv", "venv", "Objects", "LISTINGS",
    ):
        ignored = tmp_path / directory / "ignored.uvprojx"
        ignored.parent.mkdir(parents=True)
        ignored.write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("Project/sub/alpha.uvprojx", "Project/Zeta.uvprojx")


def test_keil_discovery_does_not_follow_directory_symlink(tmp_path: Path):
    root = tmp_path / "project"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (external / "outside.uvprojx").write_text("<Project/>", encoding="utf-8")
    try:
        (root / "linked").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    result = detect_project(root)

    assert result.kind == "unknown"
    assert result.files == ()


def test_keil_discovery_permission_error_is_not_reported_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    real_scandir = os.scandir

    def fail_blocked(path):
        if Path(path) == blocked:
            raise PermissionError("fixture denial")
        return real_scandir(path)

    monkeypatch.setattr(uvprojx_mod.os, "scandir", fail_blocked)

    with pytest.raises(KeilInspectionError) as error:
        detect_project(tmp_path)
    assert error.value.code == "KEIL_PROJECT_UNAVAILABLE"
    assert error.value.details == {"path": "blocked", "rule": "discoveryIncomplete"}
