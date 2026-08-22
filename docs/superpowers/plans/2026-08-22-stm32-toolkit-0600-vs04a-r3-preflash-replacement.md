# STM32 Toolkit VS04-A R3 Pre-flash Replacement Plan

## Ledger

- Product accepted base: `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.
- Rejected attempts retained, unpushed, and not accepted:
  - R1 `c0a5d4e262c2ebc42ed8df2acc31f72f693af5d8`;
  - R2 `683555eccb097c375b0175d44ef5dbaeaf523b18`.
- Same GPT-5.6-luna/max implementation owner; GPT-5.6-sol specification/review owner.
- New branch: `codex/STM32TK-0600-VS04A-PHYSICAL-TARGET-R3` from this plan's documentation head.
- No hardware or remote authority; Python 3.12 only.

This is a new implementation under a revised interface after the two-round stop-loss. It is not a
correction commit on R2. Do not cherry-pick either rejected product commit. Low-level concepts may be
reimplemented only when they conform to all three controlling VS04-A amendments.

## Product boundary

Deliver the same default public prepare/execute/show behavior as the production replacement plan,
with the pre-flash inventory amendment controlling case and inventory timing. `caseIds` is mandatory
and complete. Neither prepare nor execute may query live Target test inventory before flash.

Allowed files and verification layers are the same as the production replacement plan. Monitor and
Diagnostic remain out of scope.

## TDD sequence

### 1. Prove the source-change timing first

Build a production-shaped backend whose board begins with failing-before firmware while Project/build
facts already describe fixed-after firmware. Call default public prepare with explicit fixed case
IDs. Assert success, one OBSERVE identity check, zero Target transport opens, zero MODIFY/flash, and
an expected inventory digest computed from fixed-after identity plus cases.

Fresh-process execute must consume, preflight, flash once, cause the backend to expose fixed-after
identity/frames, run, publish, and fresh-show the TestRun. This is the first GREEN required before
adding other tests.

### 2. Reimplement only the required production contracts

Reimplement the R2 low-level facts, Probe transport identity, single-client bridge, cleanup ownership,
physical provenance, publisher, and adapters from accepted base. Do not restore pre-flash discovery,
caller inventory, injected binding/session factories, raw probe persistence, or adapter-type
provenance inference.

Generalize Target runner authorization only as required:

- prepared binding keeps the precomputed inventory digest and exact complete cases;
- public prepare requires those cases;
- execute passes the consumed expected digest/cases to the post-flash run;
- the first runtime inventory and run-start must match them exactly.

### 3. Add negative and compatibility proof

Cover digest reuse, static build/ELF/snapshot/probe/target drift before flash, busy lease, and cleanup.
After-flash wrong firmware, wrong/extra/missing cases, digest contradiction, or transport failure must
consume the digest, retain valid partial Evidence, and create no TestRun root. Host and Target replay
bytes and tests remain unchanged.

CLI/MCP schemas require `caseIds`; they forbid inventory and all identity fields. Public output and
durable bytes contain probe hash only and no absolute ELF path.

### 4. Verification

Run the production-shaped test first, then the focused/affected test list in the production
replacement plan with exact source roots and a fresh basetemp. Run changed-file `py_compile`,
accepted-base `git diff --check`, and clean status. Do not run Monitor, physical, release, coverage,
packaging, or Python 3.10 checks.

The Sol reviewer independently simulates failing-before firmware during fixed-after prepare. If any
pre-flash Target transport/inventory read occurs, or prepare requires live new-firmware identity,
the candidate is `REWRITE_REQUIRED`.

Expected commit: `feat(testing): authorize pre-flash physical target runs`.
