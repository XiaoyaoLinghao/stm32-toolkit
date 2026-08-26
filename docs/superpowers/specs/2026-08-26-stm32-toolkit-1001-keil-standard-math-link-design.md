# STM32 Toolkit 1001 Keil standard-math link design

Date: 2026-08-26
Status: approved by delegated user authority on 2026-08-26
Specification owner and acceptor: GPT-5.6-sol primary
Implementation owner: the existing single GPT-5.6-luna/max VS10-A owner
Independent reviewer: GPT-5.6-sol primary
Accepted base: `29d063a2b922dd636e0865ae3c0c6a825592dfb3`
Accepted-base tree: `21e90bb5e7b904c284b389351fcf7ac930586aab`
Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
Remote, release, and hardware authority: none

## 1. Problem and evidence

VS10-A's corrected campaign project used the accepted 0.9 runtime, explicit
project root, guarded Keil conversion, and guarded managed configuration. The
first public `arm-debug` build compiled all 54 objects, then failed at the GNU
link with unresolved `cosf`, `sinf`, and `atan2f`. The link command contained
the correct `fpv4-sp-d16/hard` pair but no GNU math library.

The historical Keil project has no explicit math-library input. ARMCC's
standard runtime resolves the same functions automatically, as shown by the
historical MAP. STM32 Toolkit's generic Schema-3 build model exposes compile
options but no bounded way to request equivalent standard-math linkage. The
native CubeMX path already emits `target_link_libraries(<target> PRIVATE m)`;
the generic path intentionally does not.

The immutable failure evidence is:

- campaign evidence
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\task-4a-build-1-failure.json`,
  SHA-256
  `c138c4a27f7df231dc7bc83a074c7dbb78dbeaf6e7892e38279ed8e6b0c50f2b`;
- public build result SHA-256
  `ca2fe3c7897869b1763db1f44b2a86aa90fa45689d6a2dc6550f8b942091e02c`;
  and
- public build log SHA-256
  `c00fe7ead47762179c3a372cd61ec255f5b9b59b08ea908374220680d84b88f5`.

This slice closes that one public capability gap. It does not add a general
linker escape hatch.

## 2. Runnable user scenarios

### Scenario A: existing generic project remains byte-compatible

Given a valid Schema-3 generic project whose `build` object omits
`linkStandardMath`, public model loading succeeds with the effective value
`false`. Public configuration produces the exact accepted-base generic CMake
bytes: `-nostartfiles`, the generic `linker/stm32tk.ld`, no nano/nosys specs,
and no `target_link_libraries` line.

An explicit JSON value `false` has the same generated behavior. Toolkit does
not rewrite an existing manifest merely to add the false value.

### Scenario B: guarded Keil migration preserves standard-runtime math

Given a Keil inspection for which the existing planner produces a Schema-3
proposal, that proposal contains exactly:

```json
"linkStandardMath": true
```

inside `build`. This is a deterministic Keil standard-runtime compatibility
mapping; it is not inferred by scanning source function names. The field is
part of the manifest bytes, guarded conversion plan identity, configuration
model hash, and downstream build input snapshot.

Only an inspection already free of accepted-base blockers can be applied.
Current accepted-base ARMCC behavior remains the supported compiler path;
ARMCLANG remains blocked by `MIGRATION_COMPILER_UNSUPPORTED` with its exact
accepted evidence and zero-write behavior.

Public generic configuration then emits exactly one:

```cmake
target_link_libraries(<target> PRIVATE m)
```

after `target_link_options`. A real public build of the frozen VS10-A project
resolves `cosf`, `sinf`, and `atan2f` without changing project source.

### Scenario C: native CubeMX math linkage remains unchanged and unique

Given a native CubeMX project with `generation.nativeLinkerScript`, public
configuration continues to emit the accepted compiler start files,
`nano.specs`, `nosys.specs`, native linker ownership, and exactly one
`target_link_libraries(<target> PRIVATE m)` line. The generated CMake output is
identical whether `build.linkStandardMath` is absent, false, or true; the new
selector must not duplicate `m` or alter native ownership.

### Scenario D: malformed or expansive input fails closed

`build.linkStandardMath` accepts only the JSON booleans `true` and `false`.
Strings, numbers, null, arrays, and objects fail public manifest validation as:

```text
code=PROJECT_SCHEMA_INVALID
field=build.linkStandardMath
rule=type
```

There is no public field for arbitrary library names, raw link flags, paths,
response files, CMake fragments, shell text, or environment injection.

## 3. Frozen public model

The root and packaged Schema-3 files gain one optional property:

```json
"linkStandardMath": {"type": "boolean"}
```

It is optional for backward compatibility and is not added to the Schema-3
`required` array. Schema versions 1 and 2 remain byte-for-byte unchanged.

`BuildSpec` gains:

```python
link_standard_math: bool = False
```

The field is appended after the existing non-default fields to preserve direct
constructor compatibility. The loader maps a missing property to `False` and
otherwise uses the schema-validated boolean without truthiness coercion. No
second model or serializer is added.

Keil `_manifest_proposal()` writes `"linkStandardMath": True` in every
supported Keil-migration `build` object. The planner already owns the single
deterministic Schema-3 proposal, so no new detector, parser, or source scanner
is introduced.

The configuration renderer receives one boolean context member:

```python
"link_standard_math": model.build.link_standard_math
```

The CMake template uses one condition:

```jinja2
{% if native_linker_script or link_standard_math %}
target_link_libraries({{ target_name }} PRIVATE m)
{% endif %}
```

This preserves one source of truth and ensures native and generic linkage can
never emit two math-library directives.

The existing canonical generation-model payload adds one member under
`build`:

```python
"link_standard_math": model.build.link_standard_math
```

This keeps guarded configuration plan identity complete. It does not create a
second identity or state format.

## 4. Identity, lifecycle, and ownership

The field participates in existing identities because:

1. guarded conversion hashes the complete proposed manifest and its exact
   input set;
2. configuration includes the field in its existing canonical model payload,
   hashes `.stm32-project.json`, and hashes generated target bytes; and
3. public build snapshots include the project manifest and managed
   configuration inputs.

No new state file, manifest, controller, provider, backend, runtime, MCP tool,
Skill, or environment channel is created.

Root and packaged Schema-3 resources remain byte-identical to one another.
Root and packaged CMake templates remain byte-identical to one another. The
managed-file manifest continues to own the generated CMake bytes and needs no
schema change.

## 5. Error and compatibility semantics

- Missing or explicit false is valid and produces accepted-base generic
  behavior.
- Explicit true is valid and adds only standard GNU math linkage in generic
  mode.
- Native mode always has exactly one standard-math linkage, as before.
- Invalid types fail at the existing schema boundary before configuration or
  build writes.
- Existing Keil inspection blocker codes, complete blocker collections,
  evidence values, guarded-apply refusal, and zero-write behavior remain
  unchanged.
- Existing `MIGRATION_COMPILER_UNSUPPORTED`, FPU/ABI normalization, and
  `MIGRATION_MANIFEST_EXISTS` behavior remain unchanged.
- Existing generic projects are not silently rewritten or switched to native
  mode.

## 6. TDD and verification

The single Luna/max implementation owner must follow RED/GREEN:

1. add model/schema tests for missing, true, false, and invalid types;
2. add generation tests proving generic true emits one `m`, generic missing or
   false remains accepted-base compatible, and native has one `m` for all
   selector values;
3. add migration tests proving supported Keil proposals carry true while the
   complete blocker/evidence and non-write oracles remain unchanged;
4. run the focused model, Schema-3, generation, migration, and packaged-resource
   tests; and
5. commit product/tests first, then a separate implementation report commit.

After independent complete-diff review, Sol builds a new reproducible 0.9 local
candidate/runtime from the accepted code head, preserving the old runtime as a
recoverable retired generation. The campaign correction restarts from exact
project parent `718c37ed5d381f01680e64abe8c3810d62723b2a` on a new protected local
branch, preserving `d701c714...`, `ba528f6b...`, and `8417f024...` as immutable
superseded evidence. It reruns public inspect, two conversion dry-runs, guarded
conversion apply, guarded configuration, and two public builds without source
or configuration changes.

The two builds must have identical input snapshot, build ID, ELF, MAP, HEX,
entry/vector/reset facts, and must have no unresolved strong symbols. H1 then
continues with the already frozen memory, symbol, DWARF `testtime`, D4/LED1
source-semantics, top-SRAM, stale-input, mailbox-absence, reporting, and cleanup
checks. Hardware remains forbidden until independent H1 acceptance.

## 7. Non-goals

- No arbitrary `linkLibraries`, `linkOptions`, raw `-l`/`-Wl` tokens, library
  paths, response files, CMake injection, or environment flags.
- No source scanning for `sin`, `cos`, `atan`, or other function names.
- No unconditional change to generic projects that omit the selector.
- No change to native linker ownership or generic linker reconstruction.
- No source-level math shim, approximation, vendor-code edit, or manual managed
  CMake/manifest edit.
- No new Agent-specific behavior, runtime family, MCP registration, controller,
  provider, backend, Python range, CI, or collaboration automation.
- No full release matrix, unrelated suite, hardware, network, push, PR, merge,
  tag, release, or remote branch mutation.

## 8. Acceptance

This slice is accepted only when all of the following are true:

- public schema/model behavior matches Scenarios A and D;
- guarded Keil conversion and generic/native generation match Scenarios B and
  C;
- accepted generic and native outputs are unchanged when the selector does not
  request new behavior;
- focused affected tests pass with exact counts and no deleted assertions;
- the complete accepted-base-to-code-head diff has no unresolved product,
  security, compatibility, or scope finding;
- a new candidate/runtime is reproducible and uniquely active;
- the restarted campaign produces two reproducible successful public builds;
- complete pre-H1 evidence passes and Sol issues `H1 ACCEPTED`;
- exact disposable artifacts are cleaned or recorded as
  `ENVIRONMENT/cleanup-policy` without bypass; and
- Toolkit and project final tracked worktrees are clean, project remote count is
  zero, and no hardware or remote operation occurred.

After H1 acceptance, stop at the hardware gate. Do not automatically flash,
reset, attach a Probe, or enter later VS10 work.
