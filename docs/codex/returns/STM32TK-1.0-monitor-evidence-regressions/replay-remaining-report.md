# STM32 Toolkit 1.0 remaining Monitor replay regressions

This report records the bounded follow-up test preparation, correction round,
and retained verification evidence for the public Replay and physical-
publication contracts. Release acceptance remains pending.

## Ledger

- Accepted integration base: `39bf982af688b7653735b0de02ce75a19804c2b4`
- Frozen product/artifact CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`
- Test CodeHead before this report commit: `eb5bae6b9853cb1087bc87d28c0c559f31c1916a`
- Branch: `codex/STM32TK-1.0-replay-remaining`
- Implementer: `/root/monitor_replay_regressions` (bounded Luna/max test owner)
- Independent review round `review-r1`: `REVISION_REQUIRED`; corrections are
  committed in `a800b96e`; follow-up review remains pending and the implementer
  has not approved this diff.
- Owned files: `tools/stm32-monitor/tests/test_replay.py`,
  `tools/stm32-monitor/tests/test_physical_publication.py`, and this report.
- Product source remained read-only at the frozen CodeHead under
  `D:\codex-tmp\v10b-0918\r10\verify`.

The retained pre-execution review `r10\e\replay-remaining\review-r1.md`
required assertion-quality corrections. The chain/window cases now place each
public mutation in its intended batch, recompute unrelated document/reference
digests where possible, and assert the exact public refusal message. The
physical transcript-root provider case now asserts that the intended root seam
was reached. These corrections are committed in `a800b96e`; no tests were run.

## Prepared public scenarios

The test code uses the existing replay fixtures, physical publication helpers,
public constructors and parsers, and the existing History and EvidenceStore
provider seams.

- Closed replay document models and parsers reject contract field drift,
  binding and batch chain contradictions, malformed nested wire values, and
  invalid selectors or windows. Typed `MonitorReplayDocument` input retains
  exact object identity through `from_value`.
- Replay v1 references exercise public identity, label, digest, optional SVD,
  git, group, and sequence/time-window constructor checks. The public parser
  preserves typed identity, and the v2-only parser rejects a v1 schema.
- A valid replay publication is retried against contradictory reference
  envelope parents or reference artifact bytes. The provider seam is asserted
  as reached, the result is `EVIDENCE_INTEGRITY_FAILURE`, and the existing
  History and authoritative reference state remain unchanged.
- Physical publication validates malformed public request fields before
  provider access, rejects empty, sequence-shifted, time-shifted, and binding-
  contradictory History windows before root writes, and classifies malformed
  project metadata and a contradictory linked TestRun state without mutation.
- Authenticated physical reload rejects provider-supplied reference metadata,
  transcript bytes, and transcript-root metadata contradictions as
  `EVIDENCE_INTEGRITY_FAILURE`, while preserving the persisted root bytes.

The tests were committed as `7afee37c` before this report commit. No product
files, fixtures, shared helper signatures/defaults, dependencies, or release
gates were changed.

## Verification status

The primary released execution after retention `r3` stopped. The planned
two-module command ran once at test CodeHead `a800b96eeca7e4e5b54a360b9346f345a7547909`
with `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe` and product imports
from the frozen `r10\verify` source paths. It exited `1` with `133 passed` and
`2 failed`. Both failures were test setup defects, not product contradictions:
the captured-time case constructed a `SampleBatch` that violated its own
scheduled/captured precondition, and the transcript-byte case passed a valid
physical float through the toolkit evidence canonicalizer, which rejects
floats. The full-run stdout and empty stderr are retained.

The two corrected failed cases then ran once in a narrow follow-up at test
CodeHead `eb5bae6b9853cb1087bc87d28c0c559f31c1916a`; it exited `0` with `2
passed` in `2.32s`. The complete two-module set was not rerun after the narrow
correction, so this evidence is not a final module-level release pass.

Retained execution evidence includes actual argv, command, environment,
stdout, stderr, exit status, JUnit, text coverage JSON, and binary coverage:

- Full affected-module run: `D:\codex-tmp\v10b-0918\r10\e\replay-remaining\run-a800b96-20260919`
- Narrow corrected cases: `D:\codex-tmp\v10b-0918\r10\e\replay-remaining\run-eb5bae6-20260919-targeted`
- Temporary, child tempfile, pytest basetemp, cache, and `COVERAGE_FILE`
  roots are retained under the corresponding directories in
  `D:\codex-tmp\v10b-0918\r10\t\re2`.

The full affected-module coverage JSON reports `955/1196` covered statements
(`79.8495%`) and `282/404` covered branches (`69.8020%`) for
`stm32_monitor.replay`. The narrow corrected-case coverage JSON reports
`632/1196` statements (`52.8428%`) and `145/404` branches (`35.8911%`). These
are scoped informational metrics; `--cov-fail-under=0` was not treated as a
release pass and no aggregate release gate was changed.

## Existing coverage and remaining boundaries

The retained pre-change aggregate evidence at
`D:\codex-tmp\v10b-0918\r10\e\python-release\monitor-aggregate-r3\coverage.json`
reports `2417/2936` Monitor branches covered (`82.3229%`). Its Replay source
attribution is `916/1196` statements and `248/404` branches, with `156`
branches missing. Those are historical aggregate values, not evidence for the
new test commit.

Some raw Replay parser exception edges are not reachable through a normal
public JSON caller because the shared closed contract validator rejects the
wire value before `MonitorReplayDocument`, `MonitorRunRef`, or
`MonitorRunRefV2` construction. Hostile custom objects and private helper
calls remain outside scope. The follow-up also does not claim coverage for
every still-reachable provider variant: malformed History fragment ordering or
metadata cases beyond the coherent window cases above, all linked TestRun
identity fields, every canonical physical transcript shape, and every
individual persisted authority field remain release-owner follow-up work when
they are required by a concrete scenario. No raw percentage target justifies
bypassing a public validator or manufacturing an impossible typed state.

No hardware, packaging, deployment, remote action, or release acceptance was
performed.
