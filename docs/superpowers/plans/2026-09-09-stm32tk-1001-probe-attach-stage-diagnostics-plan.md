# STM32TK-1001 Probe Attach Stage Diagnostics Plan

Accepted base: `1d461f23fdde8a04c845b7e3989fe41318dd3ed8`

1. In `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`, define the closed attach-stage set and extend the existing safe-detail projection so only exact `{stage: known-string}` survives for `PROBE_ATTACH_FAILED`; keep the register-state contract and fail-closed IPC validation.
2. In `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`, track the active attach phase and place the closed stage on every `PROBE_ATTACH_FAILED` production path, including cleanup-resume. Do not retain the caught exception text or raw identity fields.
3. Update only `test_pyocd_backend.py`, `test_probe_worker.py`, and `test_flash.py` using their existing fake driver, Connection, and flash client seams. Run the smallest focused node set covering stage production, IPC privacy, propagation, zero programming, and worker cleanup, followed by only the directly affected test files if focused GREEN warrants it.
4. GPT-5.6-sol reviews `1d461f23..CodeHead` in a separate clean D-drive worktree, runs proportionate focused verification, writes one short return report, and fast-forwards the existing local development branch only after ACCEPTED.

Evidence owner for implementation tests: Luna/max. Evidence owner for complete diff review and independent focused verification: Sol. All worktrees, test caches, and evidence roots are new paths below `D:\codex-tmp`.
