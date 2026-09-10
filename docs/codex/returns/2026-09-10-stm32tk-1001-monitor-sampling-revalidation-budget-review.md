# STM32TK-1001 Monitor Sampling Revalidation Budget Review

**Verdict:** ACCEPTED  
**Accepted product base:** `7f1a5215c291aa6b805bd4c3b7215bbc49540f50`  
**Approved-docs / implementation base:** `178e09d2d1daea1467f16d6feac442554e1bc6c8`  
**Reviewed CodeHead:** `fd5833740c2a3e1c56dd1b65b0bc8f9ea95164c3`  
**Implementation owner:** GPT-5.6-luna/max  
**Specification owner and independent reviewer:** GPT-5.6-sol

## Result

`sampling.start` and `sampling.resume` now perform one full firmware admission before a run enters
or re-enters RUNNING. Stable ticks use the same-session lightweight guard: current disk/Git/flash
evidence, root and endpoint/session/lease identity, committed probe/target attachment, and DWARF/SVD
provenance remain fail-closed, while the tick no longer invokes full target ELF-segment readback.
Pause, stop, block, close, resume, and a new run invalidate the sampler epoch so an in-flight older
read cannot publish into a later lifecycle state.

The user explicitly accepted the residual contract delta: an external debugger, another probe, or
target self-programming may change ELF load-segment bytes during one admitted RUNNING interval
without a complete target scan on every tick. Full target comparison remains at observation open,
start, resume, and reconnect admission. The comparison remains a point-in-time byte proof; it does
not prove reset state or atomicity with the later sample.

No Probe Service/client/worker/backend, public schema, SQLite, CLI/MCP, debug-firmware binding,
runtime, pack, deployment, hardware, remote, or historical evidence bytes changed in this slice.

## Review and verification

Sol reviewed the complete
`7f1a5215c291aa6b805bd4c3b7215bbc49540f50..fd5833740c2a3e1c56dd1b65b0bc8f9ea95164c3`
diff in a separate clean D: worktree. The diff contains the two approved design documents, three
product files, and their three focused test files. It adds no TTL, persisted token, lock, queue,
deadline, retry, or new hardware operation. The private logical attach check reuses committed
OBSERVE attachment evidence in the existing service.

Implementation evidence:

- RED: the initial five contract nodes failed as expected (`5 failed`).
- GREEN: initial five nodes `5 passed`; new cancellation/epoch nodes `4 passed`; complete sampler
  file `35 passed`; probe-session plus sampler `47 passed`; final drift/lifecycle set `11 passed`.
- A whole-file observation attempt in the implementation worktree was blocked during fixture
  staging by `GENERATION_APPLY_FAILED` with `phase=stage` (`21 passed, 1 skipped, 31 errors`). This
  was classified as ENVIRONMENT/fixture state rather than a product failure. In the independent
  clean review worktree, the affected production lightweight node passed.

Independent evidence:

- At intermediate CodeHead `90558322d697f96b4a880fe5741a414a6e8d5328`, 13 selected production,
  admission, cancellation, publication, and cleanup nodes passed in 3.74 s.
- At final CodeHead `fd5833740c2a3e1c56dd1b65b0bc8f9ea95164c3`, the eight drift cases plus
  lifecycle re-admission, stable lightweight ticks, and pause race protection passed: `11 passed
  in 8.48 s`.
- The final commit after the intermediate check changed tests only; all three product-file bytes
  remained identical.

The software verdict does not convert the earlier zero-batch hardware run into PASS. A new
candidate, deployment, and separately authorized physical OBSERVE remain integration work. The
historical attempt 7 hardware PASS remains valid; Task 9, Task 10, and VS10-A remain incomplete.

## Preserved cleanup evidence

The implementer could not remove the run-owned RED basetemp
`D:\codex-tmp\stm32tk-monitor-revalidation-impl-20260910-run-red-01`: a nested fixture Git object
returned `Access is denied`; a later direct recursive `Remove-Item` request was rejected by execution
policy. No further cleanup variant is authorized or attempted. The retained path is test output,
not product or acceptance evidence.
