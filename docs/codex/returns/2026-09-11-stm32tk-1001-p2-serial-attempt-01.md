# Serial acceptance: P2 attempt 01

Status: **TERMINAL_STOPPED**. No T9, T10 or VS10-A physical acceptance is claimed.

The user authorized starting serial acceptance. One normal P2 Target prepare/execute ran through the deployed candidate `5f036363383e6c85cc87426da1b4a1c20dfe7acc`, using fresh session `vs10a-t9t10-p2-20260911-01`, case `d4-heartbeat`, and the newly prepared action digest. No retry or under-reset fallback was performed. All subsequent hardware stages stopped on failure.

Prepare exited 0. Execute exited 2 with `TEST_EXECUTION_FAILED` and no details. The actual flash receipt from this session records success and 54,896 verified bytes, matching P2 build `77d787ee83f744831316f9531b825935ef276520472221a8174f7a7d4cfe57f9` and ELF SHA256 `10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead`. The full build identity is authoritative in the retained receipt. Probe connection and flash/readback succeeded; there is no published TestRun or retained raw Target stream. The precise post-flash failure is not established by the public error alone.

The user subsequently asked whether D4 was constantly lit. This is a field-observation clue, not an independently captured GPIO/core-state measurement. A steady LED would differ from the expected P2 heartbeat; neither successful flash nor the LED state proves normal execution or a specific halt/reset fault.

Cleanup evidence records the lease as released and zero matching runtime processes. P2 source/ELF, -12 100ms continuous no-halt physical PASS and attempt 7 historical PASS hashes remain preserved. The prior canonical flash receipt was copied before execution; the canonical receipt now represents this new successful flash and must not be mixed with old sessions.

All current evidence is retained under `D:\codex-tmp\t9t10-p2-20260911-01`: `result.json`, prepare/execute responses, `flash-result.json`, prior flash receipt, prepared binding, consumed marker, released lease, session file inventory and preserved hashes. The empty run-owned temporary directory was removed. No hardware command was issued after the terminal failure. Root cause and any repair require offline analysis first; a hardware retry requires new explicit authority.

## Offline follow-up: migrated control-authority blocker

The user confirmed D4 is steadily lit. No reset, reconnect, power cycle or hardware read was performed during this follow-up. An ENVIRONMENT blocker is now independently reproducible against the real installed runtime and current data: the global control authorization authority retains C-volume identities, while its directories are on D.

The comparison is `probe/authorization.py:297-302`, inside `ControlAuthorizationStore._authority_lock`: persisted `parent`, `root`, and `records` dictionaries must equal current `os.stat` device/inode identities. Persisted values come from `data/.87547cbd313cf8847ab3f942c230a1de0cec2d3108d11ad4b9ddd1e206de54c6.control-authority.json`; actual values come from `data`, `data/control-authorizations`, and its `records` directory respectively.

| Field | Persisted expected device / inode | Actual D device / inode |
| --- | --- | --- |
| parent | 9429648286015755375 / 11540474046044328 | 2063488474270118270 / 562949955196612 |
| root | 9429648286015755375 / 6755399443056853 | 2063488474270118270 / 281474978485962 |
| records | 9429648286015755375 / 7599824373188836 | 2063488474270118270 / 281474978486455 |

Directly reading current C and D volume IDs confirms the expected device is C and the actual device is D. The preserved authority file predates migration (mtime 2026-09-07). The migration handoff records a byte-preserving campaign copy; this preserves file contents, not filesystem identity semantics.

Minimal offline validation invoked existing `_authority_lock(create=False)`, without preparing or consuming an authorization. It rejected with `PROBE_AUTHORIZATION_INVALID`, caused by `authorization authority identity changed`. Existing `PhysicalTargetFlashAdapter._raise_start_error` at `testing/target.py:950-958`, then `_exception_result` at `testing_workflows.py:197-228`, map it to the observed `TEST_EXECUTION_FAILED` with empty details. Evidence: `offline-control-authority.json`, `offline-authority-gate-reproduction.json`, and the preserved `legacy-control-authority.json`. No new diagnostic framework or product code was introduced.

This proves a current deterministic blocker before a reset/resume control authorization can be persisted. It does not recover the original swallowed exception or prove that no earlier post-flash operation failed first. Flash/readback success is confirmed; actual reset dispatch, resume, GPIO state, core state and the precise cause of the steady LED remain unmeasured. No physical TestRun or current-session control authorization was found.

Minimal correction proposal: preserve the complete old global control ledger (10 record files) together with its paired authority file outside the active data namespace, then let the existing store initialize a new D identity and only fresh authorizations. Do not rewrite inode pins, delete individual consumed markers, relax validation or revive any old digest. No packaging change is required. This proposal has not been applied; any correction and subsequent one-shot hardware verification must respect their explicit authorization boundaries.

## Authorized environment correction

The user subsequently authorized the correction with “开始修复”. The old global ledger (11 files including 10 authorization records) and paired authority were moved together into `D:\codex-tmp\control-auth-repair-20260911-01\archive`; every archived file and the authority match the pre-move SHA256 inventory. No old authorization was restored into the active namespace.

The installed runtime's existing `ControlAuthorizationStore._authority_lock(create=True)` initialized an empty D ledger and its authority. A fresh store instance then reopened it with `create=False`; all parent/root/records identities matched. This uses the same identity initialization/check boundary as prepare, without fabricating a Target snapshot or preparing/consuming a control authorization. Active record count is zero. The new D device ID is `2063488474270118270`, with parent inode `562949955196612`, root inode `1688849862539801`, and records inode `1688849862539802`.

The confirmed filesystem-identity blocker is corrected offline. Deployment remains `5f036363383e6c85cc87426da1b4a1c20dfe7acc`; no product code, firmware, packaging or runtime was changed. P2 tracked state, source/ELF, last flash receipt, -12 and attempt 7 hashes remain unchanged. No hardware access, reset, power cycle, prepare/execute retry, or P4 authorization occurred. The LED/core state has not been measured or restored by this environment correction, and physical acceptance remains pending.

Evidence in the repair directory: `preflight.json`, `archive-verification.json`, `fresh-authority-verification.json`, and `preservation-verification.json`. The one attempted temporary-directory cleanup was rejected before execution with `blocked by policy`; the directory remains retained, without retry. Further hardware verification requires new authority and a fresh Target action.

## Normal Target verification 02 after repair

With the user's new authorization “开始进入正常的target验证”, one normal prepare ran in fresh session `vs10a-t9t10-p2-20260911-02` against the unchanged deployed candidate and P2. It exited 2 with `TEST_EXECUTION_FAILED` and empty details. No action digest was returned, execute was not invoked, no flash occurred, and the canonical flash receipt remained byte-identical to attempt 01. There are no session artifacts or TestRun. Hardware activity stopped without retry or under-reset fallback; the lease is released and runtime process count is zero.

An existing read-only control-authority check still passes. The repaired environment blocker remains closed; this failure is at prepare, earlier than the prior post-flash failure. The source route is `testing_workflows.py:467-574`: normal OBSERVE attach, identity proof, fresh facts, then Target authorization preparation. Original inner code/details are absent, so neither the exact failing operation nor a core-state/resume diagnosis is established. Current evidence is `D:\codex-tmp\t9t10-p2-20260911-02\result.json`, `prepare.json`, `prepare.stderr.txt`, `control-authority-still-valid.json` and `released-lease.json`.

The next bounded diagnostic should reuse one normal prepare while retaining its original exception code/details before `_exception_result` normalizes them; stop after that prepare whether it fails or succeeds, without execute, flash, reset, under-reset fallback, or retry. A hardware run requires new explicit authorization. No new diagnostic framework, public error-code change or product modification is justified solely by this undifferentiated error.

## Diagnostic prepare 03: resume postcondition failure confirmed

The user authorized the single diagnostic prepare with “开始”. Fresh session `vs10a-t9t10-p2diag-20260911-03` ran the existing normal prepare once, with an in-process wrapper recording the exception before returning the existing normalized result. No installed source or hardware behavior was changed. Prepare exited 2; no digest, execute, flash or TestRun followed.

`original-exception.json` now proves `ProbeClientError / PROBE_ATTACH_FAILED` at `target_test_prepare:513` (`await client.attach`). `attachDiagnostic.primary` is `stage=resume-verify`, `reason=postcondition-failed`, `sourceCode=PROBE_ATTACH_FAILED`; `lastVerifiedTargetState=halted`. In `probe/pyocd_backend.py:979-987`, normal attach calls resume and then requires `get_state()` to report running. Existing same-attach cleanup recorded candidate-resume succeeded but candidate-resume-verify failed its postcondition; session close, probe close checks and worker-parent-abort succeeded. This was normal failure cleanup, not a second externally dispatched prepare. The final lease is released and runtime process count is zero.

The confirmed failure is restoration to running during normal attach, not a flash failure or inability to halt. The reason the core remains or re-enters halted is still unknown: PC, DFSR and the original breakpoint/exception cause were not captured. A possible explanation is the interrupted post-flash reset leaving execution at a flash algorithm stop point; installed PyOCD `flash/flash.py:635-640` documents that flash operations end halted, but no observed PC proves that hypothesis here. A single user-performed board power cycle followed only by LED observation is a possible next baseline check; it has not been performed by the agent and does not itself prove the original halt cause. No automated hardware retry is authorized.

Evidence: `D:\codex-tmp\t9t10-p2diag-20260911-03\original-exception.json`, `result.json`, `prepare.json`, `released-lease.json`. The flash receipt is unchanged. T9/T10/VS10-A remain incomplete.
