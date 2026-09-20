# Probe ownership retry qualification plan

Accepted base: `3ba1439c20b09257dfcbe55eee517e1349655f01`.
Governing scope: 2026-09-19 core-public-contract qualification and the adjacent
2026-09-20 probe-retry specification. This narrows the existing approved testing
scope; it changes no product contract or authorization.

Primary commits this plan and creates one clean implementation worktree at its
exact head. One gpt-5.6-luna/max owner appends tests and the minimal local seam
in tools/stm32-toolkit/tests/test_debug_handoff.py and test_probe_lease.py.
It is not alone in the codebase; preserve other work. No recursive delegation,
pytest/collection/product imports, cleanup, remote, hardware or runtime edits.
Primary remains the sole serial pytest executor. Return a committed candidate,
exact selectors, test/source mapping and AST/diff checks; runtime stays NOT_RUN.

Use D:/codex-tmp/v10b-0918/r10 only: c103l candidate, r103l detached review,
e/n95/probe-retry evidence, t/pr1 disposable run data. Primary owns cleanup;
all prior rejected cleanup roots remain untouched. Preserve original native data.

Before runtime, primary reviews the complete base-to-candidate diff in r103l,
including the one-shot provider seam, every resource assertion and finally
cleanup. The acknowledged design corrections are recorded in
e/n95/probe-lifecycle-design-review.md and probe-lifecycle-feasibility.md.
Return correctable findings to the same owner; two nonconvergent rounds require
a design decision rather than further patching.

Reuse the existing bounded completion-graph launcher, changing only source/head,
selectors, evidence/temp paths and a 180-second budget. Explicitly bind TEMP,
TMP, TMPDIR, basetemp, pytest cache and raw coverage under approved roots.
Instrument both Python packages using the existing native branch configuration;
run only the new handoff cases and acquire/heartbeat clock cases, first failure
stop. No full suite, deployment, packaging or hardware repeat.

Retain command, environment, logs, JUnit, raw native coverage and terminal process
proof. Confirm product-source identity unchanged, then reconcile complete PASS
raw data against accepted union19 using the existing helper and independent
data review. Failed batches are excluded; report-only corrections never rerun
tests. Only then update the accepted baseline and consider scoped cleanup once.
