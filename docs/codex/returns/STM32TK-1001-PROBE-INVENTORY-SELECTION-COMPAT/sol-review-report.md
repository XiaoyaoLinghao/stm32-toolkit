# STM32TK-1001 Probe Inventory/Selection Compatibility — Sol Review

## Verdict

`ACCEPTED` for the software probe-inventory/selection compatibility slice.

This verdict does not claim hardware acceptance, runtime rebuild acceptance, H2 completion, or
VS10-A completion. No hardware or remote operation was performed.

## Reviewed lineage

- Full accepted base: `74ee5f4c7872af1bb612c9068af36319457e087b`
- Approved specification: `372d80388aa2ecd806fce1ba2cc83796106e15e0`
- Approved implementation plan: `0f06a94976e14cfdd7ae3189f2e921c6aec0b20a`
- Accepted RED head: `6db9f08cb9b37c4bcb348102f47065f0d12b6c18`
- Product implementation head: `e8407f89a9ca9b2c82ffaa5c54b63f0f04faef73`
- Final code/test head: `9f6efedd16fd3c317fa3b84ea439528a79d25be1`
- Final code/test tree: `c7280970c9aca537dcbe92b159f5a9ce39c56428`
- Implementation-report head reviewed separately: `3478dfe6406f1fbb8e4091710e1864f8ba92ac61`
- Implementation-report tree: `7df21198a60e165a075bbd2638effa94d3a5ef3a`

The sole implementation owner was one GPT-5.6-luna agent at reasoning effort `max`. The
GPT-5.6-sol primary reviewed the complete accepted-base-to-code-head diff in a clean detached
worktree at the implementation-report head. The implementation report was reviewed as a separate
one-path delta.

## Scope and contract review

The complete software diff contains exactly the approved specification and plan, four allowed
product paths, nine applicable test paths, and the implementation report. Product changes are
limited to:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/selector.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`

The review confirmed:

- printable strict-UTF-8 hardware identities are bounded to 512 encoded bytes;
- `probeFingerprint` is the complete lowercase SHA-256 of the exact raw hardware ID;
- existing portable raw selectors remain byte-for-byte unchanged unless they begin with reserved
  lowercase `pyocd:`;
- nonportable and reserved raw IDs map to `pyocd:<full fingerprint>`;
- `ATK 20210914` maps exactly to
  `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`;
- PyOCD selection freshly enumerates, validates every raw identity, compares the public selector
  exactly and case-sensitively, and rejects missing or duplicate matches before session creation;
- the public descriptor is closed to six keys and the client revalidates mapping, fingerprint,
  display fields, and duplicate selectors;
- attach protocol, frequency, connect mode, target validation, cleanup, and downstream identifier
  grammar are unchanged;
- there is no selector cache, registry, index fallback, substring match, case folding,
  auto-selection, vendor-specific branch, new backend, or new controller.

`git diff --check` passed for the complete accepted-base-to-report-head range. The reviewed detached
worktree was clean.

## Independent verification

The Sol-owned focused suite covered selector, PyOCD backend, worker, service, client, direct backend
contract, public hardware workflow, CLI, and MCP behavior. It ran under CPython 3.12 from a fresh
short external basetemp and completed with exit code `0`: `440` tests passed with no failures or
skips. The exact Sol-owned basetemps `C:\tmp\t2s` and `C:\tmp\t2s2` were removed and verified
absent after the result was captured.

The implementer evidence also remains valid: `428/428` changed-behavior tests passed, the direct
backend contract passed `12/12`, and the 14-file short-root matrix completed with `697` passes, one
expected platform skip, and no failures.

## Separate accepted-base defect

The prescribed long basetemp exposes an independent accepted-base Windows path-length defect:
with `LongPathsEnabled=0`, authorization publication through `os.link()` fails when the destination
reaches 263–266 characters. This defect is not caused or altered by the selector diff, and no
physical-workflow or authorization product/test bytes changed in this slice. It remains explicitly
unresolved and requires its own interface and safety review; it is not relabeled as selector,
hardware, or environment acceptance evidence.

## Boundary and state

- `HARDWARE NOT RUN`
- `RUNTIME REBUILD NOT RUN`
- `REMOTE ACTION NONE`
- No push, PR mutation, merge, tag, release, or remote branch action was performed.
- The implementation branch remained local and unpushed at the reviewed report head.

The next authorized product phase may perform passive inventory and subsequent hardware work, but
this review stops before either action.
