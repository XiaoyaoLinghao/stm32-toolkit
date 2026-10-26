"""Static memory-margin summary, identity evidence, and admission contracts.

Every value here derives from the already validated ELF/MAP interval-union
accounting and the normalized model regions.  The tests pin the byte and
ratio thresholds (including exact equality), deterministic warning order,
strict typed round-trips, hash binding, successful runner publication, and
refusal of edited or forged summaries during current-build admission.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build.identity import (
    BuildError,
    GitEvidence,
    GitUnavailableEvidence,
    build_identity_document,
    compute_build_id,
    snapshot_project_inputs,
    validate_elf,
    validate_identity_document,
)
from stm32_toolkit.build.map_file import parse_map
from stm32_toolkit.build.memory_margin import (
    BASIS,
    MEMORY_LOW_MARGIN,
    MemorySummary,
    MemorySummaryError,
    build_memory_summary,
    memory_summary_matches,
)
from stm32_toolkit.build.model import FirmwareIdentity, MemoryUsage
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.mcp_server import ServerRuntime
from stm32_toolkit.probe import flash as flash_mod
from stm32_toolkit.probe.flash import flash_firmware, load_fresh_firmware_facts
from stm32_toolkit.project_model import MemoryRegion, load_project_model

from test_build_runner import (
    build_elf_bytes,
    build_map_text,
    install_fake_cmake,
    prepare_project,
    read_json,
)
from test_flash import (
    RecordingFlashClient,
    _publish_current_debug_build,
    _request,
)
from test_mcp_roots import _RootSession, _context

_BUILT_AT = "2026-10-25T08:00:00.000000Z"
_FLASH = (0x08000000, 0x100000)
_RAM = (0x20000000, 0x20000)


def _usage(name: str, origin: int, length: int, used: int) -> MemoryUsage:
    return MemoryUsage(
        name=name, origin=origin, length=length, used=used, free=length - used
    )


def _sample_summary() -> MemorySummary:
    """FLASH/RAM have wide margins; unused 256-byte IRAM2 warns on bytes."""
    return build_memory_summary(
        (
            _usage("FLASH", *_FLASH, 0x240),
            _usage("RAM", *_RAM, 0x500),
            _usage("IRAM2", 0x20020000, 256, 0),
        )
    )


def _identity_document(
    root: Path,
    *,
    summary: MemorySummary | None = None,
    snapshot_mode: bool = False,
) -> dict:
    model = load_project_model(root)
    snapshot = snapshot_project_inputs(model)
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    elf_path.parent.mkdir(parents=True, exist_ok=True)
    elf_path.write_bytes(build_elf_bytes())
    elf = validate_elf(elf_path, model)
    common = dict(
        model=model,
        preset="arm-debug",
        snapshot=snapshot,
        elf=elf,
        elf_size=elf.size,
        elf_sha256=elf.sha256,
        map_size=0x1000,
        map_sha256="b" * 64,
        built_at_utc=_BUILT_AT,
        memory_summary=summary,
    )
    if snapshot_mode:
        return build_identity_document(
            **common,
            git_unavailable=GitUnavailableEvidence(rule="head"),
        )
    return build_identity_document(
        **common,
        git=GitEvidence(head="a" * 40, dirty=False),
    )


# ---------------------------------------------------------------------------
# thresholds and deterministic ordering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "free", "flags"),
    [
        (131072, 1023, (True, True)),
        (131072, 1024, (False, True)),
        (65536, 1024, (False, True)),
        (20480, 1024, None),  # free == 1024 and free*20 == length
        (40000, 2000, None),  # exact 5% equality does not warn
        (40000, 1999, (False, True)),
        (131072, 6553, (False, True)),
        (131072, 6554, None),
        (100, 99, (True, False)),
        (256, 256, (True, False)),  # unused 256-byte region: bytes only
        (65536, 256, (True, True)),  # 256 free bytes in a 64 KiB region
        (100000, 0, (True, True)),
    ],
)
def test_low_margin_thresholds_are_exact_and_nonblocking(
    length: int, free: int, flags: tuple[bool, bool] | None
) -> None:
    summary = build_memory_summary((_usage("REGION", 0x20000000, length, length - free),))

    if flags is None:
        assert summary.warnings == ()
        return
    warning = summary.warnings[0]
    assert warning.code == MEMORY_LOW_MARGIN
    assert warning.region == "REGION"
    assert warning.free_bytes == free
    assert warning.length_bytes == length
    assert (warning.below_bytes, warning.below_percent) == flags
    assert warning.below_bytes or warning.below_percent
    assert warning.text().startswith(MEMORY_LOW_MARGIN + ": region REGION")
    assert "largest contiguous free block" in warning.text()
    assert "runtime stack/heap peak" in warning.text()
    assert "initialization proof" in warning.text()
    assert summary.warning_texts() == (warning.text(),)


def test_warnings_follow_model_region_order_including_unused_regions() -> None:
    summary = build_memory_summary(
        (
            _usage("FLASH", *_FLASH, 0x240),
            _usage("RAM", *_RAM, 0x500),  # free 0x1FB00: wide
            _usage("CCM", 0x10000000, 0x1000, 0xF3C),  # free 196
            _usage("IRAM2", 0x20020000, 256, 0),  # free 256
        )
    )

    assert [region.name for region in summary.regions] == [
        "FLASH",
        "RAM",
        "CCM",
        "IRAM2",
    ]
    assert [warning.region for warning in summary.warnings] == ["CCM", "IRAM2"]
    assert [warning.free_bytes for warning in summary.warnings] == [196, 256]
    assert summary.warnings[0].below_percent is True
    assert summary.warnings[1].below_percent is False


def test_interval_holes_use_union_free_not_region_span_or_largest_block() -> None:
    regions = (
        MemoryRegion("FLASH", *_FLASH, "r-x"),
        MemoryRegion("RAM", 0x20000000, 0x1000, "rwx"),
    )
    text = build_map_text(
        regions=(("FLASH", *_FLASH), ("RAM", 0x20000000, 0x1000)),
        region_attributes=("xr", "xrw"),
        sections=(
            (".text", 0x08000040, 0x10, None),
            (".data", 0x20000000, 0xF00, None),
            (".bss", 0x20000F10, 0x3C, None),
        ),
    )

    flash, ram = parse_map(text, regions)
    assert flash.used == 0x10
    assert ram.used == 0xF3C
    assert ram.free == 0xC4
    summary = build_memory_summary((flash, ram))
    assert summary.regions[1].used == 0xF3C
    assert summary.regions[1].free == 196
    # The 16-byte hole plus the 180-byte tail are 196 union-free bytes; the
    # largest contiguous free block (180) is deliberately not what is stored.
    assert summary.regions[1].free != 0x1000 - 0xF4C
    assert summary.warnings[0].region == "RAM"
    assert summary.warnings[0].free_bytes == 196


# ---------------------------------------------------------------------------
# strict typed summary validation
# ---------------------------------------------------------------------------


def test_summary_round_trip_returns_fresh_containers() -> None:
    typed = _sample_summary()
    document = typed.to_dict()
    assert document["basis"] == BASIS
    assert document["regions"][1] == {
        "name": "RAM",
        "origin": _RAM[0],
        "length": _RAM[1],
        "used": 0x500,
        "free": _RAM[1] - 0x500,
    }
    assert document["warnings"] == [
        {
            "code": MEMORY_LOW_MARGIN,
            "region": "IRAM2",
            "freeBytes": 256,
            "lengthBytes": 256,
            "belowBytes": True,
            "belowPercent": False,
        }
    ]

    assert MemorySummary.from_document(document) == typed
    assert memory_summary_matches(document, typed.regions) is True
    assert memory_summary_matches(None, typed.regions) is False

    document["regions"][0]["used"] = 0
    document["warnings"].clear()
    assert typed.to_dict()["regions"][0]["used"] == 0x240
    assert len(typed.to_dict()["warnings"]) == 1
    assert isinstance(typed.regions, tuple) and isinstance(typed.warnings, tuple)
    with pytest.raises(AttributeError):
        typed.regions[0].used = 1  # type: ignore[misc]

    fresh = typed.to_dict()
    fresh["regions"][1]["free"] = 0
    assert typed.regions[1].free == _RAM[1] - 0x500


def _mutate_region(key: str, value: object):
    def mutate(document: dict) -> None:
        document["regions"][0][key] = value

    return mutate


def _mutate_warning(key: str, value: object):
    def mutate(document: dict) -> None:
        document["warnings"][0][key] = value

    return mutate


def _overlapping_regions(document: dict) -> None:
    document["regions"][2]["origin"] = document["regions"][1]["origin"]


def _duplicate_names(document: dict) -> None:
    document["regions"][2]["name"] = document["regions"][1]["name"]


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(lambda document: document.clear(), id="not-a-summary"),
        pytest.param(lambda document: document.pop("basis"), id="missing-basis"),
        pytest.param(lambda document: document.__setitem__("extra", 1), id="extra-key"),
        pytest.param(lambda document: document.__setitem__("basis", "other"), id="basis"),
        pytest.param(lambda document: document.__setitem__("regions", []), id="empty-regions"),
        pytest.param(lambda document: document.__setitem__("regions", "x"), id="regions-type"),
        pytest.param(lambda document: document.__setitem__("warnings", "x"), id="warnings-type"),
        pytest.param(
            lambda document: document["regions"][0].__setitem__("extra", 1),
            id="region-extra-key",
        ),
        pytest.param(lambda document: document["regions"][0].pop("name"), id="region-missing-key"),
        pytest.param(_mutate_region("name", ""), id="region-empty-name"),
        pytest.param(_mutate_region("origin", True), id="region-origin-bool"),
        pytest.param(_mutate_region("origin", -1), id="region-origin-negative"),
        pytest.param(_mutate_region("origin", 0x100000000), id="region-origin-max"),
        pytest.param(_mutate_region("length", 0), id="region-length-zero"),
        pytest.param(_mutate_region("length", True), id="region-length-bool"),
        pytest.param(_mutate_region("length", 0x100000001), id="region-length-max"),
        pytest.param(_mutate_region("origin", 0xFFFFFFFF), id="region-end-max"),
        pytest.param(_mutate_region("used", True), id="region-used-bool"),
        pytest.param(_mutate_region("used", _FLASH[1] + 1), id="region-used-range"),
        pytest.param(_mutate_region("free", True), id="region-free-bool"),
        pytest.param(
            lambda document: document["regions"][0].__setitem__(
                "free", document["regions"][0]["free"] - 1
            ),
            id="region-sum",
        ),
        pytest.param(_duplicate_names, id="region-duplicate-name"),
        pytest.param(_overlapping_regions, id="region-overlap"),
        pytest.param(
            lambda document: document["warnings"].clear(), id="missing-warning"
        ),
        pytest.param(
            lambda document: document["warnings"].append(
                dict(document["warnings"][0])
            ),
            id="duplicate-warning",
        ),
        pytest.param(_mutate_warning("code", "OTHER"), id="warning-code"),
        pytest.param(_mutate_warning("region", "RAM"), id="warning-region"),
        pytest.param(_mutate_warning("freeBytes", True), id="warning-free-bool"),
        pytest.param(_mutate_warning("freeBytes", 255), id="warning-free-value"),
        pytest.param(_mutate_warning("lengthBytes", 255), id="warning-length-value"),
        pytest.param(_mutate_warning("belowBytes", False), id="warning-below-bytes"),
        pytest.param(_mutate_warning("belowPercent", True), id="warning-below-percent"),
        pytest.param(_mutate_warning("belowBytes", 1), id="warning-below-type"),
    ],
)
def test_from_document_rejects_malformed_or_forged_summaries(mutator) -> None:
    document = _sample_summary().to_dict()
    mutator(document)

    with pytest.raises(MemorySummaryError):
        MemorySummary.from_document(document)


def test_warning_order_and_exact_correspondence_are_enforced() -> None:
    usages = (
        _usage("A", 0x20000000, 0x1000, 0xF00),  # free 256
        _usage("B", 0x20001000, 0x1000, 0xF00),  # free 256
    )
    document = build_memory_summary(usages).to_dict()
    assert [warning["region"] for warning in document["warnings"]] == ["A", "B"]

    document["warnings"].reverse()
    with pytest.raises(MemorySummaryError):
        MemorySummary.from_document(document)

    document["warnings"].reverse()
    document["warnings"][0], document["warnings"][1] = (
        document["warnings"][1],
        document["warnings"][0],
    )
    document["warnings"].append(dict(document["warnings"][0]))
    with pytest.raises(MemorySummaryError):
        MemorySummary.from_document(document)


# ---------------------------------------------------------------------------
# identity schema, hash binding, and optional compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("snapshot_mode", [False, True])
def test_summary_is_optional_hash_bound_and_round_trips(
    tmp_path: Path, snapshot_mode: bool
) -> None:
    root = prepare_project(
        tmp_path, git_repo=False, name="snapshot" if snapshot_mode else "git"
    )
    legacy = _identity_document(root, snapshot_mode=snapshot_mode)
    assert "memorySummary" not in legacy
    validate_identity_document(legacy)
    assert FirmwareIdentity.from_document(legacy).to_dict() == legacy
    legacy_id = legacy["buildId"]
    assert compute_build_id(legacy) == legacy_id

    with_summary = _identity_document(
        root, summary=_sample_summary(), snapshot_mode=snapshot_mode
    )
    assert with_summary["schemaVersion"] == (2 if snapshot_mode else 1)
    assert with_summary["memorySummary"] == _sample_summary().to_dict()
    validate_identity_document(with_summary)
    typed = FirmwareIdentity.from_document(with_summary)
    assert typed.to_dict() == with_summary
    assert typed.memory_summary == _sample_summary()
    assert compute_build_id(with_summary) == with_summary["buildId"]
    assert with_summary["buildId"] != legacy_id

    without_field = {
        key: value for key, value in with_summary.items() if key != "memorySummary"
    }
    assert compute_build_id(without_field) == legacy_id

    changed_document = json.loads(json.dumps(with_summary))
    changed_document["memorySummary"]["regions"][1]["used"] += 1
    changed_document["memorySummary"]["regions"][1]["free"] -= 1
    changed_document["buildId"] = compute_build_id(changed_document)
    assert changed_document["buildId"] != with_summary["buildId"]
    validate_identity_document(changed_document)


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(
            lambda summary: summary["regions"][2].__setitem__("used", 1),
            id="region-sum",
        ),
        pytest.param(
            lambda summary: summary["warnings"].clear(), id="warning-removed"
        ),
        pytest.param(
            lambda summary: summary["warnings"][0].__setitem__(
                "belowPercent", True
            ),
            id="warning-flag",
        ),
        pytest.param(
            lambda summary: summary.__setitem__("basis", "other"), id="basis"
        ),
        pytest.param(
            lambda summary: summary["regions"][0].__setitem__("extra", 1),
            id="shape",
        ),
    ],
)
def test_identity_validation_rejects_forged_summary_with_recomputed_build_id(
    tmp_path: Path, mutator
) -> None:
    root = prepare_project(tmp_path, git_repo=False)
    document = _identity_document(root, summary=_sample_summary())
    mutator(document["memorySummary"])
    document["buildId"] = compute_build_id(document)

    with pytest.raises(BuildError) as error:
        validate_identity_document(document)
    assert error.value.code == "BUILD_EVIDENCE_FAILED"
    assert error.value.details == {"phase": "identity"}
    with pytest.raises(MemorySummaryError):
        FirmwareIdentity.from_document(document)


# ---------------------------------------------------------------------------
# successful runner publication and report/result parity
# ---------------------------------------------------------------------------


def test_successful_runner_always_emits_summary_with_empty_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result
    report = result.data
    identity_document = read_json(
        root / "build" / "arm-debug" / "firmware-identity.json"
    )
    result_document = read_json(root / "artifacts" / "migration" / "build-result.json")
    assert identity_document["memorySummary"]["basis"] == BASIS
    assert identity_document["memorySummary"]["regions"] == [
        item.to_dict() for item in report.memory
    ]
    assert identity_document["memorySummary"]["warnings"] == []
    assert report.warnings == ()
    assert result_document["warnings"] == []
    assert result_document["memory"] == [item.to_dict() for item in report.memory]
    assert report.to_dict()["identity"]["memorySummary"] == identity_document[
        "memorySummary"
    ]
    assert report.identity.memory_summary == MemorySummary.from_document(
        identity_document["memorySummary"]
    )
    assert compute_build_id(identity_document) == identity_document["buildId"]
    assert FirmwareIdentity.from_document(identity_document).to_dict() == identity_document


def test_successful_snapshot_runner_emits_summary_and_admits_content_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path, git_repo=False)
    install_fake_cmake(monkeypatch, tmp_path)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    result_path = root / "artifacts" / "migration" / "build-result.json"
    identity_document = read_json(identity_path)
    result_document = read_json(result_path)
    assert identity_document["schemaVersion"] == 2
    assert identity_document["memorySummary"]["basis"] == BASIS
    assert identity_document["memorySummary"]["warnings"] == []
    assert result_document["warnings"] == []
    assert compute_build_id(identity_document) == identity_document["buildId"]

    client = RecordingFlashClient(b"\x00" * 64)
    refused = asyncio.run(flash_firmware(_request(root, identity_document), client))
    # The snapshot identity passes every content/memory check and stops only
    # at the segment stage because this deterministic fake image carries no
    # PT_LOAD header.  Git is not required, and no probe effect occurs.
    assert refused.ok is False
    assert refused.code == "FLASH_IMAGE_INVALID"
    assert refused.details == {"path": "build/arm-debug/firmware.elf", "rule": "segments"}
    assert client.events == []

    # The malformed-summary guard still runs inside admission; schema-2
    # provenance never turns forged summary evidence into a normal result,
    # and no probe/hardware effect occurs.
    tampered = read_json(identity_path)
    tampered["memorySummary"]["warnings"].append(
        {
            "code": MEMORY_LOW_MARGIN,
            "region": "RAM",
            "freeBytes": _RAM[1] - 0x500,
            "lengthBytes": _RAM[1],
            "belowBytes": False,
            "belowPercent": True,
        }
    )
    tampered["buildId"] = compute_build_id(tampered)
    identity_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    result_document["buildId"] = tampered["buildId"]
    result_path.write_text(json.dumps(result_document) + "\n", encoding="utf-8")

    forged_client = RecordingFlashClient(b"\x00" * 64)
    forged = asyncio.run(flash_firmware(_request(root, tampered), forged_client))
    assert forged.ok is False
    assert forged.code == "FIRMWARE_EVIDENCE_INVALID"
    assert forged.details["path"] == "build/arm-debug/firmware-identity.json"
    assert forged.details["rule"] == "schema"
    assert forged_client.events == []


def test_failed_build_emits_no_fresh_identity_or_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path)
    install_fake_cmake(
        monkeypatch, tmp_path, env={"FAKE_CMAKE_ELF_DEFECT": "no-vector"}
    )

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_ARTIFACT_INVALID"
    assert not (root / "build" / "arm-debug" / "firmware-identity.json").exists()
    failure = read_json(root / "artifacts" / "migration" / "build-result.json")
    assert failure["status"] == "failure"
    assert failure["memory"] == []
    assert failure["warnings"] == []
    assert "memorySummary" not in json.dumps(failure)


def _extra_region_memory() -> dict:
    return {
        "source": "manual",
        "regions": [
            {"name": "FLASH", "origin": _FLASH[0], "length": _FLASH[1], "attributes": "r-x"},
            {"name": "RAM", "origin": _RAM[0], "length": _RAM[1], "attributes": "rwx"},
        ],
        "extraRegions": [
            {
                "name": "IRAM2",
                "origin": 0x20020000,
                "length": 256,
                "attributes": "rw-",
            }
        ],
        "layout": {
            "flash": "FLASH",
            "data": "RAM",
            "bss": "RAM",
            "heap": "RAM",
            "stack": "RAM",
        },
    }


def test_successful_runner_warns_for_unused_256_byte_extra_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path, overrides={"memory": _extra_region_memory()})
    install_fake_cmake(monkeypatch, tmp_path)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result
    report = result.data
    identity_document = read_json(
        root / "build" / "arm-debug" / "firmware-identity.json"
    )
    result_document = read_json(root / "artifacts" / "migration" / "build-result.json")
    summary = identity_document["memorySummary"]
    assert [region["name"] for region in summary["regions"]] == [
        "FLASH",
        "RAM",
        "IRAM2",
    ]
    assert summary["regions"][2] == {
        "name": "IRAM2",
        "origin": 0x20020000,
        "length": 256,
        "used": 0,
        "free": 256,
    }
    assert summary["warnings"] == [
        {
            "code": MEMORY_LOW_MARGIN,
            "region": "IRAM2",
            "freeBytes": 256,
            "lengthBytes": 256,
            "belowBytes": True,
            "belowPercent": False,
        }
    ]
    assert report.warnings == tuple(result_document["warnings"])
    assert len(report.warnings) == 1
    assert "IRAM2" in report.warnings[0]
    assert "256 free bytes" in report.warnings[0]
    assert report.identity.memory_summary.to_dict() == summary


def test_noop_rebuild_rejects_forged_warning_summary_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path, overrides={"memory": _extra_region_memory()})
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True, first

    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    document = read_json(identity_path)
    document["memorySummary"]["warnings"] = []
    document["buildId"] = compute_build_id(document)
    identity_path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-evidence-mismatch"
    assert result.details["evidenceField"] == "identityDocument"
    assert result.details["evidenceSource"] == "identity"


def test_cli_and_mcp_build_paths_propagate_summary_and_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    cli_root = prepare_project(tmp_path, name="cli-summary")
    install_fake_cmake(monkeypatch, tmp_path)

    assert cli_main(["build", "--project", str(cli_root), "--preset", "arm-debug"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["identity"]["memorySummary"]["basis"] == BASIS
    assert payload["data"]["warnings"] == []

    mcp_root = prepare_project(tmp_path, name="mcp-summary")
    install_fake_cmake(monkeypatch, tmp_path)
    runtime = ServerRuntime.create(mcp_root, tmp_path / "plugin-data", "session-a")
    mcp_payload = asyncio.run(
        mcp_mod.tool_build_for_request(
            runtime,
            _context(_RootSession([[runtime.project_root]])),
            "arm-debug",
            False,
            300,
            True,
        )
    )
    assert mcp_payload["ok"] is True
    assert mcp_payload["data"]["identity"]["memorySummary"]["basis"] == BASIS
    assert mcp_payload["data"]["warnings"] == []


# ---------------------------------------------------------------------------
# current-build admission recomputation
# ---------------------------------------------------------------------------


def test_flash_admission_recomputes_and_rejects_edited_summary(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    # Use the established current-debug fixture: a real PT_LOAD-bearing ELF,
    # matching GNU MAP, complete Git evidence and identity/result records.
    identity = _publish_current_debug_build(root)
    model = load_project_model(root)
    map_rel = "build/arm-debug/firmware.map"
    elf_evidence = validate_elf(root / "build" / "arm-debug" / "firmware.elf", model)
    usages = parse_map(
        (root / "build" / "arm-debug" / "firmware.map").read_text(encoding="utf-8"),
        model.memory.regions,
        path=map_rel,
        elf_sections=elf_evidence.sections,
    )
    identity["memorySummary"] = build_memory_summary(usages).to_dict()
    identity["buildId"] = compute_build_id(identity)

    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    result_path = root / "artifacts" / "migration" / "build-result.json"
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    result_document = read_json(result_path)
    result_document["buildId"] = identity["buildId"]
    result_path.write_text(json.dumps(result_document, indent=2) + "\n", encoding="utf-8")

    # The genuine current build with its real flashable segment is admitted,
    # proving both summary recomputation and the unchanged image guards run.
    facts = load_fresh_firmware_facts(root)
    assert facts.elf_path == "build/arm-debug/firmware.elf"

    original = read_json(identity_path)
    original_summary = json.loads(json.dumps(original["memorySummary"]))

    forged = json.loads(json.dumps(original))
    forged["memorySummary"]["regions"][1]["used"] += 1
    forged["memorySummary"]["regions"][1]["free"] -= 1
    forged["buildId"] = compute_build_id(forged)
    identity_path.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    result_document = read_json(result_path)
    result_document["buildId"] = forged["buildId"]
    result_path.write_text(json.dumps(result_document) + "\n", encoding="utf-8")

    with pytest.raises(flash_mod._FlashFailure) as mismatch:
        load_fresh_firmware_facts(root)
    assert mismatch.value.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert mismatch.value.details == {
        "field": "memorySummary",
        "rule": "identity",
    }

    # A warning-only forgery is already refused by identity semantic validation
    # even after recomputing the build ID and synchronizing the record.
    tampered = json.loads(json.dumps(original))
    tampered["memorySummary"] = original_summary
    tampered["memorySummary"]["warnings"].append(
        {
            "code": MEMORY_LOW_MARGIN,
            "region": "RAM",
            "freeBytes": _RAM[1] - 0x500,
            "lengthBytes": _RAM[1],
            "belowBytes": False,
            "belowPercent": True,
        }
    )
    tampered["buildId"] = compute_build_id(tampered)
    identity_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    result_document = read_json(result_path)
    result_document["buildId"] = tampered["buildId"]
    result_path.write_text(json.dumps(result_document) + "\n", encoding="utf-8")

    with pytest.raises(flash_mod._FlashFailure) as evidence_invalid:
        load_fresh_firmware_facts(root)
    assert evidence_invalid.value.code == "FIRMWARE_EVIDENCE_INVALID"
    assert evidence_invalid.value.details["path"] == (
        "build/arm-debug/firmware-identity.json"
    )
    assert evidence_invalid.value.details["rule"] == "schema"
