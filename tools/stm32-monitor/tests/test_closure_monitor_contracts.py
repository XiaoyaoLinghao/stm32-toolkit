"""Bounded Monitor closure checks for public discovery and pure wire guards.

The discovery test exercises the public runtime with an untrusted provider
reply. The remaining named units inspect in-memory values only; replay
Evidence supplies a genuine typed control without claiming physical access.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import stm32_monitor.analysis_workflows as analysis_workflows
import stm32_monitor.cli as cli
import stm32_monitor.replay as replay
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.publication import TestRunRepository
from test_analysis_workflows import (
    _evidence_tree,
    _ingest_pair,
    _paths,
    _publish_target_pair,
)
from test_runtime import _protocol_runtime


def test_public_probe_list_handles_empty_and_nonmapping_provider_tuples(
    tmp_path: Path,
) -> None:
    """A valid empty discovery is distinct from a malformed provider item."""

    listed: dict[str, tuple[object, ...]] = {
        "probes": (
            {
                "probeId": "probe-a",
                "vendor": "ST",
                "product": "ST-LINK",
                "boardName": None,
            },
        )
    }

    async def probe_list(_request: object) -> OperationResult[object]:
        return OperationResult.success("stm32_probe_list", {"probes": listed["probes"]})

    async def scenario() -> None:
        runtime, config, *_ = _protocol_runtime(tmp_path, probe_list_factory=probe_list)
        try:
            await runtime.start(config)
            accepted = await runtime.dispatch("monitor.probes.list", {})
            assert accepted.ok
            assert [item["probeId"] for item in accepted.data["probes"]] == ["probe-a"]

            listed["probes"] = ()
            empty = await runtime.dispatch("monitor.probes.list", {})
            assert empty.ok
            assert empty.data == {"probes": []}

            listed["probes"] = (object(),)
            malformed = await runtime.dispatch("monitor.probes.list", {})
            assert not malformed.ok
            assert malformed.code == "MONITOR_PROBE_ENUMERATION_FAILED"
            assert malformed.message == "Debug probe enumeration failed"
            assert malformed.details == {}

            listed["probes"] = (
                {"probeId": "probe-a", "vendor": "ST", "product": "ST-LINK", "boardName": None},
            )
            recovered = await runtime.dispatch("monitor.probes.list", {})
            assert recovered.ok
            assert [item["probeId"] for item in recovered.data["probes"]] == ["probe-a"]
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_named_pure_json_guards_reject_nonbytes_and_unsupported_values() -> None:
    """Internal pure units retain their bounded wire behavior without I/O."""

    canonical = b'{"source":"offline"}'
    assert cli._decode_json_bytes(canonical) == {"source": "offline"}
    nonbytes = bytearray(canonical)
    with pytest.raises(cli._AdapterFailure) as decoded_error:
        cli._decode_json_bytes(nonbytes)  # type: ignore[arg-type]
    assert decoded_error.value.code == cli.ANALYSIS_WORKFLOW_INVALID
    assert decoded_error.value.message == "JSON input is invalid"
    assert nonbytes == canonical

    ordinary_json = {"values": [1, True, None, "text"]}
    assert replay._physical_copy_json(ordinary_json) == ordinary_json
    with pytest.raises(TypeError, match="physical transcript JSON contains an unsupported value"):
        replay._physical_copy_json(b"not-json")
    assert ordinary_json == {"values": [1, True, None, "text"]}


def test_named_pure_model_and_identity_guards_preserve_published_replay(
    tmp_path: Path,
) -> None:
    """A real replay manifest matches its reference; untrusted objects do not."""

    paths = _paths(tmp_path)
    evidence, before, _after = _ingest_pair(paths)
    failed_id, _fixed_id = _publish_target_pair(paths, evidence)
    manifest = TestRunRepository(evidence).load(failed_id).manifest
    evidence_before = _evidence_tree(evidence)

    assert analysis_workflows._test_identity_matches_reference(manifest, before)
    assert not analysis_workflows._test_identity_matches_reference(object(), before)

    serialized = before.to_dict()
    assert cli._model_wire(before, "monitor run reference") == serialized
    assert cli._model_wire(serialized, "monitor run reference") is serialized
    with pytest.raises(cli._AdapterFailure) as model_error:
        cli._model_wire(object(), "monitor run reference")
    assert model_error.value.code == cli.ANALYSIS_WORKFLOW_INVALID
    assert model_error.value.message == "monitor run reference is invalid"

    assert before.to_dict() == serialized
    assert _evidence_tree(evidence) == evidence_before
