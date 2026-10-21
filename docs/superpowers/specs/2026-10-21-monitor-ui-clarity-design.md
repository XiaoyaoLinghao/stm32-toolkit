# Monitor workbench information and action clarity

Accepted base: `c9651203b6bab44feca192868846c67b8f7581b3`. On 2026-10-21 the user approved this presentation plan, its implementation, tests, independent review and local 8765 update. This document freezes that approved scope without another approval stop. Primary owns specification, integration and acceptance; one gpt-6-sol/max implementer owns product/tests and a separate gpt-6-sol/max reviewer reviews the entire diff. Branch `codex/monitor-ui-clarity`, run root `D:\codex-tmp\uc1021`. No remote action or product ownership exception.

## Runnable scenarios

1. Open the workbench before connecting. The source directory presents a search field and compact collapsed folders; parser totals and the observability rule are available in closed details. The toolbar offers connection, not inactive pause/resume/stop controls. Preview rows say `等待连接`; no stale-data badge or empty sampling metrics crowd the normal view.
2. Expand a directory, file and scope, find an eligible variable or proved header extern such as testtime, and add it to the existing group draft. Files show their basename with their full path still available accessibly. Searching reveals matching folder paths; file/scope/aggregate loading remains lazy. Group editing, members, pagination and admission continue through their existing paths.
3. Connect and start the selected group. The toolbar changes with the authoritative sampling state. Running offers pause/stop, paused offers resume/stop; transitional or blocked states retain stop cleanup. Values, chosen waveforms and sampling metrics remain truthful. Stopping retains only already-authorized same-run samples; changing the draft must not relabel old samples. History/CSV works independently of whether the live sampler is running.
4. A source coverage warning is available through a compact summary, while actual root/branch/selection operation failures still show local feedback and their original retry path. A known snapshot omission is described as such, not as a transient failure that retry will fix. Global operation failures and transport recovery remain reachable in the existing diagnostic drawer.

Non-goals: source/ELF eligibility, AST/DWARF parsing, probe connection policies, sampling state-machine or controller admission changes, new APIs/wire types, group or CSV formats, new dependencies, framework/design-system replacement, hardware/flash/build experiments, browser/HTTP validation, release/version changes and remote mutations. Version remains 1.1.2. Original/derivative firmware and user data stay unchanged.

## Frozen presentation contracts

The existing reducer/status, catalog and runtime run identity remain the sole authorities. Visibility never grants operation admission. Keep existing callbacks, busy guards, scope/requestId retry, ACK adoption and binding/freshness checks. No duplicate state machine or new global data store.

Source directory:

- Keep the search and explicit refresh entry compact. Use the existing request path; do not issue a request merely because explanatory details open.
- Place rules, raw debug counts, parsed-unit coverage and coverage issues inside a native initially closed `说明与诊断` details region. Its visible summary may say `N 项目录提示` when there are N explicit issues; when incomplete/truncated without enumerated issues, use a truthful uncounted incomplete indication. Do not claim zero issues means complete.
- Remove the prominent generic partial banner and redundant coverage `重试上次操作` button. Preserve named snapshot/rebuild explanations inside details and the ordinary explicit refresh action. Actual failed operations keep their existing local alert/retry outside this fold; this change does not hide an actionable failure.
- Retain a short file count; do not call an unfiltered browse `搜索结果`. Raw declarations/functions/units are diagnostics, not visible-variable counts.
- Ordinary empty-query browsing starts with all folder/file/scope/aggregate branches collapsed, including after an identity/generation refresh. In an explicit nonempty search, expand matching folder paths by default so results are discoverable; files and scopes stay lazy/collapsed. Manual folder choices persist within that result generation and reset with the next result context. No unsolicited descendant fetching.
- File rows show only `name`/basename and a compact variable-entry count; remove redundant `1 作用域` metadata. Preserve full path in title/accessibility, file identity, source scope grouping, member depth, declaration/definition provenance, disabled add reasons and header aliases. Never flatten scopes or deduplicate aliases by name.
- Expanded diagnostics must remain scrollable within the sidebar so large issue lists cannot permanently displace all variable navigation. Native keyboard expansion, visible focus, labels and hierarchy remain accessible.

Sampling action visibility (busy still disables every displayed write action):

| Authoritative sampling state | State actions |
| --- | --- |
| IDLE | Start if connected; connection if disconnected. Start remains disabled without a selected group. |
| STARTING | Stop |
| RUNNING | Pause and Stop |
| PAUSED | Resume and Stop |
| PAUSED_BLOCKED | Stop and the existing blocked status/diagnostic explanation |
| STOPPING | Stop cleanup and the existing stopping status |

Disconnected non-IDLE states may additionally offer the existing connection chooser; they must not lose Stop. Stop visibility must follow state, not `active` alone: the backend reports `active=false` in PAUSED_BLOCKED/STOPPING. Sample-row ERROR is not a sampling state and must not hide RUNNING controls. This intentionally replaces the previous UI-only affordances that offered Start in STOPPING and Resume in PAUSED_BLOCKED: Start waits for IDLE, and a blocked run must be stopped before a fresh start. Backend/controller semantics and failure retry remain unchanged; do not add automatic stop/restart, retries or CPU actions.

Idle presentation is defined narrowly by `runId===null && !state.live.retained`, not simply `state===IDLE` or `active===false`. Only this no-run preview receives `等待连接` (disconnected) or `等待开始` (connected) for empty values and omits the misleading non-latest badge. Do not rewrite actual values/errors/capture time or claim preview rows are fresh. Retained/stale/blocked/current-run data keep existing provenance and freshness. Keep curve toggles and the eight-series limit; the empty selected-curves popup may be omitted when no curves are selected.

Hide the compact footer sampling metric strip only for that no-run preview; retain full diagnostic metrics and the diagnostic entry. While a run exists or samples are retained, keep existing truthful rate/latency/drop values, including `尚未收到样本` rather than fabricated zero rates. Avoid repeating the same source-preview label in both the toolbar area and footer. Zero operation failures can use a plain diagnostics entry; nonzero failures retain their visible count and existing recovery workflow. Group selection/draft, chart rendering/zoom and history/export stay connected to existing components and state.

## Evidence and local promotion

The implementer owns focused UI tests for closed details/issue truth, collapse/reset/search/manual expansion, accessible basename identity, header selection, all six action states using legal fixtures, busy/disconnected/blocked cleanup, no-run vs retained values and unchanged failure recovery. Run full UI unit/a11y coverage already in the suite, both type checks, lint, build and exact dist verification because shared App/styles are affected. No new snapshot-only tests or release matrix.

Primary owns exact-head affected UI integration, static Python asset tests, full-diff review and acceptance. A separate reviewer owns complete accepted-base-to-CodeHead review and proportionate focused verification. Reuse unchanged backend/source/firmware evidence explicitly; do not rerun the four-minute real source index or hardware tests for a presentation-only diff. Browser/real layout/authenticated-HTTP and physical evidence remain DEFERRED; DOM/a11y tests are software evidence only.

After acceptance, primary verifies old service card/PID/creation/source/listener/exec, stops only the owned terminal normally, proves release, then invokes public open from the accepted clean source with unchanged `D:\codex-tmp\mr1019\p`, data `D:\codex-tmp\mr1019\data`, session `mr-stable-20261019`, port8765. Record default-browser authentication handoff and process/listener identity, not a browser or physical PASS. Primary cleans verified disposable run outputs under uc1021, preserving useful evidence, reusable dependencies, live state and all prior holds.
