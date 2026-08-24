# SDD ledger — VS07-C safe regeneration

- Status: `ACCEPTED` by the GPT-5.6-sol primary agent after independent
  complete-diff review and final slice verification.
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

- Product/tests CodeHead: `b01ece4e11c5db051f1ddbdd569195d9e47c811b`.
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
- The exact approved slice contained 699 tests: `698 passed, 1 skipped`; the
  skipped test was the Windows symlink-creation probe because this host refused symlink
  creation, and it remains deferred platform evidence rather than a physical
  pass. `compileall` and accepted-base-to-CodeHead `git diff --check` passed.
- Review-round GREEN focused coverage passed 29 tests with one skipped Windows
  symlink probe; the RED run had 11 expected failures across 30 collected
  tests. The revision product commit adds post-configure/build App/Tests
  rehashing under the activation lock, candidate-blocker rejection, complete
  preview metadata bounds, Toolkit-over-CubeMX precedence, no-follow identity
  reads for project and authorization files, and the focused authorization,
  rollback, CLI, and MCP regressions.
- Review-round 2 added a deletion RED regression for a missing
  Toolkit-owned `CMakeLists.txt`; the observed failure had both
  `REGENERATION_STATE_CHANGED` and `REGENERATION_TOOLKIT_DRIFT`. The minimal
  fix excludes Toolkit-owned paths from the missing/type CubeMX branch, so the
  focused round-2 GREEN run passed 30 with one skipped test and the exact slice
  contained 699 tests: 698 passed and one skipped. The correction is product
  commit `b01ece4e11c5db051f1ddbdd569195d9e47c811b`.
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

## Independent Sol acceptance

- The reviewer inspected the complete
  `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..4f83dbf507d468e9d923ac1ff1dd331bf1d456ff`
  diff in clean detached worktree
  `C:/tmp/stm32tk-0703-sol-final-review-4f83dbf`. The diff contains 15 files,
  3,496 insertions, and one deletion. No unresolved product defect remained
  after the two recorded revision rounds.
- The exact approved 17-file slice independently contained 699 tests: `698
  passed, 1 skipped`, with zero failures and zero errors in 430.757 seconds.
  The skip is the host-refused Windows symlink probe and remains deferred platform
  evidence. Python 3.12 `compileall` and accepted-base-to-final-head `git diff
  --check` passed.
- Independent adversarial probes passed: tampered authorization peek/consume
  returned `REGENERATION_AUTHORIZATION_INVALID`; a candidate `App/` collision
  returned `REGENERATION_STATE_CHANGED`; a 10,000-change public preview
  returned `REGENERATION_PREVIEW_TOO_LARGE`; injected activation failure
  returned `REGENERATION_ACTIVATION_FAILED` while preserving the old tree and
  leaving no residue; post-build user-tree corruption returned
  `REGENERATION_USER_DRIFT` while preserving the original user file; deletion
  of Toolkit-owned `CMakeLists.txt` returned only
  `REGENERATION_TOOLKIT_DRIFT:CMakeLists.txt`.
- A fresh independent native scenario in a local Git repository with no
  remote used the installed CubeMX 6.18.1-RC2, CubeCLT 1.22.0, and
  STM32Cube_FW_F4_V1.28.3. Plan, prepare, apply, configure, Debug, and Release
  all returned `OK`; authorization replay returned
  `REGENERATION_AUTHORIZATION_CONSUMED`. `App/` SHA-256
  `efd093802e46749d44ca5119bdaf6fde916a5df932c1b2fa3fa4d278ea80cb39`
  and `Tests/` SHA-256
  `d27f473d5cdf8d357b4969ddf7a8c318f58b38b1cad497bb80bdd973144172c2`
  were unchanged. Debug build ID was
  `4c68793a0ca5d5eee2e721f6432391e44ef9ab2899551c07cfe123d1d59b03db`;
  Release build ID was
  `a7c32fc88e46adc61bf746786699fba365e0de12b886ca72151083fd9e83ffa7`.
  No `.stm32tk-*` residue remained and only the pre-existing Java PID 32708
  was present after the run.
- Fresh independent Keil-origin planning returned
  `REGENERATION_NOT_CUBEMX_PROJECT`; its project tree digest remained
  `4443544aa370c17a642d5da5b2384b817d0eef898c6f72cbab699f106c7ab6da`
  before and after, and no data root was created.
- The implementation branch was clean, local, unpushed, and had no upstream
  before this acceptance-only ledger update. No push, PR, merge, tag, release,
  hardware action, installation, or other remote operation was performed.
  VS07-C is accepted and work stops here without entering VS08.
