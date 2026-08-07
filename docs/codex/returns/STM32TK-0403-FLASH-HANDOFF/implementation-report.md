# STM32TK-0403-FLASH-HANDOFF Implementation Report

## Delivery identity

- Status: `IMPLEMENTED`
- Accepted product base: `4424b5f45b38bb032e30ba7dc3b7bb37130fc8cd`
- Plan commit: `828e521c4f63c9d778ab996c09a42eca54797544`
- Branch: `codex/STM32TK-0403-FLASH-HANDOFF`
- Code head before this report commit:
  `930febba9a5ebbdb4495a6e2b4f6318c5a985103`
- Specification, implementation, and review owner: Codex, following the user's
  explicit pause of OpenClaw implementation after STM32TK-0306.

This report intentionally does not contain its own final commit SHA. The PR URL
and final remote head are returned after the report commit is pushed.

## Delivered scope

The code head changes exactly 20 plan, product, schema, fake, and test paths
relative to the accepted base (5,742 insertions and 76 deletions):

- one `flash.program` protocol operation with a server-owned `MODIFY` minimum,
  exact project-relative ELF path, bounded size, and SHA-256 contract;
- service-side canonical containment and reparse/regular-file checks followed
  by a descriptor identity check, one bounded byte read, and programming of
  those same in-memory bytes;
- PyOCD `FileProgrammer` integration using ELF input, sector erase,
  `trust_crc=False`, `keep_unwritten=True`, no progress output, and no reset;
- honest nullable backend byte/sector telemetry plus strict physical attach
  evidence containing probe ID, requested target, resolved part number, and
  core count;
- high-level `flash_firmware()` authorization, current build-result/identity/
  Git/input/ELF/MAP chain validation, caller build/SHA pinning, exact target
  attach, bounded PT_LOAD readback, post-readback evidence revalidation, and an
  atomic `flash-result.json` commit point;
- cancellation-safe service and supervisor start/stop: listener, endpoint,
  backend, and lease cleanup finishes before caller cancellation is propagated,
  while cleanup failures retain priority over cancellation;
- a synchronous-close modification drain gate that rejects new flash requests,
  waits successful or failed in-flight flashes, preserves observe reads, and
  remains fail-closed if the drain caller is cancelled;
- crash-safe debug handoff states (`paused-for-debug`, `externally-owned`,
  `reacquiring`, `observing`) under the exact plugin session root;
- a one-time 256-bit ticket bound to workspace, session, probe, lease, target,
  build ID, ELF SHA, and opaque prior selection, with the secret excluded from
  `repr` and error output;
- an exact Cortex-Debug attach-only data contract carrying target, ELF, PyOCD
  server type, and `serialNumber` for the released physical probe;
- complete client-to-supervisor endpoint binding before all attach/read calls,
  including protocol, Toolkit version, host, port, constant-time token match,
  workspace, session, lease, probe, and operation level;
- bounded descriptor reads for state, flash result, and lease proof with leaf
  and containment-parent identities checked before and after the read;
- safe recovery after stop cancellation, cleanup failure, state promotion
  failure, restarted service, changed target bytes, replay, and competing
  ownership without killing, stealing, or launching any external process.

No CLI/MCP/Skill, version bump, typed debug, SVD, sampling, Fault analysis,
Monitor behavior, GDB process control, chip erase, Option Bytes, arbitrary
memory write, or implicit reset was added.

## TDD and independent review corrections

Initial RED collection failed because the flash and handoff modules and the
new protocol operation did not exist. Focused RED/GREEN slices and a separate
read-only Codex review then exposed and corrected these material defects:

1. service initially accepted caller-declared operation authority and a path
   that could change between verification and programming;
2. attach evidence did not bind the resolved physical target, and backend
   telemetry would have required invented counts;
3. a running modify request could outlive a timeout or race service shutdown;
4. RAM `rwx` PT_LOAD segments were initially accepted as executable firmware;
5. persisted state, flash, and lease reads lacked duplicate-JSON, NaN, bounded
   descriptor, leaf-swap, and parent-chain-swap defenses;
6. a cancellation during start/stop could leak a listener or lease, or make the
   supervisor discard its only lifecycle reference before cleanup completed;
7. caller cancellation originally hid a backend-close cleanup failure;
8. final target readback preceded a window in which another flash could enter;
   the service now drains modifications before the final evidence/readback;
9. stop-complete cancellation could leave a paused state after the lease was
   released; external ownership is persisted before cancellation propagates;
10. failure of the final external-state atomic replace could later promote a
    paused/released state without hardware revalidation; recovery now requires
    exact service reacquisition, drain, identity validation, and readback;
11. handoff used the passed client without proving it belonged to the exact
    supervisor endpoint; forged lease/workspace/session/probe/URL/token/level
    clients now fail before hardware access;
12. the initial Cortex-Debug contract omitted the exact probe serial selector;
13. persisted watch selection bounds were weaker than request bounds;
14. missing project roots and cleanup failures could map to unstable internal
    errors instead of stable handoff codes.

Every product correction above has a focused regression. The primary agent
reran the integrated suite, and an independent review reported no remaining
P0/P1 merge blocker.

## Verification evidence

Environment: Microsoft Windows 11 Pro 10.0.26200 build 26200, AMD64, CPython
3.12.13, pytest 8.4.2, aiohttp 3.14.3, and PyOCD 0.45.1.

| Gate | Result |
|---|---|
| Final Flash/Handoff/Probe/PyOCD focused suite | 351 passed, exit 0; 160.19 s |
| Handoff suite after final review fixes | 100 passed, exit 0 |
| Full Toolkit suite with branch coverage | 1,585 passed, 3 skipped, exit 0; 934.33 s |
| Full branch coverage | 91.37%, required minimum 90% |
| Key changed module coverage | flash 94%, handoff 90%, supervisor 94% |
| `compileall` | exit 0, silent |
| accepted-base/code-head `git diff --check` | exit 0, silent |
| Root/packaged protocol schema identity | byte-identical; SHA-256 `764b7eb3a7c55295997bbf0eb67f0ca027e02c8edfb47013c4447d19ebffbb5b` |
| Changed test suppression scan | no added skip, skipif, or xfail |
| Forbidden API review | no process launch/termination, chip/mass erase, Option Bytes, arbitrary write, or implicit reset path |
| Windows path/state gates | real NTFS files plus deterministic junction/reparse, parent/leaf replacement, permission, atomicity, and cancellation seams passed |
| Fresh external wheel `[probe]` install | 63 packages installed in a new CPython 3.12.13 venv; public contracts and packaged schema loaded |
| Ordinary wheel import | no `pyocd` module imported until explicit PyOCD import |
| Installed PyOCD probe discovery | `No available debug probes are connected` |

The final full coverage command was:

`python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term --cov-fail-under=90 -o addopts=`

The three skips are pre-existing Windows environment capability skips; this
packet adds no skip or xfail. The one warning is the existing third-party
Pydantic Settings unresolved-forward-reference warning from MCP construction.

## Deferred and non-claimed evidence

- No physical debug probe is connected. Real sector programming, complete
  physical readback, Cortex-Debug ownership transfer, and exact target-state
  behavior are `DEFERRED_TO_AVAILABLE_REAL_PROBE` and remain release gates for
  `STM32TK-0405-CLI-MCP-RELEASE` and the non-skippable 1.0 acceptance.
- Linux lease/path/cancellation/programming behavior is
  `DEFERRED_TO_STM32TK-0405-CLI-MCP-RELEASE`; Windows evidence is not relabeled
  as Linux evidence.
- PyOCD's file programmer owns vendor flash algorithms internally. Toolkit
  pins sector erase and exposes no chip-erase, Option-Byte, raw-write, or reset
  operation, but does not claim physical success without hardware evidence.
- The handoff contract only supplies data for Cortex-Debug. Launch/task wiring,
  CLI/MCP/Skills, doctor capability, and release packaging belong to 0405.
- Typed DWARF/SVD reads, bounded sampling, and Fault evidence belong to 0404;
  Monitor groups/history/UI belong to 0501 and 0502.

## Known limitations

- External Cortex-Debug/PyOCD is outside Toolkit's process ownership. Toolkit
  releases only its own service and lease and never starts, kills, or steals an
  external debugger process.
- A failed state promotion after lease release requires the owning workflow to
  restart the exact Probe Service before retry. The retry then revalidates the
  client endpoint, firmware evidence, target attachment, and readback instead
  of silently promoting stale state.
- Backend byte/sector counts remain `null` when PyOCD provides no verifiable
  statistic; exact readback bytes are reported separately and are never
  inferred from API success.
