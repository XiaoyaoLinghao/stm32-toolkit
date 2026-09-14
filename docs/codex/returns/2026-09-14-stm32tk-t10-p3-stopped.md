# T10 P3 execution: terminal stop

T10 remains incomplete. The single P3 Target execution returned `TEST_FLASH_FAILED`; no physical TestRun, Monitor window, Diagnostic, source-change authorization, P4, or FixVerification followed. The user observed D4 constantly on. No hardware retry or restoration was performed.

## Baseline and scope

- T10 software accepted base: `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1`; deployed source: `70ed9c70075445d66d9229a1420817f604843fd2` in `D:\stm32tk-data\fault-controlled-20260911\runtime\0.9.0`. Deployment was reused.
- Primary owned acceptance and all hardware operations. Luna/max owned the bounded firmware change and run-local test entry implementation; primary reviewed their complete source/diff. `t10_diagnostic_contract` independently reviewed the added procedure clauses and the failure-stage evidence.
- Project: `D:\codex-tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`; P3 commit `2bfa4bd81dc7474130e2d2c5acdad0162e15eb04`. The complete P2-to-P3 diff changes only `Main/Main.c:126`, `LED1=!LED1;` to `LED1=1;`, preserving other bytes and CRLF.
- Evidence root: `D:\codex-tmp\t10-acceptance-20260911-01`; session `vs10a-t10-p3p4-20260911-01`; attempt `483a0b67-40a8-4ff5-aed8-5232c6afd8f0`. The user freshly confirmed the same board/probe, D4 blinking, stopped IDE debugging and unchanged wiring/load before execution.

## Observed results

1. Initial build failed at CMake configure: `CMAKE_HOME_DIRECTORY` and cache directory still referenced the retired C temporary project. This was an ENVIRONMENT failure. The owner preserved the log and moved only CMakeCache.txt/CMakeFiles into the run evidence root after path/reparse verification. The single corrected build succeeded in 15,812ms. No old project was recreated.
2. Fresh P3 build: `8764ad3689e5e3ca35f8afbfab655f09a3558644faae481816c9f3473cc3aeef`; ELF SHA `7bc9ae9f95f5bb1a53fea69a719e5084cb1af88c1a03b9135828abb9c284de78`; input SHA `fb41bc8e66a33fb77e2c2528b3ed0b74f42b8afa790e83466b8dd180d65fda00`. The installed `load_fresh_firmware_facts` independently verified these values. Canonical `gitDirty=true` includes the untracked build lock; tracked source was clean and the value was not rewritten.
3. One `test target prepare`: OK, 8,685ms. Its fresh action was consumed at `2026-09-14T04:26:22.634498Z` by the one execute call.
4. Execute: exit 2, 6,430ms, `TEST_FLASH_FAILED`, no outer timeout. The exception stack reaches installed `testing/target.py:855`, `PhysicalTargetFlashAdapter.run`, after calling `flash_firmware`.
5. Registry is `released`, lease `lease-9f449d4f65ec4b03978f483134129d52`. The two invocation roots, PID 7760 and 23812, and their remaining descendants were absent from the final process snapshot. User D4 observation was constant-on. Firmware programming completion and current CPU running state are not proven.

## Exact evidence limit and correction

Installed `testing/target.py:838-855` converts a failed `flash_firmware` OperationResult into the generic Target error and discards the underlying `code/message/details`. `probe/flash.py:650-668` returns failures in memory; it does not persist a negative flash receipt. The current flash receipt is absent, but no immediate pre-execute receipt preimage was captured, so that absence alone does not prove native programming or readback was reached. The exception stack proves entry into the flash adapter, not a particular lower failure branch.

Consequently, the underlying flash failure is **unclassified**: these records cannot distinguish program failure, readback failure, identity drift or another internal rejection. D4 constant-on and the public error code are insufficient to call it a hardware lock or halt failure. The exact missing evidence is the failed `flash_firmware` OperationResult's original `code/message/details`.

The run-local capture entry has been corrected to preserve that failed result before conversion, while calling the original function once and returning the same object. Its SHA is `be86610b0b9c56390d8e79d8419fa9e9e11dfb3b18070cccebe9ec3f26f9eb82`. A pure software failure case verified field retention, credential-key redaction and unchanged return identity. Primary reviewed the full resulting entry. This prepares later evidence collection; it cannot recover this run's lost result or prove that flashing is fixed. Installed product code and firmware behavior were not changed by this correction.

## Retained state

The last authoritative checkpoint is revision 2, `firmware-built-before`, with deadline `2026-09-14T04:30:03.837677Z`; the execution ledger is terminal-stopped. Its consumed action and expired continuation must not be reused. Source and build are P3; board firmware completion is unknown. P2 source/ELF/receipt snapshots and the minimum failure evidence are retained. T9 acceptance, the accepted 100ms observation, FullFault and attempt 7 historical PASS remain valid within their original scope. T10, Task11/12 and VS10-A remain incomplete.

Primary local evidence: `physical-stop-20260914.json`, `p3-target-prepare.stdout.txt`, `p3-target-execute.stdout.txt`, `target-entry/p3-execute.exceptions.jsonl`, `owned-processes-after-stop.json`, and `target-entry/p3-preserved/`. Any further hardware diagnostic/recovery operation needs new bounded authorization; none is dispatched by this report.

## Newly authorized continuation 02

The user explicitly requested continuation after the terminal stop. A new attempt `1aba83ba-531e-4ede-b2dd-553dc9fa7b47` reused the verified unchanged P3 build and common evidence session, but no previous action or checkpoint. Its begin/project-materialized/firmware-built-before transitions succeeded. The updated capture entry was copied byte-for-byte into `continuation-02/target-capture.py` before execution; SHA `be86610b0b9c56390d8e79d8419fa9e9e11dfb3b18070cccebe9ec3f26f9eb82`.

The single prepare failed after 4,746ms, without outer timeout. Public code was `TEST_EXECUTION_FAILED`; the preserved exception was `ProbeClientError`, code `PROBE_ATTACH_FAILED`, at installed `testing_workflows.py:513` → `probe/client.py:384,361,324`. The workflow had started its supervisor and issued attach, but did not complete attach or proceed to the subsequent target-identity read. It generated no new action; execute, programming, Monitor and P4 were not called. This continuation is also terminal-stopped, with no retry.

Registry lease `lease-11fbb8927a374db8b01999abb45c5018` is released. PID 25348 and its remaining descendants were absent from the final snapshot. The latest user LED observation remains the prior run's constant-on report; current running state is not proven. Evidence is under `D:\codex-tmp\t10-acceptance-20260911-01\continuation-02`, particularly `p3-prepare.exceptions.jsonl`, `p3-target-prepare.stdout.txt`, `owned-processes-after-stop.json` and `result.json`. These establish an attach-stage failure, not its lower hardware cause.

### Continuation 02 diagnostic limit

The installed backend can return `PROBE_ATTACH_FAILED` from session construction/opening, target resolution, resume, resume verification, or cleanup resume (`probe/pyocd_backend.py:934-1059`). This code does not identify which branch ran. OBSERVE prepare requests `halt_on_connect=False` (`probe/service.py:1007-1011`); this excludes the explicit halt-verification branch, but does not prove that session open or resume succeeded.

The product already forwards safe `attachDiagnostic` fields through the worker/service to `ProbeClientError.details` (`probe/client.py:70-77`). The run-local exception recorder retained the code and traceback, but omitted `message` and `details`; the public workflow subsequently returned generic `TEST_EXECUTION_FAILED` with empty details (`testing_workflows.py:206-218`). This is a confirmed REPORT defect in the test entry, separate from the still-unclassified attach failure.

The missing evidence is `details.attachDiagnostic.primary.stage/reason/sourceCode`, `cleanup`, `lastVerifiedTargetState`, and the safe message. These transient values cannot be reconstructed from the saved result. Ordinary enumeration/selection failures have different default error codes, but that source inference is not a captured enumeration result. Neither the LED observation nor a released lease proves current CPU state. No further hardware operation is authorized by this diagnostic conclusion.
### Offline capture correction and independent review

Luna/max changed only `target-entry/target-capture.py` to preserve `ProbeClientError.message` and recursively redacted `details` before the existing mapper. The final SHA is `e25b59830330d18ff339ccbfca414294c9b9279c9ea942f2d2bbd06c85f19de4`. Primary reviewed the complete original-to-final diff; argv forwarding, delegate call count, return path and spawn guard are unchanged. The actual continuation-02 execution snapshot and its archived original both remain `be86610b0b9c56390d8e79d8419fa9e9e11dfb3b18070cccebe9ec3f26f9eb82`.

The single affected offline self-check passed using the installed diagnostic constructors/validator and a synthetic ProbeClientError: it retains the complete valid details envelope and maps the original exception once. Evidence: `target-entry/offline-probe-exception-self-check.jsonl`, SHA `bd44a73d704236847e1f16b9a7c0640182b79a7e54744e498400a65ad6a8c89f`. The review caught an earlier sample's incorrect field nesting; that sample is retained separately as invalid history, not contract evidence. The corrected sample's session-open/halted values are synthetic, not observed hardware facts. Independent verdict: accepted for offline capture behavior only. No deployment, rebuild, hardware retry or physical acceptance followed.