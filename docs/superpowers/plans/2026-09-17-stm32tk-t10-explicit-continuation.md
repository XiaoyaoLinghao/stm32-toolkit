# T10 explicit continuation implementation plan

Governing specification: `../specs/2026-09-17-stm32tk-t10-explicit-continuation-design.md`. Accepted base `9975bcd3466f949c56801c81d618b2b57493a5a7`; user approved the bounded contract extension with “同意修改”. This plan schedules that approved scope, without another routine plan approval stop. Primary owns specification, integration and cleanup. No remote, deployment, firmware or hardware authority.

Temporary ownership exception: after an explicit request naming the files and behavior below, the user answered “同意”, authorizing primary to complete this offline implementation and its tests. Primary preserves the original Luna/max partial edits; that writer is stopped. The exception covers only recovery, Diagnostic, Monitor, CLI/MCP, GC root registration and corresponding tests; new product helpers are limited to `acceptance/continuation.py` and, only if necessary, `acceptance/physical_chain.py`. It expires after verification. A separate Luna/max worker owns only `test_acceptance_continuation.py`; primary owns the product files and remaining integration tests, with no overlapping write ownership. The independent `t10_continuation_review` agent must review the complete diff and does not implement or self-approve it.

## Frozen work and ownership

Deliver one connected offline scenario, not independent module patches: preserved P3/P4 physical publications → authenticated continuation proof → timed attempt → original-session Diagnostic plus each-side Monitor evidence → successful FixVerification → final continuation checkpoint. Public default compatibility, original identities and expiry immutability are acceptance requirements.

The bounded implementation scope is:

- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery.py`, `recovery_workflows.py`, corresponding `__init__.py` exports, and one bounded continuation model/reader module. A small pure chain-reader extraction is permitted only to remove workflow circular dependencies and reuse existing validation; no generic framework.
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`, `diagnostics/model.py`, `diagnostics/events.py`, `diagnostics/store.py` and corresponding exports, only for explicit continuation and versioned VerificationPlan/reference validation.
- Toolkit `cli.py` and `mcp_server.py`, only existing attempt-begin continuation input and corresponding plan parsing. Do not add tools or alter unrelated adapters.
- `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`, only register the immutable `physical-continuation` root type, with existing reachability verification; do not change GC authorization or deletion algorithms.
- `tools/stm32-monitor/src/stm32_monitor/analysis.py`, `analysis_workflows.py`, `cli.py`, only versioned continuation analysis and adapters. Physical publisher/readers in `replay.py` stay strict; use original-session contexts rather than relaxing their identity checks.
- Existing corresponding Toolkit acceptance/Diagnostic/FixVerification tests and Monitor analysis tests. One bounded persisted end-to-end test file may assemble existing helpers if an existing file would mix unrelated ownership. No production release matrix or new test framework.

Primary owns specification/plan/SOP/integration records. The worker is not alone in the repository: do not revert others' changes or edit primary-owned documents; report a concrete contract conflict before broadening files. No recursive delegation. An independent reviewer must review the complete accepted-base-to-CodeHead diff in a clean exact-head worktree.

## Execution and validation

1. Implement the closed association/v3 attempt models and authoritative immutable reader first. Use original v2/Diagnostic prefix/real TestRun readers, existing EvidenceStore/CAS and positive input/hash checks. Freeze the one shared internal validated-proof type before wiring consumers; no boolean bypass or caller-created trusted object.
2. Wire existing recovery public operations, Diagnostic including persisted event-reference replay, and Monitor compare/bundle including reload. Keep all default v1/v2 payload bytes and guards. Prove the complete persisted chain with two different physical origin sessions and original declaration/validation plan ID.
3. Run focused regression once after local convergence: acceptance physical/recovery models/workflows/CLI/MCP, Diagnostic and FixVerification model/event/workflow/CLI/MCP, Monitor analysis model/workflow/CLI and unchanged physical publication identity checks. Test CLI/MCP continuation parity and unchanged tool inventory. Avoid unrelated probe/firmware/deployment tests; no hardware test module execution.
4. Boundary evidence: exact accepted retry; concurrent single-winner publication; stale predecessor/Diagnostic head; missing/tampered proof or parents; wrong role/pair/probe/workspace/build/source intent; absent association; expiry immediately before root publication. Demonstrate fresh attempt reusing the same proof and valid verification after predecessor/earlier successor expiry. Failure must preserve predecessor/old evidence bytes.
5. Return CodeHead, exact test command/environment/results, changed file scope and any unimplemented requirement. Primary reviews the full diff, independently runs the persisted chain and strongest negative/public-adapter checks, then integrates only an accepted candidate. No extra full test run without a changed behavior or concrete unresolved concern.

## Local environment and evidence

Integration tree `D:\workspace\stm32tk-1001-legacy-hardware-impl`; implementation and review trees under `D:\codex-tmp\t10c-0917\impl` and `review`. Use branch `codex/t10-explicit-continuation`. Test interpreter verified as `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`, CPython3.12.10, pytest8.4.2. C: is used only for this installed interpreter, not temp/output. The deployed D: product runtime lacks pytest and must not be modified.

All temporary output, caches and logs remain under `D:\codex-tmp\t10c-0917`; use short basetemp children such as `b1` and `b2`, never append long descriptive paths before existing hashed fixture staging. Run from the actual worktree root with `PYTHONPATH` pointing to its Toolkit/Monitor src, `PYTHONDONTWRITEBYTECODE=1`, explicit TEMP/TMP under this root, `-B`, `-p no:cacheprovider`, and explicit `--basetemp`. Preserve minimal failure evidence before cleanup. Primary is the sole cleanup owner; do not touch any older policy-blocked cleanup hold or original business data.

The current real P3/P4 evidence may be read or copied to an isolated D: run-owned store for offline loader checks. Never write tests into the business EvidenceStore or edit the real firmware project. Capture original hashes and use the exact existing published identities. A synthetic missing P4 Monitor fixture is software test evidence only; it cannot complete the real T10 acceptance.

Engineering preflight uses GL-001/GL-005 (provisional contract-freeze/failure classification guidance) and STM32TK-EL-003 (provisional deadline-change guidance). One authority for the immutable proof, separate timed completion, existing lock order, and publication-boundary expiry checks are frozen above. No native-memory or lesson-store writes are part of this task.

Acceptance of this slice means software behavior is implemented and independently verified. Existing P4/attempt7/T9/100ms/FullFault/P3 physical evidence remains scoped as recorded; deployment, real fixed-after Monitor, T10 G/H and VS10-A remain separate pending acceptance work.
