# Align three protocol tests with accepted attachment state semantics

Accepted base: `a46310cbad431ed0f8c56d822db9054d426c4c14`.
Scope: VS10-A final software evidence reconciliation; test-only correction.
Governing contract: approved 2026-09-02 PyOCD connection-policy correction design,
especially its successful-return semantics for `halt_on_connect=False/True`, and
the existing core-register requirement for an already halted target.

The primary conversation owns this plan and independent acceptance. The existing
sole Luna/max protocol-test implementer owns the change and its tests. No hardware,
deployment, package rebuild, project firmware edit, or remote action is authorized.

Runnable scenarios:
1. A default attachment returns running; a test requiring halted-only operations
   explicitly establishes the halted precondition before testing those operations.
2. A target state failure introduced after successful attachment exercises the
   target-state error path, while attachment itself still validates target state.
3. Legacy register reads remain independent from the closed profile allowlist but
   continue to reject running targets; closed target APIs retain range/allowlist
   rejection before any underlying target read.

Only `tools/stm32-toolkit/tests/test_probe_protocol_v2.py` may change, within the
three previously recorded failing nodes. Do not modify shared fakes, product code,
skip/xfail tests, loosen register or state validation, or change attachment policy.
Record one current-base three-node RED first. If its failures differ materially
from these precondition mismatches, return the evidence before making a correction.

Use an explicit test-owned state transition for halted-only positive cases. Keep
the default running assertion and an explicit rejection while running, rather than
silently making ordinary OBSERVE attach halt. For the post-attach state-error case,
arm the fake failure only after successful attachment. Preserve existing negative
identity, limits, privacy, and partial-output assertions. Do not replace expected
rejections with broad success checks merely to make the tests pass.

Verification: the three affected nodes, followed by one complete existing
test_probe_protocol_v2.py run to reconcile the previously failed module. Use the
existing fake driver and isolated short D: scratch paths. Record exact command,
base and CodeHead, results and minimum logs. No unrelated matrix. The main agent
independently reviews the complete accepted-base-to-CodeHead diff and confirms
that no product bytes changed; an independent focused check may cover the three
changed scenarios. This work cannot invalidate unchanged 100 ms physical evidence
or claim T9, T10, or VS10-A completion. Production runtime remains pinned to a463.
