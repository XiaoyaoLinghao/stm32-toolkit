# Managed GCC content identity, slice A

Verdict: **ACCEPTED_WITH_FIXES**, bounded offline software slice, 2026-10-26. Full GCC delivery integration is still pending.

## Ownership and source

- Integration accepted base: `715f316e61821fc96c21a42ebefde213cfab6265`.
- Slice accepted plan/base: `ae259981c5a0b25c213d47e50f64d558c1be32ac`.
- Product CodeHead: `06260a44be9a57918863950682af84d6a604827a`.
- Final CodeHead before report, including final test corrections: `9e9cd9efba5e1c2b1acc4ca68b8cdd8b3eb8ed4a`.
- Branch: `codex/gcc-content-identity`; no remote action, PR or release authorization in this slice.
- Primary owns specification, plan, complete-diff review and acceptance. Implementation/tests used local Claude Code CLI 2.1.308 with existing configured `deepseek-v4.1-flash[1m]`; this describes the configured CLI route, not an Anthropic model.
- Primary clean exact-head review: `C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit`, first at product CodeHead, then at final CodeHead for complete test-only delta and independent execution.

## Accepted behavior

Managed GCC firmware freshness uses declared input snapshots and verified build/artifact content. Current Git availability, HEAD and dirty state are no longer eligibility or freshness gates. Recorded legacy Git provenance remains truthful and strictly checked against its associated records. Snapshot identities carry explicit null Git fields, `input-snapshot-v1` and bounded unavailable evidence; null never means clean.

Snapshot firmware completes the same ELF, MAP, memory, segment and identity validation before normal managed flash. Snapshot receipts use schema 2; legacy receipt bytes are unchanged. Cross-schema downgrade, missing pairs and mistyped booleans are rejected. Debug bindings and IDE handoff preserve the same provenance. Handoff begin/end verify content, release ownership and consume the ticket without manufacturing Git metadata. Context no longer directs no-Git managed outputs to external import; hardware readiness is still not claimed before it is evaluated.

Review corrections tightened downgraded receipt handling, strict schema/boolean decoding and current project/toolkit identity checks. An outdated error-code assertion was corrected after the strict reader rejected malformed `gitDirty` earlier; no product guard was weakened. A snapshot begin/end handoff regression was added.

## Evidence

Run-local evidence is retained under `D:/codex-tmp/gcc26`, including exact argv, source hashes, JUnit, stdout and native coverage. All completed runs below report source unchanged and no skipped cases.

| Owner/run | Source | Result |
| --- | --- | --- |
| Claude `core-author-tests` | Product CodeHead | INCOMPLETE: CLI foreground/background timeout; not counted as pass |
| Claude `core-snapshot-tests` | Product CodeHead | 50 passed |
| Claude `core-runner-tests` | Product CodeHead | 98 passed |
| Claude `core-stale-tests` | Product CodeHead | 27 passed |
| Claude `core-context-tests` | Product CodeHead | 49 passed |
| Claude `core-probe-debug-tests` | Product CodeHead | 457 passed, 1 failed; original assertion failure retained |
| Claude `core-memory-tests` | Product CodeHead | 63 passed |
| Claude `core-ide-tests` | Product CodeHead | 40 passed |
| Claude `core-guidance-tests` | Product CodeHead | 45 passed |
| Primary `core-primary-tests` | Product CodeHead | 26 passed |
| Claude `core-final-author-tests` | Final CodeHead | 156 passed: both changed test files, including the corrected failure and new end-handoff case |
| Primary `core-final-primary-tests` | Final CodeHead | 27 passed: complete new snapshot-admission file |

The eight smaller author groups cover 830 distinct cases at product CodeHead. Final tests add one case and replace the old failed assertion with a verified strict-error expectation. Unchanged product and test evidence is explicitly reused; this is not a full 831-case rerun at final CodeHead. Independent cases overlap author cases and are not added to coverage totals. Existing third-party Pydantic deprecation warnings do not change these results.

Final commands:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/v133-review/STM32-Toolkit' '9e9cd9efba5e1c2b1acc4ca68b8cdd8b3eb8ed4a' 'core-final-author-tests' 'core-final'
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' '9e9cd9efba5e1c2b1acc4ca68b8cdd8b3eb8ed4a' 'core-final-primary-tests' 'core-new'
```

Native PowerShell registration and actual execution were verified; final Claude session `e1447a88-957e-49da-b713-56db005c3816` contains one actual native tool call/result. File-only authoring and verification remained separate. The original long test command was split into shorter exact commands after timeout, without changing shell permissions or interpreting partial output as success.

## Remaining work and boundaries

Evidence/Host/Target/controlled-debug consumers and Monitor/analysis/diagnostic continuation are subsequent B slices. Independent migration public delivery, explicit source-intent remediation and combined new-project/migration GCC journeys remain integration work. No hardware, original project, installed runtime, global configuration, version, package or remote changes occurred. This report grants neither release nor physical acceptance.
