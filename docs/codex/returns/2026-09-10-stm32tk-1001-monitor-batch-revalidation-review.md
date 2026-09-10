# STM32TK-1001 Monitor Batch Revalidation Review

**Outcome:** `ACCEPTED`
**Accepted base:** `4db09f65067e6cacbbe88c1c4c2e1f8dd19bd451`
**Specification head:** `99b804d234030ff69d6d612b9138a51ef377ab3b`
**Reviewed code head:** `c474d07422f00c8c906a7d149b9f082ba02e8a6f`
**Implementer:** one GPT-5.6-luna/max agent
**Independent reviewer:** GPT-5.6-sol

## Result

The private Monitor stable-tick path now resolves and authorizes the complete variable/register
set, performs one existing same-session guard before the reads and one after them, and returns a
report only after the post guard succeeds. The sampler no longer runs an additional duplicate
lightweight guard before the private batch. Public standalone debug reads keep their existing
per-read behavior.

For a completed one-variable/one-register tick, the production-shaped seam proves exactly two
firmware loads, two DWARF checks, two SVD checks, two committed-attachment checks, and two memory
reads. With the current loader this corresponds to four Git subprocesses. A pre-guard failure
performs zero reads. A post-guard failure discards values before history or subscriber publication.
Cancellation and stale sampler epochs remain unpublished through the existing lifecycle checks.

The complete accepted-base-to-code-head diff contains the two approved design documents, four
product files, and three focused test files. It adds no cache, TTL, lock, queue, task, deadline,
public schema, physical control, or cross-batch reuse. The first review found that the private batch
constructed `DebugReadReport.confirmedAtUtc` before its post guard. The same Luna owner corrected
this in `c474d074`; the final report and timestamp are now constructed after the post guard with no
additional guard or read.

## Evidence

- RED: the initial private mixed-batch ProbeSession node failed because the accepted base still
  called public `read_variables` and `sample_registers`: `1 failed in 3.77s`.
- Implementer GREEN at the reviewed code: affected modules and public-read compatibility checks
  returned `189 passed, 1 skipped in 149.60s`. The skip was the unchanged
  `test_external_root_parent_change_never_writes_into_project`, because directory redirection is
  unavailable on this host. The correction nodes returned `2 passed in 3.16s`.
- Independent Sol verification at the reviewed code returned `17 passed in 20.08s`, covering exact
  call budgets, pre/post drift, grouping fallback, SVD sampling access, cancellation, private
  ProbeSession mapping, sampler publication/lifecycle behavior, and selected public read
  compatibility nodes.
- An earlier independent attempt used a long D: test root and failed during fixture staging with
  `GENERATION_APPLY_FAILED`; a fresh short path under `D:\codex-tmp` passed. This is classified
  `ENVIRONMENT`, not a product failure.
- Four changed product files compiled successfully; the product/test diff has no whitespace error.

## Remaining boundary

This acceptance proves removal of same-batch duplicate validation and preservation of the frozen
guards. Two firmware loads can still exceed 100 ms on the measured project, so it does not prove a
strict 100 ms physical sampling rate. No package, deployment, runtime, pack, hardware, remote, or
historical-evidence operation was performed. Historical attempt 7 remains PASS; the replacement
board's typed testtime and PE4 toggle observations, Task 9, Task 10, and VS10-A remain incomplete
until separately authorized physical evidence satisfies their own gates.
