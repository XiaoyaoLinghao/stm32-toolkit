# T10 bounded supplementary hypothesis assessment

Status: proposed; user approval is required before implementation or deployment. Accepted base: `f65302c72817a8f4746bcc363ff60f3c4cbffb57`. Product CodeHead: `2c00d85abc739b404bae0f37e81e8f89263ed8a4`; deployed source: `2c6aedc6f9e85e9db43d2895d26395387c127a6b`. Primary owns design, integration and acceptance; one Luna/max owner implements and tests; a separate reviewer reviews the complete correction.

## Problem and acceptance amendment

Original T10 Step 3 requires discriminating assessments of timer/interrupt, GPIO/board path and application logic. The current Diagnostic only records failed run/case observations and one unassessed application candidate. Production G/H and its FixVerification have independently passed. The original Diagnostic is RESOLVED and must remain immutable.

The installed `ObservationStep.from_value` rejects a Monitor fact selector. Its closed vocabulary contains only run-state, case-state and case-count; these cannot distinguish the three causes. Evidence: `D:\codex-tmp\t10h-0917\evidence\selector-contract-check.json`; model `_selector` and workflow `_resolve_observation_selector`. Additional hardware acquisition cannot repair this software contract gap.

This proposal makes a **new, explicitly retrospective supplementary diagnosis** over the original captured evidence. It does not assert that the missing assessments occurred before the P4 fix. Acceptance would consist of the preserved original physical repair/verification chain plus this newly executed, separately identified assessment chain. This is an explicit amendment to T10's acceptance chronology, not a retroactive completion claim. If the user requires the original sequence without this amendment, a future fully scoped physical campaign needs separate approval; it must not begin automatically.

## Three runnable scenarios

1. Create a separate Diagnostic from the same authoritative failed P3 TestRun with a fresh operation ID. Add three alternatives in evidence order, execute a bounded plan over authenticated immutable Monitor windows, and attach real supporting/refuting assessments. Record the new session ID and actual execution time as supplementary. Preserve the original RESOLVED session, FixVerification, completed v3 attempt and all source/hardware authorizations.
2. Load the supplementary session in a fresh process and reauthenticate/recompute its observations and assessments from the same immutable source bytes. Missing, tampered, replay-shaped, incorrectly bound or insufficient inputs fail without appending an event or accessing hardware.
3. Existing TestRun-only plans and old stored Diagnostic sessions retain their semantics and bytes. Completed G/H is reused; no firmware build, flash, sample acquisition, compare/bundle repetition or new FixVerification is performed to close this supplementary assessment.

## Closed observation contract

Extend the existing plan/execute/assess path with one explicit versioned selector kind, `physical-monitor-fact/1`. Preserve the existing ObservationStep fields and the legacy selector branches. The selector contains exactly:

- `kind`, `continuation_evidence_id`, the complete original `monitor_run_ref`, `selector_kind` (`variable` or `register`), `selector`, `fact`, and `minimum_valid_samples`;
- `fact=value-varies` returns integer 0 or 1; or `fact=bit-values-mask` adds `bit_index` and returns integer 1 (only zero), 2 (only one), or 3 (both observed). Empty input is rejected;
- `bit-values-mask` is register-only. Bit index must be below the authenticated scalar width; minimum is a positive integer within the existing 1,024-batch limit. Current T10 keeps minimum 297 and all 300 original batches.

No arbitrary expression evaluation, user Python, arbitrary paths, injected statistics, interpolation or live reads are allowed. Expected values remain explicit integers in the existing plan. All selected samples must be unique, successful and strictly typed; malformed/ambiguous selected values cause rejection rather than silent exclusion. No source timestamp or sample is edited.

Current supported native scalar profiles are the existing uint8/16/32 register shapes and the actually captured unsigned 32-bit DWARF variable shape (`bitWidth=32`, `typeName=long unsigned int`, exact expression, integer value and matching eight-digit `rawHex`). Reject booleans as integers, out-of-range values, conflicting raw/value/width, unsupported types and duplicate selectors. This bounded variable support does not expand Monitor's analysis request/2 public contract or change existing register comparison behavior.

The continuation proof is mandatory for this new selector and is authenticated through the existing low-level continuation reader. Its failed P3 run/evidence and full identity must match the new Diagnostic's failed source. Each full Monitor reference must equal its stored reference and the proof's actual before/after TestRun relation. Cross-session P4 facts are admitted only through that explicit proof; legacy identity checks are not weakened. The source role comes from the authenticated reference, not a caller override.

## State, ownership and evidence

Use existing Diagnostic start/begin/add-plan/run-plan/assess public adapters and existing idempotent operation IDs/revisions. Do not add a CLI verb, MCP tool, backend, runtime service or second evidence store. Assessments preserve existing explicit polarity/rationale behavior; do not auto-select a cause or fabricate a confidence/status transition. The supplementary session is an assessment record, not another completed source-change or FixVerification chain.

The immutable physical transcript and its original TestRun are the authority for observed facts. The existing continuation proof is the authority for cross-session lineage. The new Diagnostic event chain is the authority for assessments performed now. Plan/result/assessment publication includes the required transcript and continuation evidence references; fresh load recomputes results instead of trusting stored scalar summaries. Reuse existing source authentication and numeric decoding behind one shared fact evaluator, called by both execution and durable-read validation.

Use existing error classes: malformed selector/expected value is a plan error; incompatible source identity is an identity/plan rejection; missing or tampered persisted evidence is an integrity failure; I/O availability remains environmental. The first failure terminates this finite offline chain. No fallback to hardware, raw History, manual event creation or weakened checks.

## Interpretation of the three alternatives

- Timer/interrupt stopped: varying typed `testtime` plus P3 PE4 transitions refute a stopped timer throughout the captured window. They do not prove uninterrupted execution outside that interval.
- GPIO/board-path failure: original P3 PE3-low/PE4 transitions and P4 PE3/PE4 transitions weigh against a stuck output-register explanation. Existing user LED observations and schematic/source anchors are corroboration. ODR is not an electrical pin measurement; unmeasured wiring/intermittent faults remain explicit residual uncertainty.
- Application holds PE3 low: P3 PE3-low while timer/D4 remain active supports this explanation; the exact authorized periodic `LED0=0` to `LED0=!LED0` change and P4 transitions strengthen it. Bind the existing source-diff, source identities and D3/PE3 active-low schematic anchors in the supplementary report. Do not claim that a generic failed-case assertion isolates this cause.

## Scope and required verification

Product scope is the existing Diagnostic model, event/reference handling, workflows and stored-read validation, the shared native Monitor numeric contract, and only a bounded reuse seam in continuation authentication if needed. One implementation owner owns these coupled files. Adapters should pass the existing steps-file unchanged; no unrelated CLI, firmware, lease, sampling or deployment implementation changes.

Required checks: valid current scalar/fact shapes; malformed/range/duplicate/insufficient inputs; wrong run/role/proof/source identity; missing/corrupt or rehashed changed stored observation; fresh-read recomputation; unchanged legacy TestRun selectors and resolved terminal guard. First run one end-to-end chain against a verified copy of the actual evidence, with zero hardware calls and preserved original-file hashes. After independent acceptance and authorized deployment, run the supplementary assessment once against production. Preserve valid existing G/H and physical results. T10 closes only after all original clauses are individually reconciled; Task11/12 and VS10-A remain separate.
