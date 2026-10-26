# Bounded implementation plan

Spec: ../specs/2026-10-26-retest-guidance.md
Accepted base: f5d8978a2a60c59ec5afee4fc014707311210fe5.

1. Primary records the supplied evidence and checks current native Claude
   PowerShell inventory plus actual Get-Location. File-only implementation is
   separate from exact-command verification. Preserve all logs and failures.
2. Claude edits only migration constant/rule diagnostics and the CLI JSON
   serializer, affected synthetic tests, migration skill and user guide. Existing
   semantic guards stay intact; no automatic missing-return repair or transcoding.
3. Claude executes complete affected test files through the coordinator-supplied
   single native PowerShell command, using CPython 3.12 and the existing ARM GCC
   where compiler evidence is required. No shell discovery or fallback.
4. Primary freezes CodeHead, reviews every diff in a separate clean checkout,
   reconciles tests and verifies the explicit user evidence read-only. Return
   bounded corrections to Claude; never implement product fixes in primary.
5. Record accepted/revision-required verdict with CodeHead before report commit.
   Keep this change local pending separate release/remote authorization. User
   owns final installed-runtime/VS Code retest; no hardware action.
