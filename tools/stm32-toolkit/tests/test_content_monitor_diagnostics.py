"""Snapshot provenance across continuation, Diagnostic and Monitor consumers.

Every case here uses the existing persisted software fixtures.  No hardware
transport is constructed, no source tree is patched into a Git repository, and
no reader or authorization seam is replaced.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    MonitorRunRef,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.acceptance.continuation import (
    authenticate_continuation,
    validate_continuation_reference,
)
import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
from stm32_toolkit.diagnostic_workflows import diagnostic_add_plan
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import EvidenceEnvelope, get_root
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.monitor_replay_contract import (
    canonical_physical_json_bytes,
    decode_physical_transcript_bytes,
    validate_physical_transcript,
    validate_run_reference,
)

import test_continuation_monitor as monitor_fixture
import test_risk_diagnostic_native_authority as native_authority_fixture
from test_acceptance_continuation import (
    SNAPSHOT_BASELINE,
    SNAPSHOT_EVIDENCE,
    prepare_pair,
)

_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024

#: Closed legacy replay-reference wire keys (schema 1).
_LEGACY_REPLAY_KEYS = frozenset(
    {
        "schema",
        "operation_id",
        "scenario_role",
        "execution_source",
        "physical_transport_evidence",
        "origin_workspace_id",
        "import_workspace_id",
        "logical_project_id",
        "origin_session_id",
        "projected_session_id",
        "origin_run_id",
        "projected_run_id",
        "target_device",
        "probe_id",
        "physical_target",
        "build_id",
        "elf_sha256",
        "input_snapshot_sha256",
        "git_head",
        "git_dirty",
        "flash_session_id",
        "lease_id",
        "dwarf_sha256",
        "svd_sha256",
        "group_id",
        "group_revision",
        "start_sequence",
        "end_sequence_exclusive",
        "start_captured_unix_ns",
        "end_captured_unix_ns_exclusive",
        "fixture_sha256",
        "projected_batch_sha256s",
        "transcript_evidence_id",
        "run_ref_sha256",
    }
)

#: Closed legacy physical-reference wire keys (schema 2).
_LEGACY_PHYSICAL_KEYS = (_LEGACY_REPLAY_KEYS - {"fixture_sha256"}) | {
    "source_record_sha256"
}

#: The optional snapshot pair that only the snapshot form serializes.
_PROVENANCE_KEYS = frozenset({"source_baseline", "git_evidence"})

_STATUS_EVIDENCE = {
    "status": "unavailable",
    "code": "BUILD_GIT_INVALID",
    "rule": "status",
}


def _content_monitor_replay_fixture() -> object:
    """Load the sibling Monitor producer/reader helpers by resolved path."""

    name = "_content_monitor_replay_fixture"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = (
        Path(__file__).resolve().parents[2]
        / "stm32-monitor"
        / "tests"
        / "test_content_monitor_replay.py"
    )
    assert path.is_file()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _replay_identity(reference: MonitorRunRef) -> SimpleNamespace:
    """Project one published replay reference into a downstream run identity."""

    return SimpleNamespace(
        workspace_id=reference.origin_workspace_id,
        project_id=reference.logical_project_id,
        session_id=reference.origin_session_id,
        build_id=reference.build_id,
        elf_sha256=reference.elf_sha256,
        target_device=reference.target_device,
        input_snapshot_sha256=reference.input_snapshot_sha256,
        git_commit=reference.git_head,
        git_dirty=reference.git_dirty,
        source_baseline=reference.source_baseline,
        git_evidence=reference.git_evidence,
    )


def _replay_reader_state(
    paths: object, evidence: EvidenceStore, project_id: object
) -> SimpleNamespace:
    """Supply the real store/paths a Diagnostic reader consumes."""

    return SimpleNamespace(
        evidence_store=evidence,
        workspace=paths,
        model=SimpleNamespace(logical_project_id=project_id),
    )


def _install_snapshot_pair_factory(
    monkeypatch: pytest.MonkeyPatch, captured: list[object]
) -> None:
    """Make the existing fixture helpers build one snapshot-provenance pair."""

    original = monitor_fixture.prepare_pair

    def factory(root: Path, patch: pytest.MonkeyPatch, **kwargs: object) -> object:
        kwargs.pop("snapshot_provenance", None)
        pair = original(root, patch, snapshot_provenance=True, **kwargs)
        captured.append(pair)
        return pair

    monkeypatch.setattr(monitor_fixture, "prepare_pair", factory)


def _assert_snapshot_identity(identity: object) -> None:
    assert getattr(identity, "git_commit") is None
    assert getattr(identity, "git_dirty") is None
    assert getattr(identity, "source_baseline") == SNAPSHOT_BASELINE
    assert dict(getattr(identity, "git_evidence")) == SNAPSHOT_EVIDENCE


def _republish_provenance_variant(
    evidence: EvidenceStore,
    reference_document: object,
    tmp_path: Path,
    variant: str,
) -> SimpleNamespace:
    """Republish one self-consistent changed-provenance reference graph.

    The original graph is left byte-identical.  The variant is written under a
    fresh operation id and carries recomputed artifact, envelope, reference and
    root hashes, so only the provenance binding distinguishes it from the
    linked TestRun that stays borrowed from the original pair.
    """

    assert variant in {"changed-rule", "legacy"}
    original = MonitorRunRefV2.from_value(reference_document)
    transcript_envelope = evidence.get_envelope(original.transcript_evidence_id)
    original_raw = evidence.read_artifact(
        transcript_envelope.artifacts[0], maximum_bytes=_MAX_EVIDENCE_BYTES
    )
    transcript = deepcopy(decode_physical_transcript_bytes(original_raw))
    assert validate_physical_transcript(transcript) == transcript
    operation_id = str(uuid4())

    binding = dict(transcript["binding"])
    if variant == "changed-rule":
        git_evidence = dict(binding["gitEvidence"])
        git_evidence["rule"] = "status"
        binding["gitEvidence"] = git_evidence
        identity = replace(
            transcript_envelope.identity, git_evidence=dict(_STATUS_EVIDENCE)
        )
    else:
        binding.pop("sourceBaseline")
        binding.pop("gitEvidence")
        binding["gitHead"] = "a" * 40
        binding["gitDirty"] = False
        identity = replace(
            transcript_envelope.identity,
            git_commit="a" * 40,
            git_dirty=False,
            source_baseline=None,
            git_evidence=None,
        )
    transcript["binding"] = binding
    for batch in transcript["batches"]:
        batch["binding"] = deepcopy(binding)
        batch["runId"] = operation_id

    transcript_raw = canonical_physical_json_bytes(transcript)
    transcript = validate_physical_transcript(
        decode_physical_transcript_bytes(transcript_raw)
    )
    transcript_path = tmp_path / f"{variant}-{operation_id}-transcript.json"
    transcript_path.write_bytes(transcript_raw)
    transcript_artifact = evidence.ingest_file(
        transcript_path,
        kind="monitor-physical-transcript",
        media_type="application/json",
    )
    source_digest = sha256(transcript_raw).hexdigest()
    assert transcript_artifact.sha256 == source_digest

    transcript_metadata = dict(transcript_envelope.metadata)
    transcript_metadata.update(
        {
            "operation_id": operation_id,
            "origin_run_id": operation_id,
            "projected_run_id": operation_id,
            "source_record_sha256": source_digest,
        }
    )
    variant_transcript = EvidenceEnvelope(
        identity=identity,
        operation=transcript_envelope.operation,
        produced_at_utc=transcript_envelope.produced_at_utc,
        parents=(),
        artifacts=(transcript_artifact,),
        metadata=transcript_metadata,
    )
    evidence.put_envelope(variant_transcript)

    payload = original.to_dict()
    payload.update(
        {
            "operation_id": operation_id,
            "origin_run_id": operation_id,
            "projected_run_id": operation_id,
            "source_record_sha256": source_digest,
            "transcript_evidence_id": str(variant_transcript.evidence_id),
            "projected_batch_sha256s": [
                sha256(canonical_physical_json_bytes(batch)).hexdigest()
                for batch in transcript["batches"]
            ],
            "run_ref_sha256": "0" * 64,
        }
    )
    if variant == "changed-rule":
        git_evidence = dict(payload["git_evidence"])
        git_evidence["rule"] = "status"
        payload["git_evidence"] = git_evidence
    else:
        payload.pop("source_baseline")
        payload.pop("git_evidence")
        payload["git_head"] = "a" * 40
        payload["git_dirty"] = False
    unsigned = {
        key: value for key, value in payload.items() if key != "run_ref_sha256"
    }
    payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    reference = MonitorRunRefV2.from_value(payload)
    assert validate_run_reference(reference.to_dict()) == reference.to_dict()

    reference_path = tmp_path / f"{variant}-{operation_id}-reference.json"
    reference_path.write_bytes(canonical_replay_json_bytes(reference.to_dict()))
    reference_artifact = evidence.ingest_file(
        reference_path, kind="monitor-run-ref", media_type="application/json"
    )
    reference_metadata = {
        "operation_id": operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "source_record_sha256": source_digest,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }
    variant_reference = EvidenceEnvelope(
        identity=identity,
        operation="monitor-run-ref",
        produced_at_utc=transcript_envelope.produced_at_utc,
        parents=(str(variant_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(variant_reference)
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run",
            root_id=operation_id,
            manifest_id=str(variant_transcript.evidence_id),
            metadata={
                "source_record_sha256": source_digest,
                "run_ref_sha256": reference.run_ref_sha256,
                "origin_workspace_id": reference.origin_workspace_id,
                "import_workspace_id": reference.import_workspace_id,
                "execution_source": "physical",
                "physical_transport_evidence": True,
            },
        ),
    )
    put_root(
        evidence,
        RootRecord(
            root_type="monitor-run-ref",
            root_id=operation_id,
            manifest_id=str(variant_reference.evidence_id),
            metadata=reference_metadata,
        ),
    )
    return SimpleNamespace(
        variant=variant,
        operation_id=operation_id,
        transcript=transcript,
        transcript_evidence_id=str(variant_transcript.evidence_id),
        reference=reference,
        reference_evidence_id=str(variant_reference.evidence_id),
    )


def test_snapshot_continuation_monitor_and_native_plan_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = prepare_pair(tmp_path, monkeypatch, snapshot_provenance=True)
    baseline = monitor_fixture._monitor_baseline(pair, tmp_path)

    # The fixture names a snapshot baseline instead of fabricating Git history.
    assert not (pair.project_root / ".git").exists()
    _assert_snapshot_identity(pair.before_identity)
    _assert_snapshot_identity(pair.after_identity)
    assert pair.repository.load(pair.failed_run_id).manifest.identity == pair.before_identity
    assert pair.repository.load(pair.fixed_run_id).manifest.identity == pair.after_identity

    # Both published Monitor references carry the same explicit pair.
    for reference in baseline.refs:
        assert reference.schema == "stm32-monitor-run-ref/2"
        assert reference.source_baseline == SNAPSHOT_BASELINE
        assert reference.git_head is None and reference.git_dirty is None
        assert dict(reference.git_evidence) == SNAPSHOT_EVIDENCE
        assert set(reference.to_dict()) == _LEGACY_PHYSICAL_KEYS | _PROVENANCE_KEYS

    analysis = baseline.publication.analysis_result
    assert analysis.schema == "stm32-monitor-analysis/2"
    assert analysis.quality == "VALID"
    assert analysis.changed is True

    association = authenticate_continuation(
        pair.evidence,
        pair.workspace.diagnostics_root,
        baseline.continuation_id,
        expected_workspace_id=pair.before_identity.workspace_id,
        expected_project_id=pair.before_identity.project_id,
        expected_session_id=pair.before_identity.session_id,
        expected_diagnostic_session_id=pair.diagnostic_session_id,
        expected_fixed_after_test_run_id=pair.fixed_run_id,
        expected_fixed_after_evidence_id=str(
            pair.fixed_physical.envelope.evidence_id
        ),
    )
    assert association.continuation_evidence_id == baseline.continuation_id
    assert association.envelope.identity == pair.before_identity
    assert association.before.manifest.identity == pair.before_identity
    assert association.after.manifest.identity == pair.after_identity
    assert association.proof.failed_before_evidence_id == str(
        pair.failed_physical.envelope.evidence_id
    )
    assert association.proof.fixed_after_evidence_id == str(
        pair.fixed_physical.envelope.evidence_id
    )
    assert (
        validate_continuation_reference(
            pair.evidence, association, baseline.analysis_envelope
        )
        is None
    )

    # A fresh store must re-authenticate the exact same identities and bytes.
    fresh_evidence = EvidenceStore(pair.evidence.root)
    fresh_association = authenticate_continuation(
        fresh_evidence,
        pair.workspace.diagnostics_root,
        baseline.continuation_id,
        expected_workspace_id=pair.before_identity.workspace_id,
        expected_project_id=pair.before_identity.project_id,
        expected_session_id=pair.before_identity.session_id,
    )
    assert fresh_association.before.manifest.identity == pair.before_identity
    assert fresh_association.after.manifest.identity == pair.after_identity
    assert (
        validate_continuation_reference(
            fresh_evidence, fresh_association, baseline.analysis_envelope
        )
        is None
    )
    analysis_payload = json.loads(
        fresh_evidence.read_artifact(
            baseline.analysis_envelope.artifacts[0],
            maximum_bytes=_MAX_EVIDENCE_BYTES,
        ).decode("utf-8")
    )
    assert analysis_payload["analysis_id"] == analysis.analysis_id
    assert (
        get_root(fresh_evidence, "monitor-analysis", analysis.analysis_id).manifest_id
        == str(baseline.analysis_envelope.evidence_id)
    )

    # Same-session native verification plan: append then rebuild from a fresh store.
    native = monitor_fixture._same_session_native_baseline(pair, tmp_path)
    plan = monitor_fixture._same_session_native_plan(pair, native)
    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)
    accepted = store.append(
        pair.diagnostic_session_id,
        monitor_fixture._verification_plan_event(pair, plan, "snapshot-native-plan"),
        expected_revision=pair.diagnostic_revision,
    )
    assert accepted.session.revision == pair.diagnostic_revision + 1
    fresh_store = DiagnosticStore(
        pair.workspace.diagnostics_root, EvidenceStore(pair.evidence.root)
    )
    loaded = fresh_store.load(pair.diagnostic_session_id)
    assert loaded.revision == pair.diagnostic_revision + 1
    assert loaded.verification_plans[-1].verification_plan_id == plan.verification_plan_id
    assert loaded.verification_plans[-1].continuation_evidence_id is None
    assert native.publication.analysis_result.quality == "VALID"


def test_public_physical_fact_snapshot_pair_replays_through_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The existing exhaustive physical-fact test also holds for snapshot pairs."""

    captured: list[object] = []
    _install_snapshot_pair_factory(monkeypatch, captured)

    monitor_fixture.test_fresh_failed_physical_monitor_fact_v2_persists_and_replays(
        tmp_path, monkeypatch
    )

    assert len(captured) == 1
    pair = captured[0]
    _assert_snapshot_identity(pair.before_identity)
    _assert_snapshot_identity(pair.after_identity)
    assert pair.repository.load(pair.failed_run_id).manifest.identity == pair.before_identity
    assert pair.repository.load(pair.fixed_run_id).manifest.identity == pair.after_identity
    assert not (pair.project_root / ".git").exists()


def test_replay_producer_and_diagnostic_reader_roundtrip(tmp_path: Path) -> None:
    helpers = _content_monitor_replay_fixture()

    paths = helpers._paths(tmp_path)
    evidence = helpers._evidence(paths)
    document = helpers._snapshot_document("failed-before")
    target = helpers._write_document(tmp_path, document, "snapshot.json")
    published = ingest_monitor_replay(
        paths, evidence, str(helpers.RUN_IDS["failed-before"]), target
    )

    assert type(published) is MonitorRunRef
    assert published.source_baseline == helpers.SOURCE_BASELINE
    assert published.git_head is None and published.git_dirty is None
    assert dict(published.git_evidence) == helpers.GIT_EVIDENCE
    assert set(published.to_dict()) == _LEGACY_REPLAY_KEYS | _PROVENANCE_KEYS

    envelope, reference, batches = diagnostic_workflows._read_transcript_parent(
        _replay_reader_state(paths, evidence, helpers.PROJECT_ID),
        evidence_id=published.transcript_evidence_id,
        run=SimpleNamespace(
            identity=_replay_identity(published), run_id=published.operation_id
        ),
        expected_role="failed-before",
    )
    assert str(envelope.evidence_id) == published.transcript_evidence_id
    assert reference["source_baseline"] == helpers.SOURCE_BASELINE
    assert reference["git_evidence"] == helpers.GIT_EVIDENCE
    assert reference["git_head"] is None and reference["git_dirty"] is None
    assert reference["run_ref_sha256"] == published.run_ref_sha256
    assert reference["transcript_evidence_id"] == published.transcript_evidence_id
    # The producer keeps the origin workspace/session distinct from the import
    # workspace/session; the reader must preserve that distinction.
    assert reference["origin_workspace_id"] == document["binding"]["workspaceId"]
    assert reference["import_workspace_id"] == paths.workspace_id
    assert reference["origin_workspace_id"] != reference["import_workspace_id"]
    assert reference["origin_session_id"] == document["binding"]["sessionId"]
    assert reference["projected_session_id"] == paths.session_id
    assert len(batches) == len(document["batches"])
    assert batches[0]["binding"] == document["binding"]
    assert batches[0]["runId"] == document["batches"][0]["runId"]

    # The legacy fixture form keeps its exact closed key set downstream.
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    legacy_paths = helpers._paths(legacy_root, session_id="legacy-import")
    legacy_evidence = helpers._evidence(legacy_paths)
    legacy_document = helpers._fixture_document("failed-before")
    legacy_published = ingest_monitor_replay(
        legacy_paths,
        legacy_evidence,
        str(helpers.RUN_IDS["failed-before"]),
        helpers.FIXTURES / "failed-before.json",
    )
    assert legacy_published.source_baseline is None
    assert legacy_published.git_evidence is None
    assert legacy_published.git_head == "b" * 40
    assert legacy_published.git_dirty is False
    assert set(legacy_published.to_dict()) == _LEGACY_REPLAY_KEYS

    legacy_envelope, legacy_reference, legacy_batches = (
        diagnostic_workflows._read_transcript_parent(
            _replay_reader_state(legacy_paths, legacy_evidence, helpers.PROJECT_ID),
            evidence_id=legacy_published.transcript_evidence_id,
            run=SimpleNamespace(
                identity=_replay_identity(legacy_published),
                run_id=legacy_published.operation_id,
            ),
            expected_role="failed-before",
        )
    )
    assert str(legacy_envelope.evidence_id) == legacy_published.transcript_evidence_id
    assert set(legacy_reference) == _LEGACY_REPLAY_KEYS
    assert "source_baseline" not in legacy_reference
    assert "git_evidence" not in legacy_reference
    assert len(legacy_batches) == len(legacy_document["batches"])


def test_tampered_provenance_graphs_are_refused_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[object] = []
    _install_snapshot_pair_factory(monkeypatch, captured)
    fixture = monitor_fixture._supplementary_physical_fact_fixture(
        tmp_path, monkeypatch
    )
    assert len(captured) == 1
    pair = fixture.pair
    _assert_snapshot_identity(pair.before_identity)

    original_reference = fixture.selectors[0]["monitor_run_ref"]
    changed = _republish_provenance_variant(
        pair.evidence, original_reference, tmp_path, "changed-rule"
    )
    legacy = _republish_provenance_variant(
        pair.evidence, original_reference, tmp_path, "legacy"
    )

    # Both variants are independently contract-valid and only borrow the
    # original TestRun; their provenance pair no longer matches that TestRun.
    for variant in (changed, legacy):
        assert (
            validate_run_reference(variant.reference.to_dict())
            == variant.reference.to_dict()
        )
        assert validate_physical_transcript(variant.transcript) == variant.transcript
    assert changed.reference.git_evidence["rule"] == "status"
    assert (
        changed.transcript["binding"]["gitEvidence"]["rule"] == "status"
    )
    assert set(legacy.reference.to_dict()) == _LEGACY_PHYSICAL_KEYS
    # The authenticated original graph was republished, never rewritten.
    assert MonitorRunRefV2.from_value(original_reference).git_evidence["rule"] == "head"
    assert changed.operation_id != original_reference["operation_id"]
    assert legacy.operation_id != original_reference["operation_id"]

    # Same Git fields and hashes, different snapshot pair: not the same replay
    # identity.  The legacy identity differs in both fields and pair.
    head_identity = pair.before_identity
    status_identity = replace(
        head_identity, git_evidence=dict(_STATUS_EVIDENCE)
    )
    for field in (
        "workspace_id",
        "project_id",
        "build_id",
        "elf_sha256",
        "target_device",
        "input_snapshot_sha256",
        "git_commit",
        "git_dirty",
    ):
        assert getattr(status_identity, field) == getattr(head_identity, field)
    assert (
        diagnostic_workflows._same_replay_identity(head_identity, status_identity)
        is False
    )
    legacy_identity = replace(
        head_identity,
        git_commit="a" * 40,
        git_dirty=False,
        source_baseline=None,
        git_evidence=None,
    )
    assert (
        diagnostic_workflows._same_replay_identity(head_identity, legacy_identity)
        is False
    )

    store = DiagnosticStore(pair.workspace.diagnostics_root, pair.evidence)
    before_revision = store.load_durable(fixture.diagnostic_session_id).revision
    evidence_before = native_authority_fixture._tree_bytes(pair.data_root)
    diagnostics_before = native_authority_fixture._tree_bytes(
        pair.workspace.diagnostics_root
    )

    for variant in (changed, legacy):
        selector = {
            "kind": "physical-monitor-fact/2",
            "monitor_ref_evidence_id": variant.reference_evidence_id,
            "monitor_run_ref": variant.reference.to_dict(),
            "selector_kind": "register",
            "selector": "r0",
            "fact": "bit-values-mask",
            "minimum_valid_samples": 2,
            "bit_index": 0,
        }
        rejected = diagnostic_add_plan(
            pair.diagnostic,
            operation_id=f"tamper-{variant.variant}-plan",
            diagnostic_session_id=fixture.diagnostic_session_id,
            expected_revision=before_revision,
            steps=[
                {
                    "step_id": "physical-register-fact-tampered",
                    "selector": selector,
                    "expected_value": 3,
                    "purpose": "the changed provenance graph must not authenticate",
                }
            ],
        )
        assert rejected.ok is False
        assert rejected.code == EVIDENCE_INTEGRITY_FAILURE

    assert native_authority_fixture._tree_bytes(pair.data_root) == evidence_before
    assert (
        native_authority_fixture._tree_bytes(pair.workspace.diagnostics_root)
        == diagnostics_before
    )
    assert store.load_durable(fixture.diagnostic_session_id).revision == before_revision
