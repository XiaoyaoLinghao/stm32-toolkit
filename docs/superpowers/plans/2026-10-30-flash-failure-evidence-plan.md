# Flash failure evidence implementation plan

Accepted base3bf143cd314b0e396a420a8c6ef33ee3ec19535b; branch
codex/v135-flash-failure-evidence. Governing
[design](../specs/2026-10-30-flash-failure-evidence-design.md), approved by the
user's2026-10-30 request to fix this capture gap and regress offline.

1. Primary reads maintained procedure/latest NORMAL-FLASH-ENTRY report/card,
   freezes this design and exact four allowed implementation/test files.
2. Dispatch one Claude file-only edit with Read/Edit/Write/Glob/Grep and bounded
   related src/stm32_toolkit and tests read scope (explicit known dependencies,
   fixtures/helpers included). No shell/test commands or automatic retry.
3. Audit native tool inventory, matched editing events, all changed paths and full
   diff. Freeze code/tests in a local commit. Any correction stays on this slice,
   obeys explicit retry rules and at most two same-issue correction rounds.
4. Dispatch separate exact-command offline verification. Use pinned real Python,
   isolated SDK/dependencies and unique external report/temp directories. Group
   tests below native foreground limit; pending is retained and reconciled by
   Primary from existing bound artifacts, never rerun merely due pending.
5. Primary independently reviews complete diff in clean exact-head checkout,
   verifies critical subset, reconciles fresh reports/actual exits and no source
   changes. Product, tests, test execution and test passing are separate facts.
6. Primary updates standard procedure, execution card and tracked report under
   docs/codex/returns/FLASH-FAILURE-EVIDENCE. Independent local Claude review of
   fully provided updated entry/card source, no main tools, then Primary acceptance.
   Capture correction must not alter100kHz, SYSRESETREQ/HALTED, attach5s/HID10s,
   program/readback30s or existing cleanup control. Three reads total61516bytes
   remain planned; no hardware grant, target remains UNKNOWN.

Evidence owner: Claude for delegated edits/checks; Primary for specification,
source reconstruction, independent checks/review, card and final verdict.
All orchestrator artifacts are external under D:/codex-tmp/st135-flash-evidence;
no new product dispatch/test tooling, install, runtime replacement or remote action.
