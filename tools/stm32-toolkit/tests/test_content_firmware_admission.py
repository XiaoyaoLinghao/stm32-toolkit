"""Content-identity firmware admission for managed flash, debug and handoff.

These regressions cover the GCC content-identity slice A contract: a firmware
identity is admitted from its declared input snapshot, configuration, target
and exact ELF/MAP bytes.  Optional Git metadata is recorded truthfully but is
never an eligibility gate, and current Git availability/HEAD/dirty state never
changes an unchanged build's freshness.  Schema-1 and schema-2 records stay
strictly decoded under their own rules; malformed or cross-schema evidence,
changed inputs/artifacts, mixed provenance forms and malformed snapshot flash
receipts are refused before any probe effect.

Every probe is a recording/offline fake; no hardware is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.build.identity import (
    GitUnavailableEvidence,
    atomic_write_json,
    build_identity_document,
    compute_build_id,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_elf,
)
from stm32_toolkit.build.model import (
    BUILD_GIT_INVALID,
    SNAPSHOT_IDENTITY_SCHEMA_VERSION,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
)
from stm32_toolkit.build.runner import build_result_document
from stm32_toolkit.debug.firmware import bind_debug_firmware
from stm32_toolkit.debug.model import (
    DebugBindingRequest,
    identity_matches_provenance,
)
from stm32_toolkit.probe import handoff as handoff_mod
from stm32_toolkit.probe.flash import (
    FreshFirmwareFacts,
    flash_firmware,
    load_fresh_firmware_facts,
)
from stm32_toolkit.probe.handoff import (
    DebugHandoffRequest,
    _FLASH_FIELDS,
    _flash_mismatch_fields,
    _load_flash_result,
    begin_debug_handoff,
)
from stm32_toolkit.project_model import load_project_model

from test_build_runner import build_map_text, git, prepare_project
from test_debug_firmware import BindingClient, _model_binding
from test_debug_handoff import FakeClient, FakeSupervisor
from test_flash import (
    RecordingFlashClient,
    _elf_with_flash_segment,
    _request,
)

SNAPSHOT_EVIDENCE = {
    "status": "unavailable",
    "code": BUILD_GIT_INVALID,
    "rule": "head",
}
_FLASH_SNAPSHOT_FIELDS = handoff_mod._FLASH_SNAPSHOT_FIELDS
_IDENTITY_REL = "build/arm-debug/firmware-identity.json"
_RESULT_REL = "artifacts/migration/build-result.json"
_FLASH_REL = "artifacts/migration/flash-result.json"
_ARTIFACT_PATHS = (
    "artifacts/migration/build.log",
    _RESULT_REL,
    _IDENTITY_REL,
    "build/arm-debug/firmware.elf",
    "build/arm-debug/firmware.map",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_snapshot_evidence(root: Path) -> tuple[dict, bytes, bytes]:
    """Publish one coherent schema-2 success pair with a programmable ELF."""
    model = load_project_model(root)
    snapshot = snapshot_project_inputs(model)
    elf_data = _elf_with_flash_segment()
    map_data = build_map_text(
        sections=(
            (".isr_vector", 0x08000000, 0x40, None),
            (".text", 0x08000040, 0x100, None),
        )
    ).encode("utf-8")
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    map_path = root / "build" / "arm-debug" / "firmware.map"
    elf_path.parent.mkdir(parents=True, exist_ok=True)
    elf_path.write_bytes(elf_data)
    map_path.write_bytes(map_data)
    elf = validate_elf(elf_path, model)
    identity = build_identity_document(
        model=model,
        preset="arm-debug",
        snapshot=snapshot,
        git_unavailable=GitUnavailableEvidence(rule="head"),
        elf=elf,
        elf_size=len(elf_data),
        elf_sha256=_sha256(elf_data),
        map_size=len(map_data),
        map_sha256=_sha256(map_data),
        built_at_utc=utc_now_rfc3339(),
    )
    atomic_write_json(root / _IDENTITY_REL, identity)
    (root / "artifacts" / "migration").mkdir(parents=True, exist_ok=True)
    result = build_result_document(
        status="success",
        stage="",
        code="OK",
        build_id=str(identity["buildId"]),
        git_head=None,
        git_dirty=None,
        input_snapshot_sha256=str(identity["inputSnapshotSha256"]),
        target_device=str(identity["targetDevice"]),
        preset="arm-debug",
        started_at_utc=utc_now_rfc3339(),
        finished_at_utc=utc_now_rfc3339(),
        duration_ms=1,
        artifacts=[{"path": path} for path in _ARTIFACT_PATHS],
        memory=[],
        warnings=[],
        schema_version=SNAPSHOT_IDENTITY_SCHEMA_VERSION,
        source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
        git_evidence=SNAPSHOT_EVIDENCE,
    )
    atomic_write_json(root / _RESULT_REL, result)
    (root / "artifacts" / "migration" / "build.log").write_text(
        "[stage:build]\nexitCode=0\n", encoding="utf-8"
    )
    return identity, elf_data, map_data


@pytest.fixture
def snapshot_env(tmp_path: Path):
    root = prepare_project(tmp_path / "project", git_repo=False)
    identity, elf_data, map_data = _write_snapshot_evidence(root)
    return root, identity, elf_data, map_data


def _segment_image(elf_data: bytes) -> bytes:
    """The single PT_LOAD payload installed by the ELF fixture (vector+text)."""
    return elf_data[84 : 84 + 320]


# ---------------------------------------------------------------------------
# no Git / unborn HEAD snapshot admission
# ---------------------------------------------------------------------------


def test_no_git_snapshot_is_admitted_and_flashed(snapshot_env):
    root, identity, elf_data, _map_data = snapshot_env
    image = _segment_image(elf_data)
    client = RecordingFlashClient(image)

    flashed = asyncio.run(flash_firmware(_request(root, identity), client))

    assert flashed.ok is True, flashed.to_dict()
    assert [event[0] for event in client.events] == ["attach", "program", "read"]
    receipt = json.loads((root / _FLASH_REL).read_text(encoding="utf-8"))
    assert receipt["schemaVersion"] == 2
    assert set(receipt) == _FLASH_SNAPSHOT_FIELDS
    assert receipt["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert receipt["gitHead"] is None
    assert receipt["gitDirty"] is None
    assert receipt["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert "0" * 40 not in json.dumps(receipt)

    facts = load_fresh_firmware_facts(root)
    assert facts.git_commit is None
    assert facts.git_dirty is None
    assert facts.source_baseline == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert facts.git_evidence == SNAPSHOT_EVIDENCE


def test_unborn_repository_does_not_change_snapshot_admission(tmp_path: Path):
    root = prepare_project(tmp_path / "project", git_repo=False)
    git("init", "-q", cwd=root)  # unborn HEAD: no commit exists
    identity, elf_data, _map_data = _write_snapshot_evidence(root)
    assert identity["schemaVersion"] == 2
    assert identity["gitHead"] is None

    client = RecordingFlashClient(_segment_image(elf_data))
    flashed = asyncio.run(flash_firmware(_request(root, identity), client))

    assert flashed.ok is True, flashed.to_dict()
    receipt = json.loads((root / _FLASH_REL).read_text(encoding="utf-8"))
    assert receipt["gitHead"] is None
    assert receipt["gitDirty"] is None


# ---------------------------------------------------------------------------
# changed declared inputs and artifacts
# ---------------------------------------------------------------------------


def _change_source(root: Path) -> None:
    (root / "Src" / "main.c").write_text(
        "int main(void) { return 3; }\n", encoding="utf-8"
    )


def _change_header(root: Path) -> None:
    (root / "Src" / "local.h").write_text("extern int local;\n", encoding="utf-8")


def _change_model(root: Path) -> None:
    manifest = root / ".stm32-project.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["build"]["defines"] = ["CHANGED_CONFIGURATION"]
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _change_elf(root: Path) -> None:
    path = root / "build" / "arm-debug" / "firmware.elf"
    path.write_bytes(path.read_bytes() + b"\x00")


def _change_map(root: Path) -> None:
    path = root / "build" / "arm-debug" / "firmware.map"
    path.write_bytes(path.read_bytes() + b"\n")


@pytest.mark.parametrize(
    ("mutation", "code", "details"),
    [
        (
            _change_source,
            "FIRMWARE_INPUT_CHANGED",
            {"field": "inputSnapshotSha256", "rule": "current"},
        ),
        (
            _change_header,
            "FIRMWARE_INPUT_CHANGED",
            {"field": "inputSnapshotSha256", "rule": "current"},
        ),
        (
            _change_model,
            "FIRMWARE_INPUT_CHANGED",
            {"field": "inputSnapshotSha256", "rule": "current"},
        ),
        (
            _change_elf,
            "FIRMWARE_INPUT_CHANGED",
            {"field": "elfSha256", "rule": "current"},
        ),
        (
            _change_map,
            "FIRMWARE_INPUT_CHANGED",
            {"field": "mapSha256", "rule": "current"},
        ),
    ],
    ids=["source", "header", "model", "elf", "map"],
)
def test_changed_inputs_or_artifacts_are_refused_before_any_effect(
    snapshot_env, mutation, code: str, details: dict[str, str]
):
    root, identity, elf_data, _map_data = snapshot_env
    mutation(root)
    client = RecordingFlashClient(_segment_image(elf_data))

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == code
    assert result.details == details
    assert client.events == []


# ---------------------------------------------------------------------------
# malformed / cross-schema identity and result evidence
# ---------------------------------------------------------------------------


def _rewrite_identity(root: Path, changes: dict[str, object]) -> None:
    path = root / _IDENTITY_REL
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(changes)
    document["buildId"] = compute_build_id(document)
    atomic_write_json(path, document)


def _rewrite_result(root: Path, changes: dict[str, object]) -> None:
    path = root / _RESULT_REL
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(changes)
    atomic_write_json(path, document)


@pytest.mark.parametrize(
    ("mutate", "target_rel"),
    [
        (lambda root: _rewrite_identity(root, {"gitHead": "a" * 40}), _IDENTITY_REL),
        (
            lambda root: _rewrite_identity(root, {"sourceBaseline": None}),
            _IDENTITY_REL,
        ),
        (
            lambda root: _rewrite_identity(
                root, {"gitEvidence": {**SNAPSHOT_EVIDENCE, "rule": []}}
            ),
            _IDENTITY_REL,
        ),
        (lambda root: _rewrite_result(root, {"gitDirty": False}), _RESULT_REL),
        (lambda root: _rewrite_result(root, {"schemaVersion": 1}), _RESULT_REL),
        (lambda root: _rewrite_result(root, {"futureField": 1}), _RESULT_REL),
    ],
    ids=[
        "identity-forged-head",
        "identity-missing-baseline",
        "identity-malformed-evidence",
        "record-forged-dirty",
        "record-cross-schema",
        "record-extra-field",
    ],
)
def test_malformed_or_cross_schema_evidence_is_refused_before_effect(
    snapshot_env, mutate, target_rel: str
):
    root, identity, elf_data, _map_data = snapshot_env
    mutate(root)
    client = RecordingFlashClient(_segment_image(elf_data))

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_EVIDENCE_INVALID"
    assert result.details["path"] == target_rel
    assert client.events == []


# ---------------------------------------------------------------------------
# snapshot flash receipt forms
# ---------------------------------------------------------------------------


def _flash_snapshot(snapshot_env) -> tuple[Path, dict, bytes]:
    root, identity, elf_data, _map_data = snapshot_env
    client = RecordingFlashClient(_segment_image(elf_data))
    result = asyncio.run(flash_firmware(_request(root, identity), client))
    assert result.ok is True, result.to_dict()
    return root, identity, elf_data


def _mutate_receipt(root: Path, mutate) -> dict:
    path = root / _FLASH_REL
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    atomic_write_json(path, document)
    return document


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda document: document.pop("gitEvidence"), id="missing-evidence"
        ),
        pytest.param(lambda document: document.pop("sourceBaseline"), id="missing-baseline"),
        pytest.param(
            lambda document: document.__setitem__("gitDirty", False), id="fake-clean"
        ),
        pytest.param(
            lambda document: document.__setitem__("schemaVersion", 1),
            id="cross-schema",
        ),
        pytest.param(
            lambda document: document.__setitem__("schemaVersion", True),
            id="bool-schema",
        ),
        pytest.param(
            lambda document: document["gitEvidence"].__setitem__("rule", []),
            id="malformed-evidence",
        ),
        pytest.param(
            lambda document: document.__setitem__("futureField", 1), id="extra-field"
        ),
    ],
)
def test_snapshot_receipt_reader_is_a_strict_closed_set(snapshot_env, mutate):
    root, _identity, _elf_data = _flash_snapshot(snapshot_env)
    _mutate_receipt(root, mutate)

    with pytest.raises(handoff_mod._HandoffFailure) as error:
        _load_flash_result(root)

    assert error.value.code == "HANDOFF_FLASH_REQUIRED"


def test_snapshot_receipt_matches_its_own_content_provenance(snapshot_env):
    root, identity, elf_data = _flash_snapshot(snapshot_env)
    receipt = _load_flash_result(root)
    firmware = SimpleNamespace(
        identity=identity,
        model=SimpleNamespace(target=SimpleNamespace(device="STM32F407VGTx")),
        segments=(SimpleNamespace(data=_segment_image(elf_data)),),
        elf_data=elf_data,
        elf_path="build/arm-debug/firmware.elf",
    )

    def mismatches(document: dict) -> tuple[str, ...]:
        return _flash_mismatch_fields(
            document,
            firmware,
            probe="probe-123",
            workspace="workspace-a",
            session="session-a",
            target="stm32f407vg",
        )

    assert mismatches(receipt) == ()
    assert "gitEvidence" in mismatches(
        _mutate_receipt(
            root,
            lambda document: document["gitEvidence"].__setitem__("rule", "status"),
        )
    )
    assert "sourceBaseline" in mismatches(
        _mutate_receipt(
            root, lambda document: document.__setitem__("sourceBaseline", "git")
        )
    )


def _downgrade_receipt(
    root: Path, *, keep_legacy_git: bool
) -> None:
    """Turn a snapshot receipt into the legacy closed set.

    ``keep_legacy_git=False`` leaves the snapshot nulls (a malformed legacy
    receipt).  ``True`` fills a syntactically valid real head/boolean so only
    the receipt-versus-identity form comparison can refuse it.
    """

    def mutate(document: dict) -> None:
        document["schemaVersion"] = 1
        document.pop("sourceBaseline")
        document.pop("gitEvidence")
        if keep_legacy_git:
            document["gitHead"] = "a" * 40
            document["gitDirty"] = False

    _mutate_receipt(root, mutate)


def test_downgraded_stripped_snapshot_receipt_is_malformed_legacy(
    snapshot_env,
):
    root, _identity, _elf_data = _flash_snapshot(snapshot_env)
    _downgrade_receipt(root, keep_legacy_git=False)

    with pytest.raises(handoff_mod._HandoffFailure) as error:
        _load_flash_result(root)

    assert error.value.code == "HANDOFF_FLASH_REQUIRED"


def test_downgraded_snapshot_receipt_is_refused_before_public_probe_effects(
    snapshot_env, tmp_path: Path
):
    root, identity, elf_data = _flash_snapshot(snapshot_env)
    image = _segment_image(elf_data)
    _downgrade_receipt(root, keep_legacy_git=True)
    # The reader itself accepts this as a well-formed legacy receipt; only the
    # admitted firmware's own form can prove it was downgraded.
    assert set(_load_flash_result(root)) == _FLASH_FIELDS

    binding_client = BindingClient(image)
    bound = asyncio.run(
        bind_debug_firmware(
            DebugBindingRequest(
                project_root=root,
                probe_id="probe-123",
                target="stm32f407vg",
                workspace_id="workspace-a",
                observation_session_id="observe-session",
                lease_id="lease-observe",
                expected_build_id=str(identity["buildId"]),
                expected_elf_sha256=str(identity["elfSha256"]),
            ),
            binding_client,
        )
    )
    assert bound.ok is False
    assert bound.code == "DEBUG_FLASH_MISMATCH"
    assert "schemaVersion" in bound.details["mismatchedFields"]
    assert binding_client.events == []

    session_root = tmp_path / "plugin-data" / "projects" / "workspace-a" / "session-a"
    supervisor = FakeSupervisor(root, session_root)
    handoff_client = FakeClient(supervisor.endpoint, image)
    handoff = asyncio.run(
        begin_debug_handoff(
            DebugHandoffRequest(
                project_root=root,
                expected_build_id=str(identity["buildId"]),
                expected_elf_sha256=str(identity["elfSha256"]),
                authorized=True,
            ),
            supervisor,
            handoff_client,
        )
    )
    assert handoff.ok is False
    assert handoff.code == "HANDOFF_FLASH_MISMATCH"
    assert handoff_client.events == []


def test_snapshot_flash_readback_hands_off_without_git(snapshot_env, tmp_path: Path):
    root, identity, elf_data = _flash_snapshot(snapshot_env)
    image = _segment_image(elf_data)
    session_root = tmp_path / "plugin-data" / "projects" / "workspace-a" / "session-a"
    supervisor = FakeSupervisor(root, session_root)
    client = FakeClient(supervisor.endpoint, image)
    request = DebugHandoffRequest(
        project_root=root,
        expected_build_id=str(identity["buildId"]),
        expected_elf_sha256=str(identity["elfSha256"]),
        authorized=True,
    )

    result = asyncio.run(begin_debug_handoff(request, supervisor, client))

    assert result.ok is True, result.to_dict()
    state = json.loads((session_root / "debug-handoff.json").read_text(encoding="utf-8"))
    assert state["buildId"] == identity["buildId"]
    assert state["elfSha256"] == identity["elfSha256"]
    assert any(event[0] == "read" for event in client.events)


# ---------------------------------------------------------------------------
# typed provenance and legacy serialization
# ---------------------------------------------------------------------------


def test_debug_binding_rejects_mixed_provenance_forms(tmp_path: Path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    legacy = _model_binding(project_root=root)
    legacy_document = legacy.to_dict()
    assert "sourceBaseline" not in legacy_document
    assert "gitEvidence" not in legacy_document
    assert legacy_document["gitHead"] == "4" * 40
    assert legacy_document["gitDirty"] is False

    with pytest.raises(ValueError):
        # Nullable Git fields without the explicit snapshot pair.
        _model_binding(project_root=root, git_head=None, git_dirty=None)
    with pytest.raises(ValueError):
        # A real Git pair cannot also claim the snapshot discriminator.
        _model_binding(
            project_root=root,
            source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
            git_evidence=SNAPSHOT_EVIDENCE,
        )
    with pytest.raises(ValueError):
        _model_binding(
            project_root=root,
            git_head=None,
            git_dirty=None,
            source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
            git_evidence={"status": "available", "code": BUILD_GIT_INVALID, "rule": "head"},
        )

    snapshot_binding = _model_binding(
        project_root=root,
        git_head=None,
        git_dirty=None,
        source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
        git_evidence=SNAPSHOT_EVIDENCE,
    )
    snapshot_document = snapshot_binding.to_dict()
    assert snapshot_document["gitHead"] is None
    assert snapshot_document["gitDirty"] is None
    assert snapshot_document["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert snapshot_document["gitEvidence"] == SNAPSHOT_EVIDENCE

    legacy_identity = {"gitHead": "4" * 40, "gitDirty": False}
    snapshot_identity = {
        "gitHead": None,
        "gitDirty": None,
        "sourceBaseline": SOURCE_BASELINE_INPUT_SNAPSHOT,
        "gitEvidence": SNAPSHOT_EVIDENCE,
    }
    assert identity_matches_provenance(legacy, legacy_identity) is True
    assert identity_matches_provenance(snapshot_binding, snapshot_identity) is True
    assert identity_matches_provenance(legacy, snapshot_identity) is False
    assert identity_matches_provenance(snapshot_binding, legacy_identity) is False


def test_snapshot_facts_reject_coerced_or_mixed_forms(tmp_path: Path):
    root = prepare_project(tmp_path / "project", git_repo=False)
    model = load_project_model(root)
    common = dict(
        model=model,
        elf_path="build/arm-debug/firmware.elf",
        elf_sha256="1" * 64,
        build_id="2" * 64,
        input_snapshot_sha256="3" * 64,
        target_device=model.target.device,
    )

    # The complete snapshot pair is the accepted nullable form.
    snapshot = FreshFirmwareFacts(
        **common,
        git_commit=None,
        git_dirty=None,
        source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
        git_evidence=SNAPSHOT_EVIDENCE,
    )
    assert snapshot.git_commit is None and snapshot.git_dirty is None
    with pytest.raises(ValueError):
        FreshFirmwareFacts(
            **common,
            git_commit="4" * 40,
            git_dirty=False,
            source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
            git_evidence=SNAPSHOT_EVIDENCE,
        )
    with pytest.raises(ValueError):
        FreshFirmwareFacts(
            **common,
            git_commit="4" * 40,
            git_dirty=False,
            git_evidence=SNAPSHOT_EVIDENCE,
        )
    legacy = FreshFirmwareFacts(
        **common, git_commit="4" * 40, git_dirty=False
    )
    assert legacy.source_baseline is None and legacy.git_evidence is None
