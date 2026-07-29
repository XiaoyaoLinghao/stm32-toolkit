import os
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.paths import WorkspacePaths


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")


def _create_directory_redirect(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.skip("directory symlinks are unavailable on this host")

    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("directory symlinks and junctions are unavailable on this host")


def test_workspace_paths_are_namespaced(tmp_path: Path):
    project = tmp_path / "project"
    data = tmp_path / "plugin-data"
    project.mkdir()

    paths = WorkspacePaths.from_roots(data, project, PROJECT_ID, "session-1")
    paths.ensure()

    assert paths.workspace_root.parent.name == "projects"
    assert paths.session_root.parent.name == "sessions"
    assert paths.session_root.name == "session-1"
    assert all(
        directory.is_dir()
        for directory in (
            paths.monitor_root,
            paths.diagnostics_root,
            paths.logs_root,
            paths.cache_root,
            paths.session_root,
        )
    )


def test_project_path_rejects_escape(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    paths = WorkspacePaths.from_roots(
        tmp_path / "data", project, PROJECT_ID, "session-1"
    )

    with pytest.raises(ValueError, match="outside project root"):
        paths.require_project_path(tmp_path / "other" / "file.c")


def test_project_path_normalizes_relative_parent_segments(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    paths = WorkspacePaths.from_roots(tmp_path / "data", project, PROJECT_ID, "session-1")

    assert paths.require_project_path(Path("source") / ".." / "main.c") == project / "main.c"


@pytest.mark.parametrize(
    "session_id", ["", "..", "../outside", "session/child", "Session-1"]
)
def test_session_id_rejects_paths_and_windows_case_aliases(tmp_path: Path, session_id: str):
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(ValueError, match="invalid session id"):
        WorkspacePaths.from_roots(tmp_path / "data", project, PROJECT_ID, session_id)


def test_workspace_paths_reject_data_root_component_redirect(tmp_path: Path):
    project = tmp_path / "project"
    data = tmp_path / "data"
    redirected = tmp_path / "redirected"
    project.mkdir()
    data.mkdir()
    redirected.mkdir()
    _create_directory_redirect(data / "projects", redirected)

    paths = WorkspacePaths.from_roots(data, project, PROJECT_ID, "session-1")

    with pytest.raises(ValueError, match="outside plugin data root"):
        paths.ensure()
    assert not (redirected / paths.workspace_id / "monitor").exists()
