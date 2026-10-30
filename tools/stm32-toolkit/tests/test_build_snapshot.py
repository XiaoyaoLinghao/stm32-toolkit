"""Builds and build freshness from an exact input snapshot without Git.

These regressions cover the BUILD-SNAPSHOT contract: Git unavailability is
not a build failure; a schema-2 snapshot identity/record is explicit, bounded,
and nullable rather than a fake commit; context freshness never requires a Git
subprocess; no-op reuse is validated against the prior pair's own schema, so
current Git availability/HEAD/dirty state never alone rejects unchanged
outputs; and a current snapshot build is admitted by the same managed
flash/debug workflows as a Git-backed build, with an explicit schema-2 flash
receipt.  All processes are offline fakes; no probe is enumerated or attached.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit import __version__
from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build import identity as identity_mod
from stm32_toolkit.build import runner as runner_mod
from stm32_toolkit.build.identity import (
    BuildError,
    collect_build_git_evidence,
    compute_build_id,
    git_evidence,
    validate_identity_document,
)
from stm32_toolkit.build.model import (
    BUILD_GIT_INVALID,
    BUILD_INPUT_INVALID,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
)
from stm32_toolkit.build.runner import build_result_document
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.context import build_project_context
from stm32_toolkit.debug.firmware import bind_debug_firmware
from stm32_toolkit.debug.model import DebugBindingRequest
from stm32_toolkit.mcp_server import ServerRuntime
from stm32_toolkit.probe import flash as flash_mod
from stm32_toolkit.probe.flash import (
    FlashSegment,
    flash_firmware,
    load_fresh_firmware_facts,
)
from stm32_toolkit.probe.handoff import _FLASH_FIELDS
from stm32_toolkit.process import ProcessError, ProcessResult

from test_build_runner import (
    git,
    install_fake_cmake,
    install_fake_git,
    prepare_project,
    read_json,
)
from test_debug_firmware import BindingClient
from test_flash import RecordingFlashClient, _request
from test_mcp_roots import _RootSession, _context

SNAPSHOT_EVIDENCE = {
    "status": "unavailable",
    "code": BUILD_GIT_INVALID,
    "rule": "head",
}


def identity_path(root: Path) -> Path:
    return root / "build" / "arm-debug" / "firmware-identity.json"


def result_path(root: Path) -> Path:
    return root / "artifacts" / "migration" / "build-result.json"


def snapshot_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    git_mode: str = "exit1",
    name: str = "project",
    extra_env: dict[str, str] | None = None,
) -> tuple[Path, dict, dict]:
    """Materialize an unversioned project and run one fake snapshot build."""
    root = prepare_project(tmp_path, git_repo=False, name=name)
    install_fake_git(monkeypatch, tmp_path, git_mode)
    install_fake_cmake(monkeypatch, tmp_path, env=extra_env)
    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert built.ok is True, built
    return root, read_json(identity_path(root)), read_json(result_path(root))


def deny_git_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate an OS policy denying the Git executable launch."""

    def unavailable(_request):
        raise ProcessError("launch", "process could not be launched")

    monkeypatch.setattr(identity_mod, "run_process", unavailable)


# ---------------------------------------------------------------------------
# identity/record shape
# ---------------------------------------------------------------------------


def test_snapshot_identity_and_record_are_explicit_and_nullable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, record = snapshot_build(tmp_path, monkeypatch)

    assert identity["schemaVersion"] == 2
    assert identity["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert identity["gitHead"] is None
    assert identity["gitDirty"] is None
    assert identity["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert len(identity["gitHead"] or "") == 0
    assert len(identity["inputSnapshotSha256"]) == 64
    assert identity["targetDevice"] == "STM32F407VGTx"
    assert identity["elfPath"] == "build/arm-debug/firmware.elf"
    assert identity["mapPath"] == "build/arm-debug/firmware.map"
    assert compute_build_id(identity) == identity["buildId"]
    validate_identity_document(identity)

    assert record["schemaVersion"] == 2
    assert record["status"] == "success"
    assert record["code"] == "OK"
    assert record["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert record["gitHead"] is None
    assert record["gitDirty"] is None
    assert record["gitEvidence"] == identity["gitEvidence"]
    assert record["buildId"] == identity["buildId"]
    assert record["inputSnapshotSha256"] == identity["inputSnapshotSha256"]
    # No stringified None and no fabricated SHA anywhere in the evidence.
    text = json.dumps({"identity": identity, "record": record})
    assert '"gitHead": "None"' not in text
    assert "0" * 40 not in text


def test_typed_identity_round_trips_the_published_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root, identity, _record = snapshot_build(tmp_path, monkeypatch)
    from stm32_toolkit.build.model import FirmwareIdentity

    typed = FirmwareIdentity.from_document(identity)
    assert typed.to_dict() == identity
    validate_identity_document(typed.to_dict())


def test_schema_one_stays_strict_and_schema_two_requires_null_git_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    schema_one = read_json(identity_path(root))
    assert schema_one["schemaVersion"] == 1
    assert "sourceBaseline" not in schema_one and "gitEvidence" not in schema_one

    widened = dict(schema_one)
    widened["gitHead"] = None
    with pytest.raises(BuildError):
        validate_identity_document(widened)
    widened = dict(schema_one)
    widened["gitDirty"] = None
    with pytest.raises(BuildError):
        validate_identity_document(widened)

    _snapshot_root, snapshot_identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="snapshot-for-schema"
    )
    tampered = {**snapshot_identity, "gitHead": "a" * 40, "buildId": ""}
    tampered["buildId"] = compute_build_id(tampered)
    with pytest.raises(BuildError):
        validate_identity_document(tampered)
    tampered = {**snapshot_identity, "gitDirty": False, "buildId": ""}
    tampered["buildId"] = compute_build_id(tampered)
    with pytest.raises(BuildError):
        validate_identity_document(tampered)
    missing = {key: value for key, value in snapshot_identity.items() if key != "gitEvidence"}
    missing["buildId"] = compute_build_id(missing)
    with pytest.raises(BuildError):
        validate_identity_document(missing)
    tampered = {**snapshot_identity, "sourceBaseline": "git", "buildId": ""}
    tampered["buildId"] = compute_build_id(tampered)
    with pytest.raises(BuildError):
        validate_identity_document(tampered)


def test_build_result_document_keeps_schema_one_key_order(tmp_path: Path):
    document = build_result_document(
        status="success",
        stage="",
        code="OK",
        build_id="a" * 64,
        git_head="b" * 40,
        git_dirty=False,
        input_snapshot_sha256="c" * 64,
        target_device="STM32F407VGTx",
        preset="arm-debug",
        started_at_utc="2026-08-06T08:00:00.000000Z",
        finished_at_utc="2026-08-06T08:00:01.000000Z",
        duration_ms=1,
        artifacts=[],
        memory=[],
        warnings=[],
    )
    assert list(document) == [
        "schemaVersion",
        "status",
        "stage",
        "code",
        "buildId",
        "toolkitVersion",
        "gitHead",
        "gitDirty",
        "inputSnapshotSha256",
        "targetDevice",
        "preset",
        "startedAtUtc",
        "finishedAtUtc",
        "durationMs",
        "artifacts",
        "memory",
        "warnings",
    ]
    assert document["gitDirty"] is False
    assert document["toolkitVersion"] == __version__


# ---------------------------------------------------------------------------
# Git availability variants
# ---------------------------------------------------------------------------


def test_unborn_git_repository_builds_without_creating_a_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="unborn")
    git("init", "-q", cwd=root)
    head_file = root / ".git" / "HEAD"
    head_before = head_file.read_bytes()
    install_fake_cmake(monkeypatch, tmp_path)

    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert built.ok is True, built
    identity = read_json(identity_path(root))
    assert identity["schemaVersion"] == 2
    assert identity["gitHead"] is None and identity["gitDirty"] is None
    assert identity["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert head_file.read_bytes() == head_before
    with pytest.raises(Exception):
        # Still unborn: the Toolkiit never initialized or committed state.
        import subprocess

        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
        )


def test_missing_git_executable_is_not_a_build_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="missing-git")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)

    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert built.ok is True, built
    assert read_json(identity_path(root))["gitEvidence"] == SNAPSHOT_EVIDENCE


def test_denied_git_launch_is_not_a_build_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="denied-git")
    deny_git_launch(monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)

    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert built.ok is True, built
    assert read_json(identity_path(root))["gitEvidence"] == SNAPSHOT_EVIDENCE


def test_collector_maps_only_git_availability_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="collector")
    deny_git_launch(monkeypatch)
    evidence = collect_build_git_evidence(root)
    assert evidence.to_dict() == SNAPSHOT_EVIDENCE

    def other_failure(_root, _timeout=30):
        raise BuildError(BUILD_INPUT_INVALID, "build input is invalid", {"path": "x"})

    monkeypatch.setattr(identity_mod, "git_evidence", other_failure)
    with pytest.raises(BuildError) as error:
        collect_build_git_evidence(root)
    assert error.value.code == BUILD_INPUT_INVALID


def test_collector_bounds_unknown_availability_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="bounded-rule")

    def unexpected_rule(_root, _timeout=30):
        raise BuildError(
            BUILD_GIT_INVALID,
            "git evidence is unavailable",
            {"rule": "C:\\secret\\host\\path"},
        )

    monkeypatch.setattr(identity_mod, "git_evidence", unexpected_rule)
    evidence = collect_build_git_evidence(root)
    assert evidence.rule == "head"
    assert evidence.to_dict() == SNAPSHOT_EVIDENCE

    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert built.ok is True, built
    identity = read_json(identity_path(root))
    assert identity["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert "secret" not in json.dumps(identity)


def test_strict_git_evidence_api_is_unchanged(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False, name="strict")
    with pytest.raises(BuildError) as error:
        git_evidence(root)
    assert error.value.code == BUILD_GIT_INVALID
    assert error.value.details == {"rule": "head"}


def test_git_status_failure_discards_the_untrusted_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="status-failure")
    calls = {"count": 0}

    def fake_run(_request):
        calls["count"] += 1
        if calls["count"] == 1:
            return ProcessResult(
                returncode=0,
                stdout="a" * 40 + "\n",
                stderr="",
                timed_out=False,
                duration_ms=1,
                stdout_truncated=False,
                stderr_truncated=False,
            )
        raise ProcessError("launch", "process could not be launched")

    monkeypatch.setattr(identity_mod, "run_process", fake_run)
    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert built.ok is True, built
    identity = read_json(identity_path(root))
    # A real head was observed but the worktree state was not, so the whole
    # Git claim is discarded rather than emitting head with dirty=false.
    assert identity["gitHead"] is None
    assert identity["gitDirty"] is None
    assert identity["gitEvidence"]["rule"] == "status"


# ---------------------------------------------------------------------------
# no-op reuse, stale, failures, drift
# ---------------------------------------------------------------------------


def test_repeated_non_git_build_reuses_current_snapshot_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, first_identity, _record = snapshot_build(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert second.ok is True, second
    assert second.data.identity.build_id == first_identity["buildId"]
    record = read_json(result_path(root))
    assert record["schemaVersion"] == 2
    assert record["buildId"] == first_identity["buildId"]


def test_changed_snapshot_sources_are_rejected_or_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, first_identity, _record = snapshot_build(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    (root / "Src" / "main.c").write_text(
        "int main(void) { return 11; }\n", encoding="utf-8"
    )

    stale = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert stale.ok is False
    assert stale.code == "BUILD_OUTPUT_STALE"

    monkeypatch.delenv("FAKE_CMAKE_NO_OUTPUT")
    rebuilt = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert rebuilt.ok is True, rebuilt
    assert rebuilt.data.identity.build_id != first_identity["buildId"]


def test_tampered_snapshot_prior_evidence_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    document = read_json(identity_path(root))
    document["gitDirty"] = False
    document["buildId"] = compute_build_id(document)
    identity_path(root).write_text(json.dumps(document) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["path"] == "build/arm-debug/firmware.elf"
    assert result.details["rule"] == "unverifiable"
    assert result.details["reason"] == "prior-evidence-mismatch"
    assert result.details["evidenceField"] == "identityDocument"
    assert result.details["evidenceSource"] == "identity"
    assert result.details["remediation"]["action"] == "clean-rebuild"


def test_git_availability_or_head_change_never_invalidates_unchanged_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Git-backed success, then Git becomes unavailable while inputs and
    # artifacts stay unchanged.  The prior schema-1 pair is still coherent,
    # so the no-op build succeeds and records truthful snapshot provenance.
    root = prepare_project(tmp_path, name="git-to-snapshot")
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True
    assert read_json(identity_path(root))["schemaVersion"] == 1
    monkeypatch.setattr(
        "stm32_toolkit.build.runner.collect_build_git_evidence",
        lambda _root, _timeout=30: identity_mod.GitUnavailableEvidence(rule="head"),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert second.ok is True, second
    second_identity = read_json(identity_path(root))
    assert second_identity["schemaVersion"] == 2
    assert second_identity["gitHead"] is None
    assert second_identity["gitDirty"] is None
    assert second_identity["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert second.data.identity.build_id == second_identity["buildId"]

    # Snapshot success, then Git becomes available: the schema-2 prior pair
    # is still current and the new success records the real head truthfully.
    monkeypatch.delenv("FAKE_CMAKE_NO_OUTPUT")
    snapshot_root, snapshot_identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="snapshot-to-git"
    )
    assert snapshot_identity["gitHead"] is None
    monkeypatch.setattr(
        "stm32_toolkit.build.runner.collect_build_git_evidence",
        lambda _root, _timeout=30: identity_mod.GitEvidence(head="b" * 40, dirty=False),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    third = run_build(BuildRequest(project_root=snapshot_root, preset="arm-debug"))
    assert third.ok is True, third
    third_identity = read_json(identity_path(snapshot_root))
    assert third_identity["schemaVersion"] == 1
    assert third_identity["gitHead"] == "b" * 40
    assert third_identity["gitDirty"] is False


def test_failed_snapshot_build_publishes_schema_two_failure_and_supersedes_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CMAKE_EXIT", "4")

    failed = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert failed.ok is False
    assert failed.code == "BUILD_CONFIGURE_FAILED"
    failure = read_json(result_path(root))
    assert failure["schemaVersion"] == 2
    assert failure["status"] == "failure"
    assert failure["gitHead"] is None
    assert failure["gitDirty"] is None
    assert failure["gitEvidence"] == SNAPSHOT_EVIDENCE

    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.data["build"]["elfFresh"] is False
    assert context.data["build"]["buildId"] is None


def test_snapshot_input_mutation_during_compilation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="drift")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(
        monkeypatch, tmp_path, env={"FAKE_CMAKE_TOUCH_INPUT": "Src/main.c"}
    )

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_INPUT_CHANGED"
    assert result.details == {"path": "Src/main.c"}
    assert not identity_path(root).exists()


# ---------------------------------------------------------------------------
# context freshness
# ---------------------------------------------------------------------------


def test_snapshot_context_is_fresh_without_spawning_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, _record = snapshot_build(tmp_path, monkeypatch)

    def forbidden_process(*_args, **_kwargs):
        raise AssertionError("schema-2 context freshness must not spawn any process")

    monkeypatch.setattr(identity_mod, "run_process", forbidden_process)
    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.ok is True
    evidence = result.data["build"]
    assert evidence["elfFresh"] is True
    assert evidence["buildId"] == identity["buildId"]
    assert evidence["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert evidence["gitHead"] is None
    assert evidence["gitDirty"] is None
    assert evidence["gitEvidence"] == SNAPSHOT_EVIDENCE
    flash = result.data["capabilityDetails"]["flash"]
    # Hardware is still not evaluated here; a snapshot build is no longer a
    # policy blocker and context never claims a probe or target is ready.
    assert flash["status"] == "not-evaluated"
    assert "content identity" in flash["reason"]
    assert "FIRMWARE_PROVENANCE_UNSUPPORTED" not in flash["reason"]
    assert result.data["firmwareRoutes"]["managed"]["requiresGit"] is False


def test_snapshot_context_goes_stale_on_source_or_artifact_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    (root / "Src" / "main.c").write_text(
        "int main(void) { return 21; }\n", encoding="utf-8"
    )
    changed = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert changed.data["build"]["elfFresh"] is False

    rebuilt_root, _identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="artifact-change"
    )
    (rebuilt_root / "build" / "arm-debug" / "firmware.elf").write_bytes(b"tampered")
    artifact_changed = build_project_context(
        rebuilt_root, tmp_path.parent / "data", "session-a"
    )
    assert artifact_changed.data["build"]["elfFresh"] is False


def test_snapshot_context_rejects_cross_schema_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    record = read_json(result_path(root))
    record["schemaVersion"] = 1
    result_path(root).write_text(json.dumps(record) + "\n", encoding="utf-8")

    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.data["build"]["elfFresh"] is False


def _mutate_record(root: Path, mutator) -> None:
    record = read_json(result_path(root))
    mutator(record)
    result_path(root).write_text(json.dumps(record) + "\n", encoding="utf-8")


def _drop(key: str):
    return lambda record: record.pop(key)


def _set(key: str, value):
    return lambda record: record.__setitem__(key, value)


SNAPSHOT_RECORD_MUTATORS = [
    pytest.param(_drop("gitHead"), id="missing-gitHead"),
    pytest.param(_drop("gitDirty"), id="missing-gitDirty"),
    pytest.param(_drop("gitEvidence"), id="missing-gitEvidence"),
    pytest.param(_set("schemaVersion", 2.0), id="float-schemaVersion"),
    pytest.param(_set("schemaVersion", 1), id="cross-schema"),
    pytest.param(_set("stage", "complete"), id="noncurrent-stage"),
    pytest.param(_set("status", "success "), id="padded-status"),
    pytest.param(_set("futureField", 1), id="extra-field"),
    pytest.param(
        lambda record: record.__setitem__("artifacts", record["artifacts"][:-1]),
        id="missing-artifact",
    ),
    pytest.param(
        lambda record: record["artifacts"][0].__setitem__("sha256", "a" * 64),
        id="artifact-extra-field",
    ),
    pytest.param(_set("gitHead", "a" * 40), id="forged-head"),
]


@pytest.mark.parametrize("mutator", SNAPSHOT_RECORD_MUTATORS)
def test_strict_snapshot_record_blocks_freshness_and_noop_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator
):
    root, _identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="strict-record"
    )
    _mutate_record(root, mutator)

    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.data["build"]["elfFresh"] is False

    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"


MALFORMED_GIT_EVIDENCE = [
    pytest.param(
        {"status": "unavailable", "code": BUILD_GIT_INVALID, "rule": []},
        id="rule-array",
    ),
    pytest.param(
        {"status": "unavailable", "code": BUILD_GIT_INVALID, "rule": {}},
        id="rule-object",
    ),
    pytest.param(
        {"status": "unavailable", "code": BUILD_GIT_INVALID, "rule": 1},
        id="rule-number",
    ),
    pytest.param(
        {"status": "unavailable", "code": BUILD_GIT_INVALID, "rule": None},
        id="rule-null",
    ),
    pytest.param([], id="evidence-array"),
    pytest.param("unavailable", id="evidence-string"),
]


@pytest.mark.parametrize("evidence", MALFORMED_GIT_EVIDENCE)
def test_malformed_snapshot_record_objects_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence
):
    root, _identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="malformed-record"
    )
    _mutate_record(root, _set("gitEvidence", evidence))

    # Public context path: a stable stale result, never a TypeError.
    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.ok is True
    assert context.data["build"]["elfFresh"] is False

    # No-op public build path: no exception, no stale acceptance.
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"


@pytest.mark.parametrize("rule", [pytest.param([], id="array"), pytest.param({}, id="object")])
def test_collector_bounds_unhashable_availability_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rule
):
    root = prepare_project(tmp_path, git_repo=False, name="unhashable-rule")

    def unexpected_details(_root, _timeout=30):
        raise BuildError(
            BUILD_GIT_INVALID, "git evidence is unavailable", {"rule": rule}
        )

    monkeypatch.setattr(identity_mod, "git_evidence", unexpected_details)
    evidence = collect_build_git_evidence(root)
    assert evidence.to_dict() == SNAPSHOT_EVIDENCE

    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert built.ok is True, built
    identity = read_json(identity_path(root))
    assert identity["gitEvidence"] == SNAPSHOT_EVIDENCE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("logicalProjectId", "87654321-4321-8765-4321-876543218765"),
        ("toolkitVersion", "0.0.0"),
    ],
)
def test_snapshot_context_requires_current_project_and_toolkit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
):
    root, _identity, _record = snapshot_build(
        tmp_path, monkeypatch, name="identity-tamper"
    )
    document = read_json(identity_path(root))
    document[field] = value
    document["buildId"] = compute_build_id(document)
    identity_path(root).write_text(json.dumps(document) + "\n", encoding="utf-8")
    record = read_json(result_path(root))
    record["buildId"] = document["buildId"]
    result_path(root).write_text(json.dumps(record) + "\n", encoding="utf-8")

    context = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert context.data["build"]["elfFresh"] is False

    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"


def test_fresh_snapshot_context_does_not_claim_checked_hardware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch, name="neutral-hw")
    runtime = ServerRuntime.create(root, tmp_path / "plugin-data", "session-a")

    result = asyncio.run(
        mcp_mod.tool_project_context_for_request(
            runtime, _context(_RootSession([[runtime.project_root]]))
        )
    )

    assert result["ok"] is True
    details = result["data"]["capabilityDetails"]
    # Configured capability is distinct from a probe/target actually checked:
    # no snapshot policy blocker and no false readiness claim.
    for key in ("flash", "targetTest", "monitor", "breakpointDebug"):
        assert details[key]["status"] == "not-evaluated", key
        assert "FIRMWARE_PROVENANCE_UNSUPPORTED" not in details[key]["reason"], key
        assert "Git repository with a committed HEAD" not in " ".join(
            details[key]["nextSteps"]
        ), key
    assert result["data"]["capabilities"]["flash"] is False
    assert result["data"]["firmwareRoutes"]["managed"]["requiresGit"] is False
    assert details["hostTest"]["status"] == "not-evaluated"


def test_post_collection_snapshot_failure_records_null_git_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="post-collection")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    real_snapshot = runner_mod.snapshot_project_inputs
    calls = {"count": 0}

    def failing_second(model, *, policy):
        calls["count"] += 1
        first = real_snapshot(model, policy=policy)
        if calls["count"] == 1:
            return first
        raise BuildError(
            BUILD_INPUT_INVALID,
            "build input is invalid",
            {"path": "Src/main.c", "rule": "missing"},
        )

    monkeypatch.setattr(runner_mod, "snapshot_project_inputs", failing_second)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == BUILD_INPUT_INVALID
    record = read_json(result_path(root))
    assert record["schemaVersion"] == 2
    assert record["status"] == "failure"
    assert record["stage"] == "snapshot"
    assert record["gitHead"] is None
    assert record["gitDirty"] is None
    assert record["gitEvidence"] == SNAPSHOT_EVIDENCE


def test_pre_build_snapshot_drift_records_null_git_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="pre-build-drift")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    real_snapshot = runner_mod.snapshot_project_inputs
    calls = {"count": 0}

    def drifting_second(model, *, policy):
        calls["count"] += 1
        first = real_snapshot(model, policy=policy)
        if calls["count"] == 1:
            return first
        entries = tuple(first.entries) + (
            identity_mod.SnapshotEntry(
                path="late-input.c", size=1, sha256="a" * 64, mtime_ns=1
            ),
        )
        return identity_mod.InputSnapshot(
            entries=entries,
            sha256="b" * 64,
            newest_mtime_ns=first.newest_mtime_ns,
            policy=first.policy,
        )

    monkeypatch.setattr(runner_mod, "snapshot_project_inputs", drifting_second)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_INPUT_CHANGED"
    record = read_json(result_path(root))
    assert record["schemaVersion"] == 2
    assert record["gitHead"] is None
    assert record["gitDirty"] is None
    assert record["gitEvidence"] == SNAPSHOT_EVIDENCE


# ---------------------------------------------------------------------------
# public CLI/MCP build paths
# ---------------------------------------------------------------------------


def test_cli_build_path_reports_snapshot_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    root = prepare_project(tmp_path, git_repo=False, name="cli-snapshot")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)

    assert cli_main(["build", "--project", str(root), "--preset", "arm-debug"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    identity = payload["data"]["identity"]
    assert identity["schemaVersion"] == 2
    assert identity["gitHead"] is None
    assert identity["gitDirty"] is None
    assert identity["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT


def test_mcp_build_path_reports_snapshot_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path, git_repo=False, name="mcp-snapshot")
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    runtime = ServerRuntime.create(root, tmp_path / "plugin-data", "session-a")

    result = asyncio.run(
        mcp_mod.tool_build_for_request(
            runtime,
            _context(_RootSession([[runtime.project_root]])),
            "arm-debug",
            False,
            300,
            True,
        )
    )

    assert result["ok"] is True
    identity = result["data"]["identity"]
    assert identity["schemaVersion"] == 2
    assert identity["gitHead"] is None and identity["gitDirty"] is None
    assert identity["gitEvidence"] == SNAPSHOT_EVIDENCE


# ---------------------------------------------------------------------------
# hardware admission refusal with zero effects
# ---------------------------------------------------------------------------


def _recordable_segments(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    """The fake ARM GNU image has no PT_LOAD header; admit one fixed segment."""
    monkeypatch.setattr(
        flash_mod,
        "_flash_segments",
        lambda _data, _model, _rel: (FlashSegment(0x08000000, payload),),
    )


def test_flash_admits_current_snapshot_firmware_and_writes_schema_two_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, _record = snapshot_build(tmp_path, monkeypatch)
    payload = b"\x00\xbf\x00\xbf"
    _recordable_segments(monkeypatch, payload)
    client = RecordingFlashClient(payload)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is True, result.to_dict()
    assert [event[0] for event in client.events] == ["attach", "program", "read"]
    receipt = read_json(root / "artifacts" / "migration" / "flash-result.json")
    assert receipt["schemaVersion"] == 2
    assert receipt["status"] == "success"
    assert receipt["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert receipt["gitHead"] is None
    assert receipt["gitDirty"] is None
    assert receipt["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert set(receipt) == _FLASH_FIELDS | {"sourceBaseline", "gitEvidence"}
    assert receipt["buildId"] == identity["buildId"]
    assert receipt["verifiedBytes"] == len(payload)


def test_debug_binding_carries_snapshot_provenance_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, _record = snapshot_build(tmp_path, monkeypatch)
    payload = b"\x00\xbf\x00\xbf"
    _recordable_segments(monkeypatch, payload)
    flashed = asyncio.run(
        flash_firmware(_request(root, identity), RecordingFlashClient(payload))
    )
    assert flashed.ok is True, flashed.to_dict()
    client = BindingClient(payload)
    request = DebugBindingRequest(
        project_root=root,
        probe_id="probe-123",
        target="stm32f407vg",
        workspace_id="workspace-a",
        observation_session_id="observe-session",
        lease_id="lease-observe",
        expected_build_id=str(identity["buildId"]),
        expected_elf_sha256=str(identity["elfSha256"]),
    )

    result = asyncio.run(bind_debug_firmware(request, client))

    assert result.ok is True, result.to_dict()
    document = result.data.to_dict()
    assert document["gitHead"] is None
    assert document["gitDirty"] is None
    assert document["sourceBaseline"] == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert document["gitEvidence"] == SNAPSHOT_EVIDENCE
    assert client.events[0][0] == "attach"


def test_shared_admission_reports_snapshot_facts_without_fake_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, _record = snapshot_build(tmp_path, monkeypatch)
    payload = b"\x00\xbf\x00\xbf"
    _recordable_segments(monkeypatch, payload)

    facts = load_fresh_firmware_facts(root)

    assert facts.build_id == identity["buildId"]
    assert facts.git_commit is None
    assert facts.git_dirty is None
    assert facts.source_baseline == SOURCE_BASELINE_INPUT_SNAPSHOT
    assert facts.git_evidence == SNAPSHOT_EVIDENCE


def test_admission_still_rejects_tampered_snapshot_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, identity, _record = snapshot_build(tmp_path, monkeypatch)
    document = read_json(identity_path(root))
    document["gitDirty"] = False
    document["buildId"] = compute_build_id(document)
    identity_path(root).write_text(json.dumps(document) + "\n", encoding="utf-8")
    client = RecordingFlashClient(b"\x00" * 64)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_EVIDENCE_INVALID"
    assert client.events == []
