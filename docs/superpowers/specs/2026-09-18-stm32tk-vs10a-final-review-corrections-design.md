# VS10-A complete-range review corrections

Accepted integration base: `d11462ce361ed529baf142590006cb70fc87aee7` (product bytes deployed from `227f8ea8b6895d4c2eaa14bd2483cfbce668b4b9`). The user explicitly authorizes related corrections, verification and justified hardware retesting until VS10-A acceptance. Main owns this design and integration; Luna/max owns implementation/tests and cannot accept its own work. Remote actions remain unauthorized.

## Runnable scenarios and non-goals

1. A physical V2 Target execution that spends time flashing records host UTC when its first decoded run_start is captured, then uses the existing target monotonic deltas. The authorization-time clock and deadlines retain their existing meaning. Successful case outcomes, raw frames and firmware identity do not change.
2. A V2 execution with authenticated host/Probe/transport binding that receives inventory/run_start and then fails retains the exact received bytes in a partial evidence envelope. The original error remains terminal; no completed TestRun or PASS is published.
3. V2 discovery rejects a preceding valid V1 frame followed by V2 inventory, including when split across reads. A pure V2 inventory still completes discovery without waiting for later run frames; bytes after the inventory in the same read retain the existing exclusion rule.
4. ARM linker component totals require RO/RW cross-checks in their own totals footer; an unrelated later section cannot provide them. Valid retained campaign MAP values and classic Program Size precedence remain unchanged. Existing migration/Keil regression fixtures construct the intended valid FPU/output-directory setup so they test their intended behavior.

No new protocol/schema/error vocabulary, public CLI/MCP command, backend, mailbox, hardware behavior, or general diagnostics framework. No board operation is needed to prove these four corrections. Existing T9, T10, attempt7 and P3/P4 evidence remains immutable. Historical V2 absolute UTC is identified as pre-flash anchored metadata; it cannot establish exact host wall-clock acquisition time. Preserve its frame-monotonic durations and authenticated firmware/case outcomes unless a concrete consumer dependency proves otherwise.

## Frozen contracts and ownership

Target owner changes only `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py` and existing Target tests (`test_target_runner.py`, `test_target_protocol_v2.py`, `test_physical_workflows.py`) as necessary. Retain the `assemble_target_v2_run` argument contract. Capture a separate host UTC anchor once on the first decoded V2 run_start; do not reuse operation-start `instant`, move authorization checks, trust target UTC, or alter V1 timestamps. Fully validate the stream before successful publication. Existing deterministic clock seams or test monkeypatching are sufficient.

V2 partial evidence derives identity from the already authenticated host binding, never an invented inventory identity. Retain exact raw bytes, action/error, probe/lease/session and physical provenance sufficient to distinguish partial diagnostics from completed physical TestRuns. Keep the initiating error and cleanup precedence. Evidence-retention failure is reported as an added note, never success. Preserve V1 partial behavior.

At the V2 inventory boundary, check the decoder's accumulated version/recovery failure through the existing decoder contract before returning success. Do not scan or require a later run after a valid inventory, and do not weaken mixed-version errors.

Keil owner changes only `tools/stm32-toolkit/src/stm32_toolkit/keil/baseline.py` plus `tests/test_keil_baseline.py`, `tests/test_keil_inspect.py`, `tests/test_migration_apply.py` under the same Toolkit subtree. The component footer begins after the unique Grand Totals row and admits existing blank/separator lines, recognized ELF Image Totals/ROM Totals rows and Total RO/RW/ROM Size lines. End on unrelated content rather than searching to EOF. Enforce exact unique RO/RW matches, existing integer/overflow/column checks and classic precedence. Validate the retained D-drive intake MAP without touching the golden source or reading old C paths. Fixture corrections create Objects when explicitly writing a decoy there and make the default migration FPU declaration consistent; explicit negative inputs remain negative. Do not relax planner/model behavior.

Both implementation streams use isolated worktrees at the same docs head with disjoint ownership. Primary integrates their commits and owns shared docs. The existing Target reviewer independently reviews both bounded diffs, with primary complete-delta review and applicable verification. No implementation worktree may package or access hardware.
