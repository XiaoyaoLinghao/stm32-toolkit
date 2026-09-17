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
