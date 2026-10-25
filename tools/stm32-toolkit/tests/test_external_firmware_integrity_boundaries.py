"""Offline integrity and store-ownership boundaries for external firmware.

Every public case uses the real import/admission workflows against real small
synthetic BIN/ELF files and real temporary stores.  The one private cleanup
case is labeled as a unit and uses real directories with an accurate ownership
ledger.  No probe, hardware, network, or original firmware project is used.
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.external_firmware import (
    FirmwareAdmitRequest,
    _remove_owned_staging,
    external_workspace_paths,
    firmware_admit_workflow,
    firmware_import_workflow,
)
from test_external_firmware import (
    _admit,
    _apply,
    _import_request,
    _plan,
    _project,
    _sha,
    _store_file,
)


def _assert_refused(result, code: str, **details: object) -> None:
    """Assert a stable refusal code and exact diagnostic details."""

    assert result.ok is False
    assert result.code == code
    assert result.code != "FIRMWARE_INTERNAL_ERROR"
    for key, value in details.items():
        assert result.details[key] == value, (key, result.details)


def _raw_elf(
    headers: tuple[tuple[int, int, int, int], ...],
    payload: bytes,
    *,
    entry: int = 0,
) -> bytes:
    """Build ELF32-LE ARM ET_EXEC with exact program headers.

    Each header is (file_offset, physical_address, file_size, memory_size), so
    malformed-but-parseable tables can be expressed without touching helpers.
    """

    count = len(headers)
    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + b"\x00" * 8
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH",
        2,  # ET_EXEC
        40,  # EM_ARM
        1,  # EV_CURRENT
        entry,
        52,  # e_phoff
        0,  # e_shoff
        0,  # e_flags
        52,  # e_ehsize
        32,  # e_phentsize
        count,
        0,  # e_shentsize
        0,  # e_shnum
        0,  # e_shstrndx
    )
    table = bytearray()
    for file_offset, address, file_size, memory_size in headers:
        table.extend(
            struct.pack(
                "<IIIIIIII",
                1,  # PT_LOAD
                file_offset,
                address,
                address,
                file_size,
                memory_size,
                5,  # PF_R | PF_X
                1,
            )
        )
    return bytes(header + table) + payload


def _identity(path: Path) -> tuple[int, int]:
    info = os.lstat(path)
    return (info.st_dev, info.st_ino)


def test_apply_requires_exact_authorization_and_current_source(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"authorization-bound"
    source = project / "fw.bin"
    source.write_bytes(payload)
    plan_id = str(_plan(project, data_root, "fw.bin", payload)["planId"])

    # A reviewed plan without exact authorization must persist nothing.
    unauthorized = firmware_import_workflow(
        _import_request(project, data_root, "fw.bin", payload, plan_id=plan_id)
    )
    _assert_refused(
        unauthorized,
        "AUTHORIZATION_REQUIRED",
        field="authorized",
        rule="exactTrue",
    )
    assert not data_root.exists()

    # The plan is bound to the reviewed source bytes, not just the path.
    changed = bytes(value ^ 0xFF for value in payload)
    source.write_bytes(changed)
    stale = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=plan_id,
            authorized=True,
        )
    )
    _assert_refused(
        stale, "FIRMWARE_INPUT_CHANGED", field="expectedSha256", rule="current"
    )
    assert source.read_bytes() == changed
    assert sorted(path.name for path in project.iterdir()) == ["fw.bin"]
    assert not data_root.exists()


def test_data_root_inside_project_is_rejected_before_any_write(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    payload = b"inside-project"
    (project / "fw.bin").write_bytes(payload)
    inside = project / "toolkit-data"

    planned = firmware_import_workflow(
        _import_request(project, inside, "fw.bin", payload)
    )
    _assert_refused(
        planned,
        "FIRMWARE_INPUT_INVALID",
        field="data_root",
        rule="outsideProjectRoot",
    )

    admitted = _admit(project, project, "a" * 64, "b" * 64)
    _assert_refused(
        admitted,
        "FIRMWARE_INPUT_INVALID",
        field="data_root",
        rule="outsideProjectRoot",
    )

    assert sorted(path.name for path in project.iterdir()) == ["fw.bin"]


def test_malformed_sha_digests_are_rejected_before_store_access(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"digest-shape"
    (project / "fw.bin").write_bytes(payload)
    valid = _sha(payload)

    for value in (valid.upper(), valid[:-1]):
        refused = firmware_import_workflow(
            replace(
                _import_request(project, data_root, "fw.bin", payload),
                expected_sha256=value,
            )
        )
        _assert_refused(
            refused,
            "FIRMWARE_INPUT_INVALID",
            field="expectedSha256",
            rule="sha256",
        )

    refused_import_id = firmware_admit_workflow(
        FirmwareAdmitRequest(project, data_root, "session-a", "A" * 64, valid)
    )
    _assert_refused(
        refused_import_id,
        "FIRMWARE_INPUT_INVALID",
        field="importId",
        rule="sha256",
    )

    refused_pin = firmware_admit_workflow(
        FirmwareAdmitRequest(project, data_root, "session-a", "a" * 64, valid.upper())
    )
    _assert_refused(
        refused_pin,
        "FIRMWARE_INPUT_INVALID",
        field="expectedSha256",
        rule="sha256",
    )

    assert not data_root.exists()


def test_elf_overlap_bounds_and_unparsable_images_are_refused(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"

    # Two PT_LOAD rows whose physical ranges intersect by four bytes.  116 is
    # the first payload offset for two 32-byte program headers.
    overlap = _raw_elf(
        ((116, 0x0800_0000, 8, 8), (124, 0x0800_0004, 4, 4)),
        bytes(range(12)),
    )
    # Declared segment extends past the bytes actually present in the file.
    beyond = _raw_elf(((84, 0x0800_0000, 16, 16),), b"\x01" * 8)
    cases = (
        ("overlap.elf", overlap, "overlap"),
        ("beyond.elf", beyond, "segmentBounds"),
        ("garbage.elf", b"not an ELF image", "elf"),
    )
    for name, payload, rule in cases:
        (project / name).write_bytes(payload)
        refused = firmware_import_workflow(
            _import_request(
                project, data_root, name, payload, format="elf", base=None
            )
        )
        _assert_refused(refused, "FIRMWARE_IMAGE_INVALID", rule=rule)

    assert not data_root.exists()


def test_empty_payloads_and_wrapping_base_are_refused(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    (project / "empty.bin").write_bytes(b"")
    (project / "empty.hex").write_bytes(b"")
    (project / "fw.bin").write_bytes(b"\x01\x02")

    empty_bin = firmware_import_workflow(
        _import_request(project, data_root, "empty.bin", b"")
    )
    _assert_refused(empty_bin, "FIRMWARE_IMAGE_INVALID", rule="empty")

    empty_hex = firmware_import_workflow(
        _import_request(
            project, data_root, "empty.hex", b"", format="hex", base=None
        )
    )
    _assert_refused(empty_hex, "FIRMWARE_IMAGE_INVALID", rule="hexEmpty")

    # The Toolkit never infers or wraps a base address past the 32-bit space.
    wrapping = firmware_import_workflow(
        _import_request(
            project, data_root, "fw.bin", b"\x01\x02", base=0xFFFF_FFFF
        )
    )
    _assert_refused(
        wrapping, "FIRMWARE_INPUT_INVALID", field="baseAddress", rule="range"
    )

    boolean_base = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            b"\x01\x02",
            base=True,  # type: ignore[arg-type]
        )
    )
    _assert_refused(
        boolean_base,
        "FIRMWARE_INPUT_INVALID",
        field="baseAddress",
        rule="range",
    )

    assert not data_root.exists()


def test_admission_requires_every_immutable_stored_file(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = b"immutable-store"
    (project / "fw.bin").write_bytes(payload)

    # A missing immutable source copy is refused, never rebuilt from disk.
    first_root = tmp_path / "data-source"
    first = _apply(project, first_root, "fw.bin", payload)
    first_id = str(first["importId"])
    source_sha = str(first["source"]["sha256"])
    source_copy = _store_file(first_root, first_id, "source.bin")
    source_bytes = source_copy.read_bytes()
    record_copy = _store_file(first_root, first_id, "record.json")
    record_bytes = record_copy.read_bytes()
    image_copy = _store_file(first_root, first_id, "image.elf")
    image_bytes = image_copy.read_bytes()
    source_copy.unlink()
    missing_source = _admit(project, first_root, first_id, source_sha)
    _assert_refused(missing_source, "FIRMWARE_IMPORT_INVALID", rule="file")
    assert not source_copy.exists()
    assert record_copy.read_bytes() == record_bytes
    assert image_copy.read_bytes() == image_bytes

    # The immutable record is likewise required for any admission.
    second_root = tmp_path / "data-record"
    second = _apply(project, second_root, "fw.bin", payload)
    second_id = str(second["importId"])
    record_path = _store_file(second_root, second_id, "record.json")
    second_image = _store_file(second_root, second_id, "image.elf")
    second_source = _store_file(second_root, second_id, "source.bin")
    second_image_bytes = second_image.read_bytes()
    second_source_bytes = second_source.read_bytes()
    record_path.unlink()
    missing_record = _admit(project, second_root, second_id, source_sha)
    _assert_refused(missing_record, "FIRMWARE_IMPORT_INVALID", rule="file")
    assert not record_path.exists()
    assert second_image.read_bytes() == second_image_bytes
    assert second_source.read_bytes() == second_source_bytes

    # A truncated source copy fails its recorded size and digest together.
    third_root = tmp_path / "data-truncated"
    third = _apply(project, third_root, "fw.bin", payload)
    third_id = str(third["importId"])
    third_record = _store_file(third_root, third_id, "record.json")
    third_image = _store_file(third_root, third_id, "image.elf")
    third_record_bytes = third_record.read_bytes()
    third_image_bytes = third_image.read_bytes()
    truncated = _store_file(third_root, third_id, "source.bin")
    truncated.write_bytes(payload[:4])
    short = _admit(project, third_root, third_id, source_sha)
    _assert_refused(short, "FIRMWARE_IMPORT_INVALID", rule="sourceSha256")
    assert truncated.read_bytes() == payload[:4]
    assert third_record.read_bytes() == third_record_bytes
    assert third_image.read_bytes() == third_image_bytes

    assert (project / "fw.bin").read_bytes() == source_bytes


def test_admission_refuses_import_copied_to_another_bound_project(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"bound-import"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    original_dir = _store_file(data_root, import_id, "record.json").parent
    stored = {path.name: path.read_bytes() for path in original_dir.iterdir()}
    assert set(stored) == {"source.bin", "image.elf", "record.json"}

    # Place an exact copy of the import in the workspace that the relocated
    # project root owns under the same data root: a real store copy, not a
    # mismatched directory name.
    relocated = _project(tmp_path, "relocated-project")
    copied_dir = (
        external_workspace_paths(
            relocated.resolve(), data_root.resolve(), "session-a"
        ).workspace_root
        / "firmware-imports"
        / import_id
    )
    copied_dir.mkdir(parents=True)
    for name, content in stored.items():
        (copied_dir / name).write_bytes(content)

    refused = _admit(relocated, data_root, import_id, source_sha)
    _assert_refused(
        refused,
        "FIRMWARE_IMPORT_BINDING_MISMATCH",
        field="importId",
        rule="binding",
    )
    assert {path.name: path.read_bytes() for path in copied_dir.iterdir()} == stored
    assert {path.name: path.read_bytes() for path in original_dir.iterdir()} == (
        stored
    )
    assert _admit(project, data_root, import_id, source_sha).ok is True


def test_admission_refuses_record_from_incompatible_toolkit_version(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"version-bound"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    record_path = _store_file(data_root, import_id, "record.json")
    image_path = _store_file(data_root, import_id, "image.elf")
    image_bytes = image_path.read_bytes()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["toolkitVersion"] = "0.0.1-legacy"
    legacy = json.dumps(record, sort_keys=True).encode("utf-8")
    record_path.write_bytes(legacy)

    refused = _admit(project, data_root, import_id, source_sha)
    _assert_refused(
        refused,
        "FIRMWARE_IMPORT_INCOMPATIBLE",
        field="toolkitVersion",
        rule="current",
        actual="0.0.1-legacy",
        supported=__version__,
    )
    # Never repaired in place, and the refusal is stable across calls.
    assert record_path.read_bytes() == legacy
    assert image_path.read_bytes() == image_bytes
    assert _store_file(data_root, import_id, "source.bin").read_bytes() == payload
    assert (
        _admit(project, data_root, import_id, source_sha).code
        == "FIRMWARE_IMPORT_INCOMPATIBLE"
    )


def test_record_json_rejects_non_finite_and_non_object_documents(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"strict-json"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])
    record_path = _store_file(data_root, import_id, "record.json")
    image_path = _store_file(data_root, import_id, "image.elf")
    original = record_path.read_bytes()
    image_bytes = image_path.read_bytes()

    for document, rule in ((b"[]", "type"), (b'{"kind": NaN}', "json")):
        record_path.write_bytes(document)
        refused = _admit(project, data_root, import_id, source_sha)
        _assert_refused(
            refused,
            "FIRMWARE_IMPORT_INVALID",
            path="record.json",
            rule=rule,
        )
        assert record_path.read_bytes() == document

    assert _store_file(data_root, import_id, "source.bin").read_bytes() == payload
    assert image_path.read_bytes() == image_bytes

    # The invalid attempts left the store fully usable.
    record_path.write_bytes(original)
    assert _admit(project, data_root, import_id, source_sha).ok is True


def test_publish_conflict_preserves_existing_import_and_identity(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"conflict-bound"
    source = project / "fw.bin"
    source.write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    # A shape-valid record for the same identity but a different target can
    # never be overwritten or repaired by a later import.
    record_path = _store_file(data_root, import_id, "record.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["target"] = "stm32f405rg"
    altered = json.dumps(record, sort_keys=True).encode("utf-8")
    record_path.write_bytes(altered)
    source_before = _store_file(data_root, import_id, "source.bin").read_bytes()
    image_before = _store_file(data_root, import_id, "image.elf").read_bytes()

    plan_id = str(_plan(project, data_root, "fw.bin", payload)["planId"])
    refused = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=plan_id,
            authorized=True,
        )
    )
    _assert_refused(
        refused, "FIRMWARE_IMPORT_CONFLICT", field="importId", rule="conflict"
    )

    assert record_path.read_bytes() == altered
    assert _store_file(data_root, import_id, "source.bin").read_bytes() == (
        source_before
    )
    assert _store_file(data_root, import_id, "image.elf").read_bytes() == (
        image_before
    )
    assert list(record_path.parent.parent.glob(".staging-*")) == []
    assert source.read_bytes() == payload

    # The importId binds every identity field, so the altered-but-valid record
    # is refused on reconstruction instead of being silently admitted.
    identity = _admit(project, data_root, import_id, source_sha)
    _assert_refused(identity, "FIRMWARE_IMPORT_INVALID", rule="importId")


def test_publish_rename_failure_leaves_no_import_or_staging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Injected OS failure only at the real staged-directory rename."""

    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"publish-failure"
    source = project / "fw.bin"
    source.write_bytes(payload)
    plan = _plan(project, data_root, "fw.bin", payload)
    import_id = str(plan["importId"])

    real_rename = os.rename
    attempts: list[tuple[Path, Path]] = []

    def failing_rename(source_path: object, destination_path: object) -> None:
        staged = Path(str(source_path))
        final = Path(str(destination_path))
        if not staged.name.startswith(".staging-"):
            real_rename(source_path, destination_path)  # type: ignore[arg-type]
            return
        attempts.append((staged, final))
        # No destination winner exists, so publication cannot succeed.
        raise OSError("injected publication rename failure")

    monkeypatch.setattr(os, "rename", failing_rename)
    refused = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=str(plan["planId"]),
            authorized=True,
        )
    )

    _assert_refused(refused, "FIRMWARE_IMPORT_STORE_UNSAFE", rule="publish")
    assert len(attempts) == 1
    staging, final = attempts[0]
    assert final.name == import_id
    assert final.parent.name == "firmware-imports"
    assert not final.exists()
    assert not staging.exists()
    assert list(final.parent.glob(".staging-*")) == []
    assert list(final.parent.iterdir()) == []
    assert source.read_bytes() == payload


def test_publish_race_accepts_identical_winner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Injected concurrent winner: identical bytes are created=False."""

    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"race-identical"
    source = project / "fw.bin"
    source.write_bytes(payload)
    plan = _plan(project, data_root, "fw.bin", payload)
    import_id = str(plan["importId"])
    source_sha = str(plan["source"]["sha256"])

    real_rename = os.rename
    attempts: list[tuple[Path, Path]] = []
    winner: dict[str, bytes] = {}

    def winning_rename(source_path: object, destination_path: object) -> None:
        staged = Path(str(source_path))
        final = Path(str(destination_path))
        if not staged.name.startswith(".staging-"):
            real_rename(source_path, destination_path)  # type: ignore[arg-type]
            return
        attempts.append((staged, final))
        final.mkdir()
        for child in staged.iterdir():
            (final / child.name).write_bytes(child.read_bytes())
        winner.update(
            {path.name: path.read_bytes() for path in final.iterdir()}
        )
        raise FileExistsError("injected concurrent publication winner")

    monkeypatch.setattr(os, "rename", winning_rename)
    applied = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=str(plan["planId"]),
            authorized=True,
        )
    )

    assert applied.ok is True, applied.to_dict()
    assert applied.data["mode"] == "firmware-import-apply"
    assert applied.data["created"] is False
    assert applied.data["importId"] == import_id
    assert len(attempts) == 1
    staging, final = attempts[0]
    assert final.name == import_id
    assert not staging.exists()
    assert list(final.parent.glob(".staging-*")) == []
    assert set(winner) == {"source.bin", "image.elf", "record.json"}
    assert {path.name: path.read_bytes() for path in final.iterdir()} == winner

    admitted = _admit(project, data_root, import_id, source_sha)
    assert admitted.ok is True, admitted.to_dict()
    assert admitted.data["offlineReady"] is True
    assert admitted.data["hardwareVerified"] is False
    assert admitted.data["sourceSha256"] == source_sha
    assert admitted.data["imageSha256"] == plan["image"]["sha256"]
    assert source.read_bytes() == payload


def test_publish_race_conflicting_winner_preserves_every_byte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Injected concurrent winner with a valid-but-different record."""

    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"race-conflict"
    source = project / "fw.bin"
    source.write_bytes(payload)
    plan = _plan(project, data_root, "fw.bin", payload)
    import_id = str(plan["importId"])

    real_rename = os.rename
    attempts: list[tuple[Path, Path]] = []
    winner: dict[str, bytes] = {}

    def conflicting_rename(source_path: object, destination_path: object) -> None:
        staged = Path(str(source_path))
        final = Path(str(destination_path))
        if not staged.name.startswith(".staging-"):
            real_rename(source_path, destination_path)  # type: ignore[arg-type]
            return
        attempts.append((staged, final))
        final.mkdir()
        for child in staged.iterdir():
            (final / child.name).write_bytes(child.read_bytes())
        record_path = final / "record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["target"] = "stm32f405rg"
        record_path.write_bytes(
            json.dumps(record, sort_keys=True).encode("utf-8")
        )
        winner.update(
            {path.name: path.read_bytes() for path in final.iterdir()}
        )
        raise FileExistsError("injected concurrent publication winner")

    monkeypatch.setattr(os, "rename", conflicting_rename)
    refused = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=str(plan["planId"]),
            authorized=True,
        )
    )

    _assert_refused(
        refused, "FIRMWARE_IMPORT_CONFLICT", field="importId", rule="conflict"
    )
    assert len(attempts) == 1
    staging, final = attempts[0]
    assert final.name == import_id
    assert not staging.exists()
    assert list(final.parent.glob(".staging-*")) == []
    assert set(winner) == {"source.bin", "image.elf", "record.json"}
    assert json.loads(winner["record.json"])["target"] == "stm32f405rg"
    # The winner is left exactly as injected, never repaired or deleted.
    assert {path.name: path.read_bytes() for path in final.iterdir()} == winner
    assert source.read_bytes() == payload


def test_owned_staging_cleanup_preserves_foreign_and_replaced_entries(
    tmp_path: Path,
) -> None:
    """Unit: the private cleanup removes only entries this call created."""

    project = _project(tmp_path)
    data_root = tmp_path / "data"
    imports_root = (
        external_workspace_paths(
            project, data_root, "session-a"
        ).workspace_root
        / "firmware-imports"
    )
    imports_root.mkdir(parents=True)

    # Foreign files that share the staging directory are never removed.
    owned = imports_root / ".staging-owned"
    owned.mkdir()
    ledger: dict[str, tuple[int, int]] = {}
    for name in ("source.bin", "image.elf"):
        (owned / name).write_bytes(name.encode("utf-8"))
        ledger[name] = _identity(owned / name)
    foreign = owned / "record.json"
    foreign.write_bytes(b"foreign-record")
    _remove_owned_staging(owned, _identity(owned), ledger)
    assert sorted(path.name for path in owned.iterdir()) == ["record.json"]
    assert foreign.read_bytes() == b"foreign-record"

    # A staging directory replaced after creation is not this call's surface.
    replaced = imports_root / ".staging-replaced"
    replaced.mkdir()
    (replaced / "source.bin").write_bytes(b"owned-source")
    replaced_ledger = {"source.bin": _identity(replaced / "source.bin")}
    original_identity = _identity(replaced)
    moved = imports_root / ".staging-replaced-original"
    os.rename(replaced, moved)
    replaced.mkdir()
    (replaced / "source.bin").write_bytes(b"replacement")
    assert _identity(replaced) != original_identity
    _remove_owned_staging(replaced, original_identity, replaced_ledger)
    assert (replaced / "source.bin").read_bytes() == b"replacement"
    assert (moved / "source.bin").read_bytes() == b"owned-source"

    # One replaced ledger-owned file in an otherwise unchanged directory: the
    # original stays reachable as an external sibling, so its identity is
    # provably distinct and only the genuinely owned sibling is removed.
    file_staging = imports_root / ".staging-file-replaced"
    file_staging.mkdir()
    (file_staging / "source.bin").write_bytes(b"owned-file")
    (file_staging / "image.elf").write_bytes(b"owned-image")
    file_ledger = {
        name: _identity(file_staging / name)
        for name in ("source.bin", "image.elf")
    }
    external_original = imports_root / ".staging-original-source.bin"
    os.rename(file_staging / "source.bin", external_original)
    (file_staging / "source.bin").write_bytes(b"replacement-file")
    assert _identity(file_staging / "source.bin") != file_ledger["source.bin"]
    _remove_owned_staging(file_staging, _identity(file_staging), file_ledger)
    assert (file_staging / "source.bin").read_bytes() == b"replacement-file"
    assert not (file_staging / "image.elf").exists()
    assert external_original.read_bytes() == b"owned-file"

    # Without a recorded directory identity nothing may be removed at all.
    unowned = imports_root / ".staging-unowned"
    unowned.mkdir()
    (unowned / "source.bin").write_bytes(b"untracked")
    _remove_owned_staging(unowned, None, {})
    assert (unowned / "source.bin").read_bytes() == b"untracked"
