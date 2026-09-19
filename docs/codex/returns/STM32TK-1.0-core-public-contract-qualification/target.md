# Target public-contract qualification return

## Ownership and source identity

- Owner: Target qualification test implementation.
- Accepted base: 0a6bf2a6c591e5e89c6451050de3087168b77eb4.
- Runtime source identity required by the plan: a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d.
- Test head before this report commit: d0b76b3151ab3ccbf951c3a3ff0b9c373d6903c1.
- Product/runtime source files changed: none.
- Owned test files changed:
  - tools/stm32-toolkit/tests/test_target_runner.py
  - tools/stm32-toolkit/tests/test_testing_workflows.py

The test head adds one finite public Target lifecycle wave. It uses the existing
fake probe, guarded flash, transport, workflow, and EvidenceStore seams. It does
not invoke real pyOCD, probe discovery, hardware, build, package, or install
paths.

## Actual function selectors

The selectors below are the functions added or materially extended by this
head. Parameterized selectors are shown with their bounded case IDs.

- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_cancellation_closes_transport_but_preserves_borrowed_probe
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_failed_stream_settles_authority_and_borrowed_probe
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_borrowed_probe_success_reloads_published_evidence
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_prepare_rejects_cross_bound_support_before_authority_write[backend]
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_prepare_rejects_cross_bound_support_before_authority_write[target]
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_prepare_rejects_cross_bound_support_before_authority_write[mailbox]
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_prepare_rejects_cross_bound_support_before_authority_write[extra]
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_rejects_malformed_consumed_value_before_dispatch
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_prepare_rejects_malformed_public_request_before_provider (four bounded parameter cases)
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_prepare_binds_fixed_facts_and_settles_provider[False]
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_prepare_binds_fixed_facts_and_settles_provider[True]
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_execute_rejects_invalid_authority_before_loading_state

The workflow request selector uses four parameter values defined in the test;
pytest node IDs are intentionally left to the execution environment because
collection was not run in this implementation wave.

## Missing guard and public trigger map

| Public trigger | Guard group exercised | Contract assertion |
| --- | --- | --- |
| TargetTestRunner.run with an async transport read cancelled by the caller | Transport polling deadline/cancellation path and required dependency cleanup | Cancellation propagates; transport closes; borrowed probe remains open; consumed authorization remains settled; no pass manifest is published. |
| TargetTestRunner.run with an incomplete public event stream | Decoder/validator failure after flash and run cleanup | Stable stream error; transport closes; borrowed probe remains open; consumed record remains; no evidence manifest is created. |
| TargetTestRunner.run with a valid fake stream and owns_probe=False | Guarded flash, transport lifecycle, artifact publication, and evidence-store durability | Raw event bytes reload exactly; stored envelope reloads equal to the returned envelope; transport closes; borrowed probe remains open; consumed record exists. |
| TargetTestRunner.prepare with backend, target, mailbox, or extra support-profile mutation | Nested support/transport cross-binding and closed profile validation | TEST_PROTOCOL_INVALID before authority record creation. |
| TargetTestRunner.run with consumed=object() | Public consumed authorization model validation before transport factory or flash dispatch | TEST_AUTHORIZATION_INVALID; flash and transport factory are untouched; owned probe cleanup still occurs. |
| target_test_prepare with empty probe, empty cases, non-boolean recovery, or non-portable recovery probe | Public request validation and recovery profile boundary | TEST_PROTOCOL_INVALID before project state/provider construction; no provider call. |
| target_test_prepare with recovery disabled/enabled through an existing provider seam | Fixed firmware facts, identity binding, attach/cleanup lifecycle, and recovery bypass | Binding contains exact case and recovery values; normal mode starts/attaches/closes provider; recovery mode skips provider startup. |
| target_test_execute with a malformed authorization digest | Public authorization gate before state loading | TEST_AUTHORIZATION_INVALID with empty details and no state/provider call. |

Private guards are reached only through these public runner/workflow boundaries.
No new direct private-helper coverage or impossible invariant bypass was added.

## Static verification

The only verification performed in this preparation wave was AST parsing and
whitespace validation:

    python -c "import ast,pathlib; p=pathlib.Path(...); ast.parse(p.read_text(encoding='utf-8'))"
    git diff --check

Both owned test files parsed successfully and the diff was clean. Pytest,
pytest collection, product imports, coverage, build, install, hardware, and
runtime execution were intentionally not performed. The tests therefore remain
NOT_RUN until the primary releases the serial execution batch.

Reserved runtime evidence roots, not populated by this implementation turn:

- D:\codex-tmp\v10b-0918\r10\e\core95\target
- D:\codex-tmp\v10b-0918\r10\t\c95\t

## Remaining barriers

The target residual inventory is 44 source files and 937 missing arcs; that is
an upper bound, not a quota. This wave covers only the public lifecycle families
listed above. Target protocol and transport edge matrices, probe service/lease
and worker branches, MCP adapters, replay/publication validation, process and
OS-specific cleanup, real pyOCD/device identity, and physical evidence remain
in the denominator until their existing public seams are executed or explicitly
deferred.

No coverage or pass claim is made before the primary's independent diff review
and one released serial batch against the verified runtime source identity.
