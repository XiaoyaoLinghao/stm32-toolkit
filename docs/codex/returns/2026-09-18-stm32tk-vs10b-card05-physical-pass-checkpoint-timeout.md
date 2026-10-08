# VS10-B card05: physical repair passed; final checkpoint timed out

Status: **PHYSICAL_REPAIR_AND_FIX_VERIFICATION_PASSED; ACCEPTANCE_CHECKPOINT_TIMED_OUT; VS10-B NOT ACCEPTED**. This supersedes the current-state wording of card04. No hardware retry follows this stop.

## Ownership and frozen baseline

The user instruction “重新开始” authorized card05's finite remaining loop. Primary owned orchestration, integration, independent full-diff review and hardware; original Luna/max firmware owner implemented the single source correction and one Debug build; capture owner prepared configuration only. No push, PR or merge was authorized or performed.

- Integration documentation base: `efc97dc4dc710939238ed6e843dc64f3500eaf3a`, branch `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`.
- Deployed software: `12df4fe0569104d6f0e7a827496341d999e1f3ea`, existing healthy runtime reused without deployment.
- Firmware accepted before base: `d29281dcaec546f8d2b430e71620067fa0586c34`; fixed head: `8445c769c5ccf116411eb682ad41edcadf1e8ab7`, branch `codex/vs10b-svd-configuration`.
- Run root `D:\codex-tmp\v10b-0918`; evidence `evidence\closed-loop-05`; project `p\b`; deployed runtime `dgdep\data\runtime\0.9.0`. TEMP/TMP/TMPDIR were bound under this root.

## Actual completed behavior

| Evidence | Result |
| --- | --- |
| Fault Target `target-v2-5a478f28f6352a2c1b5aeff01f9fd848` | Physical expected failure only in `d3-heartbeat`, `timer-or-pe3`; flash and readback succeeded. |
| Before Monitor `a752a900-a186-46e1-af32-697aebdfb990` | 300 valid batches / 30 seconds / 10Hz, no drops; testtime varies, PE3={0}, PE4={0,1}; stopped and released. |
| Diagnostic `77e26cc9d4baaceb52ba00b333836e6d` | Existing physical-fact functions matched all three actual observations; H3 supported by PE3 evidence and inspected periodic source. |
| Source correction | Only `App/vs10_app.c` periodic PE3 `WritePin RESET` changed to `TogglePin`; initialization and PE4 unchanged. Actual source authorization preceded mutation. Primary reviewed complete base-to-head diff in clean detached `rv\f05`; source and ELF hashes matched. |
| Fixed Target `target-v2-38c8d4d3c204915e4ab3f27f3f23eead` | Physical PASS, passed=1, failed/error/timeout/skipped=0; flash/readback succeeded. |
| After Monitor `7d8575ca-88a5-4c58-8bd0-5d043a7c5a1e` | 300 valid batches / 30 seconds / 10Hz, no drops; testtime varies, PE3={0,1}, PE4={0,1}; P95 interval 102.3329ms, P99 105.1275ms; stopped and released. |
| Compare and bundle | Physical request/2, GPIOE.ODR, 300 aligned pairs, VALID / COMPLETED / changed=true; both public commands succeeded. |
| FixVerification | `2802be0ae4f00f1769c68a25cee0d7665720a231897672a93fb26a19b546f654`, PASSED / VERIFICATION_PASSED; Diagnostic revision15 / RESOLVED, confirmed by a fresh public read after the timeout. |

Before build/input/ELF: `db585b5cb902b7ee4f7f53281bbed4f7af1e26fd2a39e8b3e767bbf25d8f96b6` / `75b64c62c914ed6470279e85fce5683e7d42c20b2541599867b35f97c9c49377` / `dd8bd1cf4975d9302b1caf5e0139f7bc8f767e669e2e922d2d31be0c01bfb80b`.

After build/input/ELF: `cbf7f4b40102a54f01e55a42d374209281fe084afb4157447e4307600d2542a2` / `a4dabccbffb59ac9e9200e51d01b9eaa26b07f0b902826405aeb9c7d5750c6c3` / `cebe2ca983fcd186111a7e7c675c2b211e2de2a4730ad2cb4e3fd6a34ef8c7ad`.

The two acquired Monitor role markers are consumed and retained. The before and after Target evidence IDs are respectively `cc49dc0629ff566ea78ce5ae6e6c35f76a7f11ed3e9e449d4e885b1a22c79c34` and `4ff018bb8389f15811f9825a4519af1f6389777ea04f97094b8e32debbbcf2c9`. No new operator visual lamp observation is claimed from these machine results.

## Exact final blocker

Attempt `4787a53b-1291-4461-8a50-b984d22ad877`, schema/4, reached revision6 at `2026-09-18T11:43:02.674495Z`. The final-stage deadline was `11:48:02.674495Z`. Fixed Target finished at about11:43:55Z and Monitor command exited11:45:03Z. Verification-complete command exited successfully at11:48:07.3713716Z. Final checkpoint was launched11:48:25.2856746Z, **22.6111796 seconds after its deadline**, and returned exit2 / `ACCEPTANCE_ATTEMPT_TIMED_OUT`.

Deployed `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery.py:150` sets `target-fix-verified` to300 seconds. `recovery_workflows.py:2614` checks current wall time before loading final stage evidence; `_check_deadline_physical` at2664-2666 rejects time beyond `deadline_at_utc`. This failure therefore proves a late acceptance submission, not failed flash, sampling, identity or FixVerification validation.

Classification: **INFRASTRUCTURE / primary orchestration**. Data preparation, result inspection and sequential dispatch remained inside the timed stage. Primary did not complete the final submission within the existing contract. No unsupported product or hardware defect is inferred. The stored attempt remains ACTIVE/revision6 with an expired deadline, as confirmed by fresh `attempt show`; it was not manually rewritten to COMPLETED or TERMINAL. Execution is stopped.

Raw command/exit timestamps are the elapsed-time authority. FixVerification's `completed_at_utc` equals the fixed TestRun end timestamp; it must not be presented as the wall-clock completion time of the later verification CLI.

## Preservation and next boundary

Retain `final-timeline.json`, all public command/stdout/stderr/exit files, actual receipts, both Monitor results/history and markers, firmware sources/artifacts, source declaration, analysis publication/bundle, final public reads and `final-process-check.json`. Final machine result reports released=true/runtimeStopped=true; read-only OS process inspection found no matching runtime/hardware process. No unlock, full erase, extra flash, extra sampling, deployment or remote mutation occurred after the error.

The existing `/4` attempt cannot be completed by replaying the late command, changing a timestamp or extending its stored deadline. First investigate an explicit offline evidence-finalization/continuation contract that preserves this timeout and authenticates the already passed physical graph. No such new behavior is implemented or accepted here. Do not repeat hardware merely to rebuild an acceptance ledger. Previous VS10-A, attempt7, VS10-B NORMAL/IDE/CLI/MCP, deployment and unchanged SVD evidence retain their original scope.

Independent reviewer `/root/vs10b_host_review` reconciled the actual Target/flash, Monitor, Compare, Bundle, Diagnostic and command timestamps, and confirmed these separate pass scopes and the absence of a revision7 publication. Existing `show/resume` only reads the expired chain; it does not extend or close it. Primary retained the reconciled state in `final-ledger.json` and confirmed Diagnostic revision15/RESOLVED/PASSED through a fresh public process.

Auxiliary offline preparation errors (wrong import/serialization method, source wrapper post-write hash-check argument and truncated console projections) remain in their original logs. They were corrected without repeating hardware or build, and are not silently recategorized as successful invocations.
