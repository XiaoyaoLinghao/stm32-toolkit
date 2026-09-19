# Bounded Windows DiagnosticStore lock acquisition

Accepted base: `fa8502e6bf706fcaae26122cf996077678053cc5`.
The primary conversation owns this design, integration and acceptance. One
Luna/max owner implements it; an independent reviewer accepts the full diff.
The active 1.0 goal authorizes this correction. No remote action is authorized.

## Evidence and user scenarios

The covered continuation run at `r10/e/continuation-covered/r3` directly
captured Windows `LK_LOCK` errno 36 after 9.110 seconds during completed-result
authentication. Another caller released the same lock for 625ms and reacquired
it. That failure became a chain-corrupt exception and then a public integrity
error, despite the other checkpoint succeeding. The original full-suite native
cause remains unknown. The separate one-call native API probe at
`r10/e/diagnostic-lock-native-api/native-lock-probe.json` observed `LK_NBLCK`
contention as errno 13, with successful unlock/close of both descriptors.

1. Two identical concurrent continuation checkpoints in the existing Windows
   fixture finish with the same accepted revision-1 result when each acquisition
   succeeds within its budget. Publication CAS and exact retry remain intact.
2. A caller encountering a continuously held DiagnosticStore lock returns a
   bounded availability failure. Public Diagnostic operations return
   `DIAGNOSTIC_STORE_BUSY`; acceptance operations return `ACCEPTANCE_ATTEMPT_BUSY`.
   A later caller can acquire and authenticate after release.
3. A malformed, replaced or otherwise invalid lock file, damaged evidence, or
   a non-contention OS failure continues to fail closed under the existing
   integrity contract. Busy must not hide those failures.
4. A body exception or failed acquisition releases every resource owned by that
   invocation. Real native exclusion remains effective across processes and
   between independent DiagnosticStore instances.

## Frozen behavior and lifecycle

Change only DiagnosticStore's Windows acquisition, not the repository's other
lock primitives. Retain one-byte regular/single-link descriptor identity checks,
seek-to-zero, held-identity validation, native unlock and close. Retain POSIX
`flock(LOCK_EX)`. Do not add a process-local mutex, registry, dependency or queue.

Replace Windows `LK_LOCK` acquisition with `LK_NBLCK` attempts under one absolute
monotonic deadline. The acquisition owner is DiagnosticStore. Its deadline starts
immediately before the first native attempt and expires after **10.0 seconds**;
retry sleeps are at most **25ms** and at most the remaining budget. This makes
the previously implicit native waiting policy explicit; it is not an unchanged
timing claim or an increase intended to conceal the observed failure. The fix
uses the observed release opportunity instead of a coarse native waiting call.

Only errno `EACCES` from this narrowly scoped `LK_NBLCK` acquisition is retriable,
as confirmed by the native probe. Other native errors retain their prior failure
classification. Do not retry open, identity/layout validation, protected work,
publication, unlock or close. Check the same deadline before each attempt and
after acquisition. If acquisition returns after expiry, release the acquired
lock and close the descriptor without entering the protected body, then report
busy. Never reset the deadline on contention. OS scheduling and synchronous
open/validation latency are not promised to have a hard real-time bound.

Lifecycle: descriptor validated -> acquisition pending -> acquired -> held
identity/layout validated -> protected body -> unlock -> close. Timeout before
acquisition closes without unlocking; timeout immediately after acquisition
unlocks and closes. Descriptor close must still run if native unlock raises;
cleanup errors are never silently turned into success. Preserve the existing
failure normalization for non-contention cleanup errors.

Use a distinct `DiagnosticStoreBusyError` operational exception (a RuntimeError,
not DiagnosticValidationError or OSError) with a fixed sanitized code/message.
Expose it through `diagnostics.__init__`. It is not a new event/model validation
code and does not change `DIAGNOSTIC_CODES`, persisted schemas or JSON bytes.
The Diagnostic workflow result adapter converts it to `DIAGNOSTIC_STORE_BUSY`;
the acceptance recovery result adapter converts it to `ACCEPTANCE_ATTEMPT_BUSY`.
Neither message exposes paths or native error strings. Existing validation and
identity errors keep their current codes. No CLI/MCP response shape changes.
The same rule covers a nested Diagnostic public result: acceptance's
`_public_data` must forward the recognized `DIAGNOSTIC_STORE_BUSY` failure as
`ACCEPTANCE_ATTEMPT_BUSY`, rather than its generic output-invalid normalization.
Other non-OK results keep their existing classification. Verify both direct
exceptions and nested public-result propagation.

Availability failure does not promise rollback of earlier publication: the
observed failure occurred during a second, post-publication authentication lock.
Callers can read or retry the same immutable checkpoint after contention clears.
Do not change the attempt deadline, authorization consumption, CAS, publication
order, Diagnostic-before-EvidenceStore ordering, or the completed-result
authentication that intentionally runs after publication locks are released.
Retain one explicit regression at that second authentication boundary: revision
1 is already durably published when acquisition expires, the caller receives
`ACCEPTANCE_ATTEMPT_BUSY`, the root remains unchanged, and a later exact retry or
read authenticates the same immutable revision-1 result. Deterministic deadline
and narrowly scoped native contention injection may avoid a real ten-second
wait; the real native exclusion/release test remains a separate obligation.

Cleanup precedence is unchanged: native cleanup errors propagate from the
store's finally block (Diagnostic currently lets raw OSError escape; acceptance
normalizes it to integrity failure). The correction ensures close still runs
after an unlock failure; it does not turn that cleanup error into Busy or
silently suppress it. Retain a deterministic regression for this precedence.

## Non-goals and acceptance

No generic lock library, new diagnostic framework, timeout change to retention,
schema migration, transport/hardware change, broader supported platform, or
release-gate reduction. This slice does not diagnose an unretained historical
native failure. Preserve all existing A/B physical evidence.

Required evidence is focused DiagnosticStore/adapter regression plus the existing
covered concurrent continuation node against the new code. Include deterministic
deadline/no-late-entry checks, real native exclusion and release/reuse, and
unchanged integrity refusal. A failure stops the current run for classification;
no blind retry. Release packaging/deployment follows independent acceptance and
final candidate settlement. Other already-valid checks remain reusable when
their relevant bytes and contracts are unchanged.
