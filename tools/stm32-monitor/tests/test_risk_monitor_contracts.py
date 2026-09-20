from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from stm32_monitor.analysis import (
    ANALYSIS_REQUEST_INVALID,
    AnalysisError,
    analyze_monitor_windows,
)
from stm32_monitor.analysis_workflows import (
    ANALYSIS_WORKFLOW_INVALID,
    AnalysisBundleRef,
    AnalysisWorkflowError,
)
from stm32_monitor.models import WatchItem
from stm32_monitor.probe_session import ProbeSession
from stm32_toolkit.evidence import ArtifactRef
from test_analysis import _case, _replace_counter, _request, _with_reference
from test_probe_session import FakeObservation, _binding


@pytest.mark.parametrize("invalid_type_name", ("",))
def test_risk_analysis_excludes_reachable_invalid_type_name_without_mutation(
    tmp_path: Path,
    invalid_type_name: str,
) -> None:
    """A contract-valid window treats an empty scalar type name as untrusted."""

    paths, _, after_document, before, after, before_ref, _ = _case(tmp_path)
    malformed = tuple(
        _replace_counter(batch, 17, value_type=invalid_type_name)
        if batch.sequence == 0
        else batch
        for batch in after
    )
    after_ref = _with_reference(after_document, paths, malformed)
    request = _request(before_ref, after_ref)
    before_wire = tuple(batch.to_dict() for batch in before)
    malformed_wire = tuple(batch.to_dict() for batch in malformed)
    before_ref_wire = before_ref.to_dict()
    after_ref_wire = after_ref.to_dict()

    result = analyze_monitor_windows(request, before, malformed)

    assert result.quality == "INVALID"
    assert result.conclusion == "INCONCLUSIVE"
    assert result.reason_code == "INSUFFICIENT_VALID_PAIRS"
    assert result.aligned_position_count == 2
    assert result.aligned_pair_count == 1
    assert result.excluded_position_count == 1
    assert result.changed is None
    assert tuple(batch.to_dict() for batch in before) == before_wire
    assert tuple(batch.to_dict() for batch in malformed) == malformed_wire
    assert before_ref.to_dict() == before_ref_wire
    assert after_ref.to_dict() == after_ref_wire


def test_risk_analysis_request_type_guard_is_stable_and_input_preserving(
    tmp_path: Path,
) -> None:
    """The public analysis entry rejects a wrong request before window work."""

    _, _, _, before, after, before_ref, after_ref = _case(tmp_path)
    before_wire = tuple(batch.to_dict() for batch in before)
    after_wire = tuple(batch.to_dict() for batch in after)
    before_ref_wire = before_ref.to_dict()
    after_ref_wire = after_ref.to_dict()

    with pytest.raises(AnalysisError) as error:
        analyze_monitor_windows(object(), before, after)  # type: ignore[arg-type]

    assert error.value.code == ANALYSIS_REQUEST_INVALID
    assert error.value.message == "analysis request is invalid"
    assert tuple(batch.to_dict() for batch in before) == before_wire
    assert tuple(batch.to_dict() for batch in after) == after_wire
    assert before_ref.to_dict() == before_ref_wire
    assert after_ref.to_dict() == after_ref_wire


def _valid_bundle_ref() -> AnalysisBundleRef:
    payload = b'{"schema":"stm32-monitor-analysis-bundle/1"}'
    digest = sha256(payload).hexdigest()
    artifact = ArtifactRef(
        sha256=digest,
        size_bytes=len(payload),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind="monitor-analysis-bundle",
        media_type="application/json",
    )
    return AnalysisBundleRef(
        "stm32-monitor-analysis-bundle-ref/1",
        digest,
        "a" * 64,
        artifact,
    )


@pytest.mark.parametrize("invalid_artifact", (None, []))
def test_risk_analysis_bundle_from_value_maps_nested_artifact_type_failure(
    invalid_artifact: object,
) -> None:
    """The closed-wire parser maps nested ArtifactRef type failures stably."""

    wire = _valid_bundle_ref().to_dict()
    forged = deepcopy(wire)
    forged["artifact"] = invalid_artifact
    before = deepcopy(forged)

    with pytest.raises(AnalysisWorkflowError) as error:
        AnalysisBundleRef.from_value(forged)

    assert error.value.code == ANALYSIS_WORKFLOW_INVALID
    assert error.value.message == "analysis bundle reference is invalid"
    assert forged == before


def test_risk_probe_session_cancellation_invalidates_prepared_admission(
    tmp_path: Path,
) -> None:
    """Cancellation from a prepared provider clears the read plan and admission."""

    async def scenario() -> None:
        project = tmp_path / "project"
        project.mkdir()
        observation = FakeObservation(_binding(project))
        session = ProbeSession(observation)
        watches = (WatchItem.variable("counter"),)

        assert (await session.revalidate()).ok
        prepared = await session.prepare_read_plan(watches)
        assert prepared.ok
        assert session._read_plan is not None
        assert session._admission_token is not None
        assert observation._read_plan_admission() is not None

        prepared_reads = 0
        fallback_reads = 0
        original_batch = observation._read_batch

        async def cancelled_read_prepared(plan: object):
            nonlocal prepared_reads
            del plan
            prepared_reads += 1
            raise asyncio.CancelledError

        async def observed_fallback(
            variables: tuple[str, ...], registers: tuple[str, ...]
        ):
            nonlocal fallback_reads
            fallback_reads += 1
            return await original_batch(variables, registers)

        observation._read_prepared = cancelled_read_prepared
        observation._read_batch = observed_fallback

        with pytest.raises(asyncio.CancelledError):
            await session.read(watches)

        assert prepared_reads == 1
        assert fallback_reads == 0
        assert observation.plan_invalidations == 1
        assert session._read_plan is None
        assert session._admission_token is None
        assert observation._read_plan_admission() is None

    asyncio.run(scenario())
