# Programming diagnostic deployment and stopped prepare

**DEPLOYMENT_PASS / TERMINAL_STOPPED_PREPARE_FAILED.** The accepted diagnostic patch is installed. One normal Target prepare failed before any programming authorization or execute. Physical programming remains unverified; T10 and VS10-A remain incomplete.

Primary owns deployment, hardware dispatch and evidence. Luna/max's accepted product CodeHead is `8e75012e0c92dc37e67d0d31064590772a53be4b`, accepted base `d02a605fb4b43691f03cdccc28c418c0fc0de869`; source packaged at integration HEAD `7d22c149d5f83ded14024569bce9a17734b2b7d1` on `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Prior complete-diff review and affected tests remain valid. No product changes, ownership override or remote authority in this deployment run.

User authorized “继续完成本地部署，然后测试烧录” and confirmed the same connected board/probe, debuggers stopped, wiring/loads unchanged, D3/D4 steady on. Run root is `D:\codex-tmp\p4deploy-0917`; all invocation arguments, stdout/stderr, exits and identity checks are retained there. Old consumed actions and expired T10 attempts are not reused.

## Deployment

The existing builder packaged once from a clean LF checkout using the existing wheelhouse. Bundle checksums/verification passed. Existing setup Check → Bootstrap → Check completed healthy/matching, and **145 installed Toolkit/Monitor files matched the verified wheels**. Installed PyOCD is 0.45.1. Existing offline functions accepted the preserved firmware facts and retained an injected programming diagnostic in the public response; this injection is software evidence only.

- Explicit Python: `D:\stm32tk-data\fault-controlled-20260911\candidates\program-diagnostic-20260917\runtime\0.9.0\Scripts\python.exe`.
- Business DataRoot: `D:\stm32tk-data\fault-controlled-20260911`; its old default launcher still selects an older runtime and was not changed.
- Manifest SHA256: `80dc6d6196c18a99ea766dde3ed5baf3cae11179dcd86d9c94ee820fb445f3cf`.
- Runtime-state SHA256: `c11d102f195c7b7b9dae7fc8a8b1602337eb643ca4ec8bd467b61bee1ef8f771`.
- P4 firmware HEAD `a5ebcab69278d3e25776ba7f9b0ab1376910cdd2`, build `5089b0924da702e38b05d245ae3b05d5f73935c02ee232b097f3e243c132e9fb`, ELF SHA256 `5dfdcdf122f4886132b8270d9abdd7620766af7e81f66770a3e20337440be745`; no firmware rebuild.

## Single hardware operation

The new runtime ran the public CLI `test target prepare`, case `d3-heartbeat`, project `D:\codex-tmp\t10-d3-fw`, fresh diagnostic session `p4-program-diag-20260917-01`, portable probe `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`. Exact tokens are in `prepare-argv.json`; this was not a formal T10 acceptance attempt.

At `2026-09-17T02:18:13.2844840+00:00`, PID 18832 started. It exited **2 after 4873ms**, without timeout, returning `TEST_EXECUTION_FAILED`, `data:null`, `details:{}`; stderr is empty. No action/digest was returned or persisted. No execute, programming, Monitor, manual recovery or retry followed. New registry lease `lease-4d9d9ce475cd4e1e90f8fc07d5f4df90` was released; owned processes exited. The session contains only an empty test-results directory. No current Flash receipt exists; that absence does not establish Flash contents.

Post-operation the user reported **D3/D4 both steady on**, recorded separately in `user-led-after.json`. This is not a measured CPU state or proof that this operation changed the LEDs.

## Offline finding and bounded correction

At this deployed source, `testing_workflows.py:207-238` maps unrecognized typed errors to `TEST_EXECUTION_FAILED` without original details. `target_test_prepare()` at lines 477-584 attaches before preparing/persisting an action. The new lease proves service lease activity, not enumeration or attach success. The generic response does not identify which typed exception occurred. Existing current inputs also pass `_target_state()` offline, recorded in `static-inputs-after-stop.json`; that check does not reconstruct the physical failure stage.

Independent read-only trace by `p4_acceptance_contract` found no persisted original exception. `PROBE_ATTACH_FAILED` is one code that would take this mapping, but it is **not established as this run's original code**. Missing evidence is the original code/message/details, including any attachDiagnostic. Hardware/environment/firmware root cause remains unclassified; programming was never entered.

Primary's execution card incorrectly treated programming-detail coverage as sufficient to remove the existing outer capture for the complete prepare/execute chain. The established procedure already required capturing errors before a lossy mapping. This was a **test-entry INFRASTRUCTURE omission**, separate from the unknown cause of prepare failure. The deployed patch preserves programming diagnostics as designed; its validity is unchanged.

No new diagnostic framework or product patch was added. The existing reviewed `target-capture.py` was copied byte-for-byte into this run root, SHA256 `e25b59830330d18ff339ccbfca414294c9b9279c9ea942f2d2bbd06c85f19de4`. On the new runtime, its existing `--probe-exception-self-check` retained complete synthetic attachDiagnostic and delegated the same error once; `--spawn-self-check` passed using a pure-software Windows child. Both exited 0 without hardware access. These checks prepare future capture; they cannot recover this run's lost exception. SOP §2 now explicitly retains prepare capture when programming diagnostics are available.

Next hardware work requires new authorization after this terminal failure. It can reuse this deployment and firmware; do not repackage, redeploy, revive old actions or retry automatically. The sole missing diagnostic evidence is the original failure at the normal prepare boundary; no recovery-under-reset, unlock, chip erase or speculative control is justified by this record.

Primary retains the run evidence, bundle/source for rollback, runtime, P4 build and original P3 backup. Previous policy-blocked cleanup remains untouched. Historical attempt 7, T9, 100ms, FullFault and P3 results retain their original scope; this run adds no physical PASS.

## Newly authorized diagnostic-02: running postcondition failed

The user explicitly agreed to one normal prepare, outer limit120s, including existing halt/resume and no programming. The exact already-reviewed capture wrapper and deployed runtime/ELF hashes matched before dispatch; existing offline capture/spawn checks were reused. No package/deployment, product edit or test matrix was repeated. A new single-dispatch marker and session `p4-program-diag-20260917-02` were used; the previous action/authority was not revived.

At `2026-09-17T02:36:49.8173674+00:00`, PID24400 ran once and exited2 in **4884ms**, without timeout. Public response remained `TEST_EXECUTION_FAILED`, details={}; the restored capture retained the actual **PROBE_ATTACH_FAILED** from `testing_workflows.py:523` / `client.attach()`. No fresh action was produced; no execute, Flash, separate diagnostic read or retry followed.

`next-prepare-exceptions.jsonl` records:

| Field | Actual evidence | Meaning |
| --- | --- | --- |
| attachDiagnostic.primary | stage=`resume-verify`, reason=`postcondition-failed`, sourceCode=`PROBE_ATTACH_FAILED` | The normal connection reached its resume verification and failed the running postcondition |
| lastVerifiedTargetState | `faulted` | Shared state slot was overwritten by cleanup; this proves cleanup's normalized state, not the initial verify's exact state |
| cleanup candidate-resume | `succeeded` | The cleanup resume call returned; this is not proof that the core ran |
| cleanup candidate-resume-verify | `failed`, `postcondition-failed`, sourceCode=`PROBE_BACKEND_ERROR` | Cleanup did not establish running either |
| remaining cleanup | session-close, probe-open-check-before-close, probe-open-check-after-close, worker-parent-abort all `succeeded` | These cleanup steps succeeded; target recovery did not |
| outer details.stage | `cleanup-resume` | Cleanup error context; it does not replace the retained primary resume-verify failure |

New lease `lease-51ab0d531727491e88d0e97e8d6a11a7` is released, owned PID and related debug consumers are absent, and the new session has no files. Runtime, both old runtime-state files, firmware source/ELF and P3 backup manifest remain unchanged across six hash checks. Temp is empty; all diagnostic evidence is retained and the older policy cleanup hold is untouched. Post-operation LED observation has been requested but is not yet received at this checkpoint.

Offline installed PyOCD0.45.1 source provides the lower-level interpretation: `core/soc_target.py:295-296` delegates state reads to the selected core; `coresight/cortex_m.py:1154-1171` reads DHCSR, with lines1164-1165 mapping S_LOCKUP to `Target.State.LOCKUP`. Address and bit definitions are at lines129/139; `core/target.py:39-50` defines the enum. These hashed excerpts are retained in `next-pyocd-state-source.json`. The physical response does not contain raw DHCSR, the original enum or a fault-register/PC snapshot; those values must not be fabricated from this source trace.

Independent read-only source analysis by `p4_acceptance_contract` identifies the exact checks in `probe/pyocd_backend.py`: normal resume verification at lines1033-1042 requires `running`; its initial actual state is no longer separately available. Cleanup at lines864-922 resumes and reads again, also requiring `running`, and this run retained actual `faulted`. The normalizer at lines788-807 maps LOCKUP/LOCKEDUP to `faulted`; read errors and unsupported states raise `PROBE_BACKEND_ERROR` instead. Thus cleanup's observed `faulted` is not an arbitrary fallback for a read exception. The shared last-state slot is overwritten during cleanup, so the report must not claim the initial check also read that exact state. No state-mapping defect is established. `testing_workflows.py:523` failed before the separate `target_identity()` read at line524, so successful final identity verification is not claimed either.

The immediate blocker is the target's failure to satisfy normal OBSERVE's running contract. The original cause of its abnormal state and the prior programming failure remains unknown. This result does not show that Flash was written, erased or corrupt, nor establish physical board damage. Historical results and T10/VS10-A status remain unchanged.

The existing `test target prepare --recovery-under-reset` route is the bounded next proposal, not an action in this run. Recovery prepare is static; the resulting recovery execute uses SWD100kHz, two planned native under-reset connections and one programming call, with existing sector/keepUnwritten/no-unlock restrictions and readback/test/cleanup. Its September14 P3 result is historical evidence, not current P4 acceptance. `recovery-proposal-after-diag02.md` freezes this route in the run root. New recovery authorization is required; do not create an expiring action while waiting, repeat normal prepare, redeploy or automatically recover.
