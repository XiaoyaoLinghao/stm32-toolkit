# POST134 bounded delivery plan

Accepted base: `7e578ca1395ffa3b9743bef5a9fe55c40912eed6`.
Governing approved scope: [specification](../specs/2026-10-28-post134-usability.md).
User approval is the 2026-10-28 instruction to implement the preceding triage; separate
implementation-plan approval is waived under AGENTS.md.

1. Commit this coordinator-owned spec/plan on codex/v134-fixes-integration.
2. Create clean isolated slice worktrees from that governance commit:
   codex/post134-build-presets, codex/post134-cli-diagnostics,
   codex/post134-migration-guidance, codex/post134-flash-investigation.
3. Supply full source/base ledger, exact allowed files/read scope and applicable rules
   to local claude-dispatch edit invocations. Product implementation and tests are Claude's.
   No shell commands belong to edit mode. Inventory must match actual native tools.
4. Review edits, commit slice CodeHead locally, then execute delegated verify with exact
   supplied native PowerShell commands. Use existing CPython 3.12 test environment,
   selected-worktree PYTHONPATH and short independent D:/codex-tmp/f134 run directories.
   Use existing verified ARM GCC/CMake/Ninja only for synthetic GCC cases.
5. For build: complete runner/stale/snapshot and new preset tests; context/content firmware
   admission and appropriate real-GCC synthetic journey. For CLI: new parser diagnostics,
   existing CLI and external firmware routing/workflow. For guidance: migration delivery,
   independent workflow, debug configuration and relevant AI/IDE guidance.
   Split test groups below native foreground limits; retain pending execution correctly.
6. Independently inspect complete slice diffs and meaningful refusal assertions. Correct
   only concrete findings through the same slice's Claude implementation ownership.
   Integrate accepted commits locally; conflict resolution affecting code/tests belongs
   to Claude. No cherry-pick is an implicit acceptance.
7. Freeze integrated CodeHead; create a clean review worktree at that exact head.
   Primary independently runs the new regressions plus affected consumer checks,
   including real GCC preset switching. Do not rerun release matrices/packaging/IDE/hardware.
8. Record implementation-report.md and flash-offline-investigation.md under
   docs/codex/returns/POST134-USABILITY, recording accepted base, pre-report CodeHead,
   actual owners, full evidence paths/commands/results and limitations. Update standard
   test checkpoint only as the primary-owned ledger, not as new hardware authority.
9. Retain the local integrated branch and reviewable committed changes. Archive owned
   disposable worktrees after evidence is retained. Remote state stays untouched.

The exact file lists and command groups are captured in per-run task JSON under
D:/codex-tmp/f134. Any new dependency needed outside those read scopes is first assessed
and explicitly scoped by the coordinator; do not retroactively legitimize violations.

