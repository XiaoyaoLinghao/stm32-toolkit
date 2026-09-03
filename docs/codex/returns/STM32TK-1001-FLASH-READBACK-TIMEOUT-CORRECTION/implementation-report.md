# STM32TK-1001 Flash Readback Timeout Correction Implementation Report

Status: implementation evidence returned for independent Sol review; not accepted.

- Full accepted base: d462f0ba868ae3cb980544a5a3c746ee7fc996c2
- Full accepted base tree: ceeb30c228290bad48dacc2372d7978fe4acc113
- Approved specification: 8e12f2f7e697ecf5a0603411cc7d3f8302bc4014
- Approved specification tree: 182ea6204c8a2d917bf74691b2c7843769012688
- Frozen implementation plan: 3e675f1ee6565226bd6a1456e6bb7f29cc188d8c
- Frozen implementation plan tree: 7059243645bea99df82eac7fbc4f5007231e41ab
- Original frozen implementation plan: 08b92054235faf6cdd290327cf129ab07c9c83d7
- Original frozen implementation plan tree: ca06043ef810e2b07a631a34c68e3dd8aaf9af81
- Plan compatibility correction: 3e675f1ee6565226bd6a1456e6bb7f29cc188d8c
- Plan compatibility correction tree: 7059243645bea99df82eac7fbc4f5007231e41ab
- Sol-owned report-governance plan correction: 6c92b6ae1d1c7239723e7da4c21ddfc9b329ee6a
- Sol-owned report-governance plan correction tree: 31221b2a1a330fe71a9305d8b34e28e3bc301666
- RED commit: 8ebbcfd7072018c22f75e532fd385e55938ace24
- RED commit tree: 7b1730fbde171a013399319b8e8522df52f3cb6c
- RED safety-oracle completion: 966d1aaf4ca1ea5dae962be3648bc3d941d25fee
- RED safety-oracle completion tree: c481cc9793264e026e4dfcf997c6e27c8d1f9b4e
- CodeHead before this report commit: b4ce29c66d19e10ec9bd5b68f4c0c4ac127be9bd
- CodeHead tree: 272708ae49d8842ae30ced44a41736e62f41ad0a
- Implementer/evidence owner: one GPT-5.6-luna agent, reasoning effort max
- Independent reviewer: GPT-5.6-sol primary, pending
- Hardware: not run; a new explicit one-attempt authorization is required after software acceptance
- Remote actions: none

## Implemented behavior

ProbeClient.read_memory retains the generic 5,000 ms default and accepts only the explicit
keyword timeout_ms for a caller-selected deadline. It forwards that exact value through the
existing memory.read OBSERVE request with the unchanged address/length payload and response
decoder.

Flash readback uses the already validated FlashRequest.timeout_ms value for every existing
readback chunk. The existing chunk bound remains 65,536 bytes. The private _verify_segments
helper accepts an optional keyword-only timeout_ms; when it is None, it preserves the original
two-positional-argument client.read_memory call used by unchanged debug and handoff consumers.
flash_firmware supplies the validated integer and performs the same single verification
transaction.

The existing attach/program/read ordering, sector erase, trustCrc false, keepUnwritten true,
one-program behavior, no-retry behavior, fail-closed mismatch and timeout handling, unchanged
flash-result schema, and binder/handoff trust paths remain in force. No public option, lifecycle,
backend, profile, service, worker, schema, or result change was made.

## TDD lineage

The first RED commit was test-only and preceded product edits:

~~~powershell
$env:PYTHONPATH = "C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests;C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages"
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest tools/stm32-toolkit/tests/test_probe_client.py::test_read_memory_preserves_default_and_forwards_explicit_timeout tools/stm32-toolkit/tests/test_flash.py::test_flash_programs_exact_elf_reads_back_segments_and_commits_result tools/stm32-toolkit/tests/test_flash.py::test_flash_default_timeout_covers_exact_accepted_segment_without_splitting tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_is_chunked_to_protocol_limit tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_timeout_never_retries_or_commits_success tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_mismatch_never_retains_success_evidence -q -p no:cacheprovider --basetemp (Join-Path 'C:\tmp\stm32tk-1001-flash-readback-timeout-task1-red-20260903' 'red')
~~~

Result: exit 1, FFFFF. — five intended PRODUCT RED failures and one passing mismatch control.
The missing public read_memory timeout keyword failed with TypeError. The flash controls
observed 5,000 ms instead of the requested 30,000 ms or 12,345 ms while preserving their
meaningful attach/program/read, chunk, one-program, timeout, mismatch, and no-result assertions.

Test-only safety-oracle completion followed in
966d1aaf4ca1ea5dae962be3648bc3d941d25fee (tree c481cc9793264e026e4dfcf997c6e27c8d1f9b4e).
It added the final-byte mismatch proof for the exact 51,852-byte read and froze exactly one
program plus attach/program/read/read ordering for the multi-chunk case. Its short-root narrow
reruns reached FLASH_VERIFY_FAILED and all safety assertions before the expected 5,000-ms
propagation failures; the exact six-node rerun remained honest PRODUCT RED with FFFFF. No
product code was changed before either RED boundary.

The first required-helper GREEN attempt was intentionally classified BLOCKED: its six target
nodes passed, but the frozen focused binder control returned DEBUG_READBACK_MISMATCH because
the required _verify_segments timeout argument broke the unchanged two-positional
debug/firmware.py caller. The complete candidate was reverted and no product commit was made.
The Sol-owned compatibility correction 3e675f1ee6565226bd6a1456e6bb7f29cc188d8c changed the
approved private seam to optional timeout_ms, preserving unchanged debug and handoff callers.

After that correction, the exact Luna-owned target command was:

~~~powershell
$env:PYTHONPATH = "C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests;C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages"
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest tools/stm32-toolkit/tests/test_probe_client.py::test_read_memory_preserves_default_and_forwards_explicit_timeout tools/stm32-toolkit/tests/test_flash.py::test_flash_programs_exact_elf_reads_back_segments_and_commits_result tools/stm32-toolkit/tests/test_flash.py::test_flash_default_timeout_covers_exact_accepted_segment_without_splitting tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_is_chunked_to_protocol_limit tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_timeout_never_retries_or_commits_success tools/stm32-toolkit/tests/test_flash.py::test_flash_readback_mismatch_never_retains_success_evidence -q -p no:cacheprovider --basetemp (Join-Path 'C:\tmp\r2gt-20260903' 'green-target')
~~~

The first launch of this command omitted creation of its exact parent and stopped at fixture
setup with FileNotFoundError (WinError 3); no test fixture or product code ran. That attempt is
classified ENVIRONMENT/harness setup, not PRODUCT or BLOCKED. After the exact run-owned parent
was created, the command exited 0 with 6 passed. This final rerun is the only target PASS used.

The amended complete focused matrix was:

~~~powershell
$env:PYTHONPATH = "C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests;C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages"
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest tools/stm32-toolkit/tests/test_probe_client.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_debug_firmware.py::test_genuine_flash_result_is_consumed_by_binding_without_a_second_trust_schema tools/stm32-toolkit/tests/test_debug_firmware.py::test_missing_or_invalid_firmware_and_flash_evidence_are_stable tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_persists_paused_stops_releases_then_marks_external tools/stm32-toolkit/tests/test_debug_handoff.py::test_begin_drains_modifications_before_final_target_readback tools/stm32-toolkit/tests/test_debug_handoff.py::test_end_reacquires_revalidates_and_consumes_one_time_ticket -q -p no:cacheprovider --basetemp (Join-Path 'C:\tmp\r2f3-20260903' 'green-focused')
~~~

Result: exit 0 with 115 passed: 65 client tests, 45 flash tests, 2 firmware binder controls,
and 3 handoff controls. The binder controls passed 2/2 and all three named handoff controls
passed 3/3. These are Luna-owned implementation runs and are not attributed to Sol.

The independent collection-count command for the same selection used
C:\tmp\r2fc-20260903 and exited 0 with 65 client, 45 flash, 2 firmware binder, and 3 handoff
tests (115 total). No prior seven-file recovery suite, full suite, coverage, package, release,
CLI/MCP, Monitor, or hardware matrix was run.

## Changed paths and scope audit

The implementation lineage after the corrected plan is:

| Classification | Paths |
| --- | --- |
| RED tests | tools/stm32-toolkit/tests/test_probe_client.py; tools/stm32-toolkit/tests/test_flash.py |
| GREEN product | tools/stm32-toolkit/src/stm32_toolkit/probe/client.py; tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py |
| Report | docs/codex/returns/STM32TK-1001-FLASH-READBACK-TIMEOUT-CORRECTION/implementation-report.md |

The RED tests were committed before the corrected-plan GREEN boundary; the product delta after
3e675f1ee6565226bd6a1456e6bb7f29cc188d8c was exactly the two GREEN source paths. The approved
specification and plan are design inputs, and the compatibility correction is the Sol-owned
plan update recorded in the lineage; they are not additional product or test edits in this
implementation. CLI, MCP, schema, service, worker, backend, connection profiles, result
consumers, runtime, dependencies, packaging, README, Skills, and Monitor remained unchanged.

## Deferred external evidence

The earlier physical attempt entered programming and timed out during unpropagated readback.
Target contents after that attempt remain unknown. No physical attach, flash, read, or recovery
attempt was performed for this correction. This software report does not reuse the earlier
authorization and does not claim a physical PASS. A new one-attempt public recovery flash is
deferred until after Sol software acceptance and requires separate explicit user authorization.

## Cleanup and status

The exact Task 3 Luna-owned verification root
C:\tmp\stm32tk-1001-flash-readback-timeout-luna-20260903 was inspected and was absent, so it
had no residue to remove. The final Task 2 roots C:\tmp\r2gt-20260903,
C:\tmp\r2f3-20260903, and C:\tmp\r2fc-20260903 were each verified as exact run-owned paths and
removed after evidence capture. The long nested Task 1 staging roots were also removed after
their minimum setup failure evidence was recorded in the internal Task 1 report.

Before this report was created, git diff --check passed and the worktree was clean apart from
the ignored SDD workspace. The report is committed separately from CodeHead. The final report
worktree was left clean and no remote state changed. This report intentionally contains no
branch-relative ahead/behind numbers or moving commit total.
