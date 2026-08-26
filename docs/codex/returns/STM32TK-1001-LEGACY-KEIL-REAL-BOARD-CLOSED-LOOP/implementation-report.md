# STM32TK-1001 VS10-A Task 3c implementation report

Status: Task 3c implementation evidence is complete and pending independent Sol review. This
report does not issue an acceptance verdict. The report covers the no-hardware scoped-option
candidate/runtime replacement and unchanged-P0 public inspect/dry-run gate only; Task 4's
five-path ARMCC/GCC/profile correction and all later H1/physical work were not started.

## Ownership and frozen inputs

- Module/phase: VS10-A H1 / Task 3c.
- Implementer: GPT-5.6-luna, reasoning effort `max`.
- Independent reviewer/acceptor: Sol primary agent; the implementer does not self-accept.
- Accepted product base for this slice: `7c28986406f8932e96c3976b7e925bfd1c2eba44`.
- Accepted Task 2c Toolkit CodeHead used to build the candidate:
  `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa`.
- Corrected frozen specification/plan docs head:
  `8cf0f9626bce315fd313afb591ac16141915e988`.
- Specification: `docs/superpowers/specs/2026-08-25-stm32-toolkit-1001-h1-blocker-convergence-design.md`.
- Plan: `docs/superpowers/plans/2026-08-25-stm32tk-1001-h1-blocker-convergence.md`.
- Implementation branch/worktree:
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP` /
  `C:/tmp/stm32tk-1001-legacy-hardware-impl`.
- Toolkit implementation head immediately before this report commit:
  `8cf0f9626bce315fd313afb591ac16141915e988` (the only change after the product CodeHead is
  Sol's two-document blocker-accounting correction; product bytes used by the candidate remain
  at `3db9e001...`).
- Project campaign root: `C:/tmp/stm32tk-vs10a-legacy-campaign`.
- Project P0: clean/no-remote commit
  `b83b404c8da6993658586fa1b553d715f95993c1`, tree
  `a7d38844454ab22ab23ddd768675dd9e15bc210c`.
- No push, PR, merge, tag, release, remote mutation, hardware/probe access, or golden access
  was authorized or performed.

## Candidate and runtime result

The exact 66-wheel closed input set (64 runtime wheels plus the two previously authorized
`setuptools==84.0.0` and `wheel==0.48.0` backend wheels) was reused offline. No additional
backend network request was made after the recorded recovery. The candidate was built twice from
the canonical CRLF detached source at `3db9e001...` into the distinct scoped-options paths.

Formal candidate evidence:
`C:/tmp/stm32tk-vs10a-legacy-campaign/evidence/task-3c-candidate-verify.json`.

- Candidate: `runtime/scoped-options-candidate`.
- Extracted root: `runtime/scoped-options-candidate-extracted`.
- 13 top-level files, 12/12 checksum rows, and byte-identical repeat release.
- Source archive SHA-256:
  `c731a8bf8f311d6c87f5fba1ec2b0d855694b38012ba4738a3ce1b8624234c8a`.
- Windows bundle SHA-256:
  `b424e6f21bd740e7dd733268cb481bdcea8abd1a08a0a075324b4224aee12ccd`.
- Release manifest SHA-256:
  `df24abafddf4d35e70ba88a1904cc815031d90dd1959dd1551f1417924c9123a`.
- Normalized canonical Git archive equals the candidate source archive byte-for-byte; the
  earlier raw-archive mismatch was a REPORT-side normalization diagnostic, retained at
  `evidence/task-3c-source-archive-diagnostic.json`.
- Collision-safe extraction and release duplicate checks pass; `verify-bundle` exits 0.
- Runtime wheel count is exactly 64; Toolkit/Monitor source-wheel member counts are 117/25;
  public inventory is 48 MCP tools and 8 Skills.

The old active `0.9.0` generation-1 runtime (source `7c289864...`) was checked for process
holders, retired only at the exact campaign `data/runtime` path, and replaced by a fresh
Bootstrap from the extracted candidate. Formal evidence:
`evidence/task-3c-runtime-retirement-preflight.json`,
`evidence/task-3c-runtime-replacement.json`.

- Exactly one active/highest managed runtime remains: `0.9.0`, generation 1.
- Runtime state sourceCommit is `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa` and its manifest
  binding is `df24abaf...`.
- No staging directory, second runtime, reparse point, or post-verification process match.
- Fresh Bootstrap succeeds; isolated CPython is 3.12.10; Toolkit/Monitor imports resolve from
  the managed runtime; doctor exits 0 with `ok=true`, 48 MCP tools, and 8 Skills.

## Unchanged-P0 public verification

The public commands used the original `Project/LWIP.uvprojx`, not the derived
`Project/LWIP.gcc.uvprojx`. Inspect and both dry-runs were read-only and emitted no stderr.
Command/output/exit evidence is retained under
`C:/tmp/stm32tk-vs10a-legacy-campaign/evidence/task-3c-p0-*`.

Inspect result:

- Exit 0, protocol `stm32-toolkit/1`, operation `keil-inspect`, code `OK`.
- Target `Target 1`, device `STM32F429ZGTx`, compiler `armcc`, framework `spl`.
- Selected project SHA-256:
  `8efeec8cbe9366a8451d5bd59a00bf1dc11b5cff6e837a5ef12e005d609caa47`.
- AXF `Project/OBJ/LWIP.axf`: SHA-256
  `65f5b98c970befbea2c7fd529f54a51438b3c635d794e20519d284c33976c225`, 747560 bytes.
- MAP `Project/LIST/LWIP.map`: SHA-256
  `6fca9fc30bd964f81da0c2417d46fe6930f6317ce96ee30d63fbf2981e8bbe9f`, 240938 bytes.
- Program sizes: Code 62772, RO 1004, RW 1576, ZI 406440, flash 65352, RAM 408016.
- 53 selected source entries are retained: 52 C entries plus the included assembly source
  `Startup_config/startup_stm32f429_439xx.s`; target includes count is 37.
- Authored group scoped options are exactly `Main` (`USER/IWDG`, `CAN_APP`) and `USER`
  (`USER/IWDG`).

Both public convert dry-runs exit 0 with protocol `stm32-toolkit/1`, operation
`keil-conversion-plan`, code `OK`, and exactly 12 blockers. Each output is 19307 bytes with
SHA-256 `ecf2dd4868b9dee0372f4c227f1f04ae045a42ed3812176cae0f89906010b742`; both plan ID and
inspection digest are identical (`ea490ed0a60b22753690efd714a7c608a9439180a88e5c9514e17ac754ba2df5`
and `01a8fe6568b150f47b2cdaec55ec6c76d6606be98e569dd45922205facc0d38d`). The exact blocker
tuples are:

| Count | Code | Location/evidence |
| ---: | --- | --- |
| 4 | `ARMCC_INLINE_ASSEMBLY_UNSUPPORTED` | `Common/common.c`: lines 112, 117, 123, 130 |
| 4 | `ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED` | `MALLOC/malloc.c`: lines 9, 10, 13, 14 |
| 1 | `ARMCC_ASSEMBLY_UNSUPPORTED` | `Startup_config/startup_stm32f429_439xx.s`: line 0 |
| 1 | `ARMCC_PRAGMA_UNSUPPORTED` | `USER/usart1/usart1.c`: line 69 |
| 1 | `ARMCC_OPTION_UNSUPPORTED` | empty path/line 0, `group:Main` |
| 1 | `ARMCC_OPTION_UNSUPPORTED` | empty path/line 0, `group:USER` |

The former eleven-blocker wording omitted the already-proven startup assembly finding. Sol's
docs correction at `8cf0f962...` records the correct twelve-blocker arithmetic and explicitly
classifies the discrepancy as SPEC/REPORT, not product or project drift. No blocker was filtered,
rewritten, or made to pass by changing product/project bytes.

## Failure classifications and diagnostic history

- `INFRASTRUCTURE`: the prior session interruption and missing backend wheel state; the exact
  authorized backend recovery was recorded in `evidence/task-3c-backend-acquisition.json` and
  the two wheels were reused offline thereafter.
- `REPORT`: source archive verifier normalization and verify-bundle field-location assumptions;
  both were corrected only in scratch and the default builder/verifier/product bytes were not
  changed.
- `REPORT/SPEC`: former eleven-blocker ledger arithmetic, corrected by Sol before final Task3c
  public evidence.
- No PRODUCT, PROJECT_INPUT, HARDWARE, PLATFORM, or remote failure occurred in Task3c.

## Cleanup and handoff

After formal evidence capture, only these five exact run-scoped scratch roots are removed after
resolving and validating each path under `C:/tmp/stm32tk-vs10a-legacy-campaign/scratch` and
requiring the `task-3c-` prefix:

- `task-3c-backend-recovery-20260825`
- `task-3c-backend-recovery-20260826`
- `task-3c-closed-wheelhouse-20260826`
- `task-3c-repeat-candidate-20260826`
- `task-3c-source-crlf-20260826`

The formal `evidence/` directory, verified
`runtime/scoped-options-candidate`, extracted candidate, active managed runtime, unchanged P0
project, and source-controlled Toolkit worktree are retained. No golden path, shared cache, or
user-owned path is touched. The final local status is clean/no remote after this report is
committed; Sol owns complete-diff review and the acceptance verdict.
