# FLASH-PREPARATION — controlled pre-program reset

Current frequency policy is governed by the [2026-10-29 100 kHz design](2026-10-29-flash-default-100khz-design.md): ordinary production default is 100 kHz, with no 1 MHz acceptance gate. The original slice's unchanged-frequency boundary below is historical and does not override this follow-up. Reset/preparation contracts remain unchanged.

Approved scope: the user's 2026-10-28 instruction to implement the offline investigation's
direction for planned v1.3.5, using Claude Code implementation and primary independent
review. Accepted base: `528528f9e00791a96effa3a3bdb069c875fa9508`.

## Problem and behavior

The installed pyOCD 0.45.1 FileProgrammer API does not provide the CLI's pre-program
reset. A halted application can retain state unsuitable for its RAM flash algorithm.
The [investigation](../../codex/returns/POST134-USABILITY/flash-offline-followup.md)
confirms the integration difference, not the physical HardFault's cause.

1. Normal PyOCD programming performs exactly one explicit
   `target.reset_and_halt(Target.ResetType.SYSRESETREQ)` per admitted programming request,
   then reads target state and requires HALTED before entering the programmer. Use the
   pyOCD enum, not a string or default reset selection. No separate resume, reset fallback,
   state-repair halt, retry loop, frequency change or new connection is added.
2. Apply the shared preparation to managed `flash_elf` and imported `flash_imported_elf`.
   Imported native Flash-map admission must finish before preparation. Existing service
   identity, immutable-image and MODIFY/action authorization checks precede backend entry.
   Target execution already uses this backend and inherits preparation; its separately
   specified post-flash reset/run sequence is preserved.
3. Under-reset recovery reuses its connection reset: do not add another reset. Immediately
   before programming, recheck HALTED and fail if unknown/not halted. Never infer or switch
   into recovery. The observe-preserve policy must not gain programming/reset authority:
   direct misuse of that backend policy fails before reset/programming.
4. Driver acquisition remains a non-hardware prerequisite. Distinguish
   `pre-program-reset` and `pre-program-halt` from existing `driver-acquire`,
   `programmer-create`, `program-call` stages in the closed schema-1 program diagnostic.
   Keep `PROBE_PROGRAM_FAILED`, bounded exception sanitization and native IPC preservation.
   Unavailable reset methods, reset exceptions, unavailable/invalid state and every
   non-HALTED state fail closed. No programmer, readback, success receipt or later action
   may follow preparation failure; existing owned cleanup still runs.
5. `details.flashOptions` adds selected-configuration fields `preProgramReset`:
   `sysresetreq` for normal or `under-reset-connect` for recovery, and
   `preProgramHaltRequired: true`. These describe policy, not proof that reset/attach ran.
   Existing early refusals may omit flashOptions. No input option or new authorization
   bypass is added. `postFlash.targetState=unknown/runVerified=false` remains unchanged.
6. Document the reset side effect as part of the authorized flash operation, failure
   stages and stop behavior. Existing read-only attach/Monitor/discovery/handoff contracts,
   sector erase, keep-unwritten, auto-unlock disabled, identity/readback, cleanup and
   frequency defaults remain unchanged. Under-reset remains separately selected and
   authorized. No post-flash run is added to ordinary/imported flash.

## Boundaries and evidence

No pyOCD monkeypatch, dependency upgrade, flash algorithm rewrite, fault-register read,
automatic recovery, hardware access, installation, packaging, version metadata alignment
or remote action. Product metadata remains 1.3.4 until the separate release alignment;
Changelog places this behavior in Unreleased / planned v1.3.5.

Claude owns code, tests and user-facing docs. Primary owns this design/plan, orchestration,
complete-diff review and verdict. Offline tests must cover managed/imported ordering,
exact SYSRESETREQ selection, all preparation failures, zero program calls after failure,
recovery without duplicate reset, observe-preserve refusal, authorization/identity/map
refusal before preparation, diagnostic transport, no receipt/readback after failure,
and unchanged sector/readback/cleanup behavior. Use deterministic doubles; no real probe
enumeration or connection. Primary independently repeats applicable checks at the exact
frozen CodeHead in a clean review tree. Hardware efficacy remains pending to a separately
authorized future hardware acceptance phase; offline success is not a physical fix claim.
