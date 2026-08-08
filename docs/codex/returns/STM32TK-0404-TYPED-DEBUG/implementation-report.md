# STM32TK-0404-TYPED-DEBUG Implementation Report

## Delivery identity

- Status: `IMPLEMENTED`
- Accepted product base: `35a5326fed7a4810152020c363f3529ebd50c382`
- Plan commit: `5561d88067b09ab5ff3233a52fc3ca7659b12a6c`
- Branch: `codex/STM32TK-0404-TYPED-DEBUG`
- Code head before this report commit:
  `0594c86bb193752841d766a7378c440f3f5a35e0`
- Specification, implementation, test, and review owner: Codex, following the
  user's explicit pause of OpenClaw implementation and authorization to use
  independent Codex subagents on disjoint paths.

This report intentionally does not contain its own final commit SHA. The PR URL
and final remote head are returned after the report is pushed.

## Delivered scope

The code head changes 20 plan, product, fixture, and test paths relative to the
accepted base (8,444 insertions and 1 deletion):

- frozen JSON-safe typed debug evidence models with canonical project-root
  provenance, lossless 64-bit integer evidence, explicit non-finite floating
  values, bounded deep-freezing, and stable report budgets;
- `bind_debug_firmware()` with exact workspace/session/lease/probe/target,
  build/identity/Git/input/ELF/MAP/flash evidence, complete file-backed segment
  readback, and final endpoint, physical attachment, disk, and flash rechecks;
- a bounded real ELF/DWARF5 catalog using pyelftools, explicit project-readable
  regions, immutable ELF path/size/SHA/source identity, descriptor and parent
  path checks, restricted expressions, and typed scalar decoding;
- a deterministic ARM Cortex-M4 fixture built with GNU ARM 14.3.1 containing a
  valid vector table, Reset handler, entry point, and real DWARF type/location
  information;
- exact explicit CMSIS-SVD selection with project containment, descriptor
  identity, UTF-8/UTF-16 DTD/entity rejection, full register-properties
  inheritance, scoped `derivedFrom`, bounded arrays/clusters, and immutable
  SVD/readable-region provenance;
- read-risk policy that always rejects write-only registers, requires strict
  acknowledgement for a single side-effecting read, and never samples a
  side-effecting register;
- provenance-bound variable and register reads that accept no raw caller
  address or size, merge adjacent ranges only within one readable region and
  protocol bound, and retry original items independently after a merged read
  failure or short read;
- finite in-memory sampling at an applied 100-5000 ms interval with bounded
  count/duration/output, monotonic deadlines, no catch-up storm, measured rate,
  latency/deadline/drop evidence, and cancellation without orphan work;
- already-halted-only Cortex-M Fault evidence using a fixed core-register and
  SCB allowlist, EXC_RETURN MSP/PSP and basic/extended frame selection, stack
  range/alignment validation, Cortex-M4 fault-bit decoding, and bounded exact
  ELF symbolization;
- 33 public typed-debug exports without importing PyOCD during ordinary
  `stm32_toolkit.debug` import.

This packet adds no CLI, MCP tool, Skill, version bump, Monitor group/history,
database, HTTP/WebSocket service, background daemon, pointer dereference,
arbitrary address read, target write, halt, resume, reset, breakpoint, process
control, ambient pack search, or runtime network access. Those boundaries are
owned by 0405, 0501, and 0502 as recorded in the continuation plan.

## TDD and independent review corrections

Initial RED collection failed because the new debug modules did not exist.
Task-scoped RED/GREEN development and two independent read-only review passes
then exposed and corrected the following material defects:

1. shared reports were frozen dataclasses but some nested containers and
   status/value/code invariants were not deeply immutable or bounded;
2. the original firmware binding omitted a canonical root usable for later
   ELF/SVD provenance revalidation;
3. caller-adjustable DWARF limits could exceed compiled hard caps, and location
   expressions lacked separate byte/operation budgets;
4. the first DWARF catalog carried no path/size/SHA/source identity, allowing a
   later duck-typed catalog to act like a raw address capability;
5. the first SVD parser ignored cluster-level size/access/reset inheritance,
   allowing a write-only 8-bit register to become a readable 32-bit register;
6. cluster/register array products were expanded before the total budget and
   used quadratic duplicate checks;
7. valid nested clusters used the wrong local scope, while a 1,100-entry
   inheritance chain could raise raw `RecursionError` before a stable limit;
8. typed reads initially accepted test doubles rather than real immutable
   catalog/selection provenance;
9. the original DWARF fixture was type-correct but not a valid Cortex-M
   firmware image, so it was rebuilt with a vector table and exact entry proof;
10. sampling allowed a count-by-expression product whose eventual immutable
    report exceeded its node budget and raised an uncaught exception;
11. Fault symbolization accepted function symbols without proving their owner
    was an allocated executable section and lacked section/symbol budgets;
12. Cortex-M4 SHCSR active bits were incomplete and CFSR bit 20 was incorrectly
    labeled with an ARMv8-M-only meaning;
13. Fault current checks initially revalidated build/identity/ELF but not the
    complete current flash-result chain;
14. firmware binding could publish after the lease, attachment, MAP, or flash
    evidence changed during its final target interaction;
15. confirmation timestamps were moved before the last external verification,
    after which only synchronous evidence checks and report construction occur.

Each correction has a deterministic regression that fails on the predecessor
and passes on the code head. The final independent closure review returned
`ACCEPTED` with no remaining P0/P1 blocker.

## Verification evidence

Environment: Microsoft Windows 11 Pro 10.0.26200 build 26200, AMD64, CPython
3.12.13, pytest 8.4.2, pyelftools 0.33, and aiohttp 3.14.3.

| Gate | Result |
|---|---|
| Final debug focused suite before the last binding closure | 326 passed, exit 0; 86.35 s |
| Final firmware-binding closure suite | 111 passed, exit 0; 33.35 s |
| Full Toolkit suite with branch coverage on code head | 1,913 passed, 3 skipped, exit 0; 962.32 s |
| Full branch coverage | 92%, required minimum 90% |
| New debug package branch coverage | 93% aggregate |
| New module branch coverage | dwarf 91%, fault 92%, firmware 94%, model 98%, read 93%, sampling 95%, SVD 92%, types 100% |
| `compileall` | exit 0, silent |
| accepted-base/code-head `git diff --check` | exit 0, silent |
| Changed-file inventory | exactly 20 paths before report/progress reconciliation |
| Ordinary debug import | 33 public exports; no `pyocd` module loaded |
| Windows path/read-only gates | real files plus deterministic reparse/junction, descriptor/parent replacement, permission, cancellation, and evidence-race seams passed |
| ARM fixture validation | vector `0x08000000`; SP `0x20020000`; Reset/entry `0x08000101`; no undefined non-weak symbols |
| ARM fixture SHA-256 | `43ebbfac0c355dda33e1b980b5746ce166c857db6aec313b1c6f862ec6a3252a` |
| Wheel build | `stm32_toolkit-0.3.0-py3-none-any.whl`, SHA-256 `4a06bee28adc740aa5bccbd2b2fa157ae949dc8f1f0ea44dded66e69c825b6bb` |
| Fresh external wheel install | PASS in a new CPython 3.12.13 venv |
| External-cwd real fixture smoke | `WHEEL_SMOKE_OK`; DWARF lookup and exact SVD selection passed; PyOCD remained lazy |
| Forbidden boundary scan | no debug product target write/control, process, network, persistence, or background-task path |

The final full coverage command was:

`python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term -o addopts=`

The three skips are existing environment-capability skips; this packet adds no
skip or xfail. The one warning is the existing third-party Pydantic Settings
unresolved-forward-reference warning from MCP construction.

## Deferred and non-claimed evidence

- No physical debug probe is connected. Real non-halting typed reads and real
  already-halted Fault capture are `DEFERRED_TO_AVAILABLE_REAL_PROBE` and remain
  a release gate for `STM32TK-0405-CLI-MCP-RELEASE`.
- Linux path, lease, cancellation, PyOCD, typed-read, sampling, and Fault gates
  are `DEFERRED_TO_STM32TK-0405-CLI-MCP-RELEASE`; Windows evidence is not
  relabeled as Linux evidence.
- CLI/MCP/Skills, doctor capability, plugin install/upgrade, protocol release
  reconciliation, and the 0.4.0 version bump belong to 0405.
- Persistent Monitor groups, history, storage, authenticated WebSocket/HTTP,
  and the bundled UI belong to 0501 and 0502.

## Known limitations

- The real fixture covers little-endian Cortex-M4 DWARF5 produced by GNU ARM
  14.3.1. Unsupported older/location-list forms and compressed or malformed
  debug data fail closed rather than being guessed.
- Typed expressions deliberately exclude pointer dereference, casts, calls,
  arithmetic, dynamic indices, bitfields, register-only values, and arbitrary
  addresses.
- Sampling is finite and in-memory. It does not create persistent groups or a
  background subscription and therefore is not a Monitor substitute.
- Fault analysis never changes target state. A running, sleeping, reset, or
  otherwise non-readable core returns a stable failure instead of being halted.
- SVD selection is explicit and project-contained; no ambient CMSIS pack or
  network fallback is performed in this packet.
