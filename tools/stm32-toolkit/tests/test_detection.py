from pathlib import Path

import pytest

from stm32_toolkit.detection import PlannedAction, ProjectDetection, detect_project

def _assert_unavailable_action(result: ProjectDetection, action_id: str) -> None:
    assert result.recommended_action.id == action_id
    assert result.recommended_action.available is False
    assert result.recommended_action.explanation.endswith(
        "is planned but unavailable in this foundation release."
    )



def test_manifest_wins_over_other_markers(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "board.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "configured"
    assert result.files == (".stm32-project.json",)
    _assert_unavailable_action(result, "configure-project")


def test_keil_project_recommends_migration_and_sorts_marker_names(tmp_path: Path):
    (tmp_path / "zeta.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "alpha.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("alpha.uvprojx", "zeta.uvprojx")
    _assert_unavailable_action(result, "migrate-keil")


def test_cubemx_wins_over_cmake_and_sorts_marker_names(tmp_path: Path):
    (tmp_path / "zeta.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "alpha.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cubemx"
    assert result.files == ("alpha.ioc", "zeta.ioc")
    _assert_unavailable_action(result, "configure-project")


def test_cmake_project_recommends_configuration(tmp_path: Path):
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cmake"
    assert result.files == ("CMakeLists.txt",)
    _assert_unavailable_action(result, "configure-project")


def test_unknown_project_recommends_creation(tmp_path: Path):
    (tmp_path / "README.md").write_text("empty", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "unknown"
    assert result.files == ()
    _assert_unavailable_action(result, "create-project")


def test_detection_is_immutable_and_serializes_json_style_values(tmp_path: Path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.to_dict() == {
        "kind": "keil",
        "files": ["legacy.uvprojx"],
        "recommended_action": {
            "id": "migrate-keil",
            "available": False,
            "explanation": "Keil migration is planned but unavailable in this foundation release.",
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
            explanation="Project creation is planned but unavailable in this foundation release.",
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
    _assert_unavailable_action(result, "create-project")


def test_marker_shaped_directories_are_ignored_in_precedence(tmp_path: Path):
    (tmp_path / ".stm32-project.json").mkdir()
    (tmp_path / "legacy.uvprojx").mkdir()
    (tmp_path / "board.ioc").mkdir()
    (tmp_path / "CMakeLists.txt").mkdir()
    (tmp_path / "actual.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("actual.uvprojx",)
    _assert_unavailable_action(result, "migrate-keil")


def test_directory_only_markers_are_unknown(tmp_path: Path):
    for name in (".stm32-project.json", "legacy.uvprojx", "board.ioc", "CMakeLists.txt"):
        (tmp_path / name).mkdir()

    result = detect_project(tmp_path)

    assert result.kind == "unknown"
    assert result.files == ()
    _assert_unavailable_action(result, "create-project")
