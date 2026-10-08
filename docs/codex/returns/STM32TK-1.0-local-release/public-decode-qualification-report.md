# STM32TK-1.0 public evidence decoding qualification return

Status: `R2_REMAINDER_PASSED_FUNCTIONAL_52_ACROSS_TWO_RUNS_PENDING_PRIMARY_ACCEPTANCE`.
The four assigned test files were committed before execution. The first
primary-approved run retained 45 passed cases and stopped on the bounded
monitor replay setup failure. After the authorized short-ID fixture correction,
the seven-case remainder run passed all seven cases. Together these runs cover
the 52 selected test cases functionally across two bounded executions. This is
not a single 52-case run, and the result is not a qualification or acceptance
claim. The primary agent remains the independent reviewer and acceptor.

## Ownership and source ledger

- Slice: bounded public evidence decoder qualification for the local 1.0 goal.
- Accepted base: `63602bf6dbd2ad5ff2b676678695767e000bbb2a`.
- Branch/worktree: `codex/STM32TK-1.0-public-decode-qualification` /
  `D:\codex-tmp\v10b-0918\r10\dc`.
- Owned test code head before this report update:
  `1b0c3ccd5c40d6e41800d06bbe99624a079cffd5`.
- The r1 execution used test code head
  `c0884af2085b132db0b496e7f42695c0531a7051`; the r2 correction is the
  explicit short pytest IDs only.
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

The first review correction is committed at `c0884af2085b132db0b496e7f42695c0531a7051`.
The malformed 65-step event retains the original valid plan digest so the
public event decoder owns the expected limit refusal. The replay byte test
passes the decoded mapping through `validate_replay_document` before asserting
the raw input remains unchanged.

The r2 fixture correction is committed at
`1b0c3ccd5c40d6e41800d06bbe99624a079cffd5`. It adds explicit short pytest
IDs to the eight existing raw-wire parameter rows while preserving every
payload, parameter value, and assertion. It does not change product code,
schema, or expected behavior.

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
launcher pattern. The launcher is materialized at
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\launch.ps1`.
Its SHA-256 is
`91CD8156686B929A8DF0BAA079D1F0B722199C0F147A703E8380028D51753969`.
Invoke it through explicit PowerShell 7:

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
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m coverage json --data-file D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\raw-coverage\.coverage --include "*/stm32_toolkit/*" --pretty-print --fail-under=0 -o D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\stm32_toolkit.coverage.json
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m coverage json --data-file D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\raw-coverage\.coverage --include "*/stm32_monitor/*" --pretty-print --fail-under=0 -o D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\stm32_monitor.coverage.json
```

The two JSON commands are report generation from the retained single raw
measurement; they do not constitute another test run. Preserve any first
unexpected failure for classification and leave cleanup to the primary.

## Single authorized execution result

The approved launcher was invoked exactly once through explicit PowerShell 7
from the `dc` worktree:

```text
C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\launch.ps1
```

The child started at `2026-09-19T01:41:10.0158331Z` and ended at
`2026-09-19T01:41:15.2784161Z` (5.263 seconds wall time). Pytest collected
52 items, reported 45 passed and two errors in 3.40 seconds, and exited with
code `1`; the launcher also exited with code `1`, without a timeout. The
owned child PID was `24796`, and the launcher released its process handle.
The source worktree was at code head
`e059fdc90dcf7695512ddfa55043262802b0af95`; the owned test bytes were at
`c0884af2085b132db0b496e7f42695c0531a7051`. The exact child command and
source/environment bindings are retained in `command.txt`, `argv.json`,
`heads.json`, and `environment.json`.

The first unexpected failure was the `input-size-limit` row of
`test_shared_byte_decoder_rejects_caller_meaningful_raw_wire_failures`.
Pytest included the 1 MiB-plus-one-byte `raw` parameter representation in
`PYTEST_CURRENT_TEST` while entering setup/teardown. Windows rejected that
environment value with `ValueError: the environment variable is longer than
32767 characters`, before the test body could call the public byte decoder.
Classification: `INFRASTRUCTURE` (bounded test-entry/fixture setup). This
requires primary review; it is not evidence of a product decoder result for
that row.

The complete failure and process evidence is retained at
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification`, including
`child-stdout.txt`, `child-stderr.txt`,
`public-decode-qualification.junit.xml`, `command.txt`, `argv.json`,
`environment.json`, `heads.json`, `tempfile-preflight.json`, `process.json`,
`launch-result.json`, `exit-code.txt`, and `coverage-process.json`.
The real tempfile preflight passed and the child stderr was empty. No raw
coverage database was created because pytest stopped during setup, so both
package JSON reports were correctly recorded as skipped. No retry or cleanup
was performed against the unchanged r1 entry; the primary owns disposition of
this retained evidence.

## Second authorized execution result

The authorized IDs-only correction was executed through a fresh r2 launcher
after primary entry review. The exact launcher and invocation were:

```text
D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\r2\launch.ps1
SHA-256: 10B722E938027E1AA9E2FBAF5198B547E4838CEB767F43F5325ADA365B7C5C60
C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\r2\launch.ps1
```

The r2 entry selected only the failed r1 `input-size-limit` row and the six
nodes that followed it in the original selected order:

```text
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_byte_decoder_rejects_caller_meaningful_raw_wire_failures[input-size-limit]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_v2_reference_rejects_provenance_and_window_contradictions[physical_transport_evidence-False-False]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_v2_reference_rejects_provenance_and_window_contradictions[end_sequence_exclusive-0-True]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_run_references_without_mutation[failed-before]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_the_two_real_run_references_without_mutation[fixed-after]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_closed_physical_transcript_without_raw_selector[failed-before]
tools/stm32-toolkit/tests/test_monitor_replay_contract.py::test_shared_contract_accepts_closed_physical_transcript_without_raw_selector[fixed-after]
```

The r2 child started at `2026-09-19T01:49:31.2484096Z` and ended at
`2026-09-19T01:49:45.1986883Z` (13.950 seconds wall time). It collected and
passed all seven nodes in 6.03 seconds, with child and launcher exit code `0`,
no timeout, child PID `20456`, and a released process handle. The source and
test code head used was
`1b0c3ccd5c40d6e41800d06bbe99624a079cffd5`. The tempfile preflight passed and
child stderr was empty.

The r2 raw coverage database was retained at
`D:\codex-tmp\v10b-0918\r10\e\public-decode-qualification\r2\raw-coverage\.coverage`.
Both package-filtered JSON reports were generated from that same r2 database,
with exit code `0`, at `stm32_toolkit.coverage.json` and
`stm32_monitor.coverage.json` under the r2 evidence root. These coverage
artifacts describe the seven-case r2 execution only. The r1 45-pass execution
has no raw coverage database and contributes no coverage data.

The r1 45 passed cases and r2 seven passed cases provide functional evidence
for all 52 selected cases across two bounded runs. The retained r1
infrastructure failure remains part of the record and is not relabeled as a
single-run 52-case pass. No cleanup was performed; the primary owns evidence
disposition.

## Pre-execution checks

The four-file test baseline passed AST parsing; the r2 IDs-only correction also
passed AST parsing and `git diff --check` before execution. No hardware, build,
package, deployment, remote, or cleanup action has been performed for this
slice.

This report records code head
`1b0c3ccd5c40d6e41800d06bbe99624a079cffd5` before this report commit and does
not record its own final commit SHA.
