# STM32TK-1001 OBSERVE Session Attach Reuse Implementation Report

Status: `RETURNED FOR INDEPENDENT SOL REVIEW`

- Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`; tree `c183a70a07de1cf404720b82303e2f2ff5f80420`
- Approved specification: `1a54ed0f9b5c1dc9544ce3f15dc015e71e7216f3`; tree `9dc81bc81ac0ec186dddf2ada7c5701951db4684`
- Approved implementation plan: `4639e4c53749a2341baea5340c1f470eefc2538b`; tree `b289ead6c46a4dafe96dcd490e40cb4d66cb0eea`
- RED commit: `eff0b53142c9f9568a332d6a02eda5db35e0d37a`; tree `df2cb465ec38471d7d6abe8fcb9e1784e1086168`
- CodeHead before this report commit: `fb0868d5386bd2d41f602f62b069b66348ad6ea9`; tree `5ed8c196b5c21b7cddd6b6fac77410bad6b1e3af`
- Implementation owner/evidence owner: one GPT-5.6-luna agent, reasoning effort `max`
- Independent reviewer: GPT-5.6-sol primary, pending
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
- Remote baseline: `origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl` at `74ee5f4c7872af1bb612c9068af36319457e087b`
- Remote actions: none; no push, PR mutation, merge, tag, release, or branch deletion

## Implemented behavior

The Probe Service now owns one private, in-memory OBSERVE attachment record for its own
lifetime. The record contains the exact accepted probe selector, the canonical accepted target,
and the immutable `ProbeAttachmentEvidence` returned by the first successful backend attach.

- The first OBSERVE logical `probe.attach` dispatches one backend `open_attach()`, preserves the
  existing resolved-target validation and error/cleanup behavior, serializes the evidence, and
  stores the record only after payload creation succeeds.
- Later OBSERVE logical attaches with the same exact probe selector and a canonical-equivalent
  target return the stored resolved evidence without enumeration, backend attach, close,
  halt/resume, reset, or programming. The existing response shape remains valid for the current
  logical target spelling.
- A changed probe selector or non-equivalent target raises the unchanged stable
  `PROBE_IDENTITY_MISMATCH` (`Connected target identity does not match`, empty details) before any
  backend call and leaves the accepted backend session usable.
- A failed or unresolved first attach never populates reusable state. An explicit later caller
  attach can invoke the backend again; this is not an automatic product retry.
- `CONTROL` and `MODIFY` keep their existing dispatch and halt-on-connect behavior. Service
  teardown clears the private record together with other owned in-memory state, including when a
  close or lease-release error is propagated.

No public client/protocol/backend/worker interface, operation schema, debug logical attach count,
authorization contract, target-state transition, timeout/recovery path, or response model changed.
No new worker, backend, retry, fallback, reset, programming path, or persistent state was added.

## TDD lineage and evidence

Task 1 RED command (CPython 3.12, exact prescribed selector):

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-red' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'observe_reuses_one_backend_attachment or observe_rejects_changed_attachment_identity or explicit_second_attach_after_first_failure_is_not_cached or non_observe_repeat_attach or observation_attachment_is_service_local' `
  -q
```

Observed output was `FFF...F [100%]`: 4 intended failures and 3 passes. The failures were
`test_observe_reuses_one_backend_attachment_across_logical_guards`, both parameterized
`test_observe_rejects_changed_attachment_identity` cases, and
`test_observation_attachment_is_service_local`. They demonstrated repeated backend dispatch,
changed-identity replacement/incorrect errors, and missing service-lifetime isolation. The
first-failure non-caching and both non-OBSERVE compatibility tests already passed at the accepted
base. No product file was changed before the RED commit.

Task 1 RED commit:

```text
eff0b53142c9f9568a332d6a02eda5db35e0d37a
df2cb465ec38471d7d6abe8fcb9e1784e1086168
4639e4c53749a2341baea5340c1f470eefc2538b
test(vs10a): define observe session attach reuse
```

Task 2 targeted GREEN command (post-implementation):

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-green-targeted' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'observe_reuses_one_backend_attachment or observe_rejects_changed_attachment_identity or explicit_second_attach_after_first_failure_is_not_cached or non_observe_repeat_attach or observation_attachment_is_service_local' `
  -q
```

The targeted output was `....... [100%]` (7 passed, 0 failed, 0 skipped). A fresh post-refactor
targeted run used `C:\tmp\stm32tk-1001-observe-attach-reuse-green-targeted-refactor` and produced
the same 7/7 result.

Task 2 complete focused matrix, rerun with a fresh short run root, exited 0 at `[100%]` with no
failure or skip output. The three files collected 300 tests: 112 in `test_probe_service.py`, 131
in `test_debug_firmware.py`, and 57 in `test_debug_read.py`. The exact final Task 3 run is
recorded below against the frozen CodeHead.

## Final CodeHead verification

Environment:

- Interpreter: `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`
- Python: `3.12.10`
- pytest: `8.4.2`
- PyOCD: `0.45.1`
- CodeHead: `fb0868d5386bd2d41f602f62b069b66348ad6ea9`
- CodeHead tree: `5ed8c196b5c21b7cddd6b6fac77410bad6b1e3af`
- Start UTC: `2026-09-03T11:33:17.0215232Z`
- End UTC: `2026-09-03T11:36:05.6251163Z`
- Duration: `168.596` seconds
- Result: exit code `0`; 300 passed, 0 failed, 0 skipped

Exact pytest command:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-final' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q
```

Captured final output ended with:

```text
............                                                             [100%]
pytest_exit=0
```

The collection check at the same source/test set reported:

```text
tests/test_debug_firmware.py: 131
tests/test_debug_read.py: 57
tests/test_probe_service.py: 112
```

## Changed paths and self-review

The accepted-base-to-CodeHead diff contains exactly the two approved frozen lineage files and
these two product/test paths:

- `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-observe-session-attach-reuse-design.md`
  — approved specification, unchanged after approval.
- `docs/superpowers/plans/2026-09-03-stm32-toolkit-1001-observe-session-attach-reuse.md`
  — approved plan, unchanged after approval.
- `tools/stm32-toolkit/tests/test_probe_service.py` — RED regression contracts.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py` — private OBSERVE reuse state and
  dispatch/teardown behavior.

The implementation self-review checked the complete product diff against the accepted base:
the helper performs no backend call or catch; identity mismatch occurs before dispatch; first
attach mismatch restoration/close/error precedence remains intact; state is stored only after
`to_dict()` and validation; non-OBSERVE dispatch is unchanged; and teardown clears the record.
The targeted assertions cover one physical attach, canonical matching, fail-closed changed
identity, failed-first non-caching, CONTROL/MODIFY compatibility, and service-local lifetime.
Independent Sol review remains required; this self-review is not an acceptance verdict.

## Hardware and cleanup boundary

No physical probe, public bind, memory read, reset, flash, or target operation was run. Fake and
software service/client evidence is not physical acceptance, and this report makes no claim that
physical public bind/read now passes. After independent software acceptance, one separately
authorized single physical public read-only bind plus `GPIOE.ODR` read remains the next gate; no
retry is implied.

The following exact run-owned basetemps were inspected and removed without touching source,
fixtures, user files, or shared caches:

- `C:\tmp\stm32tk-1001-observe-attach-reuse-red`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-green-targeted`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-green-targeted-refactor`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-green`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-green-rerun`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-final`

The focused matrix generated read-only Git-object files and reparse-point test directories in its
own basetemps. Cleanup first reported `Access denied`; a bounded cleanup then cleared attributes
only inside each exact run root and removed reparse leaves without following them. All listed roots
were absent after cleanup. The implementation worktree was clean at the CodeHead before this
report-only file was created. The remaining gate is independent complete-diff Sol review, followed
only by the separately authorized single physical confirmation.
