# STM32TK-1001 H2 Build-to-Flash Contract Correction Design

**Status:** Approved by the user on 2026-08-27 after presentation of the
consumer-only dual-format compatibility design.

**Module and phase:** STM32 Toolkit VS10-A,
`STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP`, bounded H2 product correction before
the next physical flash attempt.

**Ownership ledger:** accepted slice base
`8149273677716840406987e342da1ccbd62969d3`, tree
`a3089b5971ad0c33252118f25f19e730577bf418`, branch
`codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. The accepted product code
below the plan-only base is `c9aae325daab90b16f3f748fd80492b0c6f377e7`.
GPT-5.6-sol owns this specification, the implementation plan, complete-diff
review, and acceptance. One GPT-5.6-luna/max implementer owns product code and
tests. No actor accepts its own work. No remote action is authorized.

**Frozen local inputs:** campaign project
`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math` at
`cf273a18b4c757b4866793c94b25d5ceaad39925`; accepted runtime state SHA-256
`266dbb1986e6e4c5bed28caba601dac909dde9f2c2edc4abf1922b8f82f65da3`;
current build ID
`a05dc376406721d497b0af451951420a583113eb298dd50d26eeb3ebdbfb8d44`;
ELF SHA-256
`f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`;
probe ID `0001A0000000`.

## 1. Trigger and safety state

The user approved the existing guarded flash as the first attach and target
identity gate. Programming is allowed only after attachment resolves to the
project-selected STM32F429 target; an identity mismatch requires zero
programming.

Exactly one authorized public flash command was attempted. It returned
`FIRMWARE_BUILD_REQUIRED` before attach. Identity resolution, programming,
readback, reset, SVD read, Fault observation, Monitor observation, and the rest
of the P1c smoke sequence were not reached. The retained failure envelope is:

`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-svd-flash-20260827-0615-01.json`

Its SHA-256 is
`9c27844e5fe12f708b5273df26e40802c715913ec519d244fa4e52f32109516b`.
The stopped run therefore preserved the zero-programming safety boundary.

## 2. Confirmed product defect

The public build producer and public flash consumer use incompatible success
records:

- `build.runner.run_build()` publishes `status="success"`, `stage=""`,
  `code="OK"`, and five artifact objects containing only portable `path`
  fields;
- `probe.flash` currently accepts only `stage="complete"` and requires rich
  ELF/MAP artifact objects containing `kind`, `path`, `sha256`, and `size`;
- the build identity specification makes the last successful
  `build-result.json` replacement the freshness commit point, but it does not
  require the flash-only stage or rich artifact dialect;
- `context.py` already consumes the genuine public producer record by checking
  success, identity agreement, current Git/input facts, and exact disk hashes.

The build runner behavior dates from `af70b075f517a29650badb549460b91115696797`.
The incompatible flash consumer behavior dates from
`66b1c42ca3252ae277a0da8209975f24d0cf4ad7`. The physical attempt exposed an
existing cross-module product defect; it is not stale project output,
environment failure, or hardware failure.

## 3. Runnable scenarios

1. A caller completes a genuine public `arm-debug` build and passes its unchanged
   `build-result.json` and `firmware-identity.json` into the public flash path.
   The evidence is accepted only after all current identity, Git, input snapshot,
   ELF, MAP, and segment checks pass.
2. A failed, malformed, stale, forged, path-conflicting, or cross-dialect build
   record is rejected before target attach. No programming or target read occurs.
3. A valid current build reaches attach, but the connected part number does not
   match the exact project-selected debug target. The workflow returns
   `FIRMWARE_IDENTITY_MISMATCH`; attach is the only target event and programming
   remains zero.
4. A valid current build and matching target proceed in the existing order:
   validate evidence, attach, validate connected identity, program the exact
   identity-bound ELF, read back every load segment, revalidate disk evidence,
   then publish flash success.

## 4. Frozen evidence dialects

The flash consumer accepts exactly two bounded success dialects under schema
version 1:

### 4.1 Canonical public-build dialect

- `status` is exactly `success`, `stage` is exactly the empty string, and `code`
  is exactly `OK`;
- `artifacts` contains exactly five path-only objects, with no duplicate or extra
  object fields;
- their exact portable path set is the build log, build result, debug firmware
  identity, model-selected debug ELF, and corresponding debug MAP;
- absolute paths, escaping paths, wrong preset paths, duplicates, missing paths,
  additional paths, rich metadata, and mixed object shapes are rejected.

### 4.2 Accepted-base compatibility dialect

- `status` is exactly `success`, `stage` is exactly `complete`, and `code` is
  exactly `OK`;
- existing rich ELF/MAP artifact validation is retained byte-for-behavior: there
  must be exactly one `elf` and one `map` record with the accepted four fields,
  and their path/hash/size facts must match the authoritative identity and disk
  bytes.

The two dialects are not freely mixed. No other stage value, artifact dialect,
schema version, or inferred fallback is accepted. The consumer does not rewrite,
upgrade, normalize, or republish either input document.

## 5. Sources of truth and safety invariants

`firmware-identity.json`, after schema validation and independent build ID
recomputation, remains the firmware identity authority. Current Git evidence,
the current input snapshot, bounded regular contained ELF/MAP files, recomputed
disk hashes, validated ELF structure, and confined load segments independently
reconfirm that identity.

The canonical artifact path list is consistency evidence only. It never selects
the ELF, MAP, target, probe, or memory ranges and never substitutes for a hash.
The model and validated identity continue to select those values. Supporting the
canonical dialect therefore removes a false rejection without weakening the
existing programming gate.

The following ordering is unchanged and mandatory:

1. validate request authorization and current disk evidence;
2. compare caller-pinned build ID, ELF hash, and project debug target;
3. attach to the exact probe and requested target;
4. compare the resolved target identity;
5. only after that comparison succeeds, remove stale flash success and program;
6. read back every expected load-segment byte;
7. revalidate current disk evidence and publish success last.

## 6. Stable failures

- A non-success status, non-`OK` code, or unaccepted stage returns the existing
  `FIRMWARE_BUILD_REQUIRED` envelope with no target event.
- A malformed artifact container or object shape returns
  `FIRMWARE_EVIDENCE_INVALID` with build-result path and `rule="artifacts"`.
- A well-formed artifact record whose paths or rich facts disagree with the
  authoritative identity returns `FIRMWARE_IDENTITY_MISMATCH` with
  `field="artifacts"` and `rule="identity"`.
- Current Git/input/ELF/MAP drift retains the existing
  `FIRMWARE_INPUT_CHANGED` behavior.
- Caller build or ELF pins retain `FLASH_PLAN_CHANGED`.
- A connected-target mismatch retains `FIRMWARE_IDENTITY_MISMATCH` with
  `field="connectedTarget"` and `rule="identity"`; no program or read call is
  permitted.

No adjacent public error code, message, details object, authorization rule,
readback behavior, or success document changes as part of this correction.

## 7. Implementation boundary

The only permitted product-code file is:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.

The primary regression-test file is:

- `tools/stm32-toolkit/tests/test_flash.py`.

Test-only reuse of the existing deterministic public build fixture is allowed.
Any test seam for load segments must remain local to tests and must not alter the
default build-runner fixture or production ELF handling. Existing rich-dialect,
authorization, evidence-tamper, identity, ordering, readback, and atomic
publication tests must be retained.

No build runner, build identity schema, project schema, CLI, MCP, service,
backend, runtime, package, dependency, project source, generated project file,
or hardware implementation change is permitted.

## 8. TDD and verification

The RED proof must pass a genuine `run_build(BuildRequest(..., preset="arm-debug"))`
success document unchanged into the public flash consumer. At the accepted base
it must fail with `FIRMWARE_BUILD_REQUIRED` before attach. A manually constructed
build result is not sufficient RED evidence.

GREEN must prove:

- genuine public build output is accepted without rewriting evidence;
- the public-build artifact paths are exact and non-authoritative;
- matching identity preserves attach -> program -> read ordering;
- connected-target mismatch produces attach only and zero programming;
- failed, stale, forged, malformed, and path-conflicting evidence fails before
  attach;
- accepted-base rich artifact validation and its tamper rejection remain green.

Focused verification is limited to the flash tests, build-runner tests, and any
direct debug-read consumer regression made relevant by the shared loader. Use
CPython 3.12, `-p no:cacheprovider`, and one external run-owned basetemp. Run
`git diff --check` and inspect the complete accepted-base-to-code-head diff.
Preserve minimum failure evidence, then clean only exact run-owned disposable
artifacts under the repository cleanup rules.

## 9. Acceptance and continuation boundary

One Luna/max implementer returns separate RED and GREEN commits plus exact test,
status, diff, and cleanup evidence. Sol reviews the complete
`8149273677716840406987e342da1ccbd62969d3..code-head` diff from a clean isolated
worktree and is the only actor that may issue the product verdict.

Acceptance of this product correction does not itself authorize a second flash.
After acceptance, the local runtime must be updated through the existing pinned
source installation path and its doctor/inventory/state facts revalidated. Only
then may the H2 plan reconcile fresh pins and the authority for another guarded
hardware attempt.

No push, PR mutation, merge, close, tag, release, remote branch action, network
action, direct PyOCD/CubeProgrammer/Keil operation, new public tool, or VS10-B
work is included.
