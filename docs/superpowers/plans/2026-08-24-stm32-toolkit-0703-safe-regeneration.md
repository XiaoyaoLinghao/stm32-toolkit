# STM32 Toolkit 0.7 VS07-C Safe Regeneration Implementation Plan

> **Status:** Approved for execution on 2026-08-24 under the user's delegated
> approval authority.

> **Implementation owner:** exactly one `gpt-5.6-luna`, reasoning `max`, for
> Tasks 1–4 as internal checkpoints. The implementer must use TDD, commit the
> complete local candidate, and may not approve its own diff.

**Goal:** Deliver the approved VS07-C safe IOC regeneration vertical slice on
accepted base `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d` without changing the
Keil path, adding a release gate, or performing remote/hardware operations.

**Design:**
`../specs/2026-08-24-stm32-toolkit-0703-safe-regeneration-design.md` is the
complete contract. Do not invent unresolved ownership, authorization, or
activation behavior in code.

## Working boundary

- Branch/worktree: `codex/STM32TK-0703-SAFE-REGENERATION` /
  `C:/tmp/stm32tk-0703-safe-regeneration`.
- CPython: only `>=3.12,<3.13`.
- CubeMX/CubeCLT/package facts currently available for native evidence:
  CubeMX 6.18.1-RC2, CubeCLT 1.22.0, and
  `C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`.
- Do not install software, touch hardware, add collaboration/release tooling,
  or operate a remote. Preserve every other worktree.
- Use `apply_patch` for source/document edits. Keep the branch clean between
  checkpoints and do not rewrite accepted history.

## Task 1 — Ownership-aware read-only plan

**Primary files:** create `regeneration.py` and `test_regeneration.py`; modify
only shared model helpers when reuse requires it.

1. Write RED tests for the exact frozen plan/model, deterministic digests,
   schema-3 CubeMX-only requirement, workspace-relative non-root destination,
   current IOC exception, strict ownership precedence, Toolkit/user/derived
   classification, all unsafe path/type/bound cases, generator/package drift,
   changed CubeMX-owned bytes, Toolkit drift, unknown paths, and byte-for-byte
   read-only behavior.
2. Run the focused RED command and record named failures in the ledger/report.
3. Implement the smallest immutable planner and strict parsers. Reuse existing
   canonical hashing, project model, managed manifest parser, native inventory
   bounds, Git evidence, and environment discovery; do not introduce a second
   schema or generic provider.
4. Run the focused GREEN command. Commit this checkpoint only if coherent;
   otherwise retain it for the slice commit.

## Task 2 — Authorized exact preview

**Primary files:** create `regeneration_workflows.py`; extend regeneration core
and tests; reuse `creation_authorization.py`, `creation_environment.py`,
`cubemx_adapter.py`, and `cubemx_project.py` without weakening their contracts.

1. Write RED tests proving prepare requires exact plan/action and JSON boolean
   true, CubeMX is never called by plan, preview uses one internal store-issued
   capability, all temporary/control roots are cleaned, no project bytes
   change, the persistent authorization is single-use/expiring, exact preview
   records are bounded/sorted, full preview digest is not truncated, and every
   preview/generator/cleanup failure issues no usable success.
2. Add deterministic two-run fake CubeMX cases and one deliberate second-run
   byte change that must later return `REGENERATION_PREVIEW_CHANGED`.
3. Implement preview-bound plan/action digests and the thin public prepare
   workflow. Do not persist preview bytes or add a daemon/cancel API.
4. Run focused GREEN and record the exact result.

## Task 3 — Transactional apply and regression protection

**Primary files:** extend regeneration core/workflows; add
`test_regeneration_workflows.py`; modify configure/build seams only when needed
for reuse.

1. Write RED tests for consume-before-execution, exact current state and
   environment revalidation, preview replay equality, `App/`/`Tests/`
   byte-preserving copy, derived-output discard, new manifests, configure then
   Debug then Release ordering, destination lock/race, collision preservation,
   failure cleanup, activation rollback, bounded cleanup-required behavior,
   and no success with a residual owned transaction root.
2. Add a Keil schema-2 fixture hash test proving typed refusal, zero CubeMX
   calls, and no Keil/migration/configuration byte or public-capability change.
3. Implement the transaction using the accepted VS07-B generation-container
   then activation-staging ordering. Never configure/build inside the CubeMX
   generation container and never delete an unowned collision.
4. Run the directly affected creation/regeneration/generation/build/Keil suites
   and record GREEN before public adapters.

## Task 4 — CLI/MCP, real native evidence, report, and local commits

**Primary files:** modify `cli.py`, `mcp_server.py`, both READMEs; create
`test_regeneration_cli.py`, `test_regeneration_mcp.py`, and
`docs/codex/returns/STM32TK-0703-SAFE-REGENERATION/implementation-report.md`;
update the SDD ledger.

1. Write RED CLI/MCP parity tests for the exact three commands/tools, argument
   schemas, boolean authorization, operation/code envelopes, root binding,
   sanitization, and unchanged existing tool contracts/inventory count.
2. Implement only thin adapters over neutral workflows. Update English/Chinese
   docs with the truthful supported boundary and no release/hardware claim.
3. Run the exact slice command:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_regeneration.py tools/stm32-toolkit/tests/test_regeneration_workflows.py tools/stm32-toolkit/tests/test_regeneration_cli.py tools/stm32-toolkit/tests/test_regeneration_mcp.py tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0703-luna-slice --junitxml=C:\tmp\p0703-luna-slice.xml
```

4. Run `py -3.12 -m compileall -q tools/stm32-toolkit/src
   tools/stm32-toolkit/tests` and
   `git diff --check fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..HEAD`.
5. In a new local Git workspace with no remote, copy the accepted VS07-B
   captured-IOC generated project, add byte fixtures below `App/` and `Tests/`,
   change only `ProjectManager.HeapSize=0x200` to `0x300`, and call the public
   plan/prepare/apply workflows with the discovered installed support profile.
   Require exact preview, Debug/Release `OK`, changed generated bytes, unchanged
   user hashes, successful activation, no hidden transaction/control residue,
   and no new persistent CubeMX/Java PID. Record the pre-existing PID 32708
   without terminating it.
6. Run a separate read-only public refusal against a copied Keil fixture and
   prove before/after tree digests equal.
7. Commit product/tests, then write the implementation report with accepted
   base and the product CodeHead before the report commit. Commit report/ledger
   separately. Do not put the report's own SHA or moving commit counts inside
   the report. Leave the worktree clean, local, unpushed, and without upstream.

## Independent Sol review

After Luna returns, Sol creates a new detached review worktree at the exact
returned head and:

1. reviews the complete accepted-base-to-final-head diff, not a summary;
2. runs `git diff --check`, the exact slice, and `compileall`;
3. independently probes CubeMX/Toolkit/user/unknown drift, preview mismatch,
   authorization replay, activation rollback, and Keil refusal;
4. repeats one fresh real IOC regeneration with user-file hashes, both builds,
   residue scan, and PID delta;
5. reconciles the report/ledger and issues `ACCEPTED`, `REVISION_REQUIRED`, or
   `REWRITE_REQUIRED`.

Correctable findings return to the same Luna and branch. If the same issue
does not converge after two review/fix rounds, stop local patching and revisit
the interface or integration design. Acceptance ends VS07-C; do not
automatically enter VS08 or perform release/remote/hardware work.
