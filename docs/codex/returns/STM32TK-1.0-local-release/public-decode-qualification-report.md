# STM32TK-1.0 public evidence decoding qualification return

Status: `PREPARED_FOR_PRIMARY_ENTRY_REVIEW`. The four assigned test files are
committed before execution. This report records the bounded entry and the
pre-execution checks only; it makes no test-result or acceptance claim. The
primary agent remains the independent reviewer and acceptor.

## Ownership and source ledger

- Slice: bounded public evidence decoder qualification for the local 1.0 goal.
- Accepted base: `63602bf6dbd2ad5ff2b676678695767e000bbb2a`.
- Branch/worktree: `codex/STM32TK-1.0-public-decode-qualification` /
  `D:\codex-tmp\v10b-0918\r10\dc`.
- Test code head before this report commit:
  `b89ef23467ad6395eac83968b4a082ceb4f259d8`.
- Implementer: `/root/public_decode_impl`; independent review and acceptance
  remain with the primary agent.
- Owned product import roots for the run:
  `D:\codex-tmp\v10b-0918\r10\dc\tools\stm32-toolkit\src` and
  `D:\codex-tmp\v10b-0918\r10\dc\tools\stm32-monitor\src`.
- Interpreter: `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`.
- No product source, schema, dependency, gate, hardware, package, deployment,
  or remote state changed.

## Delivered test-only change

The test commit adds four focused public-wire qualification groups:

- `test_diagnostic_model.py` rejects non-array lifecycle collections, refuses an
  extended OPEN session without required lifecycle data, and preserves caller
  mappings after refusal.
- `test_diagnostic_events.py` rejects contradictory event envelopes and nested
  plan, result, hypothesis, and extended source-change wires with the existing
  error families and unchanged inputs.
- `test_acceptance_recovery_model.py` rejects malformed v1 stage containers,
  outputs outside the exact stage prefix, partial physical source intent,
  unavailable physical outputs, and unpublished source-intent conditions.
- `test_monitor_replay_contract.py` reloads canonical replay and physical
  transcript bytes, exercises the final-LF option and caller-meaningful raw
  failures, and rejects physical v2 provenance/window contradictions.

The tests reuse the current public fixtures/helpers and assert decoder refusal
without materializing or mutating the caller's wire values. They do not create
hardware evidence or exercise private unreachable states.

## Exact selected node list

The entry selects these 13 new function nodes and six existing positive fixture
nodes. Parameterized functions expand to their declared rows; no whole module
or suite selector is included.

```text
tools/stm32-toolkit/tests/test_diagnostic_model.py::test_closed_models_round_trip_with_fresh_json_containers
tools/stm32-toolkit/tests/test_diagnostic_model.py::test_session_decode_rejects_non_json_lifecycle_collections_without_materializing
tools/stm32-toolkit/tests/test_diagnostic_model.py::test_extended_open_session_requires_lifecycle_data_before_materializing
tools/stm32-toolkit/tests/test_diagnostic_model.py::test_extended_session_decode_rejects_non_array_lifecycle_collection
tools/stm32-toolkit/tests/test_diagnostic_events.py::test_all_event_payloads_are_closed_and_event_round_trip_is_canonical
tools/stm32-toolkit/tests/test_diagnostic_events.py::test_event_decode_rejects_contradictory_envelope_fields_without_mutation
tools/stm32-toolkit/tests/test_diagnostic_events.py::test_event_decode_rejects_nested_public_wire_contracts_without_mutation
tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_physical_policy_and_source_intent_are_frozen_and_round_trip
tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_v1_attempt_decode_rejects_non_json_stage_shapes_without_mutation
tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_v1_attempt_decode_rejects_stage_outputs_outside_exact_prefix
tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_physical_attempt_decode_rejects_partial_intent_and_unavailable_outputs
tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_source_change_intent_decode_rejects_unpublished_wire_conditions
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_replay_documents_without_mutation
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_byte_decoder_reloads_canonical_replay_fixture_and_optional_final_lf
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_physical_byte_decoder_reloads_canonical_transcript_without_mutation
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_byte_decoder_rejects_caller_meaningful_raw_wire_failures
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_v2_reference_rejects_provenance_and_window_contradictions
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_run_references_without_mutation
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_closed_physical_transcript_without_raw_selector
```

## Bounded execution entry for primary review

Do not launch this entry while the covered continuation lock owns exclusive
execution. The primary schedules the one run through the retained finite-child
launcher pattern, with the launcher path reserved as
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\launch.ps1` and
this exact outer invocation:

```text
C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\launch.ps1
```

The bounded child must run from `D:\codex-tmp\v10b-0918\r10\dc` with a
180-second wall bound and these exact pytest arguments:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\dc\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\dc\basetemp --junitxml D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\public-decode-qualification.junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing tools/stm32-toolkit/tests/test_diagnostic_model.py::test_closed_models_round_trip_with_fresh_json_containers tools/stm32-toolkit/tests/test_diagnostic_model.py::test_session_decode_rejects_non_json_lifecycle_collections_without_materializing tools/stm32-toolkit/tests/test_diagnostic_model.py::test_extended_open_session_requires_lifecycle_data_before_materializing tools/stm32-toolkit/tests/test_diagnostic_model.py::test_extended_session_decode_rejects_non_array_lifecycle_collection tools/stm32-toolkit/tests/test_diagnostic_events.py::test_all_event_payloads_are_closed_and_event_round_trip_is_canonical tools/stm32-toolkit/tests/test_diagnostic_events.py::test_event_decode_rejects_contradictory_envelope_fields_without_mutation tools/stm32-toolkit/tests/test_diagnostic_events.py::test_event_decode_rejects_nested_public_wire_contracts_without_mutation tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_physical_policy_and_source_intent_are_frozen_and_round_trip tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_v1_attempt_decode_rejects_non_json_stage_shapes_without_mutation tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_v1_attempt_decode_rejects_stage_outputs_outside_exact_prefix tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_physical_attempt_decode_rejects_partial_intent_and_unavailable_outputs tools/stm32-toolkit/tests/test_acceptance_recovery_model.py::test_source_change_intent_decode_rejects_unpublished_wire_conditions tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_replay_documents_without_mutation tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_byte_decoder_reloads_canonical_replay_fixture_and_optional_final_lf tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_physical_byte_decoder_reloads_canonical_transcript_without_mutation tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_byte_decoder_rejects_caller_meaningful_raw_wire_failures tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_v2_reference_rejects_provenance_and_window_contradictions tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_run_references_without_mutation tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_closed_physical_transcript_without_raw_selector
```

The launcher must set `TEMP`, `TMP`, and `TMPDIR` to
`D:\codex-tmp\v10b-0918\r10\t\dc\temp`, `...\tmp`, and `...\tmpdir`,
respectively, with pytest cache and basetemp under `r10\t\dc`. Its actual
`tempfile.gettempdir()` and a real `tempfile.mkdtemp()` probe must remain under
that `tmpdir`. `PYTHONPATH` is exactly the two `dc` source roots above, and
`COVERAGE_FILE` is
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\raw-coverage\.coverage`.

Retain one raw coverage database, JUnit, stdout, stderr, command, argv,
heads, preflight, exit, and launcher metadata under
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification`. After the
single child exits, derive these package-filtered JSON reports from that same
raw database without another pytest run:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m coverage json --data-file D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\raw-coverage\.coverage --include "D:\codex-tmp\v10b-0918\r10\dc\tools\stm32-toolkit\src\stm32_toolkit\**" --pretty-print -o D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\stm32_toolkit.coverage.json
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m coverage json --data-file D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\raw-coverage\.coverage --include "D:\codex-tmp\v10b-0918\r10\dc\tools\stm32-monitor\src\stm32_monitor\**" --pretty-print -o D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\stm32_monitor.coverage.json
```

The two JSON commands are report generation from the retained single raw
measurement; they do not constitute another test run. Preserve any first
unexpected failure for classification and leave cleanup to the primary.

## Pre-execution checks

The test commit passed AST parsing for all four owned files and
`git diff --check` is clean. No pytest, hardware, build, package, deployment,
remote, or cleanup action has been performed for this slice.

This report is committed separately from the test code head recorded above and
does not record its own final commit SHA.
