# Monitor observable-running acceptance

Verdict: **ACCEPTED — software slice** on 2026-10-21. The primary independently reviewed the complete accepted-base-to-final-product diff and reconciled the separate independent review, implementation evidence and exact-head integration checks. Local 8765 promotion is authorized after this acceptance; the operational result is recorded separately below and in the run-owned service card.

## Ownership and identities

- Accepted base: `e125bc5ae362abb84ffa3d71b251681aeb7e0d48`.
- Final product/test CodeHead: `4e1e0bd4864ae337ff95fe06e39c9cbdc32ff0a9`.
- Implementation-report-only head: `fef2f22355372296efee7013db7cc8c28b924f84`; its `tools/` diff against CodeHead is empty.
- Branch: `codex/monitor-observable-running`; implementation tree `D:\codex-tmp\mo1021\impl`; independent clean review tree `D:\codex-tmp\mo1021\review`. The cached Git store has no `origin/master` ref; these are local accepted commit identities, not claims about the current remote.
- Primary owns design, plan, integration, complete-diff review, acceptance, service operations and cleanup. `observable_running_impl` is the sole product/test implementer; `variable_directory_review` is the independent reviewer. Subagents used gpt-6-sol/max. There was no product ownership override.
- Approved [design](../../../superpowers/specs/2026-10-21-monitor-observable-running-design.md), [plan](../../../superpowers/plans/2026-10-21-monitor-observable-running-plan.md) and [implementation return](implementation.md) define the slice. No remote, installation, release, user-firmware build, flash or new physical/browser action was performed. Version remains 1.1.2.

## Accepted user scenarios

The default source directory now shows structurally observable entries and their useful aggregate/file/scope ancestors. Eligibility comes from the existing ELF reader: a unique supported scalar at a fixed readable address, with source address/type attribution. This includes eligible globals, file statics, function statics and proved header extern aliases. Ordinary automatic locals, parameters and unproved or unsupported entries are excluded; empty file/scope branches are pruned. Readable members may remain available even when their aggregate as a whole crosses a readable-region boundary.

Offline eligible scalar rows remain visible as `待连接`, with add disabled. A connected binding must still pass freshness, region and identity admission; changed binding/source/ELF cannot borrow offline eligibility. Search, scope pages and counts operate on the filtered set. Counts say `变量条目`, while raw debug-discovery statistics remain explicitly separate. Existing hierarchy, group, sampling, waveform and CSV contracts remain.

Monitor alone opts into `observe-preserve` at 100 kHz. Its pyOCD attach path requests no halt/resume/reset, including failure and disconnect, and preserves an already halted target. The adapter disables pack/config/user sequences and clears the public pack sequence delegate before open so the installed pyOCD generic ADI/CortexM path remains active. Unsupported initialization fails closed. Normal Target preparation, CONTROL/MODIFY and under-reset workflows retain their separate existing behavior. This is a software CPU-control contract, not physical proof of zero timing/debug-bus effects.

## Review and verification

Independent round one required changes for five concrete issues: aggregate budget dead ends, aggregate leaf proof borrowing a different source object's address/type, a wholly unreadable large array aborting unrelated roots, missing-firmware/search-cause precedence, and raw-debug counts described as visible entries. The same implementation owner corrected them in one repair round. The final implementation reserves a proven scalar path for every admitted expandable node, survives sibling expansion order, verifies address/type again at selection, prunes provably unreadable arrays and retains explicit bounded-scan failures for genuinely unproved suffixes. Eligible 100+20 scope pagination and wrong-domain/wrong-scope cursor tests were restored.

The independent reviewer reviewed all 22 files in the complete accepted-base-to-CodeHead diff, all correction deltas and the final report. Final verdict: **ACCEPTED (software slice), no product blockers**. Full local reports are `D:\codex-tmp\mo1021\review-report.md` and `review-final.md`; the latter records commands, identities and attribution. The primary separately reviewed the complete product/test and presentation changes; generated assets were independently rebuilt byte-for-byte.

| Evidence owner and scope | Result |
| --- | --- |
| Implementer, final CodeHead source suite and affected UI | 41 source tests and 10 UI panel tests passed; both type checks, lint, build and seven-file dist comparison passed. Exact commands/logs are in the implementation return. |
| Primary, exact final clean CodeHead integration | 70 source/assets Python tests and 23 source UI tests across four files passed; all seven committed dist files matched an independent rebuild. `primary-checks/final/{proof.json,python.log,ui.log,dist.log}`. |
| Independent reviewer, exact final CodeHead | Nine focused tests passed, covering source identity, budget reservation/order, unreadable array, real AST plus synthetic DWARF scope pagination, readable-boundary positive and installed pyOCD attach fallback. Earlier 12 focused checks remain actor-attributed. |
| Primary, broader affected regression before the source/UI correction | 314 source/backend/group/export/assets tests passed at `fa8288c07064c2d729716cbe8b271974aeea2fe0`. Toolkit/backend and group/export bytes are unchanged; changed source/assets were rerun above. `primary-checks/python/{proof.json,result.log}`. |
| Implementer, earlier full UI regression | 494 passed and one existing skip. Only SourceCatalogPanel and source-catalog copy/tests changed afterward, covered by the final focused UI/static/dist checks. This is reused evidence, not a new exact-final full-suite run. |
| Primary, exact final real MR offline public provider | PASS: 53/53 compilation units parsed, 43 visible files, 808 visible root entries; disconnected scalar entries pending and useful aggregate ancestors retained, automatic locals excluded; timer.c and timer.h `testtime` plus `SPEED_PERCENT_SAFE_FB` selected with an explicitly synthetic matching binding; changed binding rejected. `primary-checks/real-final/{result.json,execution.json,result.log}`. |

The real project remains `D:\codex-tmp\mr1019\p`, clean at `3babf285f372b3ed6ef3caea71887fa8faa46997`; build `d1518c08faccd8426539bd5aa84fb01e66b4c464e11b06958e57d3ec38218989`, ELF `543ef137d06e89945df68b0ed1d29f60c31ae31b877200db26eb6f5b44a42cc8`. Source/manifest/ELF hashes were unchanged. The existing legacy snapshot omission for `Main/stm32f4xx_it.h` is still reported, so coverage correctly remains `complete=false` despite all 53 units parsing. No rebuild or flash was used to hide that warning.

Physical target-state/continuous sampling, browser and authenticated HTTP evidence remain **DEFERRED** to the user and a later authorized run. Real pyOCD library paths used fake probe I/O; synthetic ELF fixtures and synthetic matching bindings are not physical PASS.

## Operations, classification and cleanup

The original user workspace remains dirty and preserved. The old service was independently revalidated against `D:\codex-tmp\mv1020\service.json`: PID 23680, creation `2026-10-20T17:01:17.0389910+08:00`, source equal to accepted base, unchanged project/data/session and loopback listener. The first operational check incorrectly compared a JSON date after PowerShell's automatic conversion; classification REPORT. Reading the timestamp as a string and comparing exact UTC ticks confirmed the same process, not a service restart or product failure.

After document reconciliation, the primary will normally stop the owned exec 98844, prove PID/port release, then invoke public `open` from the accepted clean review source with the same project, `D:\codex-tmp\mr1019\data`, session `mr-stable-20261019` and port 8765. The authoritative successful promotion record is `D:\codex-tmp\mo1021\service.json`, including the final clean source head, process creation identity, exec ID and browser-handoff result. A startup/listener check is operational evidence only. The old service is live at acceptance; the card records the actual switch outcome.

Disposable verification projects, pytest caches and UI temporary builds under `mo1021` were removed after their results were retained. Cleanup is recorded in `D:\codex-tmp\mo1021\cleanup.json`. Three roots are held because recursive deletion would cross a reparse boundary: `impl-checks\b1`, `impl-checks\b15`, and `primary-checks\python\base`. No link traversal/deletion was attempted. Useful logs, proof JSON, repro scripts, source worktrees and reusable frozen dependency copies remain; all older policy/reparse holds are untouched. Ordinary expected-contract assertion failures are REPORT/test-expectation findings; the previously passing chart's parallel timeout was ENVIRONMENT, and the five independent-review defects were PRODUCT, repaired and verified.
