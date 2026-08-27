# STM32TK-1001 Production SVD Compatibility Correction Design

**Status:** Approved under the user's delegated best-choice authority after the
2026-08-27 connected-board operation exposed a public H1/H2 blocker.

**Module and phase:** VS10-A `STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP`,
bounded product-compatibility correction while H1 is reopened and H2 is closed.

**Accepted product base:**
`0cdd142f80421c6aea59e81e963936779b05f00f`. The current Toolkit branch also
contains only the later frozen design/plan documentation at
`4d24842e127f5d6a1779dce4e6368969b305ddb4`. Sol owns this design, the plan,
complete-diff review, and acceptance. One Luna/max implementer owns all product
code and implementation tests. No remote action is authorized.

**Project state:** local-only project head
`9aae7ffd860405fadb7ac5f6278bcbb93add8d16`, zero remotes, with only the
uncommitted expected `.stm32-project.json` debug object and exact copied SVD.
Those project changes remain uncommitted until this product slice is accepted.

## 1. Root cause and supersession boundary

The initial debug-binding correction design remains valid for explicit project
ownership and provenance, but its no-product-code assumption is superseded by
three independently reproduced production-contract failures:

1. The pinned CubeCLT 1.22.0 `STM32F429.svd` contains the CMSIS-SVD-valid decimal
   value `00000010`. `_number()` uses `int(value, 0)`, which rejects that value and
   returns `SVD_XML_INVALID` before selection.
2. The official SVD document names its device `STM32F429`, while the project and
   target pack identify the exact variant `STM32F429ZGTx`. The cached Keil PDSC
   explicitly maps that exact variant to `CMSIS/SVD/STM32F429.svd`, but the current
   selector accepts only document-name equality and deliberately rejects prefix
   guessing.
3. `DebugFirmwareBinding.memory_regions` comes only from linker memory. The
   production project therefore has FLASH, SRAM1, and CCMRAM but no peripheral
   address authority. The selector validates every SVD register against those
   linker regions, so GPIOE at `0x40021000` can never be selected.

The public failed check is retained at
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\task-1-model-svd-check.json`,
SHA-256
`70c7d63f7b132789bc72f0a4a60046c8520721262938a8d45d729fcce2018fbf`.
It is `PRODUCT/Toolkit contract` evidence, not hardware PASS. No backend, attach,
reset, target read, or flash occurred.

## 2. Runnable scenarios

1. A legacy schema-v3 project without the new debug fields retains its current
   exact SVD-device equality and linker-memory behavior byte-for-byte.
2. A schema-v3 project explicitly binds exact firmware device
   `STM32F429ZGTx`, exact debug target `stm32f429zgtx`, exact SVD document device
   `STM32F429`, a project-contained SVD path, and bounded read-only observation
   regions. The official pinned SVD parses and selects without family guessing.
3. A public register-read or Monitor observation derives every identity and
   address authority from that project model. `GPIOE.ODR` resolves to
   `0x40021014` and exposes field `ODR4` at bit 4; no caller can supply a target,
   SVD, region, raw address, or size.
4. Malformed numbers, unbound document names, missing/overlapping/out-of-range
   regions, SVD register escapes, changed SVD bytes, and firmware target drift
   fail closed with stable public error codes and no target read.

## 3. Frozen schema-v3 model

The existing `debug` object gains two optional schema-v3-only fields:

```json
{
  "backend": "pyocd",
  "target": "stm32f429zgtx",
  "svd": "svd/STM32F429.svd",
  "svdDevice": "STM32F429",
  "readableRegions": [
    {"name": "PERIPH-40000", "origin": 1073741824, "length": 32768}
  ]
}
```

`svdDevice` is the exact, case-sensitive `<device><name>` value expected inside
the selected SVD. It is not inferred from, normalized against, or substituted for
`target.device`; the selection binds both facts.

`readableRegions` is a tuple of 1 to 64 debug-only read authorities. Each item
contains exactly `name`, `origin`, and `length`. Names are non-empty, NFC,
bounded identifiers and unique. Origins and lengths are integers, exclude booleans,
are positive/in-range, do not overflow 32-bit address space, and regions do not
overlap. Their access is always `r--`; the manifest cannot request write or execute
permission. These regions are never rendered into linker scripts, CMake, build
memory comparisons, or backend write policy.

Backward compatibility is explicit:

- when both new fields are absent, `svdDevice` defaults to `target.device` and SVD
  readable regions default to the existing binding memory regions;
- when either new field is present, `debug.svd`, `svdDevice`, and a non-empty
  `readableRegions` tuple are all required;
- schema 1 and 2 continue to reject both new fields as additional properties;
- migration and native-project serializers do not invent the fields.

The generation model hash includes the new values, so public configure detects
drift. They do not change C/C++/ASM/link inputs or firmware bytes.

## 4. SVD parsing, selection, and provenance

`_number()` accepts only the already supported unsigned hexadecimal form with
`0x`/`0X`, plus unsigned decimal with optional leading `+` and any number of
leading zeros. Decimal remains base 10; there is no octal interpretation. Length
and range caps stay unchanged. Negative, empty, whitespace-internal, suffix,
binary, `#`, floating, and malformed forms remain rejected unless a later
separately specified compatibility need proves them necessary.

`select_svd()` continues to require one explicit project-contained candidate. It
accepts an optional explicit `svd_device`; absent means the historical exact target
device. It matches the SVD root name exactly against that value and records both:

- exact firmware target device;
- exact SVD document device;
- project-relative path, file size, SHA-256, canonical identity; and
- exact debug-readable region tuple.

Revalidation checks all of those facts. No family prefix, casefold, ambient pack,
network, path search, or alias table is added. Every parsed register must still fit
wholly in one explicit debug-readable region. Access/readAction rules remain
unchanged.

`DebugFirmwareBinding` carries a separate immutable
`svd_readable_regions` tuple. DWARF and firmware reads continue to use linker
`memory_regions`; SVD register selection/read uses only the new tuple when present.
This preserves the build/debug trust boundary.

## 5. Public error semantics

- invalid schema or coupled fields: `PROJECT_SCHEMA_INVALID` before backend start;
- absent exact SVD configuration: `SVD_SELECTION_REQUIRED` before backend start;
- malformed official/source XML number: `SVD_XML_INVALID`;
- exact SVD document mismatch or zero/multiple matches: `SVD_SELECTION_REQUIRED`;
- any register outside declared regions: `SVD_ADDRESS_OUT_OF_RANGE`;
- changed target, regions, path, file identity, or digest:
  `SVD_PROVENANCE_MISMATCH` or `SVD_INPUT_CHANGED` as currently applicable.

`SvdError` is added to the hardware workflow's stable public exception boundary so
its existing bounded code/message/details survive sanitization instead of becoming
`HARDWARE_INTERNAL_ERROR`. Unknown exceptions remain internal and redacted.

## 6. Non-goals

- no Toolkit inference of a family name, target, SVD, region, or address;
- no custom/rewritten vendor SVD and no peripheral region in linker memory;
- no runtime PDSC/pack search, download, dependency, or second source of truth;
- no caller-supplied raw target/SVD/region/address/size and no CLI/MCP signature
  change;
- no register write, halt, resume, reset, breakpoint, direct PyOCD call, second
  backend/runtime/controller/provider, new tool, Skill, CI, or Agent-specific logic;
- no change to migration planner output, build flags, standard-math/FPU/ABI behavior,
  Python support, version string, README inventory, or release publication.

## 7. Acceptance gates

- TDD RED commits precede every product implementation commit and fail for the
  intended missing behavior, not fixtures or typos.
- Root and packaged schema bytes remain identical; schema-v2 compatibility and
  explicit-schema behavior remain accepted-base compatible.
- Existing exact selection, family/partial rejection, path containment, DTD/entity,
  range, side-effect, and provenance tests remain; new explicit document-device
  behavior does not weaken them.
- Focused tests cover project model, generation hash/non-build bytes, SVD parser,
  debug binding/read, hardware workflow, Monitor observation, CLI/MCP parity, and
  stable errors.
- One offline external-input integration check uses the exact copied
  `STM32F429.svd` SHA-256
  `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`,
  selects 1,536 registers, and proves `GPIOE.ODR`/`ODR4` without backend import or
  hardware access.
- The implementer returns a clean code/tests head and a separate report commit.
  Sol reviews the complete `0cdd142f...`-to-code-head diff in a clean isolated
  worktree and independently runs only the risk-triggered checks.
- Only after `ACCEPTED` may a new offline candidate runtime be built, source-bound,
  installed into the campaign, and used to resume the project correction and H1.
  H2 remains closed until the later project H1 verdict.

No push, PR mutation, merge, tag, release, remote branch operation, network, or
hardware action is authorized by this design.
