from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from stm32_toolkit.identity import canonical_project_root, compute_workspace_id, new_session_id


_SESSION_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def require_safe_session_id(session_id: str) -> str:
    """Validate the shared filesystem-safe session identifier contract."""
    if (
        not _SESSION_ID_PATTERN.fullmatch(session_id)
        or session_id in _WINDOWS_DEVICE_NAMES
    ):
        raise ValueError("invalid session id")
    return session_id


@dataclass(frozen=True)
class WorkspacePaths:
    project_root: Path
    data_root: Path
    workspace_id: str
    session_id: str
    workspace_root: Path
    monitor_root: Path
    diagnostics_root: Path
    logs_root: Path
    cache_root: Path
    session_root: Path

    @classmethod
    def from_roots(
        cls,
        data_root: Path,
        project_root: Path,
        logical_project_id: UUID,
        session_id: str | None = None,
    ) -> "WorkspacePaths":
        canonical_project = canonical_project_root(project_root)
        canonical_data = data_root.expanduser().resolve(strict=False)
        resolved_session_id = require_safe_session_id(session_id if session_id is not None else new_session_id())
        workspace_id = compute_workspace_id(logical_project_id, canonical_project)
        workspace_root = canonical_data / "projects" / workspace_id

        return cls(
            project_root=canonical_project,
            data_root=canonical_data,
            workspace_id=workspace_id,
            session_id=resolved_session_id,
            workspace_root=workspace_root,
            monitor_root=workspace_root / "monitor",
            diagnostics_root=workspace_root / "diagnostics",
            logs_root=workspace_root / "logs",
            cache_root=workspace_root / "cache",
            session_root=workspace_root / "sessions" / resolved_session_id,
        )

    def _require_owned_data_path(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self.data_root)
        except ValueError as error:
            raise ValueError("path is outside plugin data root") from error

    def ensure(self) -> None:
        """Create owned state directories after resolving reparse-point redirects.

        A component can still be swapped between the check and mkdir calls; fully
        eliminating that TOCTOU race would require platform-native handle APIs.
        """
        for directory in (
            self.monitor_root,
            self.diagnostics_root,
            self.logs_root,
            self.cache_root,
            self.session_root,
        ):
            self._require_owned_data_path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            self._require_owned_data_path(directory)

    def require_project_path(self, path: Path) -> Path:
        candidate = path if path.is_absolute() else self.project_root / path
        resolved = candidate.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(self.project_root)
        except ValueError as error:
            raise ValueError("path is outside project root") from error
        return resolved
