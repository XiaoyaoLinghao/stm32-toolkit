# MONITOR-UI-01 independent review

Verdict: **ACCEPTED for the local code slice**, with browser/visual evidence explicitly **DEFERRED**. This is not full visual acceptance or release qualification.

- Accepted base: `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b` (published v1.0.1).
- Product CodeHead: `67f0ec4fbc375ed60e1f857b4cae248bf73d1589`.
- Reviewed implementation return: `c17bf0c735367cc028098a96a1a87996eb14a5ed`; its only delta from CodeHead is the implementation report.
- Acceptance owner: primary conversation agent. Implementation: one delegated `gpt-6-sol/max` owner. A separate `gpt-6-sol/max` reviewer assisted; the primary independently read the complete accepted-base-to-final product/test/documentation diff and generated manifest, including each revision delta.
- Independent review tree: `D:\codex-tmp\mui1015\review`, detached at the exact candidate, clean before and after checks. Original dirty checkout was preserved.
- Branch: `codex/monitor-ui-01-zh-workbench`; PR: none. No remote mutation, release or hardware action was authorized or performed.

## Findings closed

| Finding and evidence | Final behavior and verification |
|---|---|
| CatalogPanel raw table inherited a 470px minimum while its narrow-screen sidebar had visible overflow | A labeled, keyboard-focusable local scroll container bounds the table. Source review closed the defect; the new 320px browser assertion is present/type checked, actual viewport proof is deferred. |
| ExportPanel allowed a status refresh for an older task to complete after a newer creation and replace the sole artifact | Create/refresh are serialized at the panel boundary with a synchronous ref guard and guarded async cleanup. Deferred-response component coverage checks blocking, task/range retention and failure recovery. |
| Export confirmation declared aria-modal but did not contain Tab focus or restore it on all close paths | Shared dialog helper contains Tab/Shift-Tab and restores the trigger or an enabled local fallback. Escape/Cancel/Confirm component assertions pass. Browser keyboard/axe proof remains deferred. |
| S3 history-to-export browser coverage was absent | Existing workflow source now covers UTC query prefill, manual draft retention across navigation/query changes, explicit query-range reuse, submitted task range and CSV/JSONL creation. Controlled export responses have consistent payload/bytes/hash and the JSONL download body/hash is asserted. This is simulated response coverage, not backend export evidence. |
| Published baseline configured dataZoom without registering its ECharts component | The primary's pinned-engine SSR preflight emitted the missing-component warning and showed no active dataZoom model/4 unfiltered points. The owned adapter now registers DataZoomComponent; the final real-engine Node SSR test verifies the model and filtered window. No chart data algorithm/controller change. |

No unresolved product finding remains in the reviewed diff. Existing full-page blockingError behavior remains intentionally unchanged; local request recovery belongs to UI02. Authentication, cookie and port behavior remain unchanged; the fixed-entry proposal is not implemented by UI01.

## Primary-owned execution evidence

The primary ran these commands at the exact Product CodeHead in the clean review tree. All child temp/cache paths were bound to `D:\codex-tmp\mui1015\verify-final`.

| Check | Result |
|---|---|
| `npm.cmd run typecheck` | PASS, exit 0 |
| `npm.cmd run typecheck:e2e` | PASS, exit 0 |
| `npm.cmd run lint` | PASS, exit 0 |
| `npm.cmd run test` | PASS, exit 0; 34 files / 277 tests |
| `npm.cmd run build` | PASS, exit 0 |
| `npm.cmd run verify:dist` | PASS, exit 0; 7 generated files byte-identical |
| `git diff --check <accepted-base> <CodeHead>` | PASS, exit 0 |
| Protected-path comparison and rebuild status | API/controller/reducer/Python/lock/version/config unchanged; rebuild left no tracked changes |

Logs and command-bound result record: `D:\codex-tmp\mui1015\verify-final\*.log` and `results.json`. The implementation owner's separate exact-CodeHead runs are attributed in implementation.md, not substituted for these checks. Non-blocking diagnostics were jsdom navigation support and Vite's large-chunk advisory; neither is a browser or performance PASS.

## Scenario and evidence boundaries

| Scenario | Closed local path | Remaining evidence and owner |
|---|---|---|
| S1 connect/observe | Chinese shell, connection presentation, sample controls, latest values and real-engine zoom; original controller/WS ownership preserved | Primary conversation agent in an authorized working Windows browser/loopback environment: HTTP/WS workflow, actual rendered waveform and desktop first screen |
| S2 configure while observing | Groups/catalog/config entry points, mounted page state, drafts and resize/disposal component coverage | Same primary owner/environment: keyboard flow, real viewport resizing and navigation |
| S3 history/export | UTC/precision and range precedence component checks; full browser workflow source with controlled export responses | Same primary owner/environment: execute browser query/export/download path; simulated responses must remain labeled |
| S4 stale/blocked/errors | Typed reducer/component fixtures for stale identity/state, Chinese summaries and raw diagnostics; intentional blocking-screen contract preserved | Same primary owner/environment: actual error/stale/paused/blocked layouts; these fixtures are not physical transitions |

Real browser, screenshots, axe, 200% zoom and the specified viewport matrix were **not obtained**. Python asyncio loop creation blocked in socketpair; Chromium exited before page creation; a Node loopback self-fetch returned EACCES. The primary's CUA visit was denied by origin/network authority and no alternate surface/proxy was attempted. These are ENVIRONMENT/policy constraints, not product PASS or product defects. Minimal evidence: `run/browser-blockers.txt`, `run/browser-dev2/workflow.log`, `run/browser-dev3/workflow.log` under the task root.

Release packaging/matrix and physical board/probe sampling remain with the later release/integration owner. Local commits do not change the published v1.0.1.

## Artifact cleanup

Primary is the cleanup owner. Final commit-bound logs, minimum failure evidence, approved source/docs, generated tracked UI assets and Git objects are preserved. Cleanup completed for 44 attributable intermediate-run/dependency/cache paths under the verified task root, with no blocked path; outcome is recorded in `D:\codex-tmp\mui1015\cleanup-result.json`. Ignored Python caches found by a final read-only dry run were also removed. No original/shared cache or user data was a cleanup target. Known verification processes/sessions have ended; broad process enumeration was unavailable and no broad kill was used.
