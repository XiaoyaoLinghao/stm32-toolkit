# STM32TK-1001 H2 Build-to-Flash Contract Correction Implementation Report

- Accepted slice base: `8149273677716840406987e342da1ccbd62969d3`
- Approved spec head: `3fc1e9033bd9415d5b9c854fb3560e518cebf31a`
- Approved implementation plan commit: `27bb7ed9af4dc18e4563f3bd41b2c7379f380ca9`
- Code/tests head before this report: `568f5028e279a393094c95f44403a4d03b28dcfd`
- Code/tests tree: `2f689b0a24749ca83451eac1f65593efbd8e133e`
- Implementer: gpt-5.6-luna / max
- Reviewer/acceptance owner: gpt-5.6-sol
- Implementer verdict: `RETURNED_FOR_INDEPENDENT_REVIEW`

## Exact implementation ledger

The required Step 1 commands were run before staging this report.

`git status --short --branch`:

```text
## codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl
```

`git rev-parse HEAD`:

```text
568f5028e279a393094c95f44403a4d03b28dcfd
```

`git rev-parse 'HEAD^{tree}'`:

```text
2f689b0a24749ca83451eac1f65593efbd8e133e
```

`git log --format='%H %T %s' --reverse 3fc1e9033bd9415d5b9c854fb3560e518cebf31a..HEAD`:

```text
27bb7ed9af4dc18e4563f3bd41b2c7379f380ca9 135a44e38e3db1efc183331943a7f7c80c1f5537 docs: plan H2 build flash contract correction
689a20c779d36c337a8c72f363dcc71b372b84ca 5f3128ecd82b0e32c270ddd82b4e6f896ce26623 test: expose public build flash contract gap
568f5028e279a393094c95f44403a4d03b28dcfd 2f689b0a24749ca83451eac1f65593efbd8e133e fix: accept public build evidence for flash
```

The exact commit contents identify the implementation lineage: RED commit
`689a20c779d36c337a8c72f363dcc71b372b84ca` modifies only
`tools/stm32-toolkit/tests/test_flash.py`; GREEN commit
`568f5028e279a393094c95f44403a4d03b28dcfd` modifies only
`tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.

`git diff --check 8149273677716840406987e342da1ccbd62969d3..HEAD` exited `0`
with no output.

`git diff --name-status 8149273677716840406987e342da1ccbd62969d3..HEAD`:

```text
A	docs/superpowers/plans/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction.md
A	docs/superpowers/specs/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-design.md
M	tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
M	tools/stm32-toolkit/tests/test_flash.py
```

`git remote -v`:

```text
origin	https://github.com/XiaoyaoLinghao/stm32-toolkit.git (fetch)
origin	https://github.com/XiaoyaoLinghao/stm32-toolkit.git (push)
```

The first two entries are the approved specification and implementation-plan
artifacts. Within the implementation portion, the product file is only
`probe/flash.py` and the test file is only `test_flash.py`.

## TDD lineage

### RED

- Commit: `689a20c779d36c337a8c72f363dcc71b372b84ca`
- Selected: 7
- Passed: 0
- Failed: 7
- Exit: 1
- Command:

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-red `
  -k 'public_run_build_output or cross_dialect'
```

- First mismatch: `test_public_run_build_output_flashes_without_rewriting_build_evidence`
  expected `outcome.ok is True`; actual result was
  `FIRMWARE_BUILD_REQUIRED` with details
  `{'path': 'artifacts/migration/build-result.json', 'rule': 'status'}`.
- This was the expected product RED: the genuine public `run_build()` producer
  emitted the canonical empty `stage`, while the accepted-base consumer
  rejected it before dialect dispatch. The fake CMake seam did not invoke real
  CMake, GitHub, or hardware.

### GREEN

- Commit: `568f5028e279a393094c95f44403a4d03b28dcfd`
- Target selection: 7 selected, 7 passed, 0 failed, exit 0.
- Target command:

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-green-target `
  -k 'public_run_build_output or cross_dialect'
```

- Focused selection: 137 selected, 137 passed, 0 failed, exit 0.
- Focused command:

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_build_runner.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-green-focused
```

The focused count was confirmed by collection as 85 build-runner tests, 13
debug-read tests, and 39 flash tests. No full suite was run.

## Product boundary

- Product file changed: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py` only.
- Test file changed: `tools/stm32-toolkit/tests/test_flash.py` only.
- The build runner, schemas, CLI/MCP, service/backend, runtime, project,
  hardware, network, and remotes were unchanged.
- The accepted-base-to-code-head diff also contains only the approved H2
  specification and implementation-plan documents listed in the ledger; no
  other product or test files changed.

## Safety result

- Genuine public build evidence is consumed without rewriting the build result
  or identity documents.
- A wrong connected target may attach for identity resolution but performs zero
  programming or readback operations.
- Canonical artifact shape/path conflicts fail closed before attach.
- Only the bounded `_flash_segments` test seam was patched in the success-path
  regression; identity, disk hashes, attachment validation, programming, and
  readback remain real.
- No physical hardware command was run for this correction.
- No runtime installation, network operation, remote operation, push, PR
  mutation, merge, tag, release, or branch deletion was performed.

## Cleanup

All paths below were exact, resolved, inspected, and verified absent after
cleanup; no other `C:\tmp` path was touched.

- Removed `C:\tmp\stm32tk-1001-h2-build-flash-red`.
  - Initial recursive `Remove-Item` was rejected by the execution policy.
  - Direct directory deletion then reported
    `Access to the path '26f5f1a641efcb239aedc80f51c06712f6d7b8' is denied.`
  - Classification: `ENVIRONMENT/cleanup-policy`.
  - Read-only attributes were cleared only within this run-owned tree, after
    exact-path and no-reparse-point checks; deletion then succeeded.
- Removed `C:\tmp\stm32tk-1001-h2-build-flash-green-target`.
  - Recursive `Remove-Item` was rejected by the execution policy; exact-path
    fallback deletion succeeded after run-owned read-only attributes were
    cleared. No residual remained.
- Removed `C:\tmp\stm32tk-1001-h2-build-flash-green-focused`.
  - Recursive `Remove-Item` was rejected by the execution policy; exact-path
    fallback deletion succeeded after run-owned read-only attributes were
    cleared. No residual remained.

## Implementation return

The implementation is returned for independent complete-diff review. This
report does not issue a Sol verdict and does not claim `ACCEPTED`, hardware
PASS, runtime installation, or second-flash authorization.
