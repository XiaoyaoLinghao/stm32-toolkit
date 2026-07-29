from pathlib import Path
from uuid import UUID

from stm32_toolkit.identity import compute_workspace_id, new_session_id


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_workspace_id_is_stable_for_same_root(tmp_path: Path):
    first = compute_workspace_id(PROJECT_ID, tmp_path)
    second = compute_workspace_id(PROJECT_ID, tmp_path / ".")

    assert first == second
    assert len(first) == 24


def test_workspace_id_changes_for_second_clone(tmp_path: Path):
    first_root = tmp_path / "clone-a"
    second_root = tmp_path / "clone-b"
    first_root.mkdir()
    second_root.mkdir()

    assert compute_workspace_id(PROJECT_ID, first_root) != compute_workspace_id(
        PROJECT_ID, second_root
    )


def test_session_ids_are_unique():
    assert new_session_id() != new_session_id()
