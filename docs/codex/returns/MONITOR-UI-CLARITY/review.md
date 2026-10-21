# Monitor UI clarity acceptance

Verdict: **ACCEPTED — software slice**, 2026-10-21. The primary reviewed the complete accepted-base-to-final-product diff, reconciled independent review and verification, and accepts the four approved scenarios. Local 8765 promotion follows this acceptance; its actual process/source and browser-handoff result are recorded in the run-owned service card.

## Ownership and scope

- Accepted base: `c9651203b6bab44feca192868846c67b8f7581b3`.
- Final product/test/assets CodeHead: `ec3b6fa64b9eef0ce0c987890ad958b7cc9ef620`.
- Implementation-report-only head: `c2e9a381c75c883c110bef07b967a0214705d75b`; it changes only `implementation.md` after CodeHead.
- Branch `codex/monitor-ui-clarity`; implementation tree `D:\codex-tmp\uc1021\impl`, clean detached review tree `D:\codex-tmp\uc1021\review`. The original dirty user workspace is preserved. These are local identities; the cached Git store has no origin/master ref, and there is no claim about the current remote.
- Primary owns specification, plan, full-diff review, integration, acceptance, operations and cleanup. `ui_clarity_impl` is the sole product/test author; `ui_clarity_review` independently reviewed all 25 accepted-base-to-report-head files. Both used gpt-6-sol/max. No product ownership override or remote action.
- Approved [design](../../../superpowers/specs/2026-10-21-monitor-ui-clarity-design.md), [plan](../../../superpowers/plans/2026-10-21-monitor-ui-clarity-plan.md), and [implementation evidence](implementation.md). Version remains 1.1.2; no installation, backend/firmware build or flash.

## Accepted behavior and review

Rules, raw metadata and coverage warnings move into initially closed `说明与诊断`; explicit issue counts remain truthful. Actual failures retain their local scope/requestId retry outside that fold. The directory starts collapsed, displays basenames with accessible full paths, and keeps lazy file/scope/member loading. Search opens matching folder paths; manual choices persist within one result generation. Expanded diagnostic content is bounded, and the source panel provides vertical overflow when controls exceed a short viewport.

Connection and sampling actions follow the six authoritative states: connected IDLE offers Start, RUNNING Pause/Stop, PAUSED Resume/Stop, other non-IDLE states Stop. Disconnected states can offer connection without losing cleanup. Busy guards and controller admission remain unchanged. Only `runId===null && !live.retained` receives waiting labels and hides empty footer metrics; retained samples keep their values, timestamps, source identity and stale indicators. Group drafts, waveforms, the eight-series limit, history and CSV retain their existing paths.

Independent round one found a PRODUCT short-viewport clipping path and a REPORT test fixture incorrectly marking STARTING active. The same author repaired both in one round: vertical panel scrolling and a legal active=false fixture. The primary reviewed the entire original diff and correction delta; the independent final verdict is **ACCEPTED, no remaining findings**. Static layout reasoning is not a browser measurement. Full independent records remain at `D:\codex-tmp\uc1021\review-round1.md` and `review-final.md`.

## Evidence

| Owner and scope | Result |
| --- | --- |
| Implementer, broad UI suite before final bounded corrections | 58 files, 498 passed, one existing conditional skip. Reused evidence: the optional-property typing fix, CSS refinements and fixture correction came afterward. |
| Implementer, final CodeHead | 24 affected UI tests passed; both TypeScript checks, lint, build and seven-file dist comparison passed. Exact commands and logs: implementation return and `impl-checks/review-r1-*.log`. |
| Primary, clean first CodeHead `9f0c584bbcb8ed5701e7b922f0386277bf231d7c` | 61 UI integration tests passed across source real-client selection, six sampling states, preview/drawer behavior, workbench/recovery and CSV; 29 Python assets tests and seven-file dist verification passed. `primary-checks/round1/{proof.json,ui.log,python.log,dist.log}`. |
| Primary, clean final CodeHead | 29 Python asset tests passed and all seven committed dist files matched an independent rebuild. `primary-checks/final/{proof.json,python.log,dist.log}`. The prior 61 UI result is reused because runtime UI logic is byte-identical; only CSS, its generated references and the test fixture changed. |
| Independent reviewer, clean final CodeHead | Four files, 29 UI tests passed and one existing conditional skip, covering directory, sampling controls, preview values and retained replay. `reviewer-checks/focused-ui.log`; command in `review-final.md`. |

All paths above are under `D:\codex-tmp\uc1021`. The conditional skip requires the optional `MONITOR_REAL_BATCHES_JSONL` file; checked-in sanitized replay ran and is not physical evidence. Initial display/type defects were PRODUCT; stale test expectations and locators were REPORT. All relevant corrections passed their bounded follow-up checks.

Toolkit and Monitor backend bytes, runtime/reducer/controller, source eligibility, group/chart/export implementations and firmware identities are unchanged. Prior real-MR offline source evidence in `D:\codex-tmp\mo1021\primary-checks\real-final\result.json` is reused, not rerun: 53/53 units, 43 visible files, 808 roots, with the existing named legacy header omission. Folding this warning does not fix or hide its underlying coverage status. No new hardware claim is made.

## Local operations and cleanup

Primary promotion uses the same project `D:\codex-tmp\mr1019\p`, clean source `3babf285f372b3ed6ef3caea71887fa8faa46997`, data `D:\codex-tmp\mr1019\data`, session `mr-stable-20261019` and port8765. Build `d1518c08faccd8426539bd5aa84fb01e66b4c464e11b06958e57d3ec38218989` and ELF `543ef137d06e89945df68b0ed1d29f60c31ae31b877200db26eb6f5b44a42cc8` remain fixed. After rechecking the old service card, PID/creation, command, source and listener, stop owned exec83340 normally, prove release, and invoke public open from the accepted clean review tree. The successful switch, final source head, new PID/creation/exec, manifest hash and default-browser authorization handoff are recorded in `D:\codex-tmp\uc1021\service.json`; before that card is created, mo1021 is still the serving version.

Browser layout, authenticated HTTP and physical sampling remain **DEFERRED** to the user/later authorized validation. Public-open handoff and OS listener checks establish service startup only. No browser inspection or firmware action is part of this promotion.

Run-owned pytest/temp/build/compiler/test caches were removed after retaining proof and useful failure logs; exact paths are in `D:\codex-tmp\uc1021\cleanup.json`. Source trees, reusable frozen dependencies, useful reports and live service state remain. This task created no cleanup holds; earlier policy/reparse holds and user-owned data remain untouched.
