# T10 physical recovery software review

Status: **SOFTWARE_COMPLETE_HARDWARE_PENDING**. Independent complete-diff verdict: **ACCEPTED (T10 software scope)**. T9/T10/VS10-A physical acceptance remains incomplete.

- Accepted slice base: `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1`.
- Reviewed T10 CodeHead: `1fa1887a5703cd437cbd852e67c36ec7ce0562c9`.
- Combined T9/T10 integration code head before this report: `14a59df8c7e9542cadea56d6ca33baf17f962f21`. All T10 changed files match the reviewed head exactly; T9 retained its accepted product bytes.
- Primary conversation owns design/integration/acceptance; the original Luna/max implementer owns implementation/tests; `t10_complete_review` independently reviewed the complete base-to-final diff across its recorded review and correction deltas.
- Local branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. No remote action or ownership override.

The physical v2 attempt now binds actual Target TestRun and Diagnostic authorities, an exact source-change intent, fresh firmware identity and the resulting complete source snapshot, followed by the matching physical-shaped FixVerification lineage. It preserves v1 replay/AcceptanceRecord behavior and the 48-tool public inventory. Offline fixtures exercise these contracts; they are not physical acceptance.

The complete-review findings are closed: caller intent schemas fail closed; v1 MCP describe/record enums exclude the physical attempt-only scenario; build/ELF/input snapshot facts come from the same existing firmware authority; Diagnostic lock precedes EvidenceStore lock while full failed-run authority is retained. Both physical publication paths now use one pre-root boundary: durable envelope, applicable slow source/firmware checks, fresh deadline check against the actual locked predecessor, then root publication. This covers ordinary and terminal revisions as well as authorization; initial rev0 and exact already-accepted retries retain their defined exceptions.

## Evidence and limits

- Implementer at `215c8c82`: focused 75 cases and diagnostic regression 85 cases passed; owned compilation passed. Final `1fa1887a`: affected physical module 11 cases and full persisted chain passed; compilation passed. Unchanged evidence is retained.
- Primary at `215c8c82`: seven cases passed, then a separate existing-chain clock injection proved expired rev6 publication. That defect was not hidden by the green tests; lifecycle reconsideration is recorded in the plan and final code closes it.
- Primary at final `1fa1887a`: the existing full persisted chain passed, including rev5/6/7 expiry/source boundaries, predecessor retention, successful completion after restoring injected conditions, CAS and exact retry. Evidence: `D:\codex-tmp\stm32tk-t10-physical-recovery-verification-1fa1887a-20260911\pytest.txt` and `exit-code.txt`.
- Primary at combined `14a59df8`: two affected integration cases passed: exact 48-tool inventory and project-bound hardware argument schemas. These enumerate API definitions only. Evidence: `D:\codex-tmp\stm32tk-t9-t10-delivery-20260910\integration-pytest.txt` and `integration-exit-code.txt`.
- Independent reviewer accepted complete `4b79ad97..1fa1887a`; final diff whitespace checks passed. No remaining T10 software blocker was found.
- Verification interpreter: existing non-temporary CPython 3.12.10 with pytest 8.4.2; all run roots were on D. Earlier long-path test failure was classified ENVIRONMENT after the unchanged test passed with a shorter D root.

The combined candidate's one authorized local deployment, offline deployment checks, rollback identity and final serial execution card are recorded separately after they actually run. This report does not claim deployment, hardware execution or release acceptance. P2 remains unchanged; -12 100ms physical PASS and historical attempt 7 PASS remain preserved. Policy-blocked temporary cleanup is retained without retry and does not invalidate the recorded product checks.
