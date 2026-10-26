# Reviewed WFI source intent: core acceptance

Verdict: **ACCEPTED_WITH_FIXES**, bounded local software core, 2026-10-26.

## Ownership and source

- Accepted base: `23e157cf7c8be9a55d45b8d167efa5b91c15167d` (M2 independent public delivery).
- Product implementation: `7e77da15371302f13e6bd01c368da537de3d6235`.
- Final CodeHead before this report: `5634d7e252ae042b34f44ec723e8965a0546551e`; the final delta corrects only one new test file.
- Branch: `codex/gcc-source-intent`; no PR or remote action.
- Primary owns the [GCC delivery specification](../../../superpowers/specs/2026-10-26-gcc-delivery-contract.md), [source-intent plan](../../../superpowers/plans/2026-10-26-gcc-source-intent.md), orchestration, independent complete-diff review and acceptance. Local Claude Code CLI 2.1.308 implements code/tests through the existing `deepseek-v4.1-flash[1m]` route; this is not an Anthropic-model attribution.
- Independent review checkout: `C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit`, clean and detached at the final CodeHead.

## Accepted behavior

Analysis, preflight and independent delivery accept a bounded immutable selection of exact project-relative C paths and function names. A selected plain, unconditional, file-scope, zero-argument ARMCC WFI-only wrapper becomes ordinary non-naked C executing `__asm volatile ("wfi" ::: "memory");` and returning normally. This records requested source behavior; a Keil binary or disassembly baseline is not a prerequisite.

Unknown instructions, parameters, storage prefixes, conditional/macro/nested contexts, duplicate or unused selections and malformed WFI punctuation remain explicit errors. Existing explicit-return and MSP/interrupt translations retain their previous behavior. Comments, BOM, newline convention and adjacent source remain covered by regression tests. Nonempty choices and original/converted source hashes participate in delivery identity, preview/report and apply recomputation. Original sources are not modified. No-choice option shapes are retained; the historical in-place MigrationPlan API is not extended.

Only a scanner-established eligible WFI candidate receives the `wfiReturns` remediation. An internal trusted hint distinguishes it from unrelated embedded assembly; filenames and diagnostic text cannot spoof that hint. Other assembly receives source-port guidance without an unusable required option or a binary-baseline prerequisite.

## Review corrections and evidence

Primary review removed an unnecessary extension to the historical in-place API, required logical-directive handling for comments and LF/CRLF splices, separated strict selected-WFI grammar from the permissive legacy diagnostic tokenizer, and corrected the overly broad remediation classification. All product corrections were made by Claude before the product freeze.

| Owner/run | Head | Result |
| --- | --- | --- |
| Claude `wia` | Product implementation | 109 passed, 2 failed; retained |
| Primary `wip` | Product implementation, clean review tree | Same 109 passed, 2 failed; retained |
| Claude `wib` | Product implementation | 191 passed: migration plan/apply/independent delivery |
| Claude `wic` | Product implementation | 84 passed: preflight/startup/extra-region routing |
| Claude `wif` | Final CodeHead | 112 passed, 0 failed, 0 skipped |
| Primary `wiq` | Final CodeHead, clean review tree | 112 passed, 0 failed, 0 skipped |

The two initial failures were new-fixture mistakes. A semicolon-bearing explicit-return body was incorrectly expected to match legacy grammar; the corrected test retains that unsupported negative and adds a valid multiline explicit-return case. The GCC fixture selected a destination inside its source directory and correctly hit `DELIVERY_SOURCE_DESTINATION_OVERLAP`; its output is now a distinct sibling. No product guard was loosened. The initial compiler case did not execute the compiler; only the final passing runs provide that evidence.

The final focused runs use the real CubeCLT ARM GCC and objdump to compile the delivered function and inspect its generated object for WFI and normal return, without CPSID. This examines generated GCC output, not a required Keil baseline. Temporary projects and output roots are isolated; no user firmware or hardware is accessed.

The 275 related passes are explicitly reused because the final delta changes only the focused test file; product code and those tests are byte-identical in Git. There are 387 distinct author cases with passing evidence across these cohorts, not a final-head repository-wide rerun. The primary 112 cases overlap and are not added. One existing Pydantic forward-reference warning in the routing cohort remains non-fatal.

Exact final commands:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-creation/STM32-Toolkit' '5634d7e252ae042b34f44ec723e8965a0546551e' 'wif' 'source-intent-new'
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' '5634d7e252ae042b34f44ec723e8965a0546551e' 'wiq' 'source-intent-new'
```

`D:/codex-tmp/gcc26/{wia,wib,wic,wip,wif,wiq}` retain exact argv, owner, source hashes, unchanged-source checks, stdout, JUnit and native coverage. Global-dispatch runs `source-intent-global-{core,correction,final-review,verify,fixtures,final-verify}` retain initialization and native tool events. The initial file-only author reached its turn limit; its edits/logs were retained and reviewed, not called complete. Later bounded edits completed. Verification initialization exposed native PowerShell, its harmless smoke actually executed, and designated commands used a 600000 ms tool timeout. Final verification session `8a4571ea-8f2d-48d9-b038-8274ead0181d` has matched command/result evidence and fresh passing reports. A missing native numeric exit remains null; the run-local process record separately records exit 0.

## Remaining boundary

M3b still must expose the repeatable CLI/MCP option, update the concise migration/VS Code guidance and verify the complete reviewed encoding-preparation route, including headers. This core acceptance does not claim those public adapters are available yet. Integration with content-based managed flash, Monitor consumers and the two complete GCC journeys remains outstanding. No version, installation, global skill, remote, release or physical-hardware change is included here.
