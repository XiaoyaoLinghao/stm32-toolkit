# Public WFI source-intent route

Verdict: **ACCEPTED_WITH_FIXES**, bounded local software slice, 2026-10-26.

## Ownership and source

- Accepted base: `d8c088635760f193fa6b94e71e11e98f23496223` (M3a).
- Product implementation: `ea1bbf99e49cc18c2087f0ea1de24bd5bb539d90`.
- Final CodeHead before this report: `d73bcbd87e450c035d0fafe7ad17e14ed037056d`; subsequent candidate changes corrected only test assertions/test doubles.
- Branch: `codex/gcc-source-route`; no PR or remote action.
- Primary owns the [GCC delivery specification](../../../superpowers/specs/2026-10-26-gcc-delivery-contract.md), [bounded plan](../../../superpowers/plans/2026-10-26-gcc-source-route.md), orchestration, independent complete-diff review and acceptance. Local Claude Code CLI 2.1.308 implements code/tests using the existing `deepseek-v4.1-flash[1m]` route.
- Independent review checkout: `C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit`, clean and detached at final CodeHead. The complete eight-file accepted-base diff and final test correction were reviewed; `git diff --check` passed.

## Accepted behavior

CLI preflight/convert expose repeatable `--wfi-return PATH:FUNCTION`; actual registered MCP preflight/convert expose optional `wfiReturns=[{path,function}]`. Workflow input is a closed bounded list converted to the existing strict immutable core selection, without coercion. Invalid paths, keys, types, duplicate/excess selections and invalid names fail before mutation. No choice retains previous behavior. The historical in-place API is not extended.

The same explicit normal-return choice participates in preflight, independent PLAN and APPLY, including source hashes and reviewed plan identity. Omitting/changing it cannot reuse the reviewed plan. Original sources remain unchanged. The choice describes requested source behavior and does not require Keil disassembly or claim binary equivalence. Other unsupported assembly remains a source-port task.

## Evidence and corrections

| Owner/run | Source | Result |
| --- | --- | --- |
| Claude `wpa` | Product implementation | 33 public-route cases passed |
| Claude `wpb` | Product implementation | 112 source-intent/diagnostic cases passed |
| Primary `wpp` | Product implementation | 33 public-route cases passed |
| Claude `wpc` | `541f6e3eb24203a3b0c05cc4c4d67afa9e3353df` | 33 public-route/schema cases passed |
| Primary `wpq` | Same clean head | 33 public-route/schema cases passed |
| Claude `wpd` | Same head | 157 passed, 1 failed; retained |
| Claude `wpe` | Final CodeHead | 82 workflow cases passed, no skips |
| Primary `wpr` | Final CodeHead, clean review tree | 82 workflow cases passed, no skips |

The schema correction preserved exact property inventories and asserted the actual registered optional array/null schema. A prior file-only schema invocation read an installed dependency outside its read scope and attempted absent Bash; the Bash result proved it unexecuted, and the invocation made no edits. It was stopped without one-shot recovery. The user explicitly authorized a new two-file, no-shell, no-investigation correction; `source-route-global-approved-schema` completed with only the requested file tools and no scope violation. Its main session was `df0a6efa-51bd-451d-8340-bf6477d99c5f`.

The later executed regression failure was a historical `test_workflows.py` test double that did not accept the new `wfi_returns` keyword. Claude added the exact default parameter and an assertion that no-option calls pass the empty tuple; no product guard or existing failure assertion was weakened. `source-route-global-workflow-fixture` completed with native file edits only. The final verify session checked native PowerShell inventory and a real harmless smoke, then executed the designated single command with timeout 600000. CLI completion alone was not treated as passing evidence.

Exact final commands:

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-creation/STM32-Toolkit' 'd73bcbd87e450c035d0fafe7ad17e14ed037056d' 'wpe' 'source-route-workflow'
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gcc26/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' 'd73bcbd87e450c035d0fafe7ad17e14ed037056d' 'wpr' 'source-route-workflow'
```

Run directories under `D:/codex-tmp/gcc26` retain actual owner, argv, exact head, source hashes, unchanged-source checks, stdout, fresh JUnit and native coverage. Global-dispatch `source-route-global-*` directories preserve initialization, native tool/result pairs, original failed runs and correction records. Native success without a numeric exit remains null; the test process record separately records exit 0.

Product code and the unaffected tests are byte-identical after the product implementation. Passing 33 public, 158 affected public/workflow and 112 core cases are source-specific evidence across cohorts (303 distinct author cases), not a final-head repository-wide rerun. The primary checks overlap and are not added. Existing Pydantic forward-reference and runpy warnings are non-fatal. All cases use synthetic temporary projects; no original firmware or hardware was accessed.

## Remaining boundary

M3b2 still owns complete reviewed encoding preparation, concise migration/VS Code guidance and the combined real-GCC independent-delivery fixture. Integration with content-based normal managed flash and Monitor consumers remains outstanding. No installation, version bump, publication, global-skill update or physical acceptance is included here.
