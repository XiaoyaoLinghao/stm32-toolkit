# STM32TK-1001 Probe Inventory and Selection Compatibility Design

**Status:** FROZEN AND USER-APPROVED 2026-09-02

**Module / phase:** STM32 Toolkit 1.0 VS10-A, H2 entry correction

**Full accepted base:** `74ee5f4c7872af1bb612c9068af36319457e087b`

**Accepted product head before this correction:** `568f5028e279a393094c95f44403a4d03b28dcfd`

**Specification owner and independent reviewer:** GPT-5.6-sol primary

**Implementation owner:** exactly one GPT-5.6-luna agent at reasoning effort `max`

**Active branch:** `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

**Remote authority:** none; no push, PR mutation, merge, tag, release, closure, or remote branch deletion

**Hardware authority in this correction:** passive enumeration only after product acceptance; no attach, reset, read, or programming

## 1. Problem and evidence

VS10-A originally froze the observed CMSIS-DAP selector `0001A0000000`. The currently connected previous-generation reference probe is enumerated by Windows and PyOCD as vendor `ATK`, product `ATK-HS-V3-CMSIS-DAP`, and raw PyOCD `unique_id` `ATK 20210914`.

PyOCD 0.45.1 lists that probe successfully. Toolkit fails before target attach because it requires every public `probeId` to use the portable internal identifier grammar `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`. Passing arbitrary hardware names through all endpoint, lease, handoff, Flash, Monitor, and evidence boundaries would weaken or duplicate those already accepted internal gates.

The correction therefore adds one thin inventory/selection adapter inside the existing PyOCD backend. Hardware-provided identity remains opaque display data. The adapter emits one portable public selector that all existing downstream contracts can continue to use unchanged.

## 2. User scenarios

### Scenario P1: list arbitrary supported probes without touching a target

The existing CLI/MCP `probe list` operation asks the one Probe Service / PyOCD backend for a fresh inventory. Each descriptor contains:

- `probeId`: the portable selector used by all existing follow-up workflows;
- `hardwareId`: the exact raw PyOCD `unique_id`, for display and confirmation only;
- `probeFingerprint`: lowercase SHA-256 of `hardwareId.encode("utf-8")`;
- bounded `vendor`, `product`, and optional `boardName` display facts.

If `hardwareId` already satisfies the portable identifier grammar and does not start with the reserved `pyocd:` prefix, `probeId` remains byte-for-byte equal to `hardwareId`. This preserves selectors such as `0001A0000000` and `probe-a`.

Otherwise `probeId` is `pyocd:` followed by the full 64-character `probeFingerprint`. For the current probe:

```text
probeId:          pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c
hardwareId:       ATK 20210914
probeFingerprint: 91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c
vendor:           ATK
product:          ATK-HS-V3-CMSIS-DAP
```

Listing performs no attach, reset, target read, lease acquisition, or programming.

### Scenario P2: explicitly select, then freshly confirm one exact probe

The caller chooses the exact public `probeId` returned by P1. Immediately before session creation, the existing backend freshly enumerates raw PyOCD probes, validates each raw identity, recomputes its public selector, and requires exactly one case-sensitive match with the caller value.

No match returns existing `PROBE_NOT_FOUND`. Multiple matches return existing `PROBE_SELECTION_AMBIGUOUS`. Both create no session. List indexes, substring matching, case folding, Unicode normalization, globbing, regex matching, and implicit first-probe selection are forbidden.

A portable legacy selector continues to select the exact equal raw hardware ID. A generated `pyocd:<sha256>` selector is resolved only by recomputing candidate selectors from the fresh raw inventory; it is never decoded, cached, or used as a PyOCD partial-ID query.

If the raw hardware ID changes, the generated selector changes and the stale selector fails. The caller must list and select again. Vendor/product display changes do not affect a portable raw selector or a generated selector derived from an unchanged raw hardware ID.

### Scenario P3: keep hostile hardware names inert

A raw `hardwareId` is admitted only when it is a non-empty Python `str`, its strict UTF-8 encoding is at most 512 bytes, and every character is printable according to `str.isprintable()`. It is not trimmed, case-folded, or normalized. Empty, non-string, over-limit, non-UTF-8-encodable, NUL, newline, tab, terminal escape, bidirectional format control, surrogate, and other non-printable/control values fail closed as invalid hardware descriptors.

Printable punctuation, spaces, slashes, backslashes, quotes, brackets, wildcard characters, and Unicode text are allowed in `hardwareId` because they remain structured display data. They are never interpolated into a shell command, path, glob, regex, URL, Python source, endpoint identity, lease record, handoff state, Flash request, Monitor binding, or target evidence.

Only the portable `probeId` crosses those downstream boundaries. Existing path and evidence code continues to hash that public selector exactly as before.

### Scenario P4: preserve accepted downstream behavior

Existing portable selectors retain their exact public value and selection behavior. Existing target, board, MCU, workspace, session, lease, handoff, transport, schema, Flash, Monitor, target-test, and authorization identifier grammars remain byte-for-byte unchanged.

Existing busy-owner, target-identity, guarded-flash/readback, SVD, v1/v2, error-redaction, CLI/MCP tool names, and 48-tool inventory behavior remains unchanged. The only public response expansion is additive `hardwareId` and `probeFingerprint` fields in each probe-list descriptor.

## 3. Frozen adapter contract

### 3.1 One source of truth

One small module inside the existing `stm32_toolkit.probe` package owns:

```python
def valid_hardware_probe_id(value: object) -> bool: ...
def probe_fingerprint(hardware_id: str) -> str: ...
def public_probe_selector(hardware_id: str) -> str: ...
```

`probe_fingerprint()` returns `sha256(hardware_id.encode("utf-8")).hexdigest()`.

`public_probe_selector()` returns the raw identity only when it matches the existing portable grammar and does not start with `pyocd:`. All other admitted raw identities return `f"pyocd:{probe_fingerprint(hardware_id)}"`.

The reserved prefix rule prevents a raw hardware ID from being confused with a generated selector. Two candidate probes that produce the same public selector are ambiguous and cannot attach, including the theoretical SHA-256 collision case.

The generic internal identifier grammar remains authoritative outside this adapter and is not broadened.

### 3.2 Descriptor and structured output

`ProbeDescriptor` retains `probe_id`, `vendor`, `product`, and `board_name` and gains immutable `hardware_id` and `probe_fingerprint` facts. Trusted legacy construction may default `hardware_id` to `probe_id` and derive the fingerprint, but every public descriptor contains exactly:

```json
{
  "probeId": "<portable public selector>",
  "hardwareId": "<exact raw PyOCD unique_id>",
  "probeFingerprint": "<64 lowercase hexadecimal SHA-256 of hardwareId>",
  "vendor": "<bounded display text>",
  "product": "<bounded display text>",
  "boardName": null
}
```

CLI JSON and MCP return the same values after normal JSON serialization. Existing command/tool names do not change. A human renderer may abbreviate the fingerprint for display only when structured output retains the full value; an abbreviated fingerprint is never accepted as a selector.

### 3.3 Backend resolution

`PyOCDBackend.list_probes()` validates raw `unique_id`, computes the public selector and fingerprint, and returns descriptors sorted deterministically by public selector, then raw hardware ID.

`PyOCDBackend.open_attach(probe_id, target)` continues to require a portable caller `probe_id`. Its private selection step freshly enumerates candidates, computes the same public selector for each, and accepts one exact match. The chosen PyOCD probe object, not a raw or partial string query, is passed to session creation.

Attachment evidence returns the caller's public selector. Existing internal `probe_serial_hash`, endpoint, lease, Flash, handoff, Monitor, and target evidence remains derived from that public selector, so those modules require no grammar or storage change.

### 3.4 Worker, service, and client boundaries

The existing worker serializer carries all immutable descriptor fields. The Probe Service emits `ProbeDescriptor.to_dict()`. `ProbeClient.list_probes()` treats the response as closed data: it requires exactly the six public keys, validates the public selector with the existing grammar, validates the raw hardware ID with the adapter rule, requires the fingerprint to equal the raw hardware ID hash, bounds display fields, and rejects malformed or mismatched success responses with existing `PROBE_RESPONSE_INVALID` behavior.

No raw hardware ID is written to endpoint or lease records. No persistent raw-to-selector mapping or inventory cache is added.

## 4. Error semantics

- Invalid caller selector: existing `PROBE_SELECTION_REQUIRED`; no enumeration/session.
- Invalid raw hardware descriptor: existing `PROBE_DESCRIPTOR_INVALID`; no session and no raw exception details.
- Underlying enumeration exception: existing `PROBE_ENUMERATION_FAILED`; stable redacted message.
- No exact fresh selector match: existing `PROBE_NOT_FOUND`; no session.
- More than one exact selector match: existing `PROBE_SELECTION_AMBIGUOUS`; no session.
- Malformed service descriptor: existing `PROBE_RESPONSE_INVALID` in the client.

No retry, fallback, auto-selection, second selector syntax, backend, service, controller, provider, or persistent registry is introduced.

## 5. Required TDD evidence

The sole Luna/max implementer must demonstrate RED before product changes and GREEN afterward for:

1. `ATK 20210914` mapping to the exact selector and fingerprint shown in P1.
2. Existing `probe-a` and `0001A0000000` retaining their exact public selectors.
3. A raw ID beginning with reserved `pyocd:` mapping to a generated selector rather than passing through.
4. Printable punctuation and Unicode raw IDs listing without interpretation.
5. Empty, over-limit, non-string, newline, tab, NUL, escape, bidi-control, and surrogate raw IDs failing closed with zero session creation.
6. Exact fresh selection for both legacy and generated selectors; partial, case-changed, stale, missing, duplicate, and colliding selectors create no session.
7. Worker serialization, service response, and client parsing preserving all six descriptor facts and rejecting unknown, missing, malformed, or fingerprint-mismatched data.
8. Public CLI/MCP list parity, unchanged 48-tool inventory, and no attach call during listing.
9. Existing endpoint, lease, handoff, Flash, Monitor, target-test, attach-option, error-redaction, and cleanup regressions remaining green without product changes in those modules.

Tests must exercise production mapping, serializers, parsers, selection, and public composition. Source-text assertions and mocks that bypass the relevant production boundary are insufficient.

## 6. Proportionate verification

Implementation verification is limited to the new adapter, backend/descriptor/client/worker/service, public list composition, and directly affected CLI/MCP hardware tests, plus `git diff --check`. The affected downstream regression tests run only to prove that their product bytes remain unchanged while portable selectors continue to pass.

Tests use fake PyOCD probes, CPython 3.12.10, pytest 8.4.2, `-p no:cacheprovider`, explicit source `PYTHONPATH`, and an external run-owned basetemp. No hardware, packaging rebuild, full release matrix, or unrelated VS10-A tests run without a new risk trigger.

After independent Sol complete-diff `ACCEPTED`, the runtime may be rebuilt from accepted code. The first physical check is passive public `probe list` only. Attach, target read, guarded flash, H2, and later campaign actions retain their separate existing authority.

## 7. Allowed implementation scope

Expected product files are limited to:

- one small selector adapter inside `tools/stm32-toolkit/src/stm32_toolkit/probe/`;
- `probe/backend.py`;
- `probe/pyocd_backend.py`;
- `probe/client.py`.

`probe/worker.py`, `probe/service.py`, and public hardware composition should consume the expanded descriptor without product edits. Tests and one tracked implementation report may change in their established locations. If production changes are required in worker, service, hardware workflows, Flash, handoff, lease, Monitor, target testing, schemas, CLI/MCP registration, or any other module, implementation stops and returns to Sol design review.

The implementation report is a separate report-only commit after code/tests. The Sol review report is owned only by the independent Sol reviewer.

## 8. Non-goals

- Do not special-case ATK, CMSIS-DAP, J-Link, USB VID/PID, or any vendor/model.
- Do not broaden existing downstream identifier grammars.
- Do not expose raw `hardwareId` as an attach, lease, Flash, handoff, Monitor, or target selector.
- Do not auto-select the first/only probe or accept list indexes, short fingerprints, substrings, or case-insensitive matches.
- Do not add a vendor allowlist, VS Code dependency, persistent mapping, second Probe backend/runtime/MCP registration/controller/provider, CI, collaboration automation, Python version, MCU family, transport, or protocol.
- Do not change SWD/JTAG, frequency, reset, attach, read, programming, guarded-flash order, firmware, golden project, campaign project, target memory, remote branch, PR, tag, or release.

## 9. Acceptance boundary

This correction is product-acceptable only when the exact `74ee5f4c7872af1bb612c9068af36319457e087b`-to-code-head diff has one Luna/max implementation owner, all focused tests pass, run-owned artifacts are reconciled, downstream product bytes remain unchanged, and an independent Sol reviewer issues `ACCEPTED`.

Acceptance means only that arbitrary bounded opaque PyOCD identities can be represented by portable public selectors, listed with confirmation data, and freshly resolved through the existing backend. It is not physical attach, target identity, reference-hardware compatibility, guarded-flash, H2, VS10-A, release, or remote acceptance.
