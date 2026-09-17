# VS10-A Probe attachment lifetime corrections

Primary design under the user's active VS10-A completion and repair authority. Accepted integration base is `06d16455706d1d37a6398dcfc98ece1ea555bf85`; product bytes at that base remain the accepted T10 `e059ba14d3d8e0072206171d612f686e90329c2d`. These are two concrete findings from the independent complete-range Probe review, not a new backend or recovery capability. The partition's remaining review may identify additional findings; those require explicit scope reconciliation before implementation.

## Runnable scenarios

1. An OBSERVE service successfully attaches and caches attachment evidence. A later backend read fails and its worker is terminated. A subsequent explicit attach on the same service must not return the old cached success. It reaches the existing backend boundary and reports its actual unavailable/failure state. It does not start a replacement worker or reconnect automatically.
2. A direct PyOCD backend already has a valid attachment. A replacement request fails input validation, exact probe selection or descriptor validation before the old attachment is closed. The complete previous attachment remains internally consistent, including the private hardware identity used by handoff. A public worker may still terminate on this error under its existing contract.
3. Once replacement reaches the existing close boundary, all old attachment fields are cleared together. Failed close or failed new open must not leave an old target identity combined with absent or new private identity. A successful replacement publishes one complete new binding.

## Shared lifetime contract

The service's `_observation_attachment` is derived from the live backend attachment and cannot outlive a terminal backend failure. `ProbeWorker.call` currently aborts its owned child before returning backend errors; this behavior is retained. Invalidation must occur within the serialized backend operation boundary before another attach can consult the cache. Do not implement only an outer response-handler clear that permits another queued operation to observe stale success. Preserve initiating error codes/details, existing cancellation/timeout cleanup, worker termination checks, and lease-release ordering. A successful uninterrupted OBSERVE attachment remains reusable.

The PyOCD backend owns one attachment tuple: session, probe, target, target name, public probe hash and private hardware probe ID. Validation before `_close_internal` must not mutate just one member of that tuple. `_close_internal` already clears the raw identity with the rest of the attachment and remains the replacement boundary. No public response gains raw hardware identity. No public schema, authorization digest, session identity, connection mode, flash algorithm, reset/resume behavior, or automatic retry changes.

## Scope and ownership

Luna/max is the sole implementation and implementation-test owner. Primary owns design, integration and acceptance; the independent Probe reviewer reviews the complete correction diff. Product scope is `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py` and `probe/pyocd_backend.py`, plus the existing focused service/backend tests. Changes to worker/public protocol/lifecycle types require returning to primary with a concrete necessity; they are not implicitly included. Other Target/Keil corrections have separate owners/branches and disjoint files.

Non-goals: worker restart, automatic reattach, new diagnostics frameworks, changing valid flash/read evidence, new backend/tool inventory, or replaying completed T9/T10 physical windows.

## Evidence and acceptance

Use existing fake/backend and Windows worker seams to reproduce the stale-cache sequence and the half-attachment state before the fix, then verify the corrected behavior. Check that cache invalidation precedes the next serialized cached-attach decision, successful repeated OBSERVE attachment still reuses its evidence, pre-close invalid replacement preserves the entire old identity, and post-close failure cannot expose it. Preserve full stdout/stderr/exit evidence under the approved run root with TEMP/TMP/TMPDIR, basetemp and caches explicitly constrained there.

The two failure paths are safely proved offline. After independent acceptance, integrate with the other accepted corrections and deploy one final candidate. Because Probe attachment bytes changed, run one bounded normal attach/typed-read/cleanup smoke on the known firmware after candidate deployment. Do not inject a physical backend failure or repeat historical Target/Monitor windows to confirm the same offline result. Keep unchanged historical case results and evidence identities, with their original runtime attribution.
