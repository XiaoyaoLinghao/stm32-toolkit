# STM32TK-1001 PyOCD connection-policy correction — implementation report

## Status and ownership ledger

- Repository/worktree: C:\tmp\stm32tk-1001-legacy-hardware-impl
- Branch: codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl
- Accepted product base: 03036f912e16006b1d2030b212962d3704e8a20f
- Accepted-base tree: b7688538514a50f2e083d4bef788030f342daaba
- Implementation owner: one GPT-5.6-luna agent at reasoning effort max.
- Independent review/acceptance owner: GPT-5.6-sol primary.
- Pre-report code head: f801f41905f8601c30cbe82d6cf07753f704a357
- Pre-report code tree: cf01bca001d0a7566e83374507d6af57ba064d23
- Pre-report tracking state: git rev-list --left-right --count origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl...HEAD returned 0 33 (0 behind, 33 ahead); no fetch was performed.
- Pre-report git status --short --branch was clean apart from the normal branch-ahead indication.
- Pre-report git diff --check passed.

This report records implementation evidence only. It does not claim Sol acceptance, hardware PASS,
release readiness, runtime-launcher correction, or remote delivery.

## Specification and plan lineage

The predecessor PyOCD connection-policy specification was developed through this committed lineage
and ended at the approved head:

- 566b6f143a41652fcddbe1a6ee0aa624dfde8f16 (docs(vs10a): freeze PyOCD connection policy correction), tree 94f9c60ac313774c3f63851cfa6351846e93d81b.
- 27ee586f583a6e31daa36baa741e0408bc364c9e (docs(vs10a): bind attach mismatch error ownership), tree 10f25a1b5df280802663ba309d36f8df624e85eb.
- 7a6140f1ec8936e0b3202996ecc5ca7caba9a1bc (docs(vs10a): close target mismatch before attach response), tree 2fffd1b0d361a1fe59611081e7fceea5dfdf63f8.
- Approved predecessor specification head: 482c35f6aaddc3fd5dd3c6dba7ed5720b117e453 (docs(vs10a): admit stateful PyOCD test double), tree 5f0826d0c4d5e4f4d9fa4a8f32514bb11dc9b58a.

The approved predecessor implementation plan is 7d07c3f05af1020cc61773b33f00c88f527694c8
(docs(vs10a): plan PyOCD connection policy correction), tree
459107ab0d312d0343e5d7e388e82b7e33d592b4.

The bounded attach-recovery correction was then frozen through this specification lineage:

- 8429eabfc151859d9f8eebdfb92147ac1b938ee7 (docs(vs10a): freeze cooperative attach recovery), tree 98a04260a6bef22ece183df7a3f185310bc1ae09.
- bdcbfe72b6db80dc0cecca4d5efbf276d8f9abf7 (docs(vs10a): normalize attach recovery spec), tree b41f526ceaddc7b9440b0d0bb4bb651f10b961ac.
- Approved correction specification head: 562efee620e536ef861a445576111dac330a788b (docs(vs10a): bound attach recovery interval), tree d12d740a180c69f1634d0de9c69d08bb760b3217.
- Approved correction implementation plan: 8919dafd227f67d0f490a10706bb9d64cf9af63f (docs(vs10a): plan bounded attach recovery), tree e264030d56ccfae6d4a8e96162545fd700001682.

## Predecessor RED lineage and rejected product head

The predecessor connection-policy RED chain was test-only and culminated in the reviewed product head below:

- Task 1 RED commits: aec12890de35e757053624f35a50da7f6e41517a (tree 453c1e1f2a3c1302455ba9ab46cd24d6aad99c40), 58aa16c0cd33763e9910d6be85b1c0b995a135d6 (tree ce2b1eb65407ebac833e12cbe4dbc6f6d0f64c4e), and bb7ce710b2d2b44e453bfe294ff07dd897e713c7 (tree 8a87f9e80b236e3b81975d938ba8b52b69213fab). The final Task 1 replay was 100 collected, 87 passed, and 13 expected PRODUCT failures covering pinned connection options, required return state, state-proof failures, candidate identity rejection, and cleanup precedence.
- Task 2 RED commits: 1cf4d831780b9644b246a7e4df7474960b95a961 (tree ee078107419a0387b2085c65089e6221153b40cc), e0a82e224f3967364b29a7a611d11eca66e41b34 (tree 77c0ec44a1e5bba7023f7a9b03089ca756deae8f), and 4c943d20107d2dffba5d08016634d2a701a9ca9b (tree 59bf9a4bf0eedf6fea078697972fb6ae3e13f086). The final six-file replay was 464 collected, 437 passed, 26 expected PRODUCT failures, and one existing Windows skip; the failures covered inherited Task 1 gaps plus service halt/identity-gate/cleanup/cancellation and flash identity translation gaps.
- Predecessor test reconciliation: 38cfc86bdb434906abab828af5ced13b20e35ddd (test(vs10a): reconcile attach state assertions), tree 945f3392673884f085e43e46549ed6c91a3a4af1.

The rejected predecessor product head was 1783b33ab77bdce2f6103e7f765db8bad8cd3d00, tree
fdf79c8b8c043c3434251dcc6edb6dd6c4d184dc. Its independent REVISION_REQUIRED findings were:

1. A partially opened, halted candidate was not captured before session.open() failure and was
   therefore not guaranteed to be resumed, state-proved, closed, detached, and kept unpublished.
2. Attach cancellation/timeout could propagate before the exact worker/direct attach task reached
   terminal completion and before the candidate had been safely restored and closed.
3. Recovery and close failures did not have one authoritative sanitized precedence; raw or wrong
   causes could escape instead of a sanitized PROBE_CLOSE_FAILED chained from the initiating
   sanitized error.

The predecessor product commit changed pyocd_backend.py, service.py, and flash.py. The correction
specification froze worker.py and flash.py at this predecessor product state and limited correction
product implementation to pyocd_backend.py and service.py.

## Correction RED, GREEN, and review lineage

### Correction Task 1

328e246d6960206e2ef905abe5bb17d4fe2ccabf (tree
749603b6af9278baa3debb500f3f9df7701085e2) added the partial-open-after-halt and sanitized
close-cause RED contracts in only fake_pyocd.py and test_pyocd_backend.py. Against the reviewed
predecessor product, 102 nodes were collected, 100 passed, and exactly these two new nodes failed
as PRODUCT gaps:

- test_partial_open_failure_after_halt_restores_before_close_and_publishes_nothing
- test_candidate_close_failure_chains_only_the_initiating_sanitized_error

### Correction Task 2

4be8155df0a6af377f7515eb30ec25d801c931f0 (tree
96a8f881af97f4d548d46fd4b6df817deec708ef) added the service/worker cancellation, timeout,
cooperative recovery, hard-abort, and sanitized close-cause RED contracts. Its five new PRODUCT
failures were:

- test_cancelled_attach_waits_for_explicit_recovery_before_propagating
- test_timed_out_attach_waits_for_explicit_recovery_before_propagating
- test_cancelled_attach_close_failure_preserves_sanitized_initiating_cause
- test_spawned_worker_attach_timeout_cooperatively_recovers_before_propagating
- test_unresponsive_worker_attach_uses_bounded_close_failure_fallback

The bounded review correction was committed separately as abdb4771819556850caecf2ba60071e36ae11e3e
(tree 5c39681971e9f901104afc9f98abc8ae16c432c2). It added terminal-latency bounds, exact sanitized
error/cause details, and cancellation setup synchronization. The exact two-file replay remained
125 collected, 120 passed, and exactly the same five new PRODUCT failures; no pre-existing node
failed.

The combined correction RED head before the first product GREEN had 493 collected nodes: 483
passed, seven expected correction PRODUCT failures (the two Task 1 nodes and five Task 2 nodes),
the same two pre-existing combined-order debug lazy-import failures, and one existing Windows
monitor skip.

### First product GREEN and independent review round

The first correction GREEN product commit was
f6c567bef5b3fb5a134224fb999cd564d7766982 (tree
9695e1cb7f40f2c7402f21de690a07c584f32f9f), changing only pyocd_backend.py and service.py.

Independent review then found two bounded service issues:

1. Successful MODIFY recovery made the resume/state proof conditional on a callable target_state;
   a missing or invalid provider could silently close a halted candidate and propagate ordinary
   timeout/cancellation.
2. A task-level sanitized PROBE_CLOSE_FAILED was replaced by a synthetic duplicate, losing the
   actual sanitized task error as the direct cause and its exact safe identity/message/details.

Review RED commit 643d7d588fbedbbd657ec15006ab1061900567b2 (tree
a37f6ad6a024a283ee3042104f9fe5067309c630) added exactly these two service regressions:

- test_timed_out_modify_attach_requires_state_provider_for_recovery
- test_attach_close_failure_preserves_the_sanitized_task_error

The service RED replay collected 103 nodes, with 101 existing passes and exactly those two new
PRODUCT failures. The approved fixture reconciliation was then committed separately as
1ae26b5de062b40e5cda64bede80844e30fac4f5 (tree
adf53b408b5a42b2eb87a2e840b5f3eb0607f4df). It added a deterministic BlockingAttachBackend.target_state()
seam and inserted only the required resume/target_state(running) pair into the two legacy exact
event lists; MissingTargetStateCloseFailureBackend.target_state = None remained intact. The
reconciled RED replay again collected 103 nodes, with 101 existing passes and exactly the two
intended PRODUCT failures.

The final product GREEN commit before this report is
f801f41905f8601c30cbe82d6cf07753f704a357 (tree
cf01bca001d0a7566e83374507d6af57ba064d23). It changes only service.py relative to f6c567be:
MODIFY recovery always resumes and requires a callable valid running-state proof, cleanup remains
one close with sanitized recovery/close precedence, and an existing sanitized task-level
PROBE_CLOSE_FAILED is chained directly as the cause without raw data.

## Verification evidence

All runs used CPython 3.12
(C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe), absolute source-and-test
PYTHONPATH
C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests,
-p no:cacheprovider, and an external run-owned basetemp.

The final service-only command against the final product bytes was:

~~~powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'; & 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tools/stm32-toolkit/tests/test_probe_service.py -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-review-green-service-reconciled-20260903' -q
~~~

Result: 103 passed, exit code 0.

The final focused three-file command was:

~~~powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'; & 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_probe_worker.py -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-attach-recovery-review-green-focused-20260903' -q
~~~

Result: 229 passed, exit code 0.

The standalone debug isolation check used short external basetemp
C:\tmp\stm32tk-ar-dbg-20260903 and test_debug_firmware.py with the same interpreter/options:
113 passed, exit code 0. This independently confirms that the two combined-order lazy-import
failures are test isolation, not a debug product failure.

The final expanded seven-file command selected, in order,
test_pyocd_backend.py, test_probe_service.py, test_probe_worker.py, test_flash.py,
test_debug_firmware.py, test_hardware_workflows.py, and test_monitor_observation.py, with the same
interpreter/options and short external basetemp C:\tmp\stm32tk-ar-int2-20260903. Result:
495 collected; 492 passed; two unchanged failures; one unchanged skip; exit code 1. The failures
were exactly:

- test_debug_public_api_is_complete_and_pyocd_lazy
- test_debug_package_exports_task_one_contracts_without_importing_pyocd

Both are the existing combined-order PyOCD lazy-import isolation failures. The one skip was
test_monitor_observation.py:870, the existing Windows directory-handle rename limitation. A prior
seven-file attempt used a relative PYTHONPATH; its seven flash fixture subprocesses failed with
ModuleNotFoundError: stm32_toolkit. That invocation was classified ENVIRONMENT, not PRODUCT, and
was not used as final evidence; the corrected absolute-PYTHONPATH run above passed all
non-isolation nodes.

## Scope, freeze, cleanup, and boundaries

The exact accepted-base-to-final-code path list (before this report commit) was:

~~~text
docs/superpowers/plans/2026-09-02-stm32-toolkit-1001-attach-recovery-correction.md
docs/superpowers/plans/2026-09-02-stm32-toolkit-1001-pyocd-connection-policy-correction.md
docs/superpowers/specs/2026-09-02-stm32-toolkit-1001-attach-recovery-correction-design.md
docs/superpowers/specs/2026-09-02-stm32-toolkit-1001-pyocd-connection-policy-correction-design.md
tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py
tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
tools/stm32-toolkit/tests/fakes/fake_pyocd.py
tools/stm32-toolkit/tests/test_flash.py
tools/stm32-toolkit/tests/test_probe_service.py
tools/stm32-toolkit/tests/test_probe_worker.py
tools/stm32-toolkit/tests/test_pyocd_backend.py
~~~

The final product GREEN commit lists only tools/stm32-toolkit/src/stm32_toolkit/probe/service.py.
The following checks returned success before the report was written:

- git diff --check.
- git show --format='' --name-only f801f41905f8601c30cbe82d6cf07753f704a357 listed only service.py.
- git diff --exit-code f6c567bef5b3fb5a134224fb999cd564d7766982..f801f41905f8601c30cbe82d6cf07753f704a357 -- tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py returned 0.
- git diff --exit-code 1783b33ab77bdce2f6103e7f765db8bad8cd3d00..f801f41905f8601c30cbe82d6cf07753f704a357 -- tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py returned 0, proving the frozen worker/flash bytes remain identical to 1783b33a.

All disposable basetemps from the predecessor and correction reports were verified absent after their
runs. They included the exact predecessor backend roots
C:\tmp\stm32tk-1001-pyocd-policy-red-backend-20260902 and its rev1, rev1-final, rev2, and rev2-final
variants; the eight predecessor service/matrix roots named in the Task 2 report
(C:\tmp\stm32tk-1001-pyocd-policy-red-complete-task2-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-task2-r2-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-task2-r3-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-review3-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-review4-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-direct-review5-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-review6-20260902,
C:\tmp\stm32tk-1001-pyocd-policy-red-complete-review7-20260902);
correction roots C:\tmp\stm32tk-1001-attach-recovery-red-backend-20260902,
C:\tmp\stm32tk-1001-attach-recovery-red-service-20260902, and
C:\tmp\stm32tk-1001-attach-recovery-red-service-20260903; and Task 3 review roots
C:\tmp\stm32tk-1001-attach-recovery-review-red-service-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-green-service-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-red-reconciled-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-green-service-reconciled-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-green-focused-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-green-integration-20260903,
C:\tmp\stm32tk-1001-attach-recovery-review-green-debug-standalone-20260903,
C:\tmp\stm32tk-ar-dbg-20260903, C:\tmp\stm32tk-ar-int-20260903, and
C:\tmp\stm32tk-ar-int2-20260903. Read-only/ACL-protected generated entries were normalized only
inside their exact run-owned roots before removal. Source, reusable fixtures, shared caches, user
files, and failure evidence retained in this report were not removed.

- HARDWARE NOT RUN BY IMPLEMENTER.
- RUNTIME LAUNCHER CORRECTION NOT INCLUDED.
- SOL COMPLETE-DIFF REVIEW PENDING.
- REMOTE ACTION NONE (no fetch, push, PR, merge, tag, release, or remote branch mutation).

This report intentionally contains no report-commit SHA and makes no acceptance or release claim.
