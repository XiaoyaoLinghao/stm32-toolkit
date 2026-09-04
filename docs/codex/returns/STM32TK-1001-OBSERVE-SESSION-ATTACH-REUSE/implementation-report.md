# STM32TK-1001 OBSERVE Session Attach Reuse Implementation Report

Status: `RETURNED FOR INDEPENDENT SOL REVIEW`

- Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`; tree `c183a70a07de1cf404720b82303e2f2ff5f80420`
- Original approved specification: `1a54ed0f9b5c1dc9544ce3f15dc015e71e7216f3`; tree `9dc81bc81ac0ec186dddf2ada7c5701951db4684`
- Original approved implementation plan: `4639e4c53749a2341baea5340c1f470eefc2538b`; tree `b289ead6c46a4dafe96dcd490e40cb4d66cb0eea`
- Initial RED commit: `eff0b53142c9f9568a332d6a02eda5db35e0d37a`; tree `df2cb465ec38471d7d6abe8fcb9e1784e1086168`
- Initial GREEN commit: `fb0868d5386bd2d41f602f62b069b66348ad6ea9`; tree `5ed8c196b5c21b7cddd6b6fac77410bad6b1e3af`
- Initial implementation report: `ba5a8b4bd9a3a39cf04b400eb930f135cf09acfd`; tree `dd0b70ebcf43ede0b185de6c2c6520f10810333e`
- Fix-round RED tests commit: `7114dd3f7ae20b4a1d1314d4645a30a866b16d96`; tree `8411ac22f2153e85056135b4230dfc8f02373cae`
- Fix-round GREEN commit: `32904e71662e55fec644ca7b75f36399db52b91d`; tree `4f71eaa7a1b2ce71b96c770d9807bf9182e1d4cb`
- Fix-round implementation report: `553450694eb7b33ad6d23580f81ebc11595bd685`; tree `0d1706238c80c450336583d1f194c5ff767353fd`
- Approved amended deadline-fencing specification: `0f214e5488f5d05e18eb882b5b27576c4ba297e4`; tree `c73e627514ef35f79eba8845bf5b75cb45144973`
- Approved amended deadline-fencing plan / execution base: `39366d7eb928afc7d512118c6051bbae83580653`; tree `f1760edf42668154f445933f72650894a0e3008a`
- Absolute-deadline RED tests commit: `e07f4b3a4cb9ddfc60d91aa8f47d8097e480359c`; tree `c5aa7d50f24c6f9ba9d1a1057e4d0ad543c01884`
- Task 1 schedulability correction commit: `609c5f3386e87a7b82b0612e9bdbdfd0e302c05f`; tree `f063c9fe0dab47920efac03135702b927973b0bc`
- Final CodeHead before this report commit: `2fe70d8339963b2109db2d50a420a5b114813528`; tree `4b7bd6aa34a7d1aa45adf91f4452bd682fd52d9f`
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
- OBSERVE attach cache inspection, candidate publication, and timeout/cancellation recovery are
  fenced by a private service-local lifecycle lock. A candidate is published only after the
  serialized operation succeeds; an abandoned attach clears the candidate before recovery, and
  queued same-identity attaches cannot observe it while recovery close is running, including when
  that close fails.
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
authorization contract, target-state transition, public error code/message, entered-backend
recovery precedence, or response model changed. The approved deadline-fencing amendment
intentionally changes total OBSERVE attach timeout accounting: `timeout_ms` now starts before
private lifecycle-lock admission and includes queue wait, while entered-backend recovery remains
bounded and retains its existing cleanup-error precedence. CONTROL and MODIFY timeout and
dispatch behavior remain unchanged.
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
changed-identity replacement/incorrect errors, and repeated dispatch in the first service. The
last test did not isolate teardown cache clearing; the fix-round tests below provide that direct
same-service proof. The first-failure non-caching and both non-OBSERVE compatibility tests already
passed at the accepted base. No product file was changed before the RED commit.

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

The original Task 2 complete focused matrix, rerun with a fresh short run root, exited 0 at
`[100%]` with no failure or skip output. Before this fix round, the three files collected 300
tests: 112 in `test_probe_service.py`, 131 in `test_debug_firmware.py`, and 57 in
`test_debug_read.py`. The fix-round final CodeHead run is recorded below.

## Prior rejected waves and approved correction

The initial implementation wave (`eff0b531` RED → `fb0868d5` GREEN → `ba5a8b4b` report)
was returned `REVISION_REQUIRED` by the independent Sol review. Its stale-cache finding was
that candidate evidence could be published from the backend task before timeout/cancellation
recovery closed the session; the review also required direct same-service teardown tests and
corrected the report's teardown claim.

The first correction wave (`7114dd3f` RED → `32904e71` GREEN → `55345069` report) closed
candidate publication/recovery ordering and same-service teardown, but the next independent
review returned `REVISION_REQUIRED` because the new private lifecycle lock started queued
requests' timeout accounting too late. Its direct diagnostic held the first attach/recovery and
observed a 20 ms queued request still pending after roughly 80 ms, with later dispatch possible.
That review also required the report to state the semantic deadline change rather than claim
timeout/recovery semantics were unchanged.

The approved correction amended the design in `0f214e54` and the plan in `39366d7e`: one
private OBSERVE lifecycle lock remains the sole serialization primitive, while one monotonic
absolute deadline starts at request admission and covers lock wait, backend execution, candidate
commit/abandon, and entered-backend recovery. Task 1 then produced RED `e07f4b3a`, corrected
the schedulability oracle in `609c5f33` (its fence-bypass mutation was `FF`), and Task 2
produced the final GREEN CodeHead `2fe70d83`.

## Independent review fix round

The independent Sol review returned `REVISION_REQUIRED` for (1) publishing the OBSERVE candidate
inside the backend task before timeout/cancellation recovery had made it non-reusable, allowing a
queued same-identity request to observe stale evidence, and (2) the prior service-local test not
proving that the same service object discarded its cache during normal or error teardown.

Fix-round RED command, run before the product fix:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-fix-red' tools/stm32-toolkit/tests/test_probe_service.py -k 'observe_attach_timeout_or_cancellation or observe_stop_clears_attachment' -q
```

Observed output was `FF... [100%]`: the timeout and cancellation cases failed because the queued
request completed from the stale candidate or did not dispatch a second attach; the three direct
same-service stop/restart tests passed under the existing teardown clear. The RED test commit is
`7114dd3f7ae20b4a1d1314d4645a30a866b16d96` (tree
`8411ac22f2153e85056135b4230dfc8f02373cae`).

The minimal fix added a private OBSERVE attach lifecycle lock, moved candidate publication out of
the backend worker and onto the successful serialized return path, and cleared the candidate at
the start of every OBSERVE attach timeout/cancellation recovery. CONTROL and MODIFY continue to
use the existing path. The code commit is `32904e71662e55fec644ca7b75f36399db52b91d` (tree
`4f71eaa7a1b2ce71b96c770d9807bf9182e1d4cb`).

Fix-round targeted GREEN command:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-targeted-v3' tools/stm32-toolkit/tests/test_probe_service.py -k 'observe_reuses_one_backend_attachment or observe_rejects_changed_attachment_identity or explicit_second_attach_after_first_failure_is_not_cached or non_observe_repeat_attach or observation_attachment_is_service_local or observe_attach_timeout_or_cancellation or observe_stop_clears_attachment' -q
```

Output was `............ [100%]` (12 passed, 0 failed, 0 skipped). The required teardown mutation
check temporarily removed `_observation_attachment = None` from `_stop_owned_state()` and ran:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-mutation-no-clear' tools/stm32-toolkit/tests/test_probe_service.py -k 'observe_stop_clears_attachment' -q
```

Mutation output was `FFF [100%]`: normal stop, backend-close-error, and lease-release-error
same-service restart tests all failed to observe a second `open_attach`. The teardown clear was
restored before the final GREEN matrix and code commit.

The post-fix focused matrix command was:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-full' tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_debug_read.py -q
```

It exited 0 at `[100%]`; collection at the same source set was 117 service tests, 131
debug-firmware tests, and 57 debug-read tests (305 passed, 0 failed, 0 skipped).

## Absolute-deadline amendment wave

The amended Task 1 RED selector was run before changing product bytes:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-deadline-red' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  -k 'queued_attach_timeout_includes_lifecycle_lock_wait or queued_attach_timeout_maps_to_public_error or recovery_close_failure_releases_deadline_fence or observe_attach_timeout_or_cancellation_does_not_reuse_candidate' `
  -q
```

The result was exit code `1`, output `FFF.. [100%]`: the three new queued-expiry
contracts failed at `queued.done()` because the private lifecycle-lock wait was not
yet covered by `timeout_ms`; both existing timeout/cancellation recovery cases passed.
No accepted gate or fixture failure prevented the intended branch from being reached.
The RED commit was `e07f4b3a4cb9ddfc60d91aa8f47d8097e480359c` (tree
`c5aa7d50f24c6f9ba9d1a1057e4d0ad543c01884`).

The Task 1 test-correction review found that the existing recovery test asserted
`not queued.done()` before the queued coroutine was schedulable. A test-local in-memory
no-op lifecycle-lock mutation (no product file mutation) produced exit code `1`, output
`FF [100%]`, with both `timeout` and `cancelled` cases failing at the corrected pending
assertion while `close_release` remained unset. This mutation `FF` proves the oracle is
effective. The exact mutation basetemp was cleaned. The correction commit was
`609c5f3386e87a7b82b0612e9bdbdfd0e302c05f` (tree
`f063c9fe0dab47920efac03135702b927973b0bc`).

The exact amended RED selector was rerun unchanged after that correction and again
returned exit code `1`, output `FFF.. [100%]`, with the same three intended deadline
failures and two recovery passes. The corrected tests use a `queued_started` admission
event plus a bounded non-cancelling scheduling window before asserting that recovery
close still fences the request.

Task 2's targeted GREEN selector returned exit code `0`, output `..... [100%]` (5/5),
and its reuse/teardown contracts returned exit code `0`, output `.......... [100%]`
(10/10). The product GREEN change is the prescribed outer `asyncio.timeout_at()`
wrapper in `_run_backend()`; `_run_backend_inner()` was not changed. It is committed as
`2fe70d8339963b2109db2d50a420a5b114813528` (tree
`4b7bd6aa34a7d1aa45adf91f4452bd682fd52d9f`).

## Final CodeHead verification

Environment:

- Interpreter: `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`
- Python: `3.12.10`
- pytest: `8.4.2`
- PyOCD: `0.45.1`
- CodeHead: `2fe70d8339963b2109db2d50a420a5b114813528`
- CodeHead tree: `4b7bd6aa34a7d1aa45adf91f4452bd682fd52d9f`
- Start UTC: `2026-09-04T00:25:34.6473897+00:00`
- End UTC: `2026-09-04T00:28:01.1599346+00:00`
- Duration: `146.5125449` seconds
- Result: exit code `0`; 308 passed, 0 failed, 0 skipped

Exact pytest command:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  -p no:cacheprovider `
  --basetemp 'C:\tmp\stm32tk-1001-observe-deadline-final' `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_debug_firmware.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q
```

Captured final output was:

```text
........................................................................ [ 23%]
.............
........................................................... [ 46%]
..........................................................
........
...... [ 70%]
..
.........
.........
........
......
..
..
....
.......
.......
......
.......
... [ 93%]
...
......
......
.....                                                     [100%]
FINAL_START_UTC=2026-09-04T00:25:34.6473897+00:00
FINAL_END_UTC=2026-09-04T00:28:01.1599346+00:00
FINAL_DURATION=00:02:26.5125449
FINAL_EXIT_CODE=0
```

The collection check at the same source/test set reported:

```text
tests/test_debug_firmware.py: 131
tests/test_debug_read.py: 57
tests/test_probe_service.py: 120

Total: 308 collected; 308 passed, 0 failed, 0 skipped.
```

## Changed paths and self-review

The accepted-base-to-CodeHead diff contains exactly these seven paths. The earlier tracked
implementation report is present legitimately because this branch contains retained prior
implementation/report waves; it is classified as prior report history, not falsely omitted or
relabelled as a product path:

- `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-observe-session-attach-reuse-design.md`
  — original approved specification, frozen after approval.
- `docs/superpowers/plans/2026-09-03-stm32-toolkit-1001-observe-session-attach-reuse.md`
  — original approved plan, frozen after approval.
- `docs/superpowers/specs/2026-09-03-stm32-toolkit-1001-observe-attach-deadline-fencing-design.md`
  — approved amendment specification for total OBSERVE lifecycle deadline accounting.
- `docs/superpowers/plans/2026-09-03-stm32-toolkit-1001-observe-attach-deadline-fencing.md`
  — approved amendment plan for the absolute-deadline correction.
- `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`
  — prior tracked implementation report from the earlier waves, corrected by this report-only
  update.
- `tools/stm32-toolkit/tests/test_probe_service.py` — RED regression contracts and Task 1
  schedulability correction.
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py` — private OBSERVE reuse state,
  dispatch/teardown behavior, and the amended outer absolute deadline.

The implementation self-review checked the complete product diff against the accepted base:
the helper performs no backend call or catch; identity mismatch occurs before dispatch; first
attach mismatch restoration/close/error precedence remains intact; state is stored only after
`to_dict()` and a successful serialized wait; an abandoned candidate is cleared before recovery;
the OBSERVE lifecycle lock fences queued attach requests; the absolute deadline starts before
that lock and prevents queued expiry from entering `_run_backend_inner()`; non-OBSERVE dispatch
is unchanged; and teardown clears the record before propagating cleanup errors. The targeted
assertions cover one backend attach, canonical matching, fail-closed changed identity,
failed-first non-caching, CONTROL/MODIFY compatibility, timeout/cancellation recovery,
same-service teardown lifetime, queued expiry/no-late-dispatch, public timeout mapping, and
close-failure lock release. This is an implementer self-review only, not an acceptance verdict;
independent Sol review remains required.

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
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-red`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-targeted`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-targeted-v2`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-mutation-no-clear`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-targeted-v3`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-green-full`
- `C:\tmp\stm32tk-1001-observe-attach-reuse-fix-final`
- `C:\tmp\stm32tk-1001-observe-deadline-red`
- `C:\tmp\stm32tk-1001-observe-deadline-mutation`
- `C:\tmp\stm32tk-1001-observe-deadline-green-targeted`
- `C:\tmp\stm32tk-1001-observe-deadline-green-contracts`
- `C:\tmp\stm32tk-1001-observe-deadline-green-full`
- `C:\tmp\stm32tk-1001-observe-deadline-final`

The focused matrices generated read-only Git-object files and reparse-point test directories in
their own basetemps. Cleanup first reported `Access denied` for the full matrix and encountered two
test-owned junctions in the final run; bounded cleanup cleared attributes only inside each exact
run root and removed those junction leaves without following them. All listed roots were absent
after cleanup. The collect-only root `C:\tmp\stm32tk-1001-observe-deadline-collect` was checked
and did not exist after collection. The implementation worktree was clean at the CodeHead before
this report-only file was created. The remaining gate is independent complete-diff Sol review,
followed only by the separately authorized single physical confirmation.
