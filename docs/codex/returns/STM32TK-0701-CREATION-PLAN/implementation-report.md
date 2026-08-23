# STM32TK-0701 VS07-A implementation report

Status: `IMPLEMENTED_PENDING_INDEPENDENT_REVIEW`. This is the replacement
implementer's evidence record, not an acceptance decision. Sol must review the
complete accepted-base-to-final-head diff independently.

## Ownership and source ledger

- Governance transfer head: `50efbc9a`.
- Product accepted base named by the governing plan: `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`.
- Specification: `docs/superpowers/specs/2026-08-23-stm32-toolkit-0701-discovery-boundary-rewrite-design.md`, especially section 7.
- Execution plan: `docs/superpowers/plans/2026-08-23-stm32-toolkit-0701-discovery-boundary-rewrite.md`.
- Implementer: the user-authorized replacement GPT-5.6-luna/max owner `/root/vs07a_replacement`.
- Reviewer/acceptor: GPT-5.6-sol primary agent; the implementer did not approve this diff.
- CodeHead before this report commit: `88eb8e03` (the report does not record its own final commit SHA).
- Branch/worktree: `codex/STM32TK-0701-CREATION-PLAN` / `C:\tmp\stm32tk-0701-creation-plan`.
- Remote authority: none. No push, fetch, PR, merge, tag, release, installation, hardware, CubeMX execution, VS07-B, or VS07-C action was performed.

## Delivered recovery slice

Tasks 1R–2R replace the optional-fact discovery chain with immutable
`DiscoveryCandidate`, `CandidateTier`, and `CandidateResolution` states and one
resolver enforcing explicit > CubeCLT metadata > registered/standard > PATH,
canonical deduplication, same-tier ambiguity, preserved issues, and fail-closed
evidence. PATH enumerates every bounded candidate; HKLM and HKCU are queried
independently. CubeMX and VS Code use static PE evidence only; only CubeCLT
metadata and GCC/CMake/Ninja version probes use the bounded process runner.

The creation slice now covers all `.ioc` negative paths, safe source/destination
parents, absent/empty/populated/unsafe inventory states and digest binding,
sorted non-VS-Code support blockers, all source kinds, repeated scalar CLI
options, closed workflow errors, the exact MCP five-field schema, client-root
binding, one frozen MCP support profile reused by doctor and create-plan, and
fixed-clock CLI/MCP parity.

Product/test commits before this report are:

- `6d801d19` — `fix(project): rewrite creation environment discovery`
- `864b331d` — `fix(project): close creation planning contracts`
- `cdaebaae` — `fix(project): normalize native discovery evidence`
- `88eb8e03` — `refactor(project): remove legacy discovery fallbacks`

## Strict TDD evidence

All named Task 1R and Task 2R tests were added before their corresponding
product changes and run against the unchanged product to establish RED.

Task 1R RED:

```text
py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py -q
```

The new discovery cases produced 14 expected failures: the old optional-fact
helpers had no typed resolver, no all-candidate PATH ambiguity, no independent
registry handling, no static-only evidence boundary, and no closed metadata or
native-probe transitions. After implementation and the native-format
correction, the same focused suite passed 58 tests, exit 0, with no
skip/xfail, using disposable basetemp `C:\tmp\p0701-final-task1c`.

Task 2R RED:

```text
py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py -q
```

The first redirect-parent fixtures attempted real Windows symlinks and failed
because this host does not grant that test privilege; those failures were
classified `ENVIRONMENT` and replaced with deterministic reparse simulations.
The resulting product RED had five failures: unsafe inventory classification,
blocker ordering, and the missing fixed-clock seam in three workflow/adapter
proofs. The final focused command passed 40 tests, exit 0, with no skip/xfail,
using `C:\tmp\p0701-final-task2b`.

The first real observation also exposed a `PRODUCT` discovery defect: absent
known-layout constants were treated as invalid candidates and the native
CubeCLT command emitted single-backslash Windows paths to component `bin`
directories. The bounded parser now repairs only that known native format,
normalizes its trusted component directories to executable leaves, and treats
absent standard layouts as empty tiers. The correction is covered by a native
metadata regression test and commit `cdaebaae`.

## Exact complete VS07-A slice

The required command was run on `88eb8e03` with the worktree `src` first on
`PYTHONPATH` and short disposable TEMP/basetemp `C:\tmp\p0701-slice-4`:

```text
py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0701-slice-4
```

Result: exit `0`, 507 passed, zero failures/errors, zero skips, zero xfails.
Collection counts were: `test_tool_support.py` 30, `test_doctor.py` 28,
`test_creation_plan.py` 19, `test_creation_workflows.py` 5,
`test_creation_cli.py` 10, `test_creation_mcp.py` 6, `test_generation.py` 276,
`test_workflows.py` 79, `test_cli.py` 26, `test_mcp_server.py` 15, and
`test_mcp_roots.py` 13. The only warning was the pre-existing runpy warning
from `test_main_guard_raises_system_exit_when_run_as_module`.

## Fresh real read-only observation

Observation workspace: `C:\tmp\stm32tk-0701-observe-recovery-final-20260823-2`.
It contained one pre-existing fixture, `seed.bin`, size 6, SHA-256
`ae4442edeb4b16dd3caae01dc9f9f536ae4cb6dc78e56f5d540469de83b32779`.
The relative name/size/hash snapshot before and after both commands was
identical (`snapshotEqual=true`). CubeMX process IDs were `[]` before and
after.

Commands and results:

```text
py -3.12 -m stm32_toolkit.cli doctor --project-root C:\tmp\stm32tk-0701-observe-recovery-final-20260823-2 --json
exit 0

py -3.12 -m stm32_toolkit.cli project create-plan --project-root C:\tmp\stm32tk-0701-observe-recovery-final-20260823-2 --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --json
exit 0
```

Doctor `data.creationSupport` reported CPython `3.12.10`; CubeMX
`D:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.exe`,
version `6.18.1-RC2`, source `standard`, SHA-256
`db4ca49eea336b819eede7f2a1cea19fff65f2f435aee35efc54ce856b6fae01`; CubeCLT
root `C:/ST/STM32CubeCLT_1.22.0`; GCC `14.3.1`, source `cubeclt-metadata`,
SHA-256 `c8fcafea64559054bbfa87917182598892f81b41706b003c5a93fa7542355908`;
CMake `4.3.1`, SHA-256
`f05482595d42888f2befe209d8aa4848560c8a05356411043241a15e7d3f86a7`; and
Ninja `1.13.2`, SHA-256
`09478fb9503b6a8884b033f423148844b33f9caa179be8244f09b672b6d437d9`.
VS Code was absent and the sole support issue was `VSCODE_MISSING`.

The create-plan result had `blockers=[]`, `mutated=false`, and no destination
or source mutation. This observation is read-only evidence; no CubeMX process
was started.

## Failure classification and boundaries

- `PRODUCT` — the five Task 2 RED cases and the native discovery defect above;
  both were corrected and covered by GREEN evidence.
- `ENVIRONMENT` — real VS Code absence (`VSCODE_MISSING`) and the denied
  Windows symlink privilege during the first fixture attempt. The latter was
  removed from the final test path by deterministic reparse simulation.
- `DEFERRED` — no hardware, package/install, CubeMX generation, VS07-B, or
  VS07-C evidence was requested or authorized for this slice.

## Diff and local state

Against the named product base, `git diff --check
d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58..88eb8e03` exited 0. Against the
governance head, the product/test diff contains only the nine in-scope files:
`tool_support.py`, `creation.py`, `creation_workflows.py`, `cli.py`, and the
five corresponding discovery/creation test files (including the existing MCP
test updates). No out-of-scope product path was changed by this recovery slice.

Before this report commit, `git status --short --branch` was clean at
`88eb8e03`; the branch is local-only and has no upstream or remote mutation.
The report and SDD ledger are the only changes in the separate documentation
commit that follows. Sol remains the independent acceptance authority.
