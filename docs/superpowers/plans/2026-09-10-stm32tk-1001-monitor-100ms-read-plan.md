# Implementation plan: 100 ms Monitor read plan

Status: READY — governing specification approved and implementation authorized on 2026-09-10.
Specification: `../specs/2026-09-10-stm32tk-1001-monitor-100ms-read-plan-design.md`.
Accepted product base: `e83ecdde272c68cf22245aceb06928c46c8b7d93`.
Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
Primary conversation agent owns design, dispatch, integration, independent review and acceptance.
One directly assigned `gpt-5.6-luna` agent at `max` owns product implementation/tests.
No deployment, hardware or remote authority is included in this plan's approval.

1. Freeze the approved spec/plan and local governance edits in explicit local Git
   commits, preserving unrelated state. Record the handoff head separately from the
   accepted product base. Create one clean D: implementation worktree at that head.
   Reuse existing Python/dependencies; all verification temp/cache output stays on D:.
2. Extend the existing production-shaped tests to show that repeated continuous ticks
   still invoke source loaders/guards on the accepted base. Do not repeat the previous
   release matrix or hardware checks. Keep this RED evidence narrowly attributable.
3. Toolkit `debug/read.py`: expose/reuse only private immutable prepared descriptors
   and fresh per-call result buffers needed by a read plan; preserve public standalone
   APIs, grouping, fallback and error behavior. Never retain mutable result buffers
   across ticks, and never cache actual target memory values.
4. Toolkit `monitor_observation.py`: own private prepare/read/invalidate methods. Full
   admission precedes plan compilation; stable reads use captured immutable metadata
   with pre/post root, endpoint, committed-attachment and plan-generation checks.
   Keep existing standalone `_read_batch` compatibility if required by its callers;
   no public request can obtain or supply an unvalidated raw plan.
5. Monitor `probe_session.py`: adapt watch sets to the private prepared path and reuse
   existing binding/report mapping. Monitor `sampler.py`: integrate plan admission
   and synchronous invalidation into existing start/resume/pause/block/stop/close
   transitions. Preserve one producer, its deadline/drop accounting, group revision
   checks and epoch/state check before publication. Do not change core-control code.
6. Run the affected existing tests in `test_monitor_observation.py`,
   `test_probe_session.py`, `test_sampler.py` and relevant debug-read compatibility
   nodes. Add assertions for the exact steady-state call budget, multiple stable
   ticks, independently allocated result buffers, prepare cancellation and lifecycle
   races. Use existing fake clocks/seams; wall-time assertions on fake hardware are
   not product performance acceptance. Preserve minimum failure evidence and reusable
   fixtures; never retry cleanup previously refused by policy.
7. Return exact CodeHead and test evidence. The primary conversation agent reviews
   the complete accepted-base-to-CodeHead diff in a separate clean D: worktree and
   runs only risk-relevant independent checks. Correctable findings return directly
   to the same implementation owner; no model-specific coordinating intermediary.
8. After software acceptance, prepare one candidate offline. Separately request
   deployment and one bounded 30-second hardware window with the exact frozen spec
   metrics. Reuse the existing runner and fresh run/session-derived group name; explain
   any necessary runner changes before implementation. Do not reflash the verified
   firmware. Report software acceptance and physical performance independently.

No source changes beyond the four named product files and their existing test files
without a primary-agent design amendment. No local PASS is inferred from the old e83
hardware result. No extra hardware operation is inferred from goal continuation.
