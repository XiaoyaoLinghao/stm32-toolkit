# STM32TK-1001 debug probe evidence identity plan

Accepted base: `c1777b6be911e26b942c1b127baa799f503d071d`

Implementation owner: one GPT-5.6-luna/max agent in a D-drive isolated worktree. Review and acceptance owner: GPT-5.6-sol.

1. In `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`, derive the flash evidence probe identifier as SHA-256 of `DebugBindingRequest.probe_id` and pass only that value to `_validate_flash`.
2. In `tools/stm32-toolkit/tests/test_debug_firmware.py`, use a production-shaped hashed `flash-result.json:/probeId` and prove: same probe and workspace reaches the existing attach seam; another probe is rejected with `DEBUG_FLASH_MISMATCH` and zero attach calls; another workspace is rejected with the same code and zero attach calls.
3. Run only the focused debug-firmware tests and any directly affected existing debug binding regression. Store caches and test output under a run-owned D-drive directory.
4. GPT-5.6-sol reviews the complete accepted-base-to-code-head diff, runs focused verification against the returned commit, records the reviewed code head in a short return report, and fast-forwards the existing local branch. No remote action is authorized.

