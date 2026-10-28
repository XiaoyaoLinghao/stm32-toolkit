# Issue 2 — primary offline follow-up

Date: 2026-10-28. **The strongest current candidate is missing target reset/preparation
before normal programming. The omission is established in the inspected software path;
its causal role in the physical HardFault is not yet proven.** Do not close issue 2 or
claim a hardware fix from this investigation.

## Ownership and boundaries

- The user explicitly requested that the primary Codex agent continue this investigation
  directly. Primary Codex performed the source/evidence review and inert call tracing;
  no implementation delegation or product-code/test change occurred.
- Accepted local software checkpoint and source head before this report:
  `75c47ddb455b795d2bd954c1fd1e601b7af4fcd3`, branch
  `codex/v134-fixes-integration`. The earlier accepted product CodeHead remains
  `29d13fc75881bfc771d81aa1c54f45948a6fa0f0`.
- Read the [standard procedure](../../../testing/standard-test-procedure.md), its current
  checkpoint and [latest acceptance report](implementation-report.md) before the offline
  check. There is no new hardware execution card or authority.
- No probe enumeration, connection, target register/memory access, halt, reset, resume,
  flash, hardware readback, installation, packaging or remote mutation occurred. Public
  upstream source was consulted; “offline” here means no device operation.
- This report extends the [earlier bounded investigation](flash-offline-investigation.md).
  Its statement that no recovery evidence was supplied remains historically accurate;
  the broader follow-up found the successful records below. Earlier invocation failures
  and ownership records are unchanged.

## New evidence

`C:/work/stm32/fresh-flash-2.json` reports successful under-reset recovery at **100 kHz**,
with `automaticRetry=false` and **61,516 verified bytes**. Its matching
`fresh-out/artifacts/migration/flash-result.json` records Toolkit **1.3.4**:

- Time: `2026-10-28T04:47:14.899453Z` through `2026-10-28T04:47:30.481165Z`.
- Build: `8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc`.
- ELF SHA-256: `b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53`.
- Target: `STM32F429ZGTx`, debug target `stm32f429xg`.
- Probe: `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`.
- Session: `7e6220c6-a3eb-4232-ac8d-2310f883f417`.
- `postFlash.targetState=unknown`, `runVerified=false`: verified programming does not
  establish that the application subsequently ran.

The historical `v130-test/flash-4.json` also reports 61,516 verified bytes, the same probe
ID and target names, but a different ELF/build/session. It contains no `flashOptions`;
its frequency and connection policy cannot be inferred.

The failed `fresh-flash-1.json` records normal policy at **1 MHz** and the reported
`program-call` / `FlashFailure` / `IPSR=3`. It omits build, probe, session and runtime
identities. “Same board” across that failed attempt and recovery is still the user's
reported context, not a join independently proven by those two JSON files. The currently
installed runtime is supporting evidence, not a time-of-failure runtime attestation.

The current installed `C:/data/stm32-toolkit/runtime/1.3.4/Lib/site-packages` declares
pyOCD **0.45.1**. Eight relevant pyOCD source files byte-match the earlier reference
environment at `D:/codex-tmp/kx23/venv/Lib/site-packages`; its Toolkit
`probe/pyocd_backend.py` also byte-matches the current integration source. All 18 retained
source/log snapshots were rehashed against their originals after the offline check:
**zero mismatches**. This improves source relevance without filling the failed log's
identity gap.

## Confirmed software difference

In `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py:980-995`, normal modify
connection uses `connect_mode=halt`; the recovery path uses `under-reset`. pyOCD's
`coresight/coresight_target.py:216-268` halts for the former and explicitly asserts then
releases reset for the latter. Halting alone does not promise reset-state preparation.

Toolkit's `_DefaultPyOCDDriver.program_file` at `pyocd_backend.py:195-211` constructs
`FileProgrammer`, then calls `program()`, with no intervening reset. In the inspected
pyOCD 0.45.1 source:

| Layer | Observed behavior |
| --- | --- |
| `flash/file_programmer.py:59-99,166-199` | Builds the loader; `program()` adds the file and commits. `no_reset` is deprecated and ignored. |
| `flash/loader.py:277-333` | Erases builders, then programs builders; has no target reset. Its final `_reset_state()` clears Python bookkeeping. |
| `flash/builder.py:280,283,851,868,909,953` | Calls `Flash.init()` without enabling its optional reset. |
| `flash/flash.py:195-266` | `reset=False` by default; initial preparation calls `halt()`, then loads the algorithm into RAM. |
| `flash/flash.py:309-311,548-583` | Default preparation hook is empty. Init sets PC, arguments, R9, SP, xPSR and LR, then resumes; this wrapper does not reset CONTROL, interrupt masks, NVIC, MPU or peripherals. |
| `subcommands/load_cmd.py:116-133,176-177` | The CLI explicitly calls `session.target.reset_and_halt()` before commit unless `load.pre_reset` is `off`. |

The last distinction is also visible in the
[official pinned pyOCD 0.45.1 CLI source](https://github.com/pyocd/pyOCD/blob/v0.45.1/pyocd/subcommands/load_cmd.py#L114-L177).
Setting only `load.pre_reset` on Toolkit's Session would not fix this API path: the
option is acted upon by the CLI, not by `FileProgrammer`/`MemoryLoader`. Likewise,
passing `no_reset=False` to `FileProgrammer` is ineffective in this version.

The builtin F429xG target uses the generic Flash class. Its post-connect hook writes
debug freeze registers; it does not supply the missing target reset. `SoCTarget`
delegates halt/resume to the selected core. Cortex-M `resume()` writes DHCSR without
`C_MASKINTS`; there is no general interrupt isolation added by that call.

**Inference:** RAM-resident algorithm execution can inherit application-established
processor/peripheral state. A pending interrupt, a previous exception state, privilege/
MPU setup or peripheral activity is therefore a concrete route worth checking. This is
more specific than a generic “probe compatibility” theory and is consistent with
under-reset success. No captured register values identify which state, if any, caused
this board's failure. The algorithm's own machine code was not fully audited here.

The upstream [v0.44.1 Flash source](https://raw.githubusercontent.com/pyocd/pyOCD/v0.44.1/pyocd/flash/flash.py)
also defaults `Flash.init` to `reset=False`; do not describe this as a demonstrated
0.45.1-only regression or recommend a dependency downgrade on that basis.

## Offline checks and interpretation limits

The primary ran exactly one local analysis harness, using standard-library Python and
selected original function ASTs against inert recorders. It imports neither pyOCD nor
Toolkit, never creates a real Session, and never loads a USB/probe backend. File loading,
builders, sessions, target methods and algorithm completion are substitutes; this is a
call-order check, **not a HardFault reproduction or product/hardware test PASS**.

Command, completed with numeric exit **0** and empty stderr:

```powershell
& 'C:/Users/zhy76/AppData/Local/Programs/Python/Python312/python.exe' -I D:/codex-tmp/flash2-investigation-20261028/offline_trace.py > D:/codex-tmp/flash2-investigation-20261028/trace.stdout.txt 2> D:/codex-tmp/flash2-investigation-20261028/trace.stderr.txt
```

Assertions confirmed that the selected direct-API wrappers do not call reset, the CLI
calls reset-and-halt before the builder erase call, and `Flash.init(reset=False)` calls
halt whereas `reset=True` calls reset-and-halt. Actual extracted register setup records
no CONTROL/PRIMASK/BASEPRI/FAULTMASK write. The CLI trace deliberately disables its
post-program reset to isolate the pre-program difference; it is not a proposal to
copy the CLI's application-start behavior.

The same harness reads the existing ELF header without executing it. Its full hash
matches the successful receipt. Both nonempty PT_LOAD segments have Flash physical
addresses: `0x08000000` (61,368 bytes) and `0x0800efb8` (148 bytes), totalling 61,516.
The second has RAM virtual address `0x20000000`, but the pyOCD ELF loader uses physical
load addresses. Thus this successful input does not itself request loading application
data over the algorithm RAM buffer. This does not prove that residual RAM state was
safe, that the failed input was identical, or that the linked application is fault-free.

Further source observations prevent overinterpreting the error:

- The message matches the non-running/non-halted branch in `flash.py:668-672`, not its
  timeout branch. `IPSR=3` denotes HardFault, but the original observed state could be
  RESET, LOCKUP or SLEEPING; it is not recorded.
- `program-call` spans preparation, smart-flash analysis, erase and programming. It does
  not identify which algorithm invocation failed. `trust_crc=False` does not disable
  the CRC analyzer; the builder may still execute it.
- `FlashBuilder._enable_read_access` catches a VERIFY-init `FlashFailure` and attempts
  ERASE-init. Toolkit's `automaticRetry=false` describes its outer workflow; it does
  not prove that pyOCD made exactly one internal algorithm call. No evidence establishes
  that this internal fallback occurred in the failed run.
- A recovery success changing both reset policy and frequency cannot isolate frequency.
  The success weakens a claim of universal inability to program this target/image,
  but does not eliminate intermittent transport, target-selection or algorithm issues.

## Recommended next slice, not implemented

Prioritize an explicit **pre-program target preparation contract** over reducing every
CMSIS-DAP connection to 100 kHz. The concrete review finding is the missing reset above;
the expected behavior to specify is a known halted state suitable for running the flash
algorithm, independent of where the prior application happened to stop.

A bounded design should specify one reset-and-halt before programming, after firmware
admission, target identity and modify authorization; select and record its reset type;
verify the halt postcondition; give preparation failure a separate diagnostic stage;
and stop before erase/program if preparation fails. Reset must be disclosed as part of
the flash operation. It must not be added to shared read-only attach/monitor paths or
become an automatic under-reset recovery. Decide explicitly how an already-under-reset
connection satisfies preparation to avoid an accidental duplicate reset. Retain sector
erase, readback checks, failed-operation stop/cleanup and no implicit application run.

Software verification should assert authorization/admission before preparation,
exactly-once ordering, fail-closed reset/halt behavior, no program call after preparation
failure, unchanged read-only connection and recovery authority, and retained readback/
receipt behavior. Add bounded phase/state diagnostics inside the already-owned failing
operation before worker termination; do not reconnect afterward to obtain registers.

Hardware confirmation remains a separately authorized later stage under the standard
procedure. A one-variable comparison must retain full runtime/build/probe/target and
initial-state identities. Candidate comparisons are normal policy with explicit 100 kHz
versus 1 MHz, or an otherwise identical normal-policy run with defined pre-program reset.
These are alternatives for a future execution card, not a retry sequence; any terminal
failure stops and preserves evidence. No such execution occurred here.

Disposition: **investigation advanced; software preparation gap confirmed; physical
root cause and fix effectiveness unverified.** Items 1/3/4/5/8 keep their prior local
acceptance. Any resulting product fix belongs to planned v1.3.5, not published v1.3.4.

## Retained evidence

Root: `D:/codex-tmp/flash2-investigation-20261028`. The manifest retains exact original
paths, byte counts and hashes for all 18 source/log snapshots. Originals were unchanged.

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `f86a4b4d22095301e7e82d93852b8f2639b64a64e945e32bd430e317d867d9eb` |
| `offline_trace.py` | `a3c0df1f5788f92242fc9a276099374f431b07f43d79913f3318eb1ad66c85b6` |
| `trace-result.json` | `4dc542a706e683161225abed5f7d5ff11f4b2ce3953c08a69491be255243a02c` |
| `fresh-flash-2.json` snapshot | `53616183a40358252c66462fe175ab9ab814691e741dc2b95bae161d434b6d2a` |
| Successful receipt snapshot | `db8165a19ee8f8bf0f101f77bd3c4cd822baeae2f8ef349453fa0d07e222a4a0` |
| Installed/current Toolkit backend (identical) | `6cb29cf72e5995487a6a16f475535d1f71e2609bc3ba143fe3b7e758a33f690b` |

Only this report and its checkpoint links are repository changes. No release-level
matrix was rerun for this documentation-only investigation.
