# T9 / T10 local delivery

Status: **READY_FOR_SERIAL_HARDWARE_ACCEPTANCE**. T9, T10 and VS10-A physical acceptance remain incomplete. No hardware operation or remote action was performed for this delivery.

- Accepted software slice base: `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1`.
- Independently accepted T9 CodeHead: `6b3b786bded32c78728e53b8732c7e8175c6863a`; T10 CodeHead: `1fa1887a5703cd437cbd852e67c36ec7ce0562c9`. Their owned product bytes match the combined integration; two affected public-contract checks passed.
- Frozen package and deployed source commit: `5f036363383e6c85cc87426da1b4a1c20dfe7acc`. This later report does not change the candidate or require repackaging.
- Ownership remains primary conversation for integration, review and acceptance; existing Luna/max owners for implementation/tests; independent reviewers as recorded in the T9 and T10 software reports. Branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; no remote authorization or ownership override.

One authorized Bootstrap deployed version 0.9.0 into `D:\codex-tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0`. Bootstrap and read-only Check both exited 0; runtime is healthy and runtime state matches the candidate. The existing checks validated dependencies, final-path public launchers, and the 48-tool / 8-skill inventory. A separate byte comparison matched all 144 installed product package files against both source and wheel. No hardware enumeration is implied by API inventory checks.

Manifest SHA256: `bf452effa2dc5b03b4133f138adb228896e4dc4d1cf89ee447fe27bc26b4d673`.
Runtime-state SHA256: `f9f1a6f513097957e38f508772781f0d5bd9907e96d35e0b9499ec5aef64de1f`.
The full prior a463 runtime and state are preserved at `D:\codex-tmp\stm32tk-t9-t10-delivery-20260910\retired-a463-runtime-root`. A rollback must restore the fixed runtime path before using its launchers.

Packaging initially stopped before deployment because the new worktree inherited CRLF archive conversion, then because the runtime-only wheelhouse omitted the two build backends. These were ENVIRONMENT failures: the packaging worktree uses LF and the existing complete D build wheelhouse supplied the backends; all 62 runtime dependency hashes matched the existing release. Product bytes were not changed to address packaging.

Evidence and the reviewed serial execution card are under `D:\codex-tmp\stm32tk-t9-t10-delivery-20260910`: `deployment-summary.json`, `candidate-preparation-summary.json`, `bootstrap.json`, `check.json`, `installed-source-verification.json`, `preserved-baseline-verification.json`, and `serial-acceptance.md`. P2 tracked state, Main.c, ELF, -12 100ms continuous no-halt physical PASS and attempt 7 historical PASS are preserved by hash. Standard VS Code command discovery remains unavailable; the card records the explicit executable and installed Cortex-Debug path, while actual IDE execution remains pending.

The next hardware step requires fresh authorization: one current-P2 normal Target prepare/execute for d4-heartbeat, with matching fresh session, build/ELF/probe identity and action digest; stop on failure without retry or under-reset fallback. The card then covers necessary observations, actual T9 IDE handoff/recovery, P3 expected failure, real Diagnostic and precise source-change authorization, P4 recovery, and physical FixVerification. Current P2 was not changed and no P4 authorization was generated or consumed. Task 11 lineage and Task 12 final historical-diff review remain later acceptance work.

Automatic approval rejected cleanup of the three final run-scoped temporary roots with `blocked by policy` before execution. Those roots and earlier policy-blocked roots remain preserved without retry; `cleanup-summary.json` records the exact final targets. This housekeeping limit does not invalidate software or deployment evidence.
