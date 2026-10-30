# Flash initiating-failure evidence preservation

User-authorized slice, accepted base3bf143cd314b0e396a420a8c6ef33ee3ec19535b.
Branch codex/v135-flash-failure-evidence; reused clean isolated worktree.
Primary owns specification, orchestration, independent complete-diff review,
procedure/card and acceptance. Local Claude CLI implements code/tests using the
existing configured route. No hardware, runtime replacement, installation,
packaging or remote authority; no default retry authorization.

## Public behaviour

Preserve initiating flash diagnostics when workflow cleanup or owned worker abort
also fails, without changing calls, timing, ownership, reset/run or flash policy.
Limit implementation writes to hardware_workflows.py, probe/worker.py,
tests/test_hardware_workflows.py and tests/test_probe_worker.py under
tools/stm32-toolkit. Reuse existing validators; no new module/schema/automation.

1. Worker: for flash_elf/flash_imported_elf with a valid closed programDiagnostic,
   if abort_owned_execution raises an ordinary Exception, emit the existing
   PROBE_BACKEND_ERROR/fixed termination-failure message plus exactly:
   initiatingCode=PROBE_PROGRAM_FAILED, original validated programDiagnostic,
   cleanup={outcome:failed,stages:[one failed worker-parent-abort entry]}.
   Construct the entry through existing make_cleanup_entry; sourceCode uses the
   existing backend-code allowlist/fixed fallback, never raw abort text.
   Successful abort preserves existing normal programming-error code/details.
   Invalid diagnostic must not be promoted. Existing attach and non-programming
   behaviour stays intact. Non-Exception BaseException retains current fatal
   propagation when no attach diagnostic; no new exception swallowing.
2. Workflow: only stm32_flash/stm32_flash_imported, with cleanup.failed and no
   controlledSnapshot/attachDiagnostic branch, add a closed projection to the
   existing HARDWARE_CLEANUP_FAILED result. Preserve valid programDiagnostic via
   extract_program_diagnostic, a safe initiatingCode, and canonical
   cleanup={outcome:failed,stages:[prior validated worker abort, then actual
   workflow/service cleanup fragment]}. No arbitrary detail copy.
3. Safe initiatingCode: prefer PROBE_PROGRAM_FAILED from a fully validated
   worker-abort envelope (valid diagnostic, exact initiating code, closed failed
   worker-parent-abort fragment). Otherwise use original result.code only if its
   exact str matches existing _ERROR_CODE pattern; malformed falls back to
   HARDWARE_INTERNAL_ERROR. For no result, use fixed CALLER_CANCELLED if action
   cancelled, HARDWARE_FATAL_ERROR if action fatal, otherwise HARDWARE_INTERNAL_ERROR.
   Success+cleanup failure records initiatingCode=OK, data stays absent and receipt
   remains partial evidence. Existing cleanup.fatal precedence is unchanged.
4. Accept frozen protocol dict/MappingProxyType and tuple containers through
   bounded explicit thaw/validation where needed; reject arbitrary Mapping,
   malformed/extra fields, duplicate or out-of-order stages in incoming worker
   cleanup. Untrusted prior cleanup is dropped, never copied. Actual trusted
   workflow cleanup facts still survive. Public sanitization remains in place.
5. No change when workflow cleanup succeeds (worker failure envelope flows through
   as before); non-flash empty-details privacy tests, controlled Fault and attach
   semantics stay intact. No new success report or postFlash on cleanup failure.

## Required offline evidence

Claude authors regressions for both worker programming methods and all admitted
preparation stages; deterministic abort-failure substitute at the existing parent
process boundary, never kill a real unknown process. Cover valid/invalid closed
diagnostics, ordinary successful abort compatibility, worker failure through
workflow with/without an additional cleanup failure, immutable result containers,
safe code fallback, private-data rejection, action cancellation/fatal plus cleanup
failure, and success+cleanup partial-evidence semantics. Existing attach/non-flash
privacy and owned-worker reap tests must remain green. Fakes/inert test children
and unique temporary leases only; no physical probe or real C:/data registry.

Separate file-only edit from exact-command verification. Primary pins direct
CPython3.12.14, isolated official pyOCD0.46.0 plus existing dependencies; no install.
Verify affected modules and integration/privacy regressions in small bounded
groups with fresh JUnit and actual exits. Primary reviews the full base-to-CodeHead
diff in a clean checkout, independently samples critical regressions, updates the
normal100kHz card/procedure, and obtains a separate supplied-source independent
card review. Software acceptance does not grant hardware or release acceptance.
