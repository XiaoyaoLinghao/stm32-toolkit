# Release-test temporary-root portability plan

Specification: [bounded fixture contract](../specs/2026-09-19-stm32tk-release-test-root-portability-design.md).
Accepted base: `1df30a0f4070805488687a67f907dbaa1867d681`.
User's persistent 1.0 local-release authorization covers this necessary fix and
verification; no per-command approval is required.

1. One Luna/max owner works in `D:\codex-tmp\v10b-0918\r10\fi` on
   `codex/STM32TK-1.0-test-root-portability`. Only the ten specified test modules
   and a concise implementation report are writable. No version/package/runtime
   changes. The owner is not alone in the repository and must preserve others'
   edits. No recursive delegation or remote action.
2. Replace the concrete allocation/coupled path accesses with existing tempfile
   or fixture facilities. Keep parser-only hostile-path literals and assertions
   semantically unchanged. Resolve the effective Python temp root before tests.
3. Run the smallest representative existing tests that exercise allocation,
   native Windows locking/coverage sibling cleanup and relevant fixture setup.
   Set TEMP/TMP/TMPDIR below `r10/t`, an explicit short basetemp, cache and retained
   stdout/exit/command records below `r10/e/fixture`. Do not run the full Python
   matrix twice; final integration owns it. Preserve any failure before diagnosis.
4. A non-implementing reviewer checks the full accepted-base-to-code-head diff in
   a separate clean checkout and the actual retained results. Primary integrates
   accepted commits locally; rejected findings return to the same owner. No
   hardware/deployment/remote actions.

Primary owns cleanup. Existing `fin` evidence and its policy-rejected cleanup
remain untouched. Release work stays under `r10`; no drive-root directories or
old C-drive temporary paths are authorized.
