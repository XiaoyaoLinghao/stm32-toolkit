# T9 Cortex-Debug identity repair

## Authority and baseline

Bounded repair under the approved 2026-08-25 legacy real-board closed-loop specification, Task 9. Primary conversation owns design and acceptance; one Luna/max implementation owner; independent review by the primary or its reviewer. Accepted slice base: `4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1`. Local integration branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. No remote action or ownership exception is authorized.

Current deployed source remains `a46310cbad431ed0f8c56d822db9054d426c4c14`; physical -12 100ms observation, historical attempt 7 and current P2 are preserved. This plan authorizes offline implementation and tests only. No deployment, probe enumeration, connection, control, firmware change or retry.

## Runnable scenarios and non-goals

1. Authorized handoff begin on a verified attachment returns Cortex-Debug PyOCD `request=attach`, `targetId` and the raw `boardId` corresponding to the exact attached public probe selector. No second enumeration is used to infer identity.
2. Repeated begin after external reservation and worker shutdown returns the same ticket-bound configuration without hardware access. Missing, malformed or mismatched configuration fails closed; handoff end still permits normal ownership recovery.
3. Ordinary attach and probe service HTTP responses retain their existing public identity schema. Generated project configuration no longer advertises a runnable debugger entry with nonexistent handoff tasks.

No new backend, public tool, HTTP endpoint, automatic IDE task runner, pack discovery, hardware policy, sampling change or generalized configuration framework. This is not physical T9 acceptance.

## Frozen data and ownership contract

The attached backend owns the mapping from public selector to raw identity. Cache metadata only after the existing selected-probe attach succeeds, using that exact selected probe's `unique_id`, requested target and public selector. Validate with existing selector and hardware-ID validators. Clear on close, failed attach and replacement attach. Reading this cache must not enumerate or read hardware.

Introduce one private `debug_handoff_metadata` capability, rather than widening `ProbeAttachmentEvidence` or mandatory legacy `ProbeBackend` protocol. Use the existing worker request/reply mechanism. The value has exactly `probeId`, `target`, `boardId`. Add a typed model if useful; boardId must be excluded from repr. Worker validation must reject malformed/mismatched data and sanitize errors. Fakes supporting handoff implement this private capability; unsupported backends fail closed only for handoff.

Expose it to handoff through private supervisor/service methods under existing lifecycle and backend serialization/lease checks. It must require an active committed attachment matching probe and target. It is not a new HTTP operation and must not use the worker while stop owns it. The handoff obtains metadata after its existing attachment/segment checks and before creating an external reservation. Generic logs, errors, endpoint, lease and debug-handoff state must not acquire raw identity.

The private metadata request owns one five-second monotonic deadline captured before supervisor lifecycle-lock acquisition. Service-lock waiting and worker IPC use its remaining budget. Queue expiry must dispatch nothing and publish no companion/state/reservation. Cancellation and worker failure use existing owned-call cleanup and invalidate attachment state if the underlying worker/session is lost; a late result is never usable. This bound applies only to the new cache-read seam, not to normal attach, sampling or hardware timing. Do not add a new lock or queue.

`CortexDebugAttachContract` adds `boardId` and `targetId`; keep existing `serialNumber` (public selector), `target`, executable, request and servertype fields for compatibility. `boardId` is the validated raw identity, never the opaque hash. `targetId` is the already validated requested debug target. This intentional external IDE configuration is the sole public return boundary for raw identity. The ordinary attach response remains four fields. No SVD-to-pack inference; cmsisPack is outside this repair and must come from verified environment configuration when the IDE is exercised.

## Persistence and lifecycle

Reuse handoff's bounded safe JSON IO, atomic replacement, process guard and async lock. Keep existing `debug-handoff.json` schema and state transitions unchanged. Store only a companion external IDE configuration, `debug-handoff-cortex-debug.json`, in the same session root. Closed object: schemaVersion=1, ticketSha256, workspaceId, sessionId, probeId, target, buildId, elfSha256, executable (portable relative path), boardId. It is a purpose-specific external config, not a second ownership authority.

Validate every field against the existing handoff state and fresh firmware; validate public_probe_selector(boardId)==probeId. Thus changing the raw ID, executable, target, ticket or project identity cannot silently alter selection. Never return a stale companion solely because its ticket hash exists. No raw ticket in this artifact. Reparse, escape, duplicate-field, oversized and non-regular-file protection must be as strict as existing state IO.

Persist configuration before paused state/reservation becomes externally owned. A crash leaving only a companion grants no ownership; a later new ticket may replace it atomically after full validation. Existing paused state may receive its matching companion only while service is active and the attached identity is re-proven. Externally owned state without a valid companion returns `HANDOFF_IDENTITY_MISMATCH` without re-enumerating. It remains endable with its valid ticket. Repeated begin reads and validates the companion. Cancel/stop/cleanup retains current fail-closed reservation semantics. A consumed stale companion is harmless because every use requires matching active ticket/state; no cleanup action may undermine ownership recovery.

## Generated VS Code files

Static generation cannot know the authorized live ticket/probe. Generate `.vscode/launch.json` with version 0.2.0 and an empty configurations list for both build-only and hardware-capable projects. Preserve Build Debug/Release tasks and SVD/project data elsewhere. Document that callers construct the IDE attach entry from successful public handoff output, then explicitly end the same ticket after IDE detach; do not invent pre/post tasks or silently attach arbitrary probes. Existing user-owned P2 files are not regenerated in this slice.

Put the temporary IDE launch entry in a run-owned `.code-workspace` file outside the project input tree, with one folder pointing to the unchanged project and workspace-level launch/configurations wrapping the returned fragment with name and type=cortex-debug. Do not instruct callers to paste a live ticket-bound configuration into the project's managed `.vscode/launch.json`: owned generated files participate in InputSnapshot, so that would invalidate the firmware identity during handoff. The existing companion is also outside the project tree. This is documented use of VS Code workspace configuration, not a new Toolkit generator or automatic IDE launcher.

## File ownership and validation

Implementation owner may modify `probe/{backend,pyocd_backend,worker,service,supervisor,handoff,fake_backend}.py` (actual existing fake module name may differ), `generation/configure.py`, their focused existing tests, and a narrowly relevant existing handoff usage document. No recovery/acceptance/diagnostic workflow edits, shared CLI/MCP inventory, dependencies or lockfile changes. Any necessary additional seam must be explained to the integration owner before widening scope.

Luna runs offline fake-backed checks: actual worker metadata roundtrip; exact selected identity with no second enumeration; absent/failed/closed attachment; ordinary attach privacy; begin/repeated begin/restart; malformed/missing/stale companion; reservation/stop/cancellation and end recovery; generated config has no phantom tasks or launch mode. Reuse existing fixtures/tests, no hardware or diagnostic runner. Run relevant handoff, worker, backend and generation regressions once; existing valid unrelated tests are retained. New tests demonstrate behavior, not just dictionary spelling.

Primary reviews the complete base-to-CodeHead diff in a separate clean worktree and runs proportionate independent checks. Report software status separately from pending actual VS Code/PyOCD attach, detach, reacquisition and public entry equivalence. T9, T10 and VS10-A remain unaccepted.

## First independent review corrections

The request's five-second deadline must reach the worker proxy, including call-lock waiting and the remaining IPC response budget; no default thirty-second metadata call is permitted. Queue expiry dispatches nothing. After a dispatched request times out or is cancelled, allow a separate, explicit maximum three-second owned-cleanup budget (existing worker terminate/kill joins are one second each). Do not await provider or abort tasks indefinitely. Cleanup cannot turn an expired result into success. If owned execution cannot be confirmed stopped within cleanup, invalidate the attachment, make this service terminally unavailable, retain the lease/ownership exclusion, and report cleanup failure. Subsequent stop must return a bounded failure for this unresolved metadata execution, never release ownership while a worker may remain live and never claim successful cleanup. Scope this exceptional handling to the new metadata seam; ordinary operation deadlines and successful stop behavior remain unchanged. No new lock, retry or background hardware action.

The companion's type/content safety check belongs to begin/read/write of that companion, not the common session-root precondition used by end. A valid ticket remains endable even if the optional companion has become a directory or reparse entry. End neither follows nor deletes that entry. Begin remains fail-closed for unsafe entries; only a safe regular stale companion may be atomically replaced for a new ticket. Add focused worker deadline/cleanup and non-regular companion recovery regressions; retain existing unaffected checks.

## Lifecycle reconsideration after the second review

At b083cc12, the remaining defect is architectural within the private seam: cleanup ownership is selected by exception type. A worker-originated ProbeWorkerError can mean its child is still live even though the proxy has set _closed, and bypasses the service's TimeoutError/CancelledError branch. The two-round gate therefore returns this seam to lifecycle design before further implementation. Do not add one more error-code-specific branch.

Use one outcome boundary for the dispatched metadata operation. From provider dispatch until validated, in-deadline identity is committed, every unsuccessful exit (provider exception, cancellation, timeout, malformed/mismatched response, or failed final lifecycle check) goes through the same existing bounded owned-cleanup finalizer exactly once. Queue expiry before dispatch owns no new execution and does not abort an unrelated current call. The service owns cleanup accounting and exclusion; worker _closed and successful return from close/abort are never proof that the child stopped. For a worker, confirmation requires its existing is_alive fact to be exactly false and all owned call/cleanup tasks settled. Unsupported or inaccessible worker liveness is not positive stop evidence. Existing direct fake seams may prove completion through their settled tasks without inventing child-process facts.

Confirmed stopped: preserve the sanitized original operation failure and permit existing normal stop cleanup. Not confirmed stopped within the existing three-second cleanup budget: return ProbeServiceCleanupError/PROBE_CLOSE_FAILED, invalidate attachment, set terminal unavailable state, retain lease and endpoint plus supervisor ownership reference, and reject later start/dispatch. Subsequent stop must apply the same stop-proof predicate and remain bounded; no release based only on an empty task set, _closed, or an abort call returning. Keep this inside the T9 metadata seam, with no public schema, general backend lifecycle, hardware operation or deadline expansion.

The minimal new regression must reproduce an immediate provider ProbeWorkerError after the proxy is closed while child liveness remains true (abort may return without action), then prove bounded request/stop failure and retained exclusive lease/supervisor reference. Contrast a provider failure with positively stopped worker so this repair does not retain ownership after proven cleanup. Existing seven independent checks and all unaffected tests remain valid; rerun only the changed service/supervisor paths and this regression before final complete-diff review.
