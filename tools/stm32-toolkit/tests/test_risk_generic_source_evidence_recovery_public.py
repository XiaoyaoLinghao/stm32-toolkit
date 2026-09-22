from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from pathlib import Path

from stm32_toolkit.acceptance.recovery import SourceChangeIntent
from stm32_toolkit.acceptance.recovery_workflows import (
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    show_acceptance_scenario,
)
from test_flash import _publish_current_debug_build
from test_risk_recovery_public_producers import (
    ATTEMPT_ID,
    FAILED_RUN_ID,
    _assert_failure,
    _complete_public_tail,
    _data,
    _persistence_snapshot,
    _prepare_prefix,
    _wire,
)


def test_generic_v1_public_source_evidence_refusal_recovery(
    tmp_path: Path,
) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=True)
    context = prefix.context

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    unsupported_continuation = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        continuation={"schema": "stm32-unsupported-continuation/1"},
    )
    _assert_failure(
        unsupported_continuation,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        operation="acceptance.attempt.begin",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    started_wire = _wire(started)
    started_data = _data(started)
    started_attempt = started_data["attempt"]
    assert isinstance(started_attempt, Mapping)
    assert started_attempt["revision"] == 0

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    idempotent = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert _wire(idempotent) == started_wire
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    source_path = prefix.project_root / "App" / "main.c"
    original_source = source_path.read_bytes()
    intent_source = b"int main(void) { return 2; }\r\n"
    source_change_intent = SourceChangeIntent.new(
        changes=[
            {
                "path": "App/main.c",
                "beforeSha256": hashlib.sha256(original_source).hexdigest(),
                "afterSha256": hashlib.sha256(intent_source).hexdigest(),
                "afterSize": len(intent_source),
            }
        ]
    )
    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    before_attempt = _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    physical_only = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
        source_change_intent=source_change_intent.to_dict(),
    )
    _assert_failure(
        physical_only,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert (
        _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)) == before_attempt
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    materialized = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert _data(materialized)["attempt"]["revision"] == 1
    built = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    assert _data(built)["attempt"]["revision"] == 2
    replayed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    )
    assert _data(replayed)["attempt"]["revision"] == 3
    diagnosed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=prefix.diagnostic_compact_id,
    )
    diagnosed_attempt = _data(diagnosed)["attempt"]
    assert isinstance(diagnosed_attempt, Mapping)
    assert diagnosed_attempt["revision"] == 4

    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    action_digest = _data(resumed)["actionDigest"]
    assert isinstance(action_digest, str) and len(action_digest) == 64
    authorized = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    authorized_attempt = _data(authorized)["attempt"]
    assert isinstance(authorized_attempt, Mapping)
    assert authorized_attempt["revision"] == 5

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    before_attempt = _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    unchanged_build = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    _assert_failure(
        unchanged_build,
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert (
        _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)) == before_attempt
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    source_path.write_bytes(intent_source)
    subprocess.run(
        ("git", "add", "App/main.c"),
        cwd=prefix.project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ("git", "commit", "-q", "-m", "generic source evidence intermediate"),
        cwd=prefix.project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    intermediate_identity = _publish_current_debug_build(
        prefix.project_root,
        text_size=288,
    )
    before_attempt_data = authorized_attempt["stageOutputs"]
    assert isinstance(before_attempt_data, Mapping)
    assert intermediate_identity["buildId"] != before_attempt_data["beforeBuildId"]
    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    before_attempt = _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID))
    undeclared_build = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    _assert_failure(
        undeclared_build,
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert (
        _wire(show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)) == before_attempt
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    record, final = _complete_public_tail(tmp_path, prefix, ATTEMPT_ID)
    assert record["recordId"] == ATTEMPT_ID
    assert final["revision"] == 7
    assert final["status"] == "COMPLETED"
    shown = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    resumed_final = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert _data(shown)["attempt"] == final
    assert _data(resumed_final)["attempt"] == final

    shown_record = show_acceptance_scenario(
        AcceptanceWorkflowContext(
            prefix.project_root,
            prefix.data_root,
            context.session_id,
        ),
        record_id=ATTEMPT_ID,
    )
    record_data = _data(shown_record)["record"]
    assert isinstance(record_data, Mapping)
    assert record_data["recordId"] == record["recordId"]
    assert record_data["failedBeforeTestRunId"] == FAILED_RUN_ID
    assert record_data["fixedAfterTestRunId"] == "00000000-0000-4000-8000-000000000003"
