# Migration options and diagnostics

These are the currently accepted Keil migration inputs. Use the exact values the bound
server's actual input schema exposes. Keep every reviewed selection identical for
`stm32_keil_preflight`, the `stm32_keil_convert` PLAN call and the authorized APPLY:
omission, shortening or changing a selection is a different reviewed request. A change
either leaves a technical blocker, which fails planning with `DELIVERY_BLOCKED` before a
plan comparison, or produces a different plan and fails APPLY with `PLAN_CHANGED`. Do not
promise one precedence without reading the actual result. No option is auto-selected and
no blocker is auto-fixable.

## CMSIS startup generation

- MCP `startupStrategy: "generate-cmsis-gcc"`; CLI `--startup-strategy generate-cmsis-gcc`.
  Omit it to retain the existing arbitrary-assembly blockers.
- MCP `startupSource`; CLI `--startup-source`: the exact project-relative included ARMCC
  `.s` path using `/`. It is required when more than one included non-empty assembly source
  exists; otherwise preflight returns `MIGRATION_STARTUP_SELECTION_REQUIRED` with
  `details.candidates`.
- Supported input is a conventional ST/CMSIS Cortex-M3/M4/M7 ARMCC5 startup. The helper
  normalizes it and emits `Startup/stm32tk_startup_gcc.S`; the original ARMCC startup is
  never edited or deleted. An existing different target returns
  `MIGRATION_STARTUP_TARGET_COLLISION`, never an overwrite.
- Review `analysis.startup`: source path/hash, ordered vectors and reserved slots,
  stack/heap bytes, reset pattern, generated path/digest, warnings and diagnostics.
  Unknown instructions, custom reset/handler code, multiple vector tables, vector
  expressions, unsupported cores/layouts and undeclared handlers remain blockers.
- The generated runtime is not ARMCC, ABI or Microlib behavioral equivalence.

## Explicit memory layout

- MCP `memoryLayout` is a real object (`dict[str, str]`), never a JSON string. CLI
  `--memory-layout` takes one JSON object string.
- Exactly `flash`, `data`, `bss`, `heap`, `stack`, each naming an existing region from
  `data.analysis.memoryLayout.candidates`. Flash must be readable, executable and
  non-writable; the other roles must be readable and writable.
- `status=implicit` needs no option: exactly one non-writable executable Flash and one
  readable/writable RAM were resolved. `status=requires-selection` accompanies
  `MEMORY_LAYOUT_REQUIRED`; show the actual candidates and ask the user.
- Never infer CCM, DMA accessibility or external RAM. An all-main-RAM mapping is valid
  and leaves other regions intentionally unused. A native linker-script project keeps its
  own layout and cannot also declare `memoryLayout`.
- Invalid MCP values can be rejected by the framework before Toolkit runs; only
  schema-valid objects reach the structured `MEMORY_LAYOUT_INVALID` field/rule/remediation.
  CLI duplicate keys, malformed JSON and missing/unknown/non-string/empty roles return the
  same Toolkit error; a repeated CLI option is a parser error.

## External RAM

- MCP `extraRegions` is a real array of objects; CLI `--extra-regions` is one JSON array.
- Each entry has exactly `name`, `origin`, `length`, `attributes`. Only `rw-`/`rwx`
  writable RAM is accepted; names are 1-64 character ASCII linker identifiers; origin and
  length are exact non-empty integer ranges; at most 32 non-overlapping entries that do not
  overlap the declared base.
- Extra RAM adds RAM candidates only, never Flash. Managed `.data`/`.bss`/`.heap`/`.stack`
  are not placed there implicitly; an explicit `memoryLayout` must name the region.
- Never guess a capacity from a device, board or address. Review
  `data.analysis.extraRegions` in preflight, `data.options.extraRegions` in the PLAN and
  the conversion report's `extraRegions`.
- A fixed address outside every declared region reports
  `MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY` with `needs-user-input` and
  `requiredInputs=["extraRegions"]`. Fixed sections remain `NOLOAD` and are not promised
  initialized; the owner must initialize external memory before access.

## Explicit WFI normal-return intent

This is a requested source behavior, not a binary-equivalence claim. It is never selected
automatically and has no Keil disassembly or AXF prerequisite.

- MCP `wfiReturns` on `stm32_keil_preflight` and `stm32_keil_convert`: a real JSON array of
  exactly `{path, function}` objects with string values. `path` is an exact portable
  project-relative C source (`/`, contained, ending `.c`); `function` is an ASCII C
  identifier of at most 128 characters. At most 128 selections; duplicate, unknown-key,
  wrong-type, escaping, absolute, non-C or overlong values fail with
  `WFI_RETURNS_INVALID` before effects.
- CLI `--wfi-return PATH:FUNCTION`, repeatable on `keil preflight` and `keil convert`. The
  last colon separates path and function, so a drive path stays intact and is then refused
  as non-portable rather than silently made relative. Malformed syntax returns
  `WFI_RETURNS_INVALID` with `field=wfiReturns`, `rule=syntax` and an example.
- The same selection must be used for preflight, PLAN and APPLY. A nonempty selection is
  bound into plan identity and source-change evidence; omitting or changing it is a
  different request.
- Only a plain file-scope, zero-argument `__asm void name(void)` or `name()` whose body is
  exactly one WFI, optionally with a trailing semicolon and lexical comments, and with no
  explicit return, is eligible. Reject storage/prefix tokens, macro/directive ambiguity,
  multiple definitions, nested bodies, and any extra instruction or argument.
- The selected wrapper becomes ordinary non-naked C executing
  `__asm volatile ("wfi" ::: "memory");` and returning normally. Preserve its name,
  prototype, comment content, BOM/newline convention and adjacent functions. The patch
  carries rule `ARMCC_WFI_RETURN_INTENT` in `data.sourcePatches[]`; preflight exposes
  `analysis.wfiReturns` and `analysis.sourceChanges`.
- A wrapper with an explicit `BX LR`/`BX R14` keeps its existing naked translation and is
  not eligible for this choice. MSP/CPSID/CPSIE wrappers without an explicit return, and
  every other unsupported or ambiguous assembly form, remain project-owned source ports.
  Unused or ambiguous selections fail (`WFI_RETURN_UNUSED`/`WFI_RETURN_AMBIGUOUS`), never
  silently succeed.
- If the intended behavior is intentional fall-through into the next embedded assembly
  function rather than a normal return, that needs a project-owned source port. The WFI
  choice does not reproduce fall-through or claim binary equivalence.

## Supported common ARMCC syntax

These rules are narrow patches shown in preflight `analysis.sourceChanges` and the PLAN's
`data.sourcePatches[]`; they do not turn the Toolkit into a general ARMCC translator.

- An exact `__asm void` wrapper with an explicit `BX LR`/`BX R14` body (WFI, CPSID I,
  CPSIE I or a supported 32-bit/`unsigned int`/`unsigned long` MSP setter) becomes a GNU
  `naked` basic-asm function. Unknown, extra, conditional, nested or commented-prototype
  forms stay blockers.
- `__align(n)` on one plain object is supported for a positive power of two at most 4096,
  including a target define or supported macro; it may combine with a supported fixed
  address only when that address is a multiple of `n`.
- A single uninitialized scalar or fixed-size array `__at(EXPR)` /
  `__attribute__((at(EXPR)))` is supported when the bounded expression resolves from target
  defines and contained quoted guarded headers. Pointers, initializers, `extern`,
  `typedef`, zero-length arrays, mixed/unknown attributes, conditional or function-like
  macros and unresolved expressions stay blockers.
- The exact standalone `#pragma import(__use_no_semihosting)` is removed and the manifest
  proposal adds `build.newlibSpecs=["nosys.specs"]`. This does not add I/O stubs or imply
  runtime I/O equivalence; other `import`/`arm`/optimization pragmas stay blockers.
- Function and declaration rewrites are C-only; the historical numeric `__at` placement
  remains available for C++. The no-semihosting pragma applies to both C and C++.
- Read the full `code`, `rule_id`, `path`, `line`, `column`, `evidence` and `message`.
  Align/placement diagnostics distinguish unsupported declaration grammar from
  `address expression could not be resolved (...)` and
  `array bound '<expr>' could not be resolved (...)`, and name the bounded project-relative
  quoted include when its bytes are not UTF-8. A recognized missing-return WFI wrapper
  carries the concrete `wfiReturns` remediation; every other missing explicit return
  remains a project-owned source port.

## Include-only scopes

When a group or file scope carries only `IncludePath` and analysis produced merge
evidence, preflight returns `analysis.includeMerges` with one entry per scope/owner and
normalized directory, `decision` `added` or `already-present`, and for added entries
`inventorySha256`/`inventoryFiles`. Only scopes with included C/C++ sources contribute;
header/library-only groups do not run a compiler. A scope with defines, misc controls,
included assembly or an unknown compiled language stays a single
`ARMCC_OPTION_UNSUPPORTED` blocker without a partial merge. Any include analysis error
rejects the whole analysis and keeps the original target include list.

## Float ABI and other evidence

There is no framework, FPU or ABI override parameter. Read `analysis.floatAbi`: numeric
`uFloatingPoint` values are not ABI evidence; literal `soft`/`softfp`/`hard` is project
intent; the default hard candidate is inferred only for the documented ARMCC + Cortex-M4 +
FPU2 case. `baselineVerified` is always false. Inspect the actual compiler command lines,
objects and libraries; never edit selectors, evidence or digests to clear a blocker.
Blocked float-ABI or hardware-selection evidence stops both planning and APPLY.

An optional historical AXF/MAP baseline (`includeBaseline=true` on `stm32_keil_inspect`)
is evidence only. It is never required for migration or WFI intent and does not prove a
current build or source identity.

## Post-migration configuration

After the reviewed APPLY, bind `data.outputRoot` as the project root and use the
`configure-stm32-project` Skill. Configure an explicit debug backend/target and verified
Toolkit/GCC paths; PLAN first, then APPLY with the configure plan's `data.plan_id`. A
user-owned writable `NOLOAD` linker fragment is a separate reviewed configure input.
Rebuild after every manifest edit. On this local source tree, managed hardware admission uses the
current content identity (declared inputs, model/debug target, exact ELF/MAP and successful build evidence),
not Git, so the normal flash/debug/Target/Monitor routes need no repository; still do not
describe configuration or a successful build as hardware readiness.
