# GCC Monitor live identity acceptance

Date: 2026-10-26. Verdict: **ACCEPTED_WITH_FIXES**, bounded to B2a live Monitor/UI. Accepted base: `b0f5807bb8b8f2149a7499fed3b2b03d3e610c33`. Final CodeHead before this report: `f56deeb740e85b4eb898c08291077156c62704d5`. Plan: [Monitor live](../../../superpowers/plans/2026-10-26-gcc-monitor-live.md). Primary owns specification, complete-diff review and acceptance; local Claude Code CLI with the existing configured provider/model implemented code and tests. No publication, installation, original-project mutation or physical operation occurred.

## Accepted behavior

Monitor forwards the admitted input-snapshot provenance through firmware status, observation binding, fake connection, sampling and history. Snapshot records require null Git fields and the complete, immutable sourceBaseline/gitEvidence pair; raw partial, mixed, present-null or unknown fields are rejected. Legacy accepted Git casing and serialized field sets remain unchanged. Rebinding compares complete provenance while preserving existing firmware-versus-other-binding error classification and observer authority. The UI uses a closed union, rejects malformed forms, invalidates dependent state on identity changes and displays the input digest with “Git：未记录”. Normal Vite output was regenerated and independently reproduced.

## Evidence and corrections

Evidence root: `D:/codex-tmp/gcc26`. Every actual edit inventory contained only Read/Edit/Write/Glob/Grep. Verify inventories contained native PowerShell and an actual matched harmless smoke. Native PowerShell success results omit numeric exit codes; these remain null. Separately recorded runner subprocess exits are numeric zero for the accepted checks.

- Initial `monitor-global-live` mistakenly called absent Bash for a directory listing. Native result proved it unexecuted. Its one authorized exact Glob recovery completed, then the cumulative turn limit ended the call without product edits. Logs and one-shot ledger remain intact. This was not CLI startup failure or an executed shell command.
- Bounded model/runtime/UI calls produced candidate `6d484261364e92d37ac29ba14e18265ade025f78`. One initial Read of a not-yet-created test file failed; later native editing completed. No scope/permission bypass occurred.
- `monitor-global-verify`: Python `mna` 88, `mma` 110, `mla` 102, `mha` 253 passed (553 total, zero skips). Initial UI typecheck failed due to weak optional-only comparison typing. UI `uua` had 531 pass, three failures, one skip: two new fixture/assertion errors and one existing eight-curve test timeout. All original failures remain recorded.
- Claude's bounded UI correction fixed union narrowing, JSON float fixtures and the legacy text assertion; it also made the absent-Git label informational. Candidate `bc42649a2b187e8e3feb1d6b5bec6530af0cc517`: `utb` typecheck/lint passed; `uub` full UI suite passed 534 with one skip. The same existing test passed with two workers; no timeout was increased and no existing test was weakened.
- Primary reviewed the entire base-to-CodeHead source/test diff in the clean `gcc-delivery-review` checkout, independently ran `mnp` (88 Python pass) and `uip` (eight UI pass) at `bc42649a`, and reviewed the derived manifest/HTML/assets. These overlap author cases and are not additional distinct coverage.
- Claude `ubb` used the normal Vite build; its record verifies non-generated source unchanged. Final CodeHead only adds derived assets. Claude `udb` and primary `udp` independently passed the repository verify-dist command at final CodeHead; source remained unchanged.

Python evidence at `6d484261` is explicitly reused because subsequent changes touched only UI source/tests and derived assets. UI source evidence at `bc42649a` is explicitly reused at final CodeHead because only generated assets changed. This is not a claim of a final-head full repository matrix. The runner records exact commands, heads, source hashes and fresh JUnit reports.

## Remaining scope

The single UI skip requires the external historical 293-batch dataset (`MONITOR_REAL_BATCHES_JSONL`); the primary integration owner must retain that qualification limitation unless the dataset becomes available. Archived fixture checks still ran. Vite retains its existing large-chunk warning. Replay/publication/analysis/diagnostic snapshot support belongs to B2b and is not accepted here. Combined no-Git new-project and migrated-project GCC/fake-flash journeys remain integration gates. No fake result is physical acceptance; no release decision is implied.
