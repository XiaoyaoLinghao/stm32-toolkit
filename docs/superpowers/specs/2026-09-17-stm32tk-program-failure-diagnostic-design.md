# Programming failure evidence preservation

Approved scope: the user's 2026-09-17 "开始进行问题修复" follows the proposed bounded programming-exception preservation fix in the P4 failure report. This specification concretizes that scope; it grants no installation, hardware or remote authority.

## Baseline and ownership

Accepted base: `d02a605fb4b43691f03cdccc28c418c0fc0de869`, branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Deployment remains `0c375c03ab6afa4192a37d5732009b82845216a7`; intervening changes do not alter Toolkit product bytes. Local integration is clean, one documentation commit ahead of its last verified upstream `3206cabf2badb53f1b6a6f64410e449abffc0a42`. No remote mutation authorized, no new PR, no ownership override. Primary owns design, dispatch, integration, independent review and acceptance; one Luna/max agent owns implementation and tests.

The verified PRODUCT defect is lost programming diagnostics. The physical failure's cause remains unknown. Existing P4 source/build and historical acceptance evidence stay valid in their original scopes; this does not complete P4 programming, T10 or VS10-A.

## Runnable scenarios and non-goals

1. A programmer-construction or program-call exception reaches the public Target CLI/MCP response with the existing `TEST_FLASH_FAILED` code and bounded diagnostic facts from the original exception. A direct flash caller retains `PROBE_PROGRAM_FAILED` and the same diagnostic.
2. Original FlashFailure address/result code, OS error numbers and a bounded cause chain survive worker IPC. Sensitive paths, credentials, probe IDs, arbitrary object repr and control characters do not enter public evidence.
3. Successful programming and legacy failures without diagnostics retain existing behavior. Failure executes programming at most once, never proceeds to readback/run/sampling or publishes a successful receipt/TestRun; existing cleanup still runs.

No retry, recovery policy, timeout, attach, erase mode, firmware, transport, authorization, receipt lifecycle, dependency or deployed-runtime change. No logging service, new CLI command, general diagnostic framework or run-local capture wrapper.

## Frozen data and dependency direction

Add optional `details.programDiagnostic` to the existing failure envelope. One small shared helper in `probe/backend.py` owns construction/sanitization/validation; it depends only on the standard library. Backend, worker and Target adapter reuse it, avoiding duplicated field definitions and higher-layer imports.

The diagnostic has exactly `schemaVersion` (integer 1), `stage`, and `exceptions`. Stage is one of `driver-acquire`, `programmer-create`, `program-call`. It describes the actual entered Python boundary; do not infer erase/write completion. The exceptions list has 1–3 entries, outer to inner, follows explicit cause or unsuppressed context, stops cycles, and never fabricates missing causes. Each entry has exactly `type`, `message`, `errno`, `winerror`, `address`, `resultCode`. Numeric values are exact integers, excluding booleans, within signed 64-bit range or null. Unknown attributes stay null.

Type is a bounded qualified identifier from builtins, pyocd or usb exception classes; unsupported types become `unknown`. Message is at most 256 characters after sanitization. Retain useful error text while replacing filesystem paths (Windows/UNC/POSIX), URLs, quoted values, known raw probe identity and credential/secret assignments with `[redacted]`; remove controls and truncate. The helper must not leak raw data when exception string conversion or properties throw. Bound inspected text and chain length; no serialized traceback or object repr. Constructor passes the raw selector as a redaction value when available. Wire validation enforces the closed shape, bounds and already-sanitized text before any forwarding. Legacy missing diagnostics remain legal; malformed supplied diagnostics use existing protocol rejection/drop behavior at their respective boundaries.

The default driver records programmer-create versus program-call at the actual try boundaries; PyOCDBackend records driver-acquire or generic custom-driver program-call and preserves an already-valid default-driver diagnostic. The outer backend error code/message remain stable. Worker admits this field only for `flash_elf`/`PROBE_PROGRAM_FAILED`; unrelated error admission is unchanged. Service/flash retain the established details path. PhysicalTargetFlashAdapter forwards only a validated programDiagnostic on its existing TEST_FLASH_FAILED error. Public wrappers must preserve the diagnostic through their existing common result path, with no surface-specific copies.

## Verification and limits

Reuse existing backend/worker/flash/physical-target/public workflow tests and injected fake drivers. Cover actual default FileProgrammer constructor and program failures, OS and PyOCD FlashFailure numeric facts, nested/cyclic cause, hostile text and invalid IPC, successful options/call counts, and one public failure path through Target. At least one test crosses the real Windows spawned worker with a fake backend; it must not access a probe. Do not rerun the release matrix or hardware acceptance.

Primary independently reviews the complete base-to-CodeHead diff in a clean worktree and verifies the changed public path with the existing tests. Software acceptance proves future evidence preservation, not this lost exception's root cause or physical recovery. A later deployment and single physical operation need their own authority and the standard test procedure.
