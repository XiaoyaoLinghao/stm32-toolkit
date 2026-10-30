# NORMAL-FLASH-ENTRY review report

2026-10-30 checkpoint: **REVISION_REQUIRED / BLOCKED_NOT_EXECUTED**.
Independent entry review and the blocked execution card are complete; hardware
entry is not accepted. Accepted base65e5b637069342b2472fad50fcf771801e7337c8;
reviewed documentation CodeHeadb439cb3d774e5a836901230b5e35d157bb965a28;
branch codex/v135-normal-flash-entry. Product/test CodeHead remains
694e1e912adfc017c31b52630a323bd733567688, with no product/test edit in this slice.
Primary owns design/procedure/card, orchestration, full-diff review and acceptance;
local Claude CLI retained configured deepseek-v4.1-flash[1m] for independent
review. No implementation ownership override or remote authority.

Governing [design](../../../superpowers/specs/2026-10-30-normal-flash-entry-design.md),
[plan](../../../superpowers/plans/2026-10-30-normal-flash-entry-plan.md),
[source analysis](source-review.md) and
[execution card](../../../testing/cards/2026-10-30-normal-100khz-flash.md) and
[maintained procedure](../../../testing/standard-test-procedure.md).

## Verdict and required correction

| Finding | Evidence and disposition |
| --- | --- |
| F01 — initiating failure capture, blocking |hardware_workflows.py1286–1316 replaces ordinary flash details on cleanup failure, losing initiating code, valid programDiagnostic and cleanup stages. worker.py699–728 can replace the program error if owned abort fails. Cancellation/fatal facts can also be masked by the cleanup override. Preserve closed initiating and cleanup facts before hardware; no arbitrary details copy or Mapping-only trust. |
| Reset/HALTED ordering |Independent backend/SDK verdict NO_BLOCKERS within supplied excerpts: initial MODIFY HALTED/identity gate; normal SYSRESETREQ reset_and_halt then fresh HALTED gate before programmer creation. SDK return/warning alone is insufficient. Static ordering is not physical success or an IPSR result. |
| Failure controls |Parent abort races child finally backend.close after an error response. SDK cleanup may occur or be interrupted; close/uninit/USB release cannot be guaranteed. Service program timeout can abort mid-write. Physical CPU/flash/USB state remains UNKNOWN on unresolved failure. |
| Receipt interpretation |Old receipt can remain after attach failure. Successful stale removal precedes programming. A new receipt can precede cleanup failure, which drops public report data/postFlash; that receipt is forensic partial evidence, never overall PASS. |

Before hardware, freeze a bounded correction covering workflow and worker failure
projection plus their implementation tests through Claude. Use existing closed
diagnostic/cleanup validators, preserve non-flash privacy behaviour and keep
hardware calls, deadlines, frequency, lease and stop policy unchanged.
Required regressions: valid/invalid diagnostic with cleanup failure, non-flash
privacy, worker abort failure retaining the initiating program fact,
cancellation/fatal with cleanup failure, and success+cleanup receipt interpretation.
These are future checks, not tests run here. Independently review the complete
correction and updated entry card before READY.

## Evidence and reconciliation

Existing ELF passed pure file admission and proposed flags passed parser-only
observation. SDK was not imported, no CLI main/workflow/worker/lease/health call
ran, and protected project/model/identity/build/ELF/old-receipt bytes stayed
unchanged. Two ELF segments total61516bytes. Primary initially used65536 instead
of MAX_READ_BYTES32768 for RPC count; original observation is retained and
explicitly superseded by firmware-observation-reconciled.json:
three reads,0x08000000/32768,0x08008000/28600,0x0800efb8/148.
FlashRequest passes30000ms to each read, overriding the generic client default.
Total bytes, image/build identity and admission result are unchanged.

Original A/B calls at reviewed CodeHead completed14/15 authorized reads; all
model-visible text/hash/END markers matched. Both then requested an unlisted
nonexistent next packet, A12/B13, and received native permission refusals;
extra requests did not execute. A stopped through dispatcher; Primary terminated
only the identity-matched owned B CLI after refusal. B CLI exit4294967295;
both dispatcher exits1. Both remain REVIEW_INCOMPLETE. No edits/tests/hardware.
B termination recording failed after the kill due a bare PowerShell false token;
no second termination attempted. An audit assertion expecting both classifier
states blocked was corrected: B retained unknown_error without final-result
metadata. Raw native refusal and non-execution are retained, not called success.

User explicitly allowed one bounded supplied-source supplement. Actual tools:
PowerShell-only inventory, one harmless native startup smoke, zero main tool
calls/writes/tests; unchanged route, CLI/dispatcher exits0. All26 complete packets
(382003 UTF-8 bytes) were supplied in the task and matched the recorded prompt.
That grant is consumed. Public lifecycle REVISION_REQUIRED; backend/SDK ordering
NO_BLOCKERS within excerpts. Both assistant messages are retained: CLI result
alone contained only the second and omitted the first verdict table.

Primary reviewed the complete source verdict, with these corrections:

- Reject Mapping-only diagnostic copy; reuse extract_program_diagnostic.
- Reject categorical no-SDK-close: child finally close races parent abort.
- Retain HID10s, verified in Interface constants and Windows HID read;
  algorithm10s options are separate. No service5s/SDK10s budget change.
- Resolve builtin class part_number canonical matching statically; actual
  identity remains a hardware gate. Correct chunking to3 requests as above.
- Disclose DBGMCU connection writes, DEMCR reset catch, NUL warning loss,
  partial-write/unknown state and partial receipt evidence.

Source/test bytes and347 SDK files stayed unchanged after all calls. Primary
reviews the full documentation diff in a clean exact-head checkout and checks
whitespace. No product tests are needed or rerun for this documentation-only
slice. Existing qualification stays historical at its recorded heads; it is
not fresh testing here.

Retained evidence under D:/codex-tmp/st135-normal-flash-entry:
firmware-observation.json, firmware-observation-reconciled.json, source-packets.json,
packet-layout.json, review-A/B-run logs, stopped-review-evidence-audit.json,
supplement-proposal.json, supplement-authorization.json, supplement-run,
supplement-evidence-audit.json, supplement-complete-review.md and
primary-review-reconciliation.json.

## Retained boundary

No hardware, installation/runtime replacement, packaging, push or publication.
No fixture rebuild or receipt rewrite. Original constructor PASS and authority
remain narrow and consumed. Future card needs corrected software and entry
recheck, new explicit finite hardware grant and current original-board/probe
power/exclusivity/changes confirmation plus source/runtime/firmware/output/guard
preflight. Proposed180s is an observation budget, not hard exit or force-kill
authority. Any failure stops later hardware; no automatic recovery.
