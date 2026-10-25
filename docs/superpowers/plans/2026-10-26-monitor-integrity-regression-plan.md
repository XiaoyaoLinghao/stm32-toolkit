# Monitor integrity regression plan

Accepted base `1b79981e1916e1f704c5c4ee393d6b935e705aaa`; [design](../specs/2026-10-26-monitor-integrity-regression-design.md). No separate written-plan approval stop is required.

1. Reuse the clean isolated author tree on `codex/monitor-integrity-regression`. Supply full AGENTS, exact base/head, three allowed files, verified runtime paths, native gap index and primary corrections to the read-only audit.
2. Claude implements catalog, then storage/history, then replay corruption/publication cases with file tools only. Keep tests deterministic and bounded, preserve sentinels and distinguish real filesystem state from injected external outcomes. Do not modify existing helpers or execute shell commands.
3. Primary reviews all additions, resolves defects through the same Claude branch and freezes CodeHead. Prepare exact collection and native coverage manifests. Claude separately runs the complete affected suite with the supplied single-command PowerShell invocation, budget1,800seconds; no automatic retry.
4. Primary independently runs the new files and relevant integration callers at the same clean head. Record original failures and any bounded corrections, with at most two correction rounds before revisiting scope.
5. Combine only successful native data, rechecking all original and supplemental source/raw hashes, fixed policy/membership/denominators and package-qualified node identities. Record measured changes and remaining gates; no automatic exception or final release acceptance.
