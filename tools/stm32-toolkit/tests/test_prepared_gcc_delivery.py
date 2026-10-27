"""Combined prepared-source GCC delivery and managed simulated flash journey.

One synthetic, complete, no-Git Keil project with authored GBK C comments and
a required quoted macro header is reviewed with the existing comment
normalizer, copied into a complete prepared tree, migrated through the public
preflight/PLAN/APPLY workflow into an independent GCC project, built with the
installed ARM GNU toolchain, relocated without source/prepared access, rebuilt,
and finally programmed through the normal managed flash workflow whose only
test seam is a deterministic in-memory backend.

No product identity, managed digest, compiler output or firmware artifact is
fabricated: the real Toolkit build workflow produces every admitted byte.  The
simulated probe is not physical evidence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.build.model import (
    SNAPSHOT_IDENTITY_SCHEMA_VERSION,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
)
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    preflight_keil_workflow,
)

from gcc_delivery_integration_helpers import (
    ALIGNMENT,
    BINARY_RESOURCE,
    EXTRA_SRAM2,
    FIXED_ADDRESS,
    LICENSE_TEXT,
    MAIN_RAM_LAYOUT,
    PROBE_ID,
    RUNTIME_LITERAL,
    SIM_LOG_ENV,
    SIM_MODE_ENV,
    STARTUP_SOURCE,
    STARTUP_STRATEGY,
    TARGET_NAME,
    UNLISTED_SOURCE_TEXT,
    UVPROJX,
    WFI_RETURNS,
    WFI_SOURCE,
    WFI_TEXT,
    FlashOutcome,
    apply_toolchain_path,
    assert_no_git_metadata,
    assert_under,
    build_no_git_project,
    copy_output_only,
    copy_reviewed_comments,
    elf_entry_and_symbols,
    event_names,
    prepare_complete_project,
    preview_source_comments,
    pt_load_segments,
    read_probe_log,
    relocate_fixture_tree,
    run_managed_flash,
    sha256_bytes,
    tree_inventory,
)
from startup_gcc_fixture import STARTUP_SOURCE as FIXTURE_STARTUP_SOURCE

DEBUG_TARGET = "stm32f429zgtx"
IREGION = (0x08000000, 0x08100000)
IRAM1 = (0x20000000, 0x20030000)
#: The second internal RAM region selected for the stack role.
IRAM2 = (0x10000000, 0x10010000)
STAGING_MARKER = ".stm32tk-staging-"


def _assert_snapshot_git_evidence(evidence: object) -> None:
    assert isinstance(evidence, dict)
    assert evidence["status"] == "unavailable"
    assert evidence["code"] == "BUILD_GIT_INVALID"
    assert evidence["rule"] in {"head", "status"}


def _identity(root: Path) -> tuple[dict[str, object], bytes, bytes]:
    document = json.loads(
        (root / "build" / "arm-debug" / "firmware-identity.json").read_text(
            encoding="utf-8"
        )
    )
    elf = root.joinpath(*str(document["elfPath"]).split("/")).read_bytes()
    map_data = root.joinpath(*str(document["mapPath"]).split("/")).read_bytes()
    return document, elf, map_data


def _assert_flash_confined(elf: bytes) -> None:
    segments = pt_load_segments(elf)
    assert segments
    for address, payload in segments:
        assert IREGION[0] <= address, hex(address)
        assert address + len(payload) <= IREGION[1], hex(address)


def _initial_stack_pointer(elf: bytes) -> int:
    """Read the vector table's initial SP word from the linked flash image."""

    segments = pt_load_segments(elf)
    address, payload = min(segments, key=lambda item: item[0])
    assert address == IREGION[0], hex(address)
    assert len(payload) >= 4
    return int.from_bytes(payload[:4], "little")


def _assert_fixed_placement(elf: bytes) -> None:
    entry, symbols = elf_entry_and_symbols(elf)
    assert IREGION[0] <= entry < IREGION[1]
    # The supported absolute-placement rewrite produced one fixed section at
    # the exact value of the authored address expression.
    assert symbols["fixed_buffer"] == FIXED_ADDRESS
    aligned = symbols["aligned_runtime"]
    assert aligned % ALIGNMENT == 0
    assert IRAM1[0] <= aligned < IRAM1[1]
    assert "Reset_Handler" in symbols
    # main() calls WFI_SET, so the converted wrapper survives --gc-sections
    # in the executable flash region rather than being dropped as unused.
    assert IREGION[0] <= symbols["WFI_SET"] < IREGION[1]
    # The selected stack role is real: the vector table's initial stack
    # pointer points into IRAM2, while bss stays in IRAM1 above.
    stack_pointer = _initial_stack_pointer(elf)
    assert IRAM2[0] < stack_pointer <= IRAM2[1], hex(stack_pointer)
    assert RUNTIME_LITERAL.encode("ascii") in elf


def _assert_no_reference(project: Path, tokens: tuple[Path, ...]) -> None:
    normalized = tuple(os.path.normcase(str(token)) for token in tokens)
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(project).as_posix()
        if relative == "build" or relative.startswith("build/"):
            continue
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            continue
        text = os.path.normcase(data.decode("utf-8", "replace"))
        for token in normalized:
            assert token not in text, (relative, token)
        assert STAGING_MARKER not in text, relative


@pytest.fixture(scope="module")
def journey(tmp_path_factory) -> SimpleNamespace:
    """One real delivery/build/relocation journey shared by flash scenarios."""

    root = tmp_path_factory.mktemp("gcc-delivery-journey")
    with pytest.MonkeyPatch.context() as monkeypatch:
        gcc, cmake, ninja = apply_toolchain_path(monkeypatch)
        assert Path(gcc).is_file() and Path(cmake).is_file() and Path(ninja).is_file()

        source = build_no_git_project(root)
        source_before = tree_inventory(source)
        assert_no_git_metadata(source)

        (root / "prep").mkdir(parents=True, exist_ok=True)
        preview_dir = root / "prep" / "preview"
        copy_dir = root / "prep" / "copy"
        prepared = root / "prep" / "prepared"
        preview_payload, preview_plan = preview_source_comments(source, preview_dir)
        copy_payload, copy_manifest = copy_reviewed_comments(
            source, preview_payload, copy_dir
        )
        prepared_before = prepare_complete_project(
            source, copy_dir, copy_manifest, prepared
        )
        assert tree_inventory(source) == source_before

        delivery_options = {
            "uvprojx": UVPROJX,
            "target_name": TARGET_NAME,
            "startup_strategy": STARTUP_STRATEGY,
            "startup_source": STARTUP_SOURCE,
            "memory_layout": dict(MAIN_RAM_LAYOUT),
            "extra_regions": [dict(EXTRA_SRAM2)],
            "wfi_returns": [dict(entry) for entry in WFI_RETURNS],
        }

        preflight = preflight_keil_workflow(prepared, **delivery_options)
        assert preflight.ok is True, preflight.to_dict()
        assert preflight.to_dict()["data"]["analysis"]["blockers"] == []
        assert (
            preflight.to_dict()["data"]["planReadiness"]["status"]
            == "ready-for-plan"
        )

        # Delivery planning requires an existing destination parent and a
        # destination that is absent or empty; it never creates either.
        destination = root / "out" / "gcc-project"
        destination.parent.mkdir(parents=True, exist_ok=True)
        planned = convert_keil_workflow(
            prepared, destination=destination, **delivery_options
        )
        assert planned.ok is True, planned.to_dict()
        assert planned.operation == "keil-conversion-plan"
        plan_id = planned.to_dict()["data"]["planId"]
        assert not destination.exists()
        assert tree_inventory(source) == source_before
        assert tree_inventory(prepared) == prepared_before

        applied = convert_keil_workflow(
            prepared,
            destination=destination,
            plan_id=plan_id,
            authorized=True,
            **delivery_options,
        )
        assert applied.ok is True, applied.to_dict()
        assert applied.operation == "keil-conversion-apply"
        assert applied.to_dict()["data"]["configured"] is True
        assert applied.to_dict()["data"]["built"] is False
        assert applied.to_dict()["data"]["flashed"] is False
        assert tree_inventory(source) == source_before
        assert tree_inventory(prepared) == prepared_before
        assert_no_git_metadata(source, prepared, destination)

        configuring = configure_project_workflow(
            destination, debug_backend="pyocd", debug_target=DEBUG_TARGET
        )
        assert configuring.ok is True, configuring.to_dict()
        # The configure PLAN response carries the snake_case plan_id.
        configuration_id = configuring.to_dict()["data"]["plan_id"]
        configured = configure_project_workflow(
            destination,
            plan_id=configuration_id,
            authorized=True,
            debug_backend="pyocd",
            debug_target=DEBUG_TARGET,
        )
        assert configured.ok is True, configured.to_dict()

        built = build_firmware_workflow(
            destination, preset="arm-debug", authorized=True, timeout_seconds=300
        )
        assert built.ok is True, built.to_dict()
        first_identity, first_elf, first_map = _identity(destination)
        assert first_identity["schemaVersion"] == SNAPSHOT_IDENTITY_SCHEMA_VERSION
        assert first_identity["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
        assert first_identity["gitHead"] is None
        assert first_identity["gitDirty"] is None
        _assert_snapshot_git_evidence(first_identity["gitEvidence"])
        assert first_identity["buildId"] == built.data.identity.build_id
        first_cache = (destination / "build" / "arm-debug" / "CMakeCache.txt").read_text(
            encoding="utf-8", errors="replace"
        )

        # Only fixture-owned trees are relocated, and they are retained rather
        # than deleted.
        retired = root / "retired"
        assert_under(root, source, prepared)
        retired_source = relocate_fixture_tree(root, source, retired / "source")
        retired_prepared = relocate_fixture_tree(
            root, prepared, retired / "prepared"
        )
        assert tree_inventory(retired_source) == source_before
        assert tree_inventory(retired_prepared) == prepared_before

        relocated = copy_output_only(root, destination, root / "relocated" / "project")
        assert_under(root, relocated)
        assert (destination / "build").is_dir()  # owned build state is retained

        rebuilt = build_firmware_workflow(
            relocated,
            preset="arm-debug",
            clean=True,
            authorized=True,
            timeout_seconds=300,
        )
        assert rebuilt.ok is True, rebuilt.to_dict()
        second_identity, second_elf, second_map = _identity(relocated)
        assert second_identity["buildId"] == rebuilt.data.identity.build_id
        second_cache = (
            relocated / "build" / "arm-debug" / "CMakeCache.txt"
        ).read_text(encoding="utf-8", errors="replace")

    report = json.loads(
        (
            destination / "artifacts" / "migration" / "conversion-report.json"
        ).read_text(encoding="utf-8")
    )
    return SimpleNamespace(
        root=root,
        source=retired_source,
        prepared=retired_prepared,
        source_before=source_before,
        prepared_before=prepared_before,
        preview_payload=preview_payload,
        preview_plan=preview_plan,
        copy_payload=copy_payload,
        copy_manifest=copy_manifest,
        preflight=preflight.to_dict(),
        planned=planned.to_dict(),
        applied=applied.to_dict(),
        destination=destination,
        report=report,
        first_identity=first_identity,
        first_elf=first_elf,
        first_map=first_map,
        first_cache=first_cache,
        relocated=relocated,
        second_identity=second_identity,
        second_elf=second_elf,
        second_map=second_map,
        second_cache=second_cache,
        toolchain=(gcc, cmake, ninja),
    )


def _flash_pins(identity: dict[str, object]) -> tuple[str, str]:
    return str(identity["buildId"]), str(identity["elfSha256"])


# ---------------------------------------------------------------------------
# step 1: preparation, public delivery and real GCC evidence
# ---------------------------------------------------------------------------


def test_prepared_complete_project_delivery_and_real_build(journey) -> None:
    assert FIXTURE_STARTUP_SOURCE == STARTUP_SOURCE

    # The original and prepared hash inventories are bound and unchanged by
    # preview, copy and delivery.
    assert tree_inventory(journey.source) == journey.source_before
    assert tree_inventory(journey.prepared) == journey.prepared_before
    assert_no_git_metadata(
        journey.source, journey.prepared, journey.destination, journey.relocated
    )

    # Public preflight/PLAN/APPLY shapes are distinct from build and flash.
    assert journey.preflight["data"]["analysis"]["blockers"] == []
    assert journey.preflight["data"]["planReadiness"]["status"] == (
        "ready-for-plan"
    )
    assert journey.planned["data"]["planId"] == journey.applied["data"]["planId"]
    assert journey.applied["data"]["outputRoot"] == str(journey.destination)
    for data in (journey.planned["data"], journey.applied["data"]):
        assert data["built"] is False
        assert data["flashed"] is False
    assert journey.planned["data"]["configured"] is False
    assert journey.applied["data"]["configured"] is True

    # The complete prepared tree retains licenses, unlisted resources and
    # unselected sources byte-for-byte, and overlays only reviewed copies.
    for relative, expected in (
        ("LICENSE", LICENSE_TEXT.encode("utf-8")),
        ("Assets/logo.bin", BINARY_RESOURCE),
        ("Legacy/notes.c", UNLISTED_SOURCE_TEXT.encode("utf-8")),
    ):
        assert (journey.prepared / relative).read_bytes() == expected
        assert (journey.destination / relative).read_bytes() == expected
    prepared_main = (journey.prepared / "Main" / "main.c").read_bytes()
    prepared_header = (journey.prepared / "Board" / "board_layout.h").read_bytes()
    prepared_main.decode("utf-8", "strict")
    prepared_header.decode("utf-8", "strict")
    assert RUNTIME_LITERAL.encode("ascii") in prepared_main
    assert (journey.destination / "Board" / "board_layout.h").read_bytes() == (
        prepared_header
    )

    # The existing comment helper reviewed valid authored GBK comments only;
    # no lossy replacement or confirmation was needed.  The GBK WFI source is
    # part of the reviewed selection, so its explicit normal-return intent can
    # be analyzed as UTF-8.
    assert journey.preview_payload["mode"] == "strict"
    assert journey.preview_payload["lossyFiles"] == []
    assert journey.preview_payload["totalReplacementCount"] == 0
    assert journey.copy_payload["copyOnly"] is True
    assert journey.copy_payload["notAProject"] is True
    assert journey.copy_manifest["confirmedFiles"] == []
    reviewed = {entry["path"] for entry in journey.copy_manifest["files"]}
    assert reviewed == {"Main/main.c", "Board/board_layout.h", WFI_SOURCE}
    prepared_wfi = (journey.prepared / WFI_SOURCE).read_bytes()
    prepared_wfi.decode("utf-8", "strict")
    assert prepared_wfi != WFI_TEXT.encode("gbk")
    assert "等待中断".encode("utf-8") in prepared_wfi

    # The reviewed conversion is bound into the public delivery report.
    assert journey.report["schemaVersion"] == 2
    assert journey.report["extraRegions"] == [EXTRA_SRAM2]
    manifest = json.loads(
        (journey.destination / ".stm32-project.json").read_text(encoding="utf-8")
    )
    assert manifest["memory"]["layout"] == MAIN_RAM_LAYOUT
    assert manifest["memory"]["extraRegions"] == [EXTRA_SRAM2]
    assert [region["name"] for region in manifest["memory"]["regions"]] == [
        "IROM1",
        "IRAM1",
        "IRAM2",
    ]
    assert manifest["debug"]["backend"] == "pyocd"
    assert manifest["debug"]["target"] == DEBUG_TARGET
    merges = journey.report["includeMerges"]
    assert len(merges) == 1
    assert merges[0]["scope"] == "group"
    assert merges[0]["owner"] == "Main"
    assert merges[0]["path"] == "Board"
    assert merges[0]["decision"] == "added"
    assert merges[0]["inventoryFiles"] == 1
    assert len(merges[0]["inventorySha256"]) == 64
    fixed = journey.report["fixedSections"]
    assert any(
        entry["address"] == FIXED_ADDRESS
        and entry["symbol"] == "fixed_buffer"
        and entry["sourcePath"] == "Main/main.c"
        and entry["section"] == ".stm32tk.abs.68000010"
        for entry in fixed
    ), fixed
    delivered_wfi = (journey.destination / WFI_SOURCE).read_bytes()
    (wfi_entry,) = journey.report["wfiReturns"]
    assert set(wfi_entry) == {
        "path",
        "function",
        "sourceSha256",
        "convertedSha256",
        "requestedBehavior",
        "binaryEquivalent",
    }
    assert wfi_entry["path"] == WFI_SOURCE
    assert wfi_entry["function"] == "WFI_SET"
    assert wfi_entry["requestedBehavior"] == "normal-return"
    assert wfi_entry["binaryEquivalent"] is False
    # Both digests are proven by independently hashing the actual fixture
    # bytes (the reviewed UTF-8 source and the delivered conversion), never by
    # comparing a returned value with itself.
    assert wfi_entry["sourceSha256"] == sha256_bytes(prepared_wfi)
    assert wfi_entry["convertedSha256"] == sha256_bytes(delivered_wfi)
    assert wfi_entry["sourceSha256"] != wfi_entry["convertedSha256"]

    delivered_main = (journey.destination / "Main" / "main.c").read_bytes()
    # The supported rewrites replaced both authored ARMCC forms with GNU C.
    assert b"__align(" not in delivered_main
    assert b"at(0x68000000" not in delivered_main
    assert b".stm32tk.abs.68000010" in delivered_main
    assert b"fixed_buffer" in delivered_main
    assert b"aligned_runtime" in delivered_main
    assert b"WFI_SET();" in delivered_main
    # The selected WFI wrapper is ordinary C now.
    assert b"__asm void" not in delivered_wfi
    assert b'__asm volatile ("wfi" ::: "memory");' in delivered_wfi

    # The delivered build inputs never reference the source or prepared tree.
    _assert_no_reference(
        journey.destination, (journey.source, journey.prepared)
    )

    # Real GCC performed both builds with the verified installed compiler.
    gcc, _cmake, _ninja = journey.toolchain
    for cache_text in (journey.first_cache, journey.second_cache):
        normalized = os.path.normcase(cache_text.replace("/", os.sep))
        assert "arm-none-eabi-gcc" in normalized
        assert os.path.normcase(str(Path(gcc).parent)) in normalized

    # Actual ELF/MAP placement, not a synthesized image.
    _assert_flash_confined(journey.first_elf)
    _assert_flash_confined(journey.second_elf)
    _assert_fixed_placement(journey.first_elf)
    _assert_fixed_placement(journey.second_elf)
    for map_data in (journey.first_map, journey.second_map):
        text = map_data.decode("utf-8", "replace")
        assert "fixed_buffer" in text
        assert "aligned_runtime" in text
        assert "WFI_SET" in text
        assert "68000010" in text.lower()

    # The relocated output-only rebuild had no source/prepared access and no
    # carried build cache; it produced a fresh, current identity.
    assert (journey.relocated / "build").is_dir()
    assert journey.second_identity["schemaVersion"] == SNAPSHOT_IDENTITY_SCHEMA_VERSION
    assert journey.second_identity["gitHead"] is None
    assert journey.second_identity["gitDirty"] is None
    assert journey.second_identity["sourceBaseline"] == (
        SOURCE_BASELINE_INPUT_SNAPSHOT
    )
    _assert_no_reference(
        journey.relocated,
        (journey.source, journey.prepared, journey.destination),
    )
    # The original and prepared fixture trees still exist after relocation.
    assert journey.source.is_dir() and journey.prepared.is_dir()


def _write_fixture_tree(root: Path, files: dict[str, bytes]) -> None:
    for relative, data in files.items():
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@pytest.mark.parametrize("git_form", ["directory", "worktree-pointer"])
def test_prepare_complete_project_excludes_git_metadata_only(
    tmp_path: Path, git_form: str
) -> None:
    """The complete-copy step omits ``.git`` but keeps every project file.

    This is fixture-only: a synthetic ``.git`` directory (with nested objects)
    or a synthetic worktree ``.git`` pointer file is written below ``tmp_path``.
    No real repository metadata is read or modified.
    """

    source = tmp_path / "source"
    project_files = {
        "Main/main.c": b"int main(void) { return 0; }\n",
        "README.md": b"synthetic fixture\n",
    }
    _write_fixture_tree(source, project_files)
    if git_form == "directory":
        _write_fixture_tree(
            source,
            {
                ".git/HEAD": b"ref: refs/heads/main\n",
                ".git/objects/ab/cdef0123": b"object bytes\n",
            },
        )
    else:
        (source / ".git").write_bytes(
            b"gitdir: ../elsewhere/.git/worktrees/source\n"
        )

    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    (copy_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    prepared = tmp_path / "prepared"

    inventory = prepare_complete_project(
        source, copy_dir, {"planId": "fixture", "files": []}, prepared
    )

    assert not (prepared / ".git").exists()
    assert not any(".git" in relative.split("/") for relative in inventory)
    assert inventory == {
        relative: sha256_bytes(data) for relative, data in project_files.items()
    }
    for relative, data in project_files.items():
        assert prepared.joinpath(*relative.split("/")).read_bytes() == data


# ---------------------------------------------------------------------------
# step 3: normal managed flash route with a deterministic simulated backend
# ---------------------------------------------------------------------------


def _set_backend_env(
    monkeypatch, log_path: Path, mode: str = "ok"
) -> Path:
    monkeypatch.setenv(SIM_LOG_ENV, str(log_path))
    monkeypatch.setenv(SIM_MODE_ENV, mode)
    return log_path


def test_managed_simulated_flash_programs_and_reads_back(
    journey, tmp_path: Path, monkeypatch
) -> None:
    build_id, elf_sha = _flash_pins(journey.second_identity)
    log_path = _set_backend_env(monkeypatch, tmp_path / "probe-success.log")
    outcome: FlashOutcome = run_managed_flash(
        journey.relocated,
        tmp_path / "data-success",
        "flash-success",
        build_id=build_id,
        elf_sha256=elf_sha,
    )

    assert outcome.result.ok is True, outcome.result.to_dict()
    assert outcome.result.operation == "stm32_flash"
    details = outcome.result.to_dict()["details"]
    assert details["postFlash"] == {
        "targetState": "unknown",
        "runVerified": False,
    }
    assert details["flashOptions"]["automaticRetry"] is False
    names = event_names(list(outcome.events))
    assert names.count("flash_elf") == 1
    assert names.count("open_attach") == 1
    assert "flash_file" not in names
    assert "flash_imported_elf" not in names
    assert names.index("flash_elf") < names.index("read_memory")

    segments = pt_load_segments(journey.second_elf)
    expected_bytes = sum(len(payload) for _address, payload in segments)
    assert names.count("program_segment") == len(segments)
    data = outcome.result.to_dict()["data"]
    assert data["verifiedBytes"] == expected_bytes > 0
    assert data["backendBytesProgrammed"] == expected_bytes > 0
    assert data["backendSectorsProgrammed"] == len(segments)
    assert data["elfSha256"] == elf_sha
    assert data["buildId"] == build_id
    assert "importId" not in data
    assert "sourceSha256" not in data

    receipt = json.loads(outcome.receipt_path.read_text(encoding="utf-8"))
    assert receipt["schemaVersion"] == SNAPSHOT_IDENTITY_SCHEMA_VERSION
    assert receipt["status"] == "success"
    assert receipt["code"] == "OK"
    assert receipt["buildId"] == journey.second_identity["buildId"]
    assert receipt["elfSha256"] == journey.second_identity["elfSha256"]
    assert receipt["elfSize"] == journey.second_identity["elfSize"]
    assert receipt["elfPath"] == journey.second_identity["elfPath"]
    assert receipt["inputSnapshotSha256"] == (
        journey.second_identity["inputSnapshotSha256"]
    )
    assert receipt["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert receipt["gitEvidence"] == journey.second_identity["gitEvidence"]
    assert receipt["gitHead"] is None and receipt["gitDirty"] is None
    assert receipt["targetDevice"] == journey.second_identity["targetDevice"]
    assert receipt["debugTarget"] == DEBUG_TARGET
    assert receipt["probeId"] == PROBE_ID
    assert receipt["sessionId"] == "flash-success"
    assert isinstance(receipt["workspaceId"], str) and receipt["workspaceId"]
    assert receipt["verifiedBytes"] == expected_bytes
    assert receipt["backendBytesProgrammed"] == expected_bytes
    assert receipt["backendSectorsProgrammed"] == len(segments)
    assert receipt["operationLevel"] == "modify"
    assert receipt["authorized"] is True
    assert "importId" not in receipt
    assert "0" * 40 not in json.dumps(receipt)
    # No imported-firmware detour occurred at the backend either.
    assert all(
        event.get("event") != "flash_imported_elf" for event in outcome.events
    )
    # Owned cleanup really ran after the verified readback: the simulated
    # backend was closed last, and the real lease manager recorded that the
    # probe lease was released (the existing tested probe.lock contract).
    assert names.count("close") >= 1
    assert names[-1] == "close"
    leases = sorted((tmp_path / "data-success").rglob("probe.lock"))
    assert leases, "no probe lease record was written"
    states = {
        json.loads(path.read_text(encoding="utf-8")).get("state")
        for path in leases
    }
    assert states == {"released"}


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unauthorized", "AUTHORIZATION_REQUIRED"),
        ("changed-source", "FIRMWARE_INPUT_CHANGED"),
        ("changed-header", "FIRMWARE_INPUT_CHANGED"),
        ("changed-elf", "FIRMWARE_INPUT_CHANGED"),
        ("changed-model", "FIRMWARE_INPUT_CHANGED"),
        ("wrong-target", "FIRMWARE_IDENTITY_MISMATCH"),
        ("wrong-build-pin", "FLASH_PLAN_CHANGED"),
        ("wrong-elf-pin", "FLASH_PLAN_CHANGED"),
    ],
)
def test_rejected_inputs_never_program(
    journey, tmp_path: Path, monkeypatch, case: str, expected_code: str
) -> None:
    build_id, elf_sha = _flash_pins(journey.second_identity)
    receipt_before = (
        journey.relocated / "artifacts" / "migration" / "flash-result.json"
    )
    previous_receipt = (
        receipt_before.read_bytes() if receipt_before.is_file() else None
    )
    log_path = _set_backend_env(monkeypatch, tmp_path / f"probe-{case}.log")

    authorized = case != "unauthorized"
    extra: dict[str, object] = {}
    restore: tuple[Path, bytes] | None = None

    if case == "changed-source":
        target = journey.relocated / "Main" / "main.c"
        original = target.read_bytes()
        target.write_bytes(original + b"\n/* concurrent edit */\n")
        restore = (target, original)
    elif case == "changed-header":
        target = journey.relocated / "Board" / "board_layout.h"
        original = target.read_bytes()
        target.write_bytes(original + b"\n/* concurrent edit */\n")
        restore = (target, original)
    elif case == "changed-elf":
        target = journey.relocated.joinpath(
            *str(journey.second_identity["elfPath"]).split("/")
        )
        original = target.read_bytes()
        target.write_bytes(original + b"\x00")
        restore = (target, original)
    elif case == "changed-model":
        # Configuration drift after the admitted build changes the declared
        # input snapshot, so the current firmware is no longer fresh.
        target = journey.relocated / ".stm32-project.json"
        original = target.read_bytes()
        document = json.loads(original.decode("utf-8"))
        document["build"]["defines"] = [
            *document["build"]["defines"],
            "STM32TK_MODEL_DRIFT",
        ]
        target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        assert (
            "STM32TK_MODEL_DRIFT"
            in load_project_model(journey.relocated).build.defines
        )
        restore = (target, original)
    elif case == "wrong-target":
        # A manifest that no longer describes the admitted firmware target is
        # refused as an identity mismatch before any probe effect.
        target = journey.relocated / ".stm32-project.json"
        original = target.read_bytes()
        document = json.loads(original.decode("utf-8"))
        document["target"]["device"] = "STM32F407VGTx"
        target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        assert load_project_model(journey.relocated).target.device == (
            "STM32F407VGTx"
        )
        restore = (target, original)
    elif case == "wrong-build-pin":
        extra["build_id"] = "0" * 64
    elif case == "wrong-elf-pin":
        extra["elf_sha256"] = "0" * 64

    try:
        outcome = run_managed_flash(
            journey.relocated,
            tmp_path / f"data-{case}",
            f"flash-{case}",
            build_id=extra.get("build_id", build_id),
            elf_sha256=extra.get("elf_sha256", elf_sha),
            authorized=authorized,
        )
        assert outcome.result.ok is False, outcome.result.to_dict()
        assert outcome.result.code == expected_code
        names = event_names(list(outcome.events))
        assert "flash_elf" not in names
        assert "flash_imported_elf" not in names
        assert "flash_file" not in names
        # A rejected request has no programming or receipt effect.
        if previous_receipt is None:
            assert not outcome.receipt_path.exists()
        else:
            assert outcome.receipt_path.read_bytes() == previous_receipt
    finally:
        if restore is not None:
            target, original = restore
            target.write_bytes(original)
            assert target.read_bytes() == original
            assert sha256_bytes(target.read_bytes()) == sha256_bytes(original)


def test_readback_mismatch_fails_once_without_retry(
    journey, tmp_path: Path, monkeypatch
) -> None:
    build_id, elf_sha = _flash_pins(journey.second_identity)
    log_path = _set_backend_env(
        monkeypatch, tmp_path / "probe-mismatch.log", mode="mismatch"
    )
    outcome = run_managed_flash(
        journey.relocated,
        tmp_path / "data-mismatch",
        "flash-mismatch",
        build_id=build_id,
        elf_sha256=elf_sha,
    )

    assert outcome.result.ok is False
    assert outcome.result.code == "FLASH_VERIFY_FAILED"
    details = outcome.result.to_dict()["details"]
    first_address = min(
        address for address, _payload in pt_load_segments(journey.second_elf)
    )
    assert details["address"] == first_address
    assert details["length"] > 0
    assert "recoverySuggestion" not in details
    names = event_names(list(outcome.events))
    assert names.count("flash_elf") == 1  # exactly one program, no auto retry
    assert names.count("open_attach") == 1
    assert names.count("read_memory") >= 1
    assert "flash_imported_elf" not in names
    assert "flash_file" not in names
    # The stale success receipt was removed before programming and no new
    # receipt was published for the failed verification.
    assert not outcome.receipt_path.exists()
    assert read_probe_log(log_path) == list(outcome.events)
    # A failed verification still performs owned cleanup after the single
    # attempt: the backend is closed and the probe lease is released.
    assert names[-1] == "close"
    leases = sorted((tmp_path / "data-mismatch").rglob("probe.lock"))
    assert leases, "no probe lease record was written"
    assert {
        json.loads(path.read_text(encoding="utf-8")).get("state")
        for path in leases
    } == {"released"}
