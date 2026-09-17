# Release child environment correction plan

Design: [bounded temporary environment propagation](../specs/2026-09-18-stm32tk-build-temp-environment-design.md). Accepted base `822b705b53da958aca4fa4420c6fdc39b21f7c60`.

1. Existing Luna/max hypothesis_impl owns one clean branch `codex/vs10a-build-temp-environment` in `D:\codex-tmp\t10h-0917\bf`. Sole files: `tools/release/build_0900_artifacts.py`, `bin/setup-stm32-env.ps1`, and `tools/stm32-toolkit/tests/release/test_0900_artifacts.py`. Preserve other agents' changes; no recursion, hardware, remote action or cleanup.
2. Reuse the existing utility import/test seam and capture `_build_wheel`'s actual `_process` invocation. Verify present/absent temporary variables and unchanged build environment/arguments. Retain RED/GREEN commands/stdout/stderr/exit under `t10h-0917\bl`, with all three temporary variables and explicit pytest basetemp/cache there. Update only the utility trust-anchor digest after the final product edit.
3. Primary reviews the complete base-to-CodeHead diff independently, verifies the exact trust anchor and applicable existing archive check, and integrates only accepted bytes. Return corrections to the same owner. No new hardware verification is implied.
4. Final build uses a fresh clean LF packaging checkout and the preserved complete wheelhouse, then existing bundle verifier/Bootstrap/Check and package-byte checks. The earlier failed pre-build invocations are retained as ENVIRONMENT/input failures, not product-candidate failures or successful deployments. Primary owns cleanup within existing policy holds.
