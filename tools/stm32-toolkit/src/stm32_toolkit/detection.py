from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ProjectKind = Literal["configured", "keil", "cubemx", "cmake", "unknown"]
ActionId = Literal["migrate-keil", "configure-project", "create-project"]

_ACTION_EXPLANATIONS: dict[ActionId, str] = {
    "migrate-keil": (
        "Inspect the Keil project and convert ARMCC sources to GCC "
        "with a read-only plan and explicit authorization."
    ),
    "configure-project": (
        "Generate managed GCC/CMake and VS Code configuration "
        "with a read-only plan and explicit authorization."
    ),
    "create-project": (
        "Project creation is planned but unavailable in this foundation release."
    ),
}

_CONFIGURATION_PREREQUISITE = (
    "Project configuration requires a valid Schema v2 .stm32-project.json manifest."
)


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
    """Return the shipped action; project creation remains unavailable."""
    return PlannedAction(
        action_id,
        _ACTION_EXPLANATIONS[action_id],
        available=action_id != "create-project",
    )


def _configuration_prerequisite_action() -> PlannedAction:
    """The configure action for kinds that lack the Schema v2 prerequisite."""
    return PlannedAction(
        "configure-project",
        _CONFIGURATION_PREREQUISITE,
        available=False,
    )


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
            recommended_action=_configuration_prerequisite_action(),
        )

    if "CMakeLists.txt" in names:
        return ProjectDetection(
            kind="cmake",
            files=("CMakeLists.txt",),
            recommended_action=_configuration_prerequisite_action(),
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
