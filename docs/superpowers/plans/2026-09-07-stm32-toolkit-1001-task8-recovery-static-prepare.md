# STM32TK-1001 Task 8 Recovery Static-Prepare Implementation Plan

**Goal:** Keep normal Target prepare unchanged while making recovery prepare a static-only
authorization so recovery execute performs the first target attach, identity gate, and at most
one program using the existing 100 kHz connect-under-reset profile.

**Architecture:** One existing canonical authorization remains the source of truth. Recovery
prepare binds closed static facts without service or hardware access. Execute already consumes
the action, revalidates static facts before service creation, uses the existing recovery worker,
checks physical identity, and only then enters the existing flash/readback/run path.

**Accepted base:** `fe01c4fcd28792c512dd71beb51b47aa391db6f7` (tree
`905d6739d3d3ea402e0ebd0d4f0f04549de43ae4`).

**Specification:**
`docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-task8-recovery-static-prepare-design.md`.

**Implementation owner:** existing Task 8 GPT-5.6-luna/max agent.

**Reviewer:** GPT-5.6-sol primary.

**Remote authority:** none. **Hardware authority:** none during implementation/review; one existing
recovery guarded-flash authorization becomes usable only after independent acceptance.

## Task 1 - Commit static-prepare RED

- [ ] In `test_physical_target_workflows.py`, replace or extend recovery-prepare assertions so a
  supervisor seam raises if constructed and the public workflow still returns a valid prepared
  action with exact recovery/static bindings.
- [ ] Prove normal prepare still constructs one OBSERVE supervisor and attaches.
- [ ] Prove recovery prepare emits no lease/backend/attach/target-read/control/program event.
- [ ] Prove a syntactically invalid recovery selector and a second-read static firmware drift both
  fail before authorization and service creation.
- [ ] Prove the real recovery prepared record is consumable only once by execute; retain all
  existing zero-program identity and one-program success assertions.
- [ ] Commit the failing tests before product code.

## Task 2 - Implement bounded GREEN

- [ ] In `testing_workflows.py`, add one exact portable probe-selector predicate matching
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` and apply it before static recovery authorization.
- [ ] Keep the current normal branch byte-for-byte behavior-equivalent: construct OBSERVE
  supervisor, attach, prove physical identity, then freshness-check.
- [ ] For recovery only, skip all supervisor/client construction and physical identity access.
  Build expected identity solely from fresh project/build facts and the exact probe hash.
- [ ] Re-read firmware facts immediately before `TargetTestRunner.prepare()` and retain the full
  existing static drift comparison.
- [ ] Keep the canonical binding, action digest, response, execute path, worker derivation,
  authorization consumption, identity-before-program, flash/readback/run, cleanup, and publication
  unchanged.
- [ ] Do not edit CLI, MCP, runner, worker, backend, service, schemas, firmware, or release files.
- [ ] Commit only the allowed product file as GREEN.

## Task 3 - Proportionate verification and return

- [ ] Run the affected recovery/normal prepare and execute nodes first under CPython 3.12 with
  source/test `PYTHONPATH`, `-p no:cacheprovider`, `-o addopts=''`, and a short unique basetemp.
- [ ] Run `test_physical_target_workflows.py` and `test_vs10a_target_v2_public.py` completely.
- [ ] Because the canonical action is shared, run the existing five-file Target matrix only after
  the narrow tests pass: target runner, physical workflow, CLI, MCP, and public v2.
- [ ] Run `git diff --check`, `git diff --name-only`, exact HEAD/tree/status, and verify no path
  outside the two documents, one product file, and allowed tests changed from accepted base.
- [ ] Clean or classify only run-owned test output. Do not touch campaign/runtime/project evidence.
- [ ] Return RED/GREEN commits and evidence to Sol without hardware, runtime, report, or remote work.

## Independent Sol review

- [ ] Create a fresh detached clean worktree at the returned code head.
- [ ] Review the complete accepted-base-to-head diff, not only the final patch.
- [ ] Verify static recovery prepare cannot construct a supervisor, normal behavior is unchanged,
  and the real action flows into one recovery execute identity/program sequence.
- [ ] Re-run the focused files and the five-file matrix with a new short basetemp.
- [ ] Check TDD lineage, diff-check, status, cleanup, and SDD accuracy; issue one verdict.
- [ ] Do not run hardware, rebuild/install runtime, or perform remote actions during review.

## Physical continuation

After `ACCEPTED`, build and verify one exact-head offline 0.9.0 candidate, recoverably replace the
campaign runtime, run public build and passive probe discovery, run one static recovery prepare,
and validate its case digest. Only then execute the single already authorized recovery guarded
flash. Stop on any failure; never retry automatically.
