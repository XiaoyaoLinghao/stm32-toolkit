# SDD ledger — VS07-C safe regeneration

- Status: Luna implementation returned for independent Sol review; no final
  acceptance verdict has been issued.
- Module/phase: STM32 Toolkit 0.7 / VS07-C.
- Accepted base: `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d`.
- Specification/plan owner: GPT-5.6-sol primary agent.
- Implementer: one GPT-5.6-luna, reasoning max, complete local pass.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0703-SAFE-REGENERATION` /
  `C:/tmp/stm32tk-0703-safe-regeneration`.
- Remote authority: none.
- Specification:
  `docs/superpowers/specs/2026-08-24-stm32-toolkit-0703-safe-regeneration-design.md`.
- Plan:
  `docs/superpowers/plans/2026-08-24-stm32-toolkit-0703-safe-regeneration.md`.

## Implementer return

- Product/tests CodeHead: `94fd34a0b19890accdedc6002ab3c84fb87e8689`.
- The product/tests commit and the updated implementation report/ledger are
  local, unpushed, and separate. The report/ledger commit SHA is supplied in
  the implementer return rather than recorded inside its own tracked files.
- No PR, merge, tag, release, hardware, installation, or remote action was
  performed.

## Reconstructed baseline facts

- VS07-B was independently accepted at the full base above. Its product
  CodeHead was `e515eac91e99b777819c1660221d5c29ad1ef9a5`; later commits through
  this base are documentation/report reconciliation only.
- Installed environment observed during VS07-B acceptance: CubeMX
  6.18.1-RC2, CubeCLT 1.22.0, GCC 14.3.1, CMake 4.3.1, Ninja 1.13.2, and
  `STM32Cube_FW_F4_V1.28.3` below the user's local Cube repository. No install
  was performed by Codex.
- The accepted captured IOC SHA-256 is
  `636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
- Two independent accepted VS07-B native outputs each contained 1,460
  CubeMX-owned files, and their path/hash inventories were byte-identical.
  This supports, but does not replace, VS07-C's fail-closed preview replay
  check.
- Pre-existing `javaw.exe` PID 32708 is environmental state. It must not be
  terminated; only PID delta may be attributed to this slice.
- The unrelated `D:/workspace/stm32-toolkit` worktree and every other existing
  worktree remain out of scope.

## Frozen slice boundary

- Public plan is read-only and never launches CubeMX.
- Authorized prepare runs one cleaned preview generation and persists only a
  single-use apply capability.
- Authorized apply reruns generation, requires an exact preview digest,
  preserves `App/` and `Tests/`, rebuilds Debug/Release, and transactionally
  activates.
- Unknown ownership, non-IOC owned drift, Toolkit drift, exact generator/
  package drift, unsafe paths, or Keil origin fail closed with typed results.
- No hardware, release gate, compatibility matrix, coverage gate, VS08 work,
  Python expansion, installation, or remote action is in scope.

## Progress tracking

Progress is recorded by completed public scenarios and independently reviewed
behavior, not task percentages. Task 1–4 are one Luna implementer's internal
checkpoints. TDD evidence, classifications, product CodeHead, slice result,
real native result, implementation report, branch cleanliness, and final Sol
verdict will be appended here without deleting this reconstructed baseline.

## Completed public scenarios and evidence

- Read-only plan, authorized preview, exact replay/apply, user-tree
  preservation, configure, Debug, Release, atomic activation, and
  single-use authorization were exercised by the focused tests and the fresh
  native software scenario.
- The exact approved slice passed `698 passed, 1 skipped`; the skipped test was
  the Windows symlink-creation probe because this host refused symlink
  creation, and it remains deferred platform evidence rather than a physical
  pass. `compileall` and accepted-base-to-CodeHead `git diff --check` passed.
- Review-round GREEN focused coverage passed 29 tests with one skipped Windows
  symlink probe; the RED run had 11 expected failures across 30 collected
  tests. The revision product commit adds post-configure/build App/Tests
  rehashing under the activation lock, candidate-blocker rejection, complete
  preview metadata bounds, Toolkit-over-CubeMX precedence, no-follow identity
  reads for project and authorization files, and the focused authorization,
  rollback, CLI, and MCP regressions.
- Fresh r3 native evidence used the installed CubeMX 6.18.1-RC2, CubeCLT
  1.22.0, and F4 V1.28.3 package. The copied prior owned IOC was changed from
  `ProjectManager.HeapSize=0x200` to `0x300`; plan/prepare/apply returned `OK`;
  configure, Debug, and Release returned `OK`; `App/keep.txt` SHA-256
  `727948d3d05623d6152720a780545ecc7da8f9fb5a8c2885fe8f565733b8c6dd` and
  `Tests/keep.txt` SHA-256
  `b3c0f9601084c9d578dcf5621fab01ee59fa46957f424c51dee9a5a48dbf4b4c` were
  unchanged; `.stm32tk-*` transaction/control roots were absent; only the
  pre-existing javaw PID 32708 remained. Authorization replay returned
  `REGENERATION_AUTHORIZATION_CONSUMED`.
- Fresh copied schema-2 Keil read-only evidence returned operation
  `project-regenerate-plan` / `REGENERATION_NOT_CUBEMX_PROJECT` with equal
  before/after tree digest
  `3fe379cf892915a39f4c063704bf757e390b44dd7cfb14bbf35cbd4b5a5cb47c`.

## Outstanding owner

- GPT-5.6-sol must review the complete accepted-base-to-final-head diff in a
  clean worktree, repeat the required slice and independent probes, reconcile
  the report, and issue the final `ACCEPTED`, `REVISION_REQUIRED`, or
  `REWRITE_REQUIRED` verdict.
