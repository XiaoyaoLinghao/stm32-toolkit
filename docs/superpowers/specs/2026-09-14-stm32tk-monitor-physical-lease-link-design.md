# Physical Monitor evidence across sequential leases

Status: proposed; requires user approval before product implementation. Current integration base `e3784aa8551faaba7ec1c67126ae9ad320c889de`. Primary owns design and independent review; one Luna/max owner implements the bounded Monitor slice. Firmware P4 remains unchanged at `8755ba8fd0c678f32d7d23e7d827e84317026429`.

## Verified problem

The public offline `stm32_monitor physical publish` rejected the actual failed-before window with `INCOMPATIBLE_IDENTITY`. Existing authoritative TestRun/history loaders compared 26 conditions: only `lease_id` differed. TestRun root metadata records `lease-203e4bda26ec46bd9b7424c26f36cfec`; all 300 Monitor batches record `lease-8adfb28e758f48759ce46b91594d85f6`. Both operations completed and released their own leases. `tools/stm32-monitor/src/stm32_monitor/replay.py:1976` incorrectly requires these two separate operations to share a lease.

The serial Target-then-Monitor campaign uses a new exclusive connection for each operation. A lease identifies an ownership interval, not the firmware installation shared across the operations. Classification: PRODUCT / cross-operation evidence contract. The current hardware window and successful programming remain valid; publication and T10 completion are blocked. Full reproduction details are in the corresponding return report.

## Scenarios and boundaries

1. A committed physical Target run and later committed Monitor window with matching project/workspace/session, portable probe, target, flash session, build/ELF/source/git identity can publish when each contains its own valid physical lease. Preserve both original lease values and their source evidence; do not copy or normalize one lease into the other.
2. Changed probe, target, flash session, project/workspace/session or firmware identity remains rejected. Missing/invalid physical ownership data remains rejected by the relevant existing evidence authority.
3. Within one Monitor window, transcript and reference, lease consistency remains mandatory. A mixed/tampered window or conflicting publication retry must still fail. Existing same-lease records remain readable.

Only the cross-operation lease equality assumption changes. The Target root and Monitor transcript/reference remain the separate authorities for their ownership facts. Retain every other binding predicate, full stored-TestRun/history validation, canonical evidence and idempotency checks. `MonitorRunRef.lease_id` continues to mean the Monitor observation lease; no schema additions, public error-code additions, synthetic evidence, ID rewriting or new storage/diagnostic framework.

Non-goals: hardware lifecycle/backend changes, timeout changes, firmware/P4 edits, sampling/performance changes, evidence migration or repair, deployment and remote actions. Intra-Monitor lease equality in `replay.py` and `analysis.py` remains unchanged. If those guards reveal a distinct contract issue, return to the primary instead of expanding implementation.
