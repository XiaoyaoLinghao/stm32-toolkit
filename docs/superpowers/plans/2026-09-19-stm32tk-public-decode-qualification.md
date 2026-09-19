# Public evidence decoding qualification plan

Accepted base: `63602bf6dbd2ad5ff2b676678695767e000bbb2a`.
Design: `../specs/2026-09-19-stm32tk-public-decode-qualification-design.md`.

Primary owns coordination, design, integration, exact-entry review and cleanup.
One Luna/max owner works in `D:\codex-tmp\v10b-0918\r10\dc`, branch
`codex/STM32TK-1.0-public-decode-qualification`, and owns only these existing
files under `tools/stm32-toolkit/tests/`:

- `test_diagnostic_model.py` and `test_diagnostic_events.py` for the two
  Diagnostic wire scenarios;
- `test_acceptance_recovery_model.py` for checkpoint and source-intent decoding;
- `test_monitor_replay_contract.py` for raw-byte import and reference validation.

The owner may add one short report at
`docs/codex/returns/STM32TK-1.0-local-release/public-decode-qualification-report.md`.
Other code and tests are outside ownership. No recursive delegation. Other
workers are active; preserve their files and do not revert unrelated changes.

## Execution

Read the current tests before adding rows. Reuse `_canonical_payloads`, existing
revision/source-intent helpers, `_document`, `_reference`, `_physical_transcript`
and versioned fixture files. Do not import a whole unrelated test module solely
to obtain a fixture if its collection has side effects; prefer the existing
local equivalent or a small concrete fixture in the owned test module.

Commit the tests before execution and return the exact node list and command to
the primary for entry review. Use `r10/py/Scripts/python.exe`, explicit PowerShell
7, imports from this worktree, branch coverage and `-x`. All temporary roots,
basetemp and caches go under `r10/t/dc`; actual tempfile must match the bound
TEMP/TMP/TMPDIR. Durable evidence goes in `r10/e/public-decode-qualification`.
Reuse the working finite child-launch pattern from retention r3, not a new
runner. Bound the scoped child at 180 seconds, preserve stdout/stderr, JUnit,
command, code head, actual child exit and raw coverage plus JSON. Do not run
during the exclusive covered continuation lock check; primary schedules it.

First unexpected failure stops for classification. Tests may be corrected only
with concrete fixture/contract evidence; do not retry unchanged or change a
public expected result to mirror a bug. Independent review uses a clean checkout
at the exact returned head, covers accepted-base-to-final diff and retained
results, and precedes integration. Accepted raw coverage is combined once with
other accepted batches by primary; failed data is never included. Preserve
minimum failure evidence, source fixtures and raw coverage. No cleanup until
primary disposition; no remote, package, deployment or hardware actions.
