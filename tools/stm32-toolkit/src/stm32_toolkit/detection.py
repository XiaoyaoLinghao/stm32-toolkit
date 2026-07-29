from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ProjectKind = Literal["configured", "keil", "cubemx", "cmake", "unknown"]


@dataclass(frozen=True)
class ProjectDetection:
    kind: ProjectKind
    files: tuple[str, ...]
    recommended_skill: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "files": list(self.files),
            "recommended_skill": self.recommended_skill,
        }


def detect_project(project_root: Path) -> ProjectDetection:
    """Identify project markers without reading or modifying their contents."""
    try:
        entries = tuple(entry for entry in project_root.iterdir() if entry.is_file())
    except (FileNotFoundError, NotADirectoryError):
        return _unknown_detection()

    names = {entry.name for entry in entries}

    if ".stm32-project.json" in names:
        return ProjectDetection(
            kind="configured",
            files=(".stm32-project.json",),
            recommended_skill="/configure-stm32-project",
        )

    keil_files = _sorted_marker_names(entries, ".uvprojx")
    if keil_files:
        return ProjectDetection(
            kind="keil",
            files=keil_files,
            recommended_skill="/migrate-keil",
        )

    cubemx_files = _sorted_marker_names(entries, ".ioc")
    if cubemx_files:
        return ProjectDetection(
            kind="cubemx",
            files=cubemx_files,
            recommended_skill="/configure-stm32-project",
        )

    if "CMakeLists.txt" in names:
        return ProjectDetection(
            kind="cmake",
            files=("CMakeLists.txt",),
            recommended_skill="/configure-stm32-project",
        )

    return _unknown_detection()


def _unknown_detection() -> ProjectDetection:
    return ProjectDetection(
        kind="unknown",
        files=(),
        recommended_skill="/create-stm32-project",
    )


def _sorted_marker_names(entries: tuple[Path, ...], suffix: str) -> tuple[str, ...]:
    return tuple(sorted(entry.name for entry in entries if entry.name.endswith(suffix)))
