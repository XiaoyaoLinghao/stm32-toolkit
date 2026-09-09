# STM32TK-1001 Probe Attach Stage Diagnostics

Accepted base: `1d461f23fdde8a04c845b7e3989fe41318dd3ed8`

Owner ledger: specification and review are owned by GPT-5.6-sol; implementation and implementation tests are owned by one GPT-5.6-luna/max agent. The active local branch is `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. No remote action, deployment, runtime replacement, hardware action, or ownership override is authorized.

## User scenarios

1. When normal attach fails while creating or opening the pyOCD session, the public failure remains `PROBE_ATTACH_FAILED` with the generic message and includes only a stable stage such as `session-create` or `session-open`.
2. When attach cleanup cannot restore the target, the failure identifies `cleanup-resume`, remains privacy-safe, and still runs the existing owned-child cleanup.
3. A valid attach stage crosses worker IPC and the existing service/client/flash layers unchanged; flash still performs no programming after an attach failure.
4. Unknown stages, extra keys, wrong types, backend exception text, paths, raw serials, and arbitrary details never cross the worker privacy boundary.

## Contract

`PROBE_ATTACH_FAILED.details` may be either empty for compatibility or exactly:

```json
{"stage":"session-open"}
```

`stage` is one of `session-create`, `session-open`, `target-resolve`, `halt-verify`, `resume`, `resume-verify`, or `cleanup-resume`. `pyocd_backend.py` is the producer. `worker.py` owns the shared closed set and accepts only that exact one-key mapping. Existing code, generic message, connection policy, lifecycle, cleanup, timeout, authorization, and error propagation remain unchanged.

## Non-goals

- Exposing pyOCD exception text, filesystem paths, probe objects, raw serials, stack traces, or arbitrary backend details.
- Changing enumeration, selection, attach, halt/resume, reset, programming, readback, service/client/flash behavior, or hardware retry policy.
- Diagnosing the already completed physical failure retroactively.
- Packaging, deployment, runtime modification, hardware access, or changes outside the two product files and three focused test files.

## Acceptance

Existing fakes and worker IPC seams must distinguish session-open from cleanup-resume, preserve a valid stage, reject malformed or unsafe details, propagate the safe stage through public flash failure, prove zero programming after attach failure, and prove the child is reclaimed. Review covers the complete accepted-base-to-CodeHead diff. No full repository or release matrix is required.
