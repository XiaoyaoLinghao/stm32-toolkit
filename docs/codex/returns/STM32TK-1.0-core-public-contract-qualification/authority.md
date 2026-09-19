# Authority public-contract qualification return

Status: **IMPLEMENTED; TEST EXECUTION NOT_RUN**.

This bounded Luna/max test wave starts at accepted base
`0a6bf2a6c591e5e89c6451050de3087168b77eb4` on branch
`codex/STM32TK-1.0-core-authority`. The runtime source remains the accepted
`a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d`. The test code head before this
report commit is `7e400ca48b4f84988034079b70496eeaadf3c927`.

Only four existing Toolkit test files changed:

- `tools/stm32-toolkit/tests/test_acceptance_model.py`
- `tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py`
- `tools/stm32-toolkit/tests/test_diagnostic_mcp.py`
- `tools/stm32-toolkit/tests/test_fix_verification_model.py`

The wave adds 30 concrete public invalid-input variants across the accepted
model and recovery authorities. It uses the existing scenario, project
transition, and physical monitor wire factories. No product source, schema,
configuration, dependency, fixture, shared helper, or coverage configuration
changed.

## Added public guard families

| Source authority | Public trigger | Expected result and state assertion |
| --- | --- | --- |
| `acceptance/model.py` definition and scenario wire parsing | `AcceptanceScenario.from_value` receives an unknown scenario, unsupported version, tuple or malformed `requiredStages`, or non-boolean transport flag | Exact `ACCEPTANCE_SCENARIO_UNKNOWN` / `ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED` or `ACCEPTANCE_INPUT_INVALID`; the caller mapping is unchanged |
| `acceptance/model.py` record wire parsing | `AcceptanceRecord.from_value` receives tuple/object stages or a UUID object in a JSON field | `ACCEPTANCE_INPUT_INVALID`; the caller mapping is unchanged |
| `acceptance/recovery_workflows.py` begin adapter | `begin_acceptance_attempt` receives a malformed attempt ID, unsupported scenario/version, or non-string scenario ID | `ACCEPTANCE_ATTEMPT_INPUT_INVALID`; no data root, evidence root, or project file is created |
| `acceptance/recovery_workflows.py` checkpoint adapter | An existing revision-zero attempt receives a boolean/out-of-range revision or unknown stage | `ACCEPTANCE_ATTEMPT_INPUT_INVALID` / `ACCEPTANCE_ATTEMPT_STAGE_INVALID`; resume returns the original revision-zero snapshot and the evidence file inventory is unchanged |
| `acceptance/recovery_workflows.py` resume adapter | `resume_acceptance_attempt` receives a malformed attempt ID | `ACCEPTANCE_ATTEMPT_INPUT_INVALID`; no state is created |
| `diagnostics/model.py` physical observation selector | `ObservationStep.from_value` receives missing v1 continuation evidence, an illegal fact/bit combination, sample or bit bounds, a v2 role mismatch, a non-physical reference, an invalid fact value, or a malformed monitor reference | `DIAGNOSTIC_PLAN_INVALID`; the complete caller wire remains unchanged |
| `diagnostics/model.py` verification plan V2 | `VerificationPlan.from_value` receives a V2 plan without continuation evidence, a legacy schema with the V2 field, or a changed continuation digest input | `DIAGNOSTIC_INVALID_EVENT`; the candidate wire remains unchanged and the valid V2 plan round-trips |

The authority residual source map reports 941 missing arcs across ten source
families. That is an upper bound, not a coverage quota. The cases above cover
the distinct public guard groups reached by this wave; no gain is claimed for
private or unreachable branches.

## Exact selected functions

The primary-owned launcher can select these functions without guessed
parameter IDs:

```text
tools/stm32-toolkit/tests/test_acceptance_model.py::test_scenario_wire_guards_preserve_input_and_exact_error_codes
tools/stm32-toolkit/tests/test_acceptance_model.py::test_record_wire_container_guards_preserve_input
tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_begin_public_input_rejection_publishes_no_state
tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_checkpoint_public_input_rejection_preserves_revision_zero
tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_resume_public_attempt_id_rejection_creates_no_state
tools/stm32-toolkit/tests/test_diagnostic_mcp.py::test_physical_observation_step_wire_guards_fail_closed_without_mutation
tools/stm32-toolkit/tests/test_fix_verification_model.py::test_v2_verification_plan_requires_and_binds_continuation_evidence
```

## Verification and remaining barriers

AST-only syntax inspection passed for all four changed test files. The
inspection used the approved D-drive temporary root with `TEMP`, `TMP`, and
`TMPDIR` bound before Python:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -c "import ast, pathlib; paths=[pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_model.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_diagnostic_mcp.py'), pathlib.Path(r'tools/stm32-toolkit/tests/test_fix_verification_model.py')]; [ast.parse(p.read_text(encoding='utf-8')) for p in paths]; print('AST_OK', *paths, sep='\\n')"
AST_OK
exit code 0
```

`git diff --check` passed. Pytest, collect-only, package imports, builds,
installers, hardware, remote operations, and cleanup were not performed in
this implementation wave. The tests remain `NOT_RUN` pending the primary's
independent complete-diff review and serial selected-node execution. Native
coverage aggregation and any residual disposition remain primary-owned.
