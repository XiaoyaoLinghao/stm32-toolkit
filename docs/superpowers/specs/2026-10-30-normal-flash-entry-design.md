# Normal100kHz connection/flash entry review

Accepted base `65e5b637069342b2472fad50fcf771801e7337c8`; unchanged product/test
CodeHead `694e1e912adfc017c31b52630a323bd733567688`. Branch
codex/v135-normal-flash-entry, reused clean isolated source checkout. Primary
owns source reconstruction, specification, plan, procedure/card and acceptance.
Local Claude Code CLI retains configured model/provider/permissions and performs
independent source review; any necessary product/test implementation remains
with that CLI in a separately bounded edit task. No implementation ownership
override, hardware, installed-runtime replacement, packaging or remote authority.

## Requested scope

Prepare and independently review the actual public managed normal-flash path
using the original board/probe and existing firmware. One future CLI flash call
includes its own connection; do not add a separate discovery/attach or reuse the
consumed constructor-only grant. No hardware is authorized by this preparation.
Firmware admission and parser-only observation are read-only ordinary checks.

## Required contract and interpretation

- Exact project/data/session/probe/build/ELF pins, normal policy, explicit100000Hz.
  Public main/module, worker spawning and SDK/module origins must be real,
  not a direct fake/in-process backend. Do not replace the installed runtime.
- Authorization and fresh-image admission precede device access. MODIFY normal
  Session.open configures clock and can halt/read/write target debug state.
  Initial HALTED/identity checks precede programming. A second distinct Toolkit
  pre-program call requests Target.ResetType.SYSRESETREQ reset_and_halt, then
  explicitly requires HALTED before creating FileProgrammer.
- Failed pre-program reset/halt stops before programmer/readback/success receipt.
  No agent/Toolkit-level retry, fallback/under-reset, unlock or extra reset/run.
  Sector-only, trustCrc=false, keepUnwritten=true; exact readback61516bytes.
  SDK algorithm execution legitimately uses target RAM, registers, halt/resume;
  it is not user-firmware execution acceptance.
- SDK reset_and_halt may warn rather than raise for halt timeout, so Toolkit's
  subsequent HALTED gate matters. SYSRESETREQ includes SDK post-reset accessibility
  polling and possible DP auto-reconnect; any future authorization must disclose
  that intrinsic behavior. Do not promise no internal SDK reconnect/reset/control
  or only one physical reset from one Toolkit API request.
- Existing attach failure/late-MODIFY cleanup may resume, check running and close.
  Program/reset preparation failures do not invoke that attach restoration branch.
  Standard close uses resume_on_disconnect=false but SDK disconnect can perform
  debug cleanup; failure does not guarantee halted/running or rollback of writes.
- Preserve initiating and cleanup evidence. CLI error/cleanup override must not
  silently erase a required programDiagnostic. Final receipt alone is insufficient:
  it can be old after attach failure or newly written before a later cleanup failure.
- Preserve5s attach success deadline, SDK per-read10s, program30s, each of two
  readback RPCs30s, worker startup10s/ordinaryRPC30s/flashRPC300s/close5s and existing bounded
  owned-worker abort joins. The constructor20s+2s budget does not apply. A proposed
  future180s observation budget is not a hard CLI/OS/persistence deadline or force
  kill permission; unfinished execution remains UNKNOWN and forbids later hardware.

## Known candidate blocker, subject to independent confirmation

hardware_workflows._one_shot currently preserves attach/controlledFault details
when cleanup fails, but appears to replace ordinary flash programDiagnostic with
empty HARDWARE_CLEANUP_FAILED details. The maintained procedure requires original
failure capture before the first hardware step. Do not mark the entry READY or
software-complete by pretending this detail survives. Independent reviewers must
confirm the source behavior and whether a bounded correction is required; a
software defect is not deferred as a hardware-only uncertainty.

Completion requires both public lifecycle/IPC and backend/SDK review, explicit
failure/cleanup/reset boundaries and a concrete pinned card. Findings remain
REVISION_REQUIRED until resolved, otherwise ACCEPTED applies only to offline
entry preparation. No normal connection, program, target read or hardware health
query is part of the review. Fresh hardware authority/readiness/preflight remains
a later gate regardless of an offline NO_BLOCKERS verdict.
