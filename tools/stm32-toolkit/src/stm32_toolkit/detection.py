from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ProjectKind = Literal["configured", "keil", "cubemx", "cmake", "unknown"]
ActionId = Literal["migrate-keil", "configure-project", "create-project"]
_ACTION_EXPLANATIONS: dict[ActionId, str] = {
    "migrate-keil": (
        "Keil migration is planned but unavailable in this foundation release."
    ),
    "configure-project": (
        "Project configuration is planned but unavailable in this foundation release."
    ),
    "create-project": (
        "Project creation is planned but unavailable in this foundation release."
    ),
}


@dataclass(frozen=True)
class PlannedAction:
    id: ActionId
    explanation: str
    available: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "available": self.available,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ProjectDetection:
    kind: ProjectKind
    files: tuple[str, ...]
    recommended_action: PlannedAction

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "files": list(self.files),
            "recommended_action": self.recommended_action.to_dict(),
        }


def planned_action(action_id: ActionId) -> PlannedAction:
    return PlannedAction(action_id, _ACTION_EXPLANATIONS[action_id])


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
            recommended_action=planned_action("configure-project"),
        )

    keil_files = _sorted_marker_names(entries, ".uvprojx")
    if keil_files:
        return ProjectDetection(
            kind="keil",
            files=keil_files,
            recommended_action=planned_action("migrate-keil"),
        )

    cubemx_files = _sorted_marker_names(entries, ".ioc")
    if cubemx_files:
        return ProjectDetection(
            kind="cubemx",
            files=cubemx_files,
            recommended_action=planned_action("configure-project"),
        )

    if "CMakeLists.txt" in names:
        return ProjectDetection(
            kind="cmake",
            files=("CMakeLists.txt",),
            recommended_action=planned_action("configure-project"),
        )

    return _unknown_detection()


def _unknown_detection() -> ProjectDetection:
    return ProjectDetection(
        kind="unknown",
        files=(),
        recommended_action=planned_action("create-project"),
    )


def _sorted_marker_names(entries: tuple[Path, ...], suffix: str) -> tuple[str, ...]:
    return tuple(sorted(entry.name for entry in entries if entry.name.endswith(suffix)))
