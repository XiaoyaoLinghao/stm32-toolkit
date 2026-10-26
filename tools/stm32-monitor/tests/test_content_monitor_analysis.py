"""Snapshot provenance through Monitor analysis and source context.

Every case uses disposable synthetic recorded data.  No hardware transport is
constructed: analysis reads the same accepted replay fixtures as the content
replay suites, with the snapshot provenance pair applied synthetically.
B2b1 physical-shaped fixtures remain synthetic software data, never physical
acceptance.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_monitor.analysis_workflows as workflows
import stm32_monitor.source_catalog as source_catalog
from stm32_monitor.analysis import (
    ANALYSIS_REQUEST_INVALID,
    AnalysisError,
    AnalysisRequest,
    analyze_monitor_windows,
)
from stm32_monitor.analysis_workflows import (
    OPERATION_CONFLICT,
    AnalysisPublication,
    AnalysisWorkflowError,
    compare_monitor_runs,
)
from stm32_monitor.models import ObservationBinding
from stm32_monitor.replay import (
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.store import MAX_EVIDENCE_READ_BYTES
from test_content_monitor_replay import (
    FIXTURES,
    GIT_EVIDENCE,
    PROJECT_ID,
    RUN_IDS,
    SOURCE_BASELINE,
    STATUS_EVIDENCE,
    _evidence,
    _fixture_document,
    _paths,
    _read_batches,
    _redigest_document,
    _redigest_reference,
    _root_files,
    _snapshot_document,
    _write_document,
)
from test_source_catalog import _setup as _source_setup


HYPOTHESIS_ID = "1" * 32
DIAGNOSTIC_SESSION_ID = "f" * 32
PROVENANCE_KEYS = frozenset({"source_baseline", "git_evidence"})
#: The exact accepted v1 evidence-identity keys; the provenance pair is not one.
EVIDENCE_IDENTITY_FIELDS = frozenset(
    {
        "workspace_id",
        "project_id",
        "session_id",
        "build_id",
        "elf_sha256",
        "target_device",
        "input_snapshot_sha256",
        "git_commit",
        "git_dirty",
    }
)
#: The exact accepted analysis lineage keys; the provenance pair is not one.
ANALYSIS_LINEAGE_FIELDS = frozenset(
    {
        "schema",
        "origin_workspace_id",
        "import_workspace_id",
        "logical_project_id",
        "target_device",
        "before_input_snapshot_sha256",
        "before_build_id",
        "before_elf_sha256",
        "after_input_snapshot_sha256",
        "after_build_id",
        "after_elf_sha256",
        "source_change_declaration_id",
    }
)


def _request(
    before: MonitorRunRef,
    after: MonitorRunRef,
    *,
    minimum: int = 2,
) -> AnalysisRequest:
    return AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=before,
        after_run=after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=minimum,
    )


def _identical_firmware_after(snapshot: bool) -> dict[str, object]:
    """Return the fixed-after window bound to the failed-before firmware."""

    before = _snapshot_document("failed-before") if snapshot else _fixture_document("failed-before")
    after = _snapshot_document("fixed-after") if snapshot else _fixture_document("fixed-after")
    binding = deepcopy(before["binding"])
    after["binding"] = deepcopy(binding)
    for batch in after["batches"]:
        batch["binding"] = deepcopy(binding)  # type: ignore[index]
    _redigest_document(after)
    return after


def _import_pair(tmp_path: Path, *, snapshot: bool) -> tuple[object, object, MonitorRunRef, MonitorRunRef]:
    paths = _paths(tmp_path)
    evidence = _evidence(paths)
    before_target = (
        _write_document(tmp_path, _snapshot_document("failed-before"), "before.json")
        if snapshot
        else FIXTURES / "failed-before.json"
    )
    after_target = _write_document(tmp_path, _identical_firmware_after(snapshot), "after.json")
    before = ingest_monitor_replay(
        paths, evidence, str(RUN_IDS["failed-before"]), before_target
    )
    after = ingest_monitor_replay(
        paths, evidence, str(RUN_IDS["fixed-after"]), after_target
    )
    return paths, evidence, before, after


def _changed_pair_reference(reference: MonitorRunRef, form: str) -> MonitorRunRef:
    """Return one reference whose snapshot provenance pair differs."""

    payload = reference.to_dict()
    if form == "evidence":
        payload["git_evidence"] = dict(STATUS_EVIDENCE)
    else:
        # A validated downgrade to the closed legacy Git form.
        payload.pop("source_baseline")
        payload.pop("git_evidence")
        payload["git_head"] = "a" * 40
        payload["git_dirty"] = False
    _redigest_reference(payload)
    return MonitorRunRef.from_value(payload)


def _publish(paths: object, evidence: object, before: MonitorRunRef, after: MonitorRunRef) -> AnalysisPublication:
    return compare_monitor_runs(
        paths,
        evidence,
        _request(before, after),
        DIAGNOSTIC_SESSION_ID,
        HYPOTHESIS_ID,
        "supports",
        "the fixed replay changed the observed counter",
        None,
    )


def _analysis_document(evidence: object, publication: AnalysisPublication) -> dict[str, object]:
    root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    envelope = evidence.get_envelope(root.manifest_id)
    raw = evidence.read_artifact(envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES)
    return json.loads(raw)


def test_snapshot_analysis_publication_carries_pair_and_reads_back(tmp_path: Path) -> None:
    paths, evidence, before, after = _import_pair(tmp_path, snapshot=True)

    assert type(before) is MonitorRunRef and type(after) is MonitorRunRef
    for reference in (before, after):
        assert reference.source_baseline == SOURCE_BASELINE
        assert dict(reference.git_evidence or {}) == GIT_EVIDENCE
        assert reference.git_head is None and reference.git_dirty is None

    request = _request(before, after)
    request_wire = request.to_dict()
    assert request_wire["before_run"]["source_baseline"] == SOURCE_BASELINE
    assert request_wire["before_run"]["git_evidence"] == GIT_EVIDENCE

    publication = _publish(paths, evidence, before, after)

    assert publication.analysis_result.quality == "VALID"
    assert publication.analysis_result.conclusion == "COMPLETED"
    assert publication.analysis_result.changed is True
    assert publication.analysis_result.request is None
    assert publication.analysis_result.identity.source_change_declaration_id is None

    wire = publication.to_dict()
    assert AnalysisPublication.from_value(wire).to_dict() == wire

    root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    envelope = evidence.get_envelope(root.manifest_id)
    identity = envelope.identity
    assert identity.source_baseline == SOURCE_BASELINE
    assert dict(identity.git_evidence or {}) == GIT_EVIDENCE
    assert identity.git_commit is None and identity.git_dirty is None
    assert set(identity.to_dict()) == EVIDENCE_IDENTITY_FIELDS | PROVENANCE_KEYS
    assert identity == workflows._identity_for_ref(after)

    document = _analysis_document(evidence, publication)
    assert document["schema"] == "stm32-monitor-analysis/1"
    assert document["analysis_id"] == publication.analysis_result.analysis_id
    assert set(document["identity"]) == ANALYSIS_LINEAGE_FIELDS
    assert document["identity"] == publication.analysis_result.identity.to_dict()

    reference_root = get_root(evidence, "monitor-run-ref", str(RUN_IDS["fixed-after"]))
    reference_envelope = evidence.get_envelope(reference_root.manifest_id)
    assert reference_envelope.identity == workflows._identity_for_ref(after)
    stored_bytes = evidence.read_artifact(
        reference_envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES
    )
    assert stored_bytes == canonical_replay_json_bytes(after.to_dict())
    assert json.loads(stored_bytes)["source_baseline"] == SOURCE_BASELINE
    assert json.loads(stored_bytes)["git_evidence"] == GIT_EVIDENCE


@pytest.mark.parametrize("form", ("evidence", "legacy"))
def test_analysis_rejects_a_changed_snapshot_pair(tmp_path: Path, form: str) -> None:
    paths, _evidence_store, before, after = _import_pair(tmp_path, snapshot=True)
    before_batches = _read_batches(paths, RUN_IDS["failed-before"])
    after_batches = _read_batches(paths, RUN_IDS["fixed-after"])

    assert analyze_monitor_windows(
        _request(before, after), before_batches, after_batches
    ).conclusion == "COMPLETED"

    changed = _changed_pair_reference(after, form)
    with pytest.raises(AnalysisError) as error:
        analyze_monitor_windows(_request(before, changed), before_batches, after_batches)

    assert error.value.code == ANALYSIS_REQUEST_INVALID


@pytest.mark.parametrize("form", ("evidence", "legacy"))
def test_workflow_rejects_a_changed_pair_before_publication(
    tmp_path: Path, form: str
) -> None:
    paths, evidence, before, after = _import_pair(tmp_path, snapshot=True)
    changed = _changed_pair_reference(after, form)

    with pytest.raises(AnalysisWorkflowError) as error:
        _publish(paths, evidence, before, changed)

    # The run-reference digest binds the pair, so a changed pair is a different
    # accepted operation intent before any analysis identity is published.
    assert error.value.code == OPERATION_CONFLICT
    assert _root_files(evidence, "monitor-analysis") == ()
    assert _root_files(evidence, "diagnostic-marker") == ()


def test_test_run_identity_comparison_includes_the_pair(tmp_path: Path) -> None:
    _paths_, _evidence_, _before, after = _import_pair(tmp_path, snapshot=True)

    matching = SimpleNamespace(identity=workflows._identity_for_ref(after))
    assert workflows._test_identity_matches_reference(matching, after)

    changed = _changed_pair_reference(after, "evidence")
    mismatched = SimpleNamespace(identity=workflows._identity_for_ref(changed))
    assert not workflows._test_identity_matches_reference(mismatched, after)

    # A real legacy EvidenceIdentity never satisfies a snapshot reference.
    legacy_identity = EvidenceIdentity(
        workspace_id=after.origin_workspace_id,
        project_id=after.logical_project_id,
        session_id=after.origin_session_id,
        build_id=after.build_id,
        elf_sha256=after.elf_sha256,
        target_device=after.target_device,
        input_snapshot_sha256=after.input_snapshot_sha256,
        git_commit="c" * 40,
        git_dirty=False,
    )
    assert not workflows._test_identity_matches_reference(
        SimpleNamespace(identity=legacy_identity), after
    )


def test_test_run_identity_comparison_keeps_legacy_compatibility(tmp_path: Path) -> None:
    _paths_, _evidence_, _before, after = _import_pair(tmp_path, snapshot=False)

    identity = workflows._identity_for_ref(after)
    assert identity.source_baseline is None and identity.git_evidence is None
    assert set(identity.to_dict()) == EVIDENCE_IDENTITY_FIELDS
    assert workflows._test_identity_matches_reference(
        SimpleNamespace(identity=identity), after
    )

    snapshot_identity = EvidenceIdentity(
        workspace_id=after.origin_workspace_id,
        project_id=after.logical_project_id,
        session_id=after.origin_session_id,
        build_id=after.build_id,
        elf_sha256=after.elf_sha256,
        target_device=after.target_device,
        input_snapshot_sha256=after.input_snapshot_sha256,
        git_commit=None,
        git_dirty=None,
        source_baseline=SOURCE_BASELINE,
        git_evidence=dict(GIT_EVIDENCE),
    )
    assert not workflows._test_identity_matches_reference(
        SimpleNamespace(identity=snapshot_identity), after
    )


def test_legacy_analysis_publication_keeps_exact_identity_keys(tmp_path: Path) -> None:
    paths, evidence, before, after = _import_pair(tmp_path, snapshot=False)

    for reference in (before, after):
        assert reference.source_baseline is None and reference.git_evidence is None
        assert set(reference.to_dict()).isdisjoint(PROVENANCE_KEYS)
    assert set(_request(before, after).to_dict()["before_run"]) == set(before.to_dict())

    publication = _publish(paths, evidence, before, after)

    root = get_root(evidence, "monitor-analysis", publication.analysis_result.analysis_id)
    envelope = evidence.get_envelope(root.manifest_id)
    assert envelope.identity.source_baseline is None
    assert envelope.identity.git_evidence is None
    assert set(envelope.identity.to_dict()) == EVIDENCE_IDENTITY_FIELDS
    assert set(envelope.to_dict()["identity"]).isdisjoint(PROVENANCE_KEYS)
    assert envelope.identity == workflows._identity_for_ref(after)

    document = _analysis_document(evidence, publication)
    assert set(document["identity"]) == ANALYSIS_LINEAGE_FIELDS
    assert set(publication.to_dict()["analysis_result"]["identity"]) == ANALYSIS_LINEAGE_FIELDS
    assert set(publication.to_dict()).isdisjoint(PROVENANCE_KEYS)


def _observation_binding(evidence: dict[str, str] | None) -> ObservationBinding:
    snapshot = evidence is not None
    return ObservationBinding(
        workspace_id="a" * 64,
        logical_project_id=str(PROJECT_ID),
        session_id="analysis-import",
        probe_id="probe/serial/01",
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="9" * 64,
        git_head=None if snapshot else "c" * 40,
        git_dirty=None if snapshot else False,
        flash_session_id="flash-01",
        lease_id="lease-01",
        dwarf_sha256="d" * 64,
        svd_sha256=None,
        source_baseline=SOURCE_BASELINE if snapshot else None,
        git_evidence=None if evidence is None else dict(evidence),
    )


def test_source_binding_signature_carries_the_immutable_pair() -> None:
    head = _observation_binding(GIT_EVIDENCE)
    status = _observation_binding(STATUS_EVIDENCE)

    assert head.git_head is None and status.git_head is None
    assert head.git_dirty is None and status.git_dirty is None
    assert head.source_baseline == status.source_baseline == SOURCE_BASELINE

    head_signature = source_catalog._binding_signature(head)
    status_signature = source_catalog._binding_signature(status)

    assert head_signature != status_signature
    assert source_catalog._binding_signature(head) == head_signature
    # Usable wherever an existing signature is a key and a catalog digest part.
    assert len({head_signature, status_signature}) == 2
    assert json.dumps([head_signature], separators=(",", ":"))
    assert head_signature[12] == (
        SOURCE_BASELINE,
        tuple(sorted(dict(GIT_EVIDENCE).items())),
    )

    legacy = _observation_binding(None)
    legacy_signature = source_catalog._binding_signature(legacy)
    assert legacy_signature == tuple(
        getattr(legacy, key, None)
        for key in (
            "workspace_id",
            "observation_session_id",
            "logical_project_id",
            "target_device",
            "build_id",
            "elf_sha256",
            "input_snapshot_sha256",
            "probe_id",
            "lease_id",
            "flash_session_id",
            "git_head",
            "git_dirty",
        )
    ) + ((),)
    # A loose test double without the pair attributes keeps working.
    assert source_catalog._binding_signature(
        SimpleNamespace(workspace_id="workspace", observation_session_id="session")
    )


@pytest.mark.parametrize(
    "pair",
    (
        {"source_baseline": SOURCE_BASELINE, "git_evidence": None},
        {"source_baseline": None, "git_evidence": dict(GIT_EVIDENCE)},
        {"source_baseline": SOURCE_BASELINE, "git_evidence": dict(GIT_EVIDENCE, status="available")},
        {"source_baseline": SOURCE_BASELINE, "git_evidence": dict(GIT_EVIDENCE, extra="value")},
        {"source_baseline": "input-snapshot-v2", "git_evidence": dict(GIT_EVIDENCE)},
        {
            "source_baseline": SOURCE_BASELINE,
            "git_evidence": dict(GIT_EVIDENCE),
            "git_head": "a" * 40,
        },
    ),
)
def test_source_binding_signature_rejects_malformed_raw_provenance(
    pair: dict[str, object],
) -> None:
    values = {"git_head": None, "git_dirty": None, **pair}
    binding = SimpleNamespace(**values)

    with pytest.raises(source_catalog.SourceCatalogFailure) as error:
        source_catalog._binding_signature(binding)

    assert error.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"


def test_source_catalog_invalidates_a_catalog_when_only_the_pair_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider, _facts, binding = _source_setup(monkeypatch, tmp_path)
    base = dict(vars(binding))
    head = SimpleNamespace(
        **{
            **base,
            "git_head": None,
            "git_dirty": None,
            "source_baseline": SOURCE_BASELINE,
            "git_evidence": dict(GIT_EVIDENCE),
        }
    )
    status = SimpleNamespace(
        **{
            **base,
            "git_head": None,
            "git_dirty": None,
            "source_baseline": SOURCE_BASELINE,
            "git_evidence": dict(STATUS_EVIDENCE),
        }
    )

    async def scenario() -> None:
        first = await provider.page(
            query="", cursor=None, limit=1, parent_id=None, catalog_id=None,
            binding=head, binding_epoch=0,
        )
        other = await provider.page(
            query="", cursor=None, limit=1, parent_id=None, catalog_id=None,
            binding=status, binding_epoch=0,
        )
        assert other["catalogId"] != first["catalogId"]
        reused = await provider.page(
            query="", cursor=None, limit=1, parent_id=None,
            catalog_id=first["catalogId"], binding=head, binding_epoch=0,
        )
        assert reused["catalogId"] == first["catalogId"]
        with pytest.raises(source_catalog.SourceCatalogFailure) as raised:
            await provider.page(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=first["catalogId"], binding=status, binding_epoch=0,
            )
        assert raised.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        provider.close()

    asyncio.run(scenario())
