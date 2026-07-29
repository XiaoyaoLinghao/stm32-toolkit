from pathlib import Path

import pytest

from stm32_toolkit.detection import ProjectDetection, detect_project


def test_manifest_wins_over_other_markers(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "board.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "configured"
    assert result.files == (".stm32-project.json",)
    assert result.recommended_skill == "/configure-stm32-project"


def test_keil_project_recommends_migration_and_sorts_marker_names(tmp_path: Path):
    (tmp_path / "zeta.uvprojx").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "alpha.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "keil"
    assert result.files == ("alpha.uvprojx", "zeta.uvprojx")
    assert result.recommended_skill == "/migrate-keil"


def test_cubemx_wins_over_cmake_and_sorts_marker_names(tmp_path: Path):
    (tmp_path / "zeta.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "alpha.ioc").write_text("Mcu.Name=STM32F4", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cubemx"
    assert result.files == ("alpha.ioc", "zeta.ioc")
    assert result.recommended_skill == "/configure-stm32-project"


def test_cmake_project_recommends_configuration(tmp_path: Path):
    (tmp_path / "CMakeLists.txt").write_text("project(example)", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "cmake"
    assert result.files == ("CMakeLists.txt",)
    assert result.recommended_skill == "/configure-stm32-project"


def test_unknown_project_recommends_creation(tmp_path: Path):
    (tmp_path / "README.md").write_text("empty", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.kind == "unknown"
    assert result.files == ()
    assert result.recommended_skill == "/create-stm32-project"


def test_detection_is_immutable_and_serializes_json_style_values(tmp_path: Path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")

    result = detect_project(tmp_path)

    assert result.to_dict() == {
        "kind": "keil",
        "files": ["legacy.uvprojx"],
        "recommended_skill": "/migrate-keil",
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
        recommended_skill="/create-stm32-project",
    )

    with pytest.raises(AttributeError):
        detection.files = ("unexpected",)
