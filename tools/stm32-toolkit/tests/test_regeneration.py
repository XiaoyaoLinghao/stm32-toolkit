from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import regeneration
from stm32_toolkit.regeneration import (
    MAX_DIFF_BYTES,
    MAX_PREVIEW_BYTES,
    InventoryEntry,
    RegenerationError,
    RegenerationInputError,
    RegenerationWorkflowRequest,
    build_regeneration_preview,
    plan_regeneration,
)


def test_regeneration_request_requires_portable_non_root_destination(tmp_path: Path):
    with pytest.raises(RegenerationInputError):
        RegenerationWorkflowRequest(tmp_path, tmp_path / "data", "session", ".")


def test_regeneration_request_normalizes_absolute_roots(tmp_path: Path):
    request = RegenerationWorkflowRequest(
        tmp_path.resolve(), (tmp_path / "data").resolve(), "session", "generated"
    )
    assert request.destination == "generated"
    assert request.project_root == tmp_path / "generated"


def test_plan_regeneration_is_read_only_for_non_project(tmp_path: Path):
    request = RegenerationWorkflowRequest(
        tmp_path.resolve(), (tmp_path / "data").resolve(), "session", "generated"
    )
    result = plan_regeneration(request)
    assert result.code in {"REGENERATION_PROJECT_INVALID", "REGENERATION_NOT_CUBEMX_PROJECT"}
    assert not (tmp_path / "generated").exists()


def test_regeneration_preview_omits_text_diff_over_record_bound_but_keeps_hashes():
    before_bytes = b"a" * (MAX_DIFF_BYTES + 1)
    after_bytes = b"b" * (MAX_DIFF_BYTES + 1)
    before = SimpleNamespace(
        inventory=(InventoryEntry("Core/main.c", "file", len(before_bytes), "a" * 64, "cubemx"),),
        file_bytes={"Core/main.c": before_bytes},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=(InventoryEntry("Core/main.c", "file", len(after_bytes), "b" * 64, "cubemx"),),
        file_bytes={"Core/main.c": after_bytes},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    preview = build_regeneration_preview(before, after)
    assert preview.changes[0].unified_diff is None
    assert preview.changes[0].before_sha256 == "a" * 64


def test_regeneration_preview_fails_closed_when_aggregate_display_exceeds_bound():
    old = b"a\n" * 1_000
    new = b"b\n" * 1_000
    before_entries = tuple(
        InventoryEntry(f"Core/{index:02d}.c", "file", len(old), "a" * 64, "cubemx")
        for index in range(300)
    )
    after_entries = tuple(
        InventoryEntry(f"Core/{index:02d}.c", "file", len(new), "b" * 64, "cubemx")
        for index in range(300)
    )
    before = SimpleNamespace(
        inventory=before_entries,
        file_bytes={entry.path: old for entry in before_entries},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=after_entries,
        file_bytes={entry.path: new for entry in after_entries},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    with pytest.raises(RegenerationError) as caught:
        build_regeneration_preview(before, after)
    assert caught.value.code == "REGENERATION_PREVIEW_TOO_LARGE"


@pytest.mark.parametrize("status", ("added", "deleted", "binary"))
def test_regeneration_preview_bounds_complete_change_record_metadata(status: str):
    count = 10_000
    before_data = b"\xff" if status == "binary" else b""
    after_data = b"\xfe" if status == "binary" else b""
    before_entries = ()
    after_entries = ()
    before_bytes = {}
    after_bytes = {}
    if status in {"deleted", "binary"}:
        before_entries = tuple(
            InventoryEntry(f"App/{index:05d}.bin", "file", len(before_data), f"{index:064x}", "user")
            for index in range(count)
        )
        before_bytes = {entry.path: before_data for entry in before_entries}
    if status in {"added", "binary"}:
        after_entries = tuple(
            InventoryEntry(f"App/{index:05d}.bin", "file", len(after_data), f"{index + 1:064x}", "user")
            for index in range(count)
        )
        after_bytes = {entry.path: after_data for entry in after_entries}
    before = SimpleNamespace(
        inventory=before_entries,
        file_bytes=before_bytes,
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=after_entries,
        file_bytes=after_bytes,
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    with pytest.raises(RegenerationError) as caught:
        build_regeneration_preview(before, after)
    assert caught.value.code == "REGENERATION_PREVIEW_TOO_LARGE"


def test_regeneration_preview_public_payload_is_bounded_for_successful_preview():
    before = SimpleNamespace(
        inventory=(InventoryEntry("App/keep.txt", "file", 1, "a" * 64, "user"),),
        file_bytes={"App/keep.txt": b"a"},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=(InventoryEntry("App/keep.txt", "file", 1, "b" * 64, "user"),),
        file_bytes={"App/keep.txt": b"b"},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    preview = build_regeneration_preview(before, after)
    encoded = json.dumps(preview.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= MAX_PREVIEW_BYTES


def test_regeneration_read_rejects_open_identity_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    victim = tmp_path / "victim.bin"
    replacement = tmp_path / "replacement.bin"
    victim.write_bytes(b"same-size")
    replacement.write_bytes(b"same-size")
    real_open = regeneration.os.open

    def open_replacement(path, flags, *args, **kwargs):
        if Path(path) == victim:
            return real_open(replacement, flags, *args, **kwargs)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(regeneration.os, "open", open_replacement)
    with pytest.raises(RegenerationError) as caught:
        regeneration._read_file(victim)
    assert caught.value.code == "REGENERATION_STATE_CHANGED"


def test_destination_symlink_is_rejected_before_resolution(tmp_path: Path):
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "generated"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    request = RegenerationWorkflowRequest(tmp_path, tmp_path / "data", "session", "generated")
    result = plan_regeneration(request)
    assert result.code == "REGENERATION_PATH_UNSAFE"
