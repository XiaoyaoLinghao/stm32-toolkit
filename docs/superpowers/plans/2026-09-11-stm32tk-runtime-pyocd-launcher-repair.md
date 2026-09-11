# Final-path PyOCD launcher correction

Accepted base: `cdeee36261ff6977dcb07971a583d1f44a1e732f`.
Governing specification: `../specs/2026-08-25-stm32-toolkit-0902-install-upgrade-security-release-design.md`, scenarios B1/B2/B4. User authorized correction and durable deployment guidance on 2026-09-11. This is a correction to the existing offline installation contract, not a new deployment engine.

Primary owns design, integration, deployment guidance and acceptance. One Luna/max worker owns `bin/setup-stm32-env.ps1` and `tools/stm32-toolkit/tests/test_setup_runtime.py`; the primary independently reviews the complete base-to-code diff in an isolated worktree. No remote mutation or hardware is authorized by this plan.

## Scenarios and behavior

1. Bootstrap or Repair installs the manifest-verified PyOCD wheel in staging, promotes the runtime, and regenerates its console launchers with the final runtime Python before publishing healthy state.
2. Check on an existing runtime with a missing/staging-bound PyOCD executable returns broken/Repair guidance without mutation. Module import/version success alone cannot produce healthy status.
3. A bad PyOCD launcher/version during finalization prevents healthy state publication and follows the existing rollback path. The real final `pyocd.exe --version` must succeed offline and agree with the pinned PyOCD version.

Keep existing toolkit/monitor launchers, final-path binding checks, timeouts, verified wheel hash/size/path validation, no-index/no-deps install and rollback semantics. Extend the existing product-wheel selection to include exactly one verified `pyocd` wheel at the existing policy pin (0.45.1); do not reinstall unrelated dependencies or loosen product version equality. Regeneration also replaces the PyOCD wheel's legacy executable, but Cortex-Debug continues to use pyocd.exe plus gdbserver, never the incompatible legacy entry.

Single state authority remains runtime-state.json, published only after final-path validation; no new state format or launcher framework. Non-goals: Cortex-Debug extension changes, generic IDE configuration generation fixes, runtime schema changes, full release rebuild, firmware, probe actions, handoff end/reacquisition, hardware retry, C temp resurrection.

## Verification and delivery

Reuse the Windows `test_setup_runtime.py` real pip/distlib fixture and existing rollback/read-only checks. Add realistic PyOCD console entry-point metadata to the existing fake wheel so tests exercise executable generation, not just module import. Demonstrate regression failure before the fix, then final-path executable success, Check refusal for stale/missing binding, and finalization failure rollback. Run the affected setup test module once after focused checks; no full product/release matrix. Tests run under an attributed D path and retain only concise useful results after cleanup.

The primary captures the observed launcher byte offset/hash, actual IDE session configuration, prior URI/task/argument failures and their source/evidence boundaries in maintained deployment documentation. Guidance must give machine-independent root placeholders, exact final-executable checks, the correct IDE readiness order, and first-error stop behavior; no local probe IDs or old temporary paths as reusable defaults.

After independent acceptance, the current D runtime may receive a bounded offline regeneration from its own verified PyOCD wheel using its final interpreter. Preserve runtime-state, installed product/firmware identities and external reservation; do not run full Repair or repackage/redeploy unchanged products. Record before/after launcher hashes and actual --version results. If safe wheel identity or absence of runtime consumers cannot be established, leave the live correction blocked with the precise reason. Real IDE attach remains a separate newly authorized test after the failed attempt.
