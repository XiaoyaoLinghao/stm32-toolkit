"""Offline external-firmware import, identity, store and admission tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
from pathlib import Path

import pytest
from elftools.elf.elffile import ELFFile

from stm32_toolkit.external_firmware import (
    FirmwareAdmitRequest,
    FirmwareImportRequest,
    firmware_admit_workflow,
    firmware_import_workflow,
    load_admission,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _elf(
    segments: tuple[tuple[int, bytes], ...],
    *,
    entry: int = 0,
    machine: int = 40,
    e_type: int = 2,
    extra_dynamic: bool = False,
) -> bytes:
    """Build a minimal ELF32 little-endian ARM image from exact segments."""

    count = len(segments) + (1 if extra_dynamic else 0)
    offset = 52 + 32 * count
    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + b"\x00" * 8
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH",
        e_type,
        machine,
        1,
        entry,
        52,
        0,
        0,
        52,
        32,
        count,
        0,
        0,
        0,
    )
    headers = bytearray()
    payload = bytearray()
    cursor = offset
    if extra_dynamic:
        headers.extend(struct.pack("<IIIIIIII", 2, 0, 0, 0, 0, 0, 6, 1))
    for address, data in segments:
        headers.extend(
            struct.pack(
                "<IIIIIIII", 1, cursor, address, address, len(data), len(data), 5, 1
            )
        )
        payload.extend(data)
        cursor += len(data)
    return bytes(header + headers + payload)


def _hex_record(address: int, record_type: int, payload: bytes = b"") -> str:
    body = bytes(
        (len(payload), (address >> 8) & 0xFF, address & 0xFF, record_type)
    ) + payload
    checksum = (-sum(body)) & 0xFF
    return ":" + body.hex().upper() + f"{checksum:02X}"


def _hex_file(records: list[str]) -> str:
    return "\n".join([*records, _hex_record(0, 0x01)]) + "\n"


def _project(tmp_path: Path, name: str = "project") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _regions(*pairs: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(pairs))


def _import_request(
    project: Path,
    data: Path,
    source: str,
    payload: bytes,
    *,
    format: str = "bin",
    base: int | None = 0x0800_0000,
    target: str = "stm32f407vg",
    regions: tuple[tuple[int, int], ...] | None = None,
    plan_id: str | None = None,
    authorized: object = False,
) -> FirmwareImportRequest:
    return FirmwareImportRequest(
        project,
        data,
        "session-a",
        source,
        _sha(payload),
        format,
        target,
        regions if regions is not None else _regions((0x0800_0000, 0x1_0000)),
        base,
        plan_id,
        authorized,
    )


def _plan(
    project: Path, data: Path, source: str, payload: bytes, **kwargs: object
) -> dict[str, object]:
    result = firmware_import_workflow(
        _import_request(project, data, source, payload, **kwargs)  # type: ignore[arg-type]
    )
    assert result.ok is True, result.to_dict()
    return result.to_dict()["data"]  # type: ignore[return-value]


def _apply(
    project: Path, data: Path, source: str, payload: bytes, **kwargs: object
) -> dict[str, object]:
    plan = _plan(project, data, source, payload, **kwargs)
    result = firmware_import_workflow(
        _import_request(
            project,
            data,
            source,
            payload,
            **{**kwargs, "plan_id": plan["planId"], "authorized": True},  # type: ignore[arg-type]
        )
    )
    assert result.ok is True, result.to_dict()
    return result.to_dict()["data"]  # type: ignore[return-value]


def _admit(
    project: Path, data: Path, import_id: str, source_sha: str
):
    return firmware_admit_workflow(
        FirmwareAdmitRequest(project, data, "session-a", import_id, source_sha)
    )


def _store_file(data_root: Path, import_id: str, name: str) -> Path:
    matches = list(
        (data_root / "projects").glob(f"*/firmware-imports/{import_id}/{name}")
    )
    assert len(matches) == 1, matches
    return matches[0]


def test_plan_is_deterministic_read_only_and_reports_distinct_hashes(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"\x01\x02\x03\x04\x05"
    (project / "fw.bin").write_bytes(payload)

    first = _plan(project, data_root, "fw.bin", payload)
    second = _plan(project, data_root, "fw.bin", payload)

    assert first["mode"] == "firmware-import-plan"
    assert first["planId"] == second["planId"]
    assert first["importId"] == second["importId"]
    assert first["source"]["sha256"] == _sha(payload)
    assert first["image"]["sha256"] != first["source"]["sha256"]
    assert first["image"]["segments"] == [{"address": 0x0800_0000, "length": 5}]
    assert first["authorization"] == {
        "required": True,
        "scope": "immutable-import-copy",
        "hardware": False,
    }
    assert not data_root.exists()
    assert sorted(path.name for path in project.iterdir()) == ["fw.bin"]


def test_import_requires_plan_and_exact_true_boolean(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = b"abc"
    (project / "fw.bin").write_bytes(payload)

    no_plan = firmware_import_workflow(
        _import_request(
            project, tmp_path / "data", "fw.bin", payload, authorized=True
        )
    )
    assert no_plan.code == "FIRMWARE_PLAN_REQUIRED"

    plan_id = _plan(project, tmp_path / "data2", "fw.bin", payload)["planId"]
    not_true = firmware_import_workflow(
        _import_request(
            project,
            tmp_path / "data3",
            "fw.bin",
            payload,
            plan_id=str(plan_id),
            authorized="true",
        )
    )
    assert not_true.code == "FIRMWARE_INPUT_INVALID"
    assert not_true.details["field"] == "authorized"

    truthy = firmware_import_workflow(
        _import_request(
            project,
            tmp_path / "data4",
            "fw.bin",
            payload,
            plan_id=str(plan_id),
            authorized=1,
        )
    )
    assert truthy.code == "FIRMWARE_INPUT_INVALID"


def test_apply_is_idempotent_and_tampered_store_never_reports_success(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"0123456789abcdef"
    (project / "fw.bin").write_bytes(payload)

    applied = _apply(project, data_root, "fw.bin", payload)
    assert applied["created"] is True
    assert applied["hardware"] == {
        "authorized": False,
        "hardwareVerified": False,
        "next": (
            "Call stm32_firmware_admit offline, select a probe with "
            "stm32_probe_list, then separately authorize "
            "stm32_flash_imported."
        ),
    }
    repeated = _apply(project, data_root, "fw.bin", payload)
    assert repeated["created"] is False
    assert repeated["importId"] == applied["importId"]

    record_path = _store_file(data_root, str(applied["importId"]), "record.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["image"]["segments"][0]["length"] += 1
    record_path.write_text(json.dumps(record), encoding="utf-8")

    tampered = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            plan_id=str(applied["planId"]),
            authorized=True,
        )
    )
    assert tampered.ok is False
    assert tampered.code in {
        "FIRMWARE_IMPORT_INVALID",
        "FIRMWARE_IMPORT_CONFLICT",
    }
    assert tampered.code != "FIRMWARE_INTERNAL_ERROR"


def test_identity_binds_project_and_data_roots(tmp_path: Path) -> None:
    project = _project(tmp_path)
    other_project = _project(tmp_path, "other-project")
    data_root = tmp_path / "data"
    other_data = tmp_path / "other-data"
    payload = b"root-bound"
    (project / "fw.bin").write_bytes(payload)
    (other_project / "fw.bin").write_bytes(payload)

    applied = _apply(project, data_root, "fw.bin", payload)
    source_sha = str(applied["source"]["sha256"])

    # Same record bytes under a different data root cannot be admitted.
    other_data.mkdir()
    copied = other_data / "projects"
    copied.mkdir()
    for child in (data_root / "projects").iterdir():
        (copied / child.name).mkdir()
        for import_dir in (child / "firmware-imports").iterdir():
            target = copied / child.name / "firmware-imports" / import_dir.name
            target.mkdir()
            for stored in import_dir.iterdir():
                (target / stored.name).write_bytes(stored.read_bytes())
    assert _admit(project, other_data, str(applied["importId"]), source_sha).ok is False
    assert _admit(project, other_data, str(applied["importId"]), source_sha).code in {
        "FIRMWARE_IMPORT_NOT_FOUND",
        "FIRMWARE_IMPORT_BINDING_MISMATCH",
    }

    # The same project/data binding cannot admit a different project root.
    relocated = _admit(
        other_project, data_root, str(applied["importId"]), source_sha
    )
    assert relocated.ok is False
    assert relocated.code in {
        "FIRMWARE_IMPORT_NOT_FOUND",
        "FIRMWARE_IMPORT_BINDING_MISMATCH",
    }

    # A plan from one data root is invalid when applied against another.
    drifted = firmware_import_workflow(
        _import_request(
            project,
            other_data,
            "fw.bin",
            payload,
            plan_id=str(applied["planId"]),
            authorized=True,
        )
    )
    assert drifted.code == "FIRMWARE_PLAN_CHANGED"


def test_admission_reconstructs_bytes_and_rejects_each_tamper(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"admission-bytes"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    admitted = _admit(project, data_root, import_id, source_sha)
    assert admitted.ok is True
    assert admitted.data["offlineReady"] is True
    assert admitted.data["hardwareVerified"] is False
    assert admitted.data["sourceSha256"] != admitted.data["imageSha256"]
    assert "stm32_flash_imported" in " ".join(
        admitted.data["remainingRequirements"]
    )

    wrong_pin = _admit(project, data_root, import_id, "0" * 64)
    assert wrong_pin.code == "FIRMWARE_INPUT_CHANGED"

    source_path = _store_file(data_root, import_id, "source.bin")
    original = source_path.read_bytes()
    source_path.write_bytes(b"X" + original[1:])
    corrupted = _admit(project, data_root, import_id, source_sha)
    assert corrupted.code == "FIRMWARE_IMPORT_INVALID"
    source_path.write_bytes(original)

    image_path = _store_file(data_root, import_id, "image.elf")
    image_bytes = image_path.read_bytes()
    image_path.write_bytes(image_bytes[:-1] + bytes([image_bytes[-1] ^ 0xFF]))
    corrupted_image = _admit(project, data_root, import_id, source_sha)
    assert corrupted_image.code == "FIRMWARE_IMPORT_INVALID"


def test_record_shape_errors_are_stable_import_failures(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"record-shape"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])
    record_path = _store_file(data_root, import_id, "record.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))

    def refused(mutated: dict[str, object]) -> None:
        record_path.write_text(json.dumps(mutated), encoding="utf-8")
        result = _admit(project, data_root, import_id, source_sha)
        assert result.ok is False
        assert result.code == "FIRMWARE_IMPORT_INVALID"

    for value in ([], {}, 1, True, None):
        mutated = json.loads(json.dumps(record))
        mutated["format"] = value
        refused(mutated)
    for value in ({}, [], "a" * 64, None):
        mutated = json.loads(json.dumps(record))
        mutated["flashRegions"] = value
        refused(mutated)
    mutated = json.loads(json.dumps(record))
    mutated["source"]["path"] = "../escape.bin"
    refused(mutated)
    mutated = json.loads(json.dumps(record))
    mutated["format"] = "hex"
    refused(mutated)
    mutated = json.loads(json.dumps(record))
    mutated["baseAddress"] = None
    refused(mutated)
    mutated = json.loads(json.dumps(record))
    mutated["createdAtUtc"] = "yesterday"
    refused(mutated)
    mutated = json.loads(json.dumps(record))
    mutated["image"]["entryPoint"] = 0x0800_0000
    refused(mutated)

    record_path.write_text(
        json.dumps(record)[:-1] + ', "format": "bin"}', encoding="utf-8"
    )
    duplicate = _admit(project, data_root, import_id, source_sha)
    assert duplicate.code == "FIRMWARE_IMPORT_INVALID"


def test_bin_and_region_rules_are_strict(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"region"
    (project / "fw.bin").write_bytes(payload)

    missing_base = firmware_import_workflow(
        _import_request(project, data_root, "fw.bin", payload, base=None)
    )
    assert missing_base.code == "FIRMWARE_INPUT_INVALID"
    assert missing_base.details["field"] == "baseAddress"

    for regions in (
        _regions((0x2000_0000, 0x100)),
        _regions((0x0801_0000, 0x100), (0x0800_0000, 0x100)),
        _regions((0x0800_0000, 0x200), (0x0800_0100, 0x100)),
    ):
        result = firmware_import_workflow(
            _import_request(
                project, data_root, "fw.bin", payload, regions=regions
            )
        )
        assert result.code == "FIRMWARE_FLASH_REGION_INVALID"

    for regions in (
        ((True, 0x100),),
        ((0x0800_0000, "0x100"),),
        ((0x0800_0000, 0.5),),
        ((0x0800_0000, 0),),
    ):
        result = firmware_import_workflow(
            _import_request(
                project, data_root, "fw.bin", payload, regions=regions  # type: ignore[arg-type]
            )
        )
        assert result.code in {
            "FIRMWARE_INPUT_INVALID",
            "FIRMWARE_FLASH_REGION_INVALID",
        }

    outside = firmware_import_workflow(
        _import_request(
            project,
            data_root,
            "fw.bin",
            payload,
            regions=_regions((0x0800_0000, 4)),
        )
    )
    assert outside.code == "FIRMWARE_FLASH_REGION_INVALID"
    assert not data_root.exists()


def test_base_address_is_forbidden_for_non_bin(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = _elf(((0x0800_0000, b"\x01\x02"),))
    (project / "fw.elf").write_bytes(payload)
    result = firmware_import_workflow(
        _import_request(
            project,
            tmp_path / "data",
            "fw.elf",
            payload,
            format="elf",
            base=0x0800_0000,
        )
    )
    assert result.code == "FIRMWARE_INPUT_INVALID"
    assert result.details["field"] == "baseAddress"


def test_unsafe_portable_paths_are_rejected_before_any_write(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "fw.bin").write_bytes(b"x")
    data_root = tmp_path / "data"

    for value in (
        "../fw.bin",
        "/absolute.bin",
        "C:/fw.bin",
        "a/../fw.bin",
        "a\\fw.bin",
        "con.bin",
        "fw.bin/",
        "a//b.bin",
    ):
        result = firmware_import_workflow(
            _import_request(project, data_root, value, b"x")
        )
        assert result.ok is False
        assert result.code == "FIRMWARE_PATH_UNSAFE"
    assert not data_root.exists()


def test_hex_crosses_64k_boundary_type04_after_data_and_type05_entry(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    lower = b"\x10" * 16
    upper = b"\x20" * 16
    text = _hex_file(
        [
            _hex_record(0x0000, 0x00, lower),
            _hex_record(0x0000, 0x04, (1).to_bytes(2, "big")),
            _hex_record(0x0000, 0x00, upper),
            _hex_record(0x0000, 0x05, (0x0800_0101).to_bytes(4, "big")),
        ]
    )
    payload = text.encode("ascii")
    (project / "fw.hex").write_bytes(payload)

    applied = _apply(
        project, data_root, "fw.hex", payload, format="hex", base=None
    )
    assert applied["image"]["segments"] == [
        {"address": 0x0000, "length": 16},
        {"address": 0x1_0000, "length": 16},
    ]
    assert applied["image"]["entryPoint"] == 0x0800_0101
    image = _store_file(data_root, str(applied["importId"]), "image.elf").read_bytes()
    elf = ELFFile(io.BytesIO(image))
    loads = [segment for segment in elf.iter_segments() if segment.header.p_type == "PT_LOAD"]
    assert [int(segment.header.p_paddr) for segment in loads] == [0, 0x1_0000]
    assert bytes(loads[0].data()) == lower
    assert bytes(loads[1].data()) == upper
    assert all(int(segment.header.p_align) == 1 for segment in loads)
    assert int(elf.header["e_entry"]) == 0x0800_0101


def test_hex_type03_segment_entry_uses_cs_times_sixteen_plus_ip(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    cs, ip = 0x1234, 0x5678
    text = _hex_file(
        [
            _hex_record(0x0000, 0x00, b"\xAA\xBB"),
            _hex_record(0x0000, 0x03, cs.to_bytes(2, "big") + ip.to_bytes(2, "big")),
        ]
    )
    payload = text.encode("ascii")
    (project / "fw.hex").write_bytes(payload)
    applied = _apply(
        project, data_root, "fw.hex", payload, format="hex", base=None
    )
    assert applied["image"]["entryPoint"] == (cs << 4) + ip


def test_hex_out_of_order_records_merge_by_address_and_keep_sparse_gaps(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    high = bytes(range(8))
    low = bytes(range(8, 16))
    sparse = b"\xFE" * 4
    text = _hex_file(
        [
            _hex_record(0x0010, 0x00, sparse),
            _hex_record(0x0008, 0x00, high),
            _hex_record(0x0000, 0x00, low),
        ]
    )
    payload = text.encode("ascii")
    (project / "fw.hex").write_bytes(payload)
    applied = _apply(
        project, data_root, "fw.hex", payload, format="hex", base=None
    )
    assert applied["image"]["segments"] == [
        {"address": 0x00, "length": 16},
        {"address": 0x10, "length": 4},
    ]
    image = _store_file(data_root, str(applied["importId"]), "image.elf").read_bytes()
    loads = [
        segment
        for segment in ELFFile(io.BytesIO(image)).iter_segments()
        if segment.header.p_type == "PT_LOAD"
    ]
    assert bytes(loads[0].data()) == low + high
    assert bytes(loads[1].data()) == sparse

    try:
        from intelhex import IntelHex  # type: ignore[import-not-found]
    except ImportError:
        IntelHex = None  # type: ignore[assignment,misc]
    if IntelHex is not None:
        reference = IntelHex()
        reference.loadhex(io.StringIO(text))
        payload_map = reference.todict()
        expected = {0x00 + index: low[index] for index in range(8)}
        expected.update({0x08 + index: high[index] for index in range(8)})
        expected.update({0x10 + index: 0xFE for index in range(4)})
        assert payload_map == expected


@pytest.mark.parametrize(
    ("records", "rule"),
    [
        (
            [
                _hex_record(0x0000, 0x00, b"\x01\x02"),
                _hex_record(0x0001, 0x00, b"\x03"),
            ],
            "overlap",
        ),
        ([":00000001FE"], "hexChecksum"),
        (
            [
                _hex_record(0x0000, 0x04, (0xFFFF).to_bytes(2, "big")),
                _hex_record(0xFFFF, 0x00, b"\x01\x02"),
            ],
            "hexAddress",
        ),
        ([_hex_record(0x0000, 0x06, b"")], "hexType"),
    ],
)
def test_hex_rejects_overlap_checksum_wrap_and_unknown_records(
    tmp_path: Path, records: list[str], rule: str
) -> None:
    project = _project(tmp_path)
    text = "\n".join([*records, _hex_record(0, 0x01)]) + "\n"
    if rule == "hexChecksum":
        text = records[0] + "\n"
    payload = text.encode("ascii")
    (project / "fw.hex").write_bytes(payload)
    result = firmware_import_workflow(
        _import_request(
            project,
            tmp_path / "data",
            "fw.hex",
            payload,
            format="hex",
            base=None,
        )
    )
    assert result.code == "FIRMWARE_IMAGE_INVALID"
    assert result.details["rule"] == rule
    assert not (tmp_path / "data").exists()


def test_hex_rejects_data_after_eof_and_missing_eof(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    after = "\n".join(
        [
            _hex_record(0, 0x01),
            _hex_record(0x0000, 0x00, b"\x01"),
        ]
    )
    for text, rule in (
        (after, "hexTrailing"),
        (_hex_record(0x0000, 0x00, b"\x01"), "hexEof"),
    ):
        payload = (text + "\n").encode("ascii")
        (project / "fw.hex").write_bytes(payload)
        result = firmware_import_workflow(
            _import_request(
                project, data_root, "fw.hex", payload, format="hex", base=None
            )
        )
        assert result.code == "FIRMWARE_IMAGE_INVALID"
        assert result.details["rule"] == rule


def test_elf_rejects_dynamic_wrong_arch_and_zero_data(tmp_path: Path) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    cases = (
        (_elf(((0x0800_0000, b"\x01\x02"),), extra_dynamic=True), "dynamic"),
        (_elf(((0x0800_0000, b"\x01\x02"),), machine=62), "elfHeader"),
        (_elf(((0x0800_0000, b""),)), "segments"),
        (_elf(((0x0800_0000, b"\x01"),), e_type=3), "elfHeader"),
    )
    for payload, rule in cases:
        (project / "fw.elf").write_bytes(payload)
        result = firmware_import_workflow(
            _import_request(
                project, data_root, "fw.elf", payload, format="elf", base=None
            )
        )
        assert result.code == "FIRMWARE_IMAGE_INVALID"
        assert result.details["rule"] == rule
    assert not data_root.exists()


def test_elf_segment_and_table_limits_are_enforced_before_payload_copy(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    too_many = _elf(
        tuple((0x0800_0000 + index * 4, b"\x00") for index in range(1025))
    )
    (project / "many.elf").write_bytes(too_many)
    many = firmware_import_workflow(
        _import_request(
            project, data_root, "many.elf", too_many, format="elf", base=None
        )
    )
    assert many.code == "FIRMWARE_IMAGE_INVALID"
    assert many.details["rule"] in {"size", "elfTable"}

    truncated = _elf(((0x0800_0000, b"\x01\x02"),))[:60]
    (project / "short.elf").write_bytes(truncated)
    short = firmware_import_workflow(
        _import_request(
            project, data_root, "short.elf", truncated, format="elf", base=None
        )
    )
    assert short.code == "FIRMWARE_IMAGE_INVALID"
    assert short.details["rule"] in {"elf", "elfTable", "elfSegments"}
    assert not data_root.exists()


def test_normalized_image_preserves_odd_payload_and_arbitrary_base(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"\xDE\xAD\xBE\xEF\x00\x5A\xC3"
    (project / "fw.bin").write_bytes(payload)
    base = 0x0800_0003
    applied = _apply(
        project,
        data_root,
        "fw.bin",
        payload,
        base=base,
        regions=_regions((0x0800_0000, 0x100)),
    )
    image = _store_file(data_root, str(applied["importId"]), "image.elf").read_bytes()
    loads = [
        segment
        for segment in ELFFile(io.BytesIO(image)).iter_segments()
        if segment.header.p_type == "PT_LOAD"
    ]
    assert len(loads) == 1
    assert int(loads[0].header.p_paddr) == base
    assert int(loads[0].header.p_vaddr) == base
    assert int(loads[0].header.p_filesz) == len(payload)
    assert int(loads[0].header.p_align) == 1
    assert bytes(loads[0].data()) == payload


def test_import_is_an_immutable_snapshot_of_the_original_source(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"snapshot-bytes"
    source = project / "fw.bin"
    source.write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    # Deleting or changing the original must not silently replace the import.
    source.write_bytes(b"rebuilt-differently")
    assert _admit(project, data_root, import_id, source_sha).ok is True
    source.unlink()
    assert _admit(project, data_root, import_id, source_sha).ok is True

    rebuilt = b"rebuilt"
    source.write_bytes(rebuilt)
    new_plan = _plan(project, data_root, "fw.bin", rebuilt)
    assert new_plan["importId"] != import_id
    stale_pin = _admit(project, data_root, import_id, _sha(rebuilt))
    assert stale_pin.code == "FIRMWARE_INPUT_CHANGED"


def _make_redirect(source: Path, destination: Path) -> None:
    try:
        os.symlink(source, destination, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        try:
            import _winapi  # type: ignore[attr-defined]

            _winapi.CreateJunction(str(source), str(destination))
            return
        except (AttributeError, OSError):
            pass
    pytest.skip("directory redirects require a platform privilege")


def test_intermediate_store_redirect_is_rejected_before_reads(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    data_root = tmp_path / "data"
    payload = b"redirect-test"
    (project / "fw.bin").write_bytes(payload)
    applied = _apply(project, data_root, "fw.bin", payload)
    import_id = str(applied["importId"])
    source_sha = str(applied["source"]["sha256"])

    workspace_root = next((data_root / "projects").iterdir())
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = outside / workspace_root.name
    os.rename(workspace_root, moved)
    _make_redirect(moved, workspace_root)

    try:
        result = _admit(project, data_root, import_id, source_sha)
        assert result.ok is False
        assert result.code == "FIRMWARE_IMPORT_STORE_UNSAFE"
    finally:
        if workspace_root.is_symlink():
            workspace_root.unlink()
        elif workspace_root.exists():
            os.rmdir(workspace_root)
        os.rename(moved, workspace_root)


def test_same_inputs_produce_the_same_plan_on_every_call(tmp_path: Path) -> None:
    project = _project(tmp_path)
    payload = _elf(((0x0800_0000, b"\x01\x02\x03"),), entry=0x0800_0001)
    (project / "fw.elf").write_bytes(payload)
    first = _plan(project, tmp_path / "data", "fw.elf", payload, format="elf", base=None)
    second = _plan(project, tmp_path / "data", "fw.elf", payload, format="elf", base=None)
    assert first == second
