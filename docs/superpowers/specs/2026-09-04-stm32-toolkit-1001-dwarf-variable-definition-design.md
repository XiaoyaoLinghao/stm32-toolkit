# STM32TK-1001 DWARF variable declaration/definition correction

Status: frozen for local execution under the user's 2026-09-04 instruction to advance the
complete repair without per-step approvals. This does not authorize hardware or remote actions.

## Ownership and baseline

- Accepted base: `472481232bfad99d4d298e0590035e88a6be7044`, tree
  `043f373e538218a2c9e3fc65f21035de5bb70e93`.
- Module: VS10-A / H2 typed-variable observation. Sol owns specification, plan, complete-diff
  review and acceptance; one GPT-5.6-luna/max owns product/tests.
- Existing isolated branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Remote-tracking baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`; no push/PR/merge/tag/release.
- The only intervening unrelated-to-product change is the separately requested original-source
  location document. Preserve and classify it, never absorb it into product evidence.

## Evidence and cause

One authorized physical public sample bound the exact firmware successfully but every returned
`testtime` item had `DWARF_SYMBOL_AMBIGUOUS`: seven errors, zero values, thirteen dropped slots.
Top-level OK was not a typed-variable PASS. Evidence is
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-testtime-sample-physical-20260904-01.json`,
SHA256 `18752506408c470bbc659debe39eea1c17367706a49356582d9a3a1baff3e6ee`.

Sol reproduced this entirely offline against `build/arm-debug/LWIP.elf` in
`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`, SHA256
`f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`:

- Named DIEs `0x179` and `0x148d` are declarations, with `DW_FORM_flag_present` decoded as Python
  `True`. `_integer_attribute` intentionally rejects bool, so the current declaration filter
  incorrectly includes both as location-less symbols.
- Concrete definition DIE `0x1649` has `DW_AT_specification` (`DW_FORM_ref4`, relative value1515,
  CU offset `0xea2`) pointing to declaration `0x148d`. It inherits name/type and has its own
  location expression `[3,52,1,0,32]`. The parser currently drops it for lacking a direct name.
- ELF symtab independently contains one global object `testtime`, address `0x20000134`, size4.
- All232 variable specification references in this ELF are one-hop same-CU ref4 references to
  variable declarations. There is no need to change the firmware or use symtab as a fallback.

Classification: PRODUCT / DWARF catalog ingestion, not probe connectivity or physical memory.

## Runnable scenarios

1. **Extern declarations plus concrete definition.** Parse real ELF/DWARF containing two CUs,
   bool flag-present declarations and one nameless/type-less definition referencing a declaration.
   Lookup and catalog listing expose exactly one readable unsigned32 `testtime` at `0x20000134`.
   Decoding offline bytes yields the expected value; no target access is needed.
2. **Declaration-only and true ambiguity.** Declarations never become readable variables.
   Declaration-only lookup returns existing `DWARF_SYMBOL_NOT_FOUND`. Two distinct concrete
   definitions with the same name remain `DWARF_SYMBOL_AMBIGUOUS`, even at the same address;
   no first-match, name/address deduplication, or ignored invalid candidate is permitted.
3. **Definition provenance and malformed reference safety.** A concrete variable inherits only
   missing name/type from one supported declaration reference. Its own name/type take precedence;
   its own location is authoritative. Missing or unsupported concrete location remains the
   existing location error. Invalid specification references fail boundedly and never authorize
   a guessed address or target read.
4. **Connected typed observation.** The production catalog and `read_variables`/`sample_variables`
   path decode the generated fixture using a memory-only test seam, preserving binding revalidation,
   per-item status and sampling behavior. Exact external ELF lookup also succeeds offline; fake
   memory is not physical PASS. A new real-board sample remains separately authorized.

## Frozen implementation contract

- Only production file `tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py` may change.
- Keep `_integer_attribute` byte-for-byte unchanged. Add a private declaration predicate accepting
  exact bool True or integer1; False/0/absent do not mean declaration. Do not globally coerce types.
- Skip declarations before catalog entry accounting. Recognize the real supported shape:
  a concrete `DW_TAG_variable` references one same-CU `DW_TAG_variable` declaration by
  `DW_FORM_ref1/ref2/ref4/ref8/ref_udata`. Resolve through the current pyelftools DIE reference API.
- Validate the reference as a non-bool nonnegative integer within the current CU, and the returned
  target identity/offset/tag/CU. Target must be a declaration and have no further specification.
  Cross-CU, absolute/supplementary/signature references, dangling/wrong-tag/self/chained references
  are outside this bounded shape and return existing `DWARF_ELF_MALFORMED`, with sanitized text.
  No recursive reference walk or new public limit is introduced.
- Select a name owner and type owner independently: prefer each direct definition attribute, else
  the referenced declaration. Resolve type using its owning DIE so CU-relative references remain
  correct. Missing type follows existing `DWARF_TYPE_INCOMPLETE`; concrete location parsing stays
  unchanged. Never inherit declaration flag/location into a concrete definition or mutate DIEs.
- Existing duplicate-name policy, region/size/provenance checks, type/location budgets, error
  inventories, `_location`, sample scheduler and per-item/top-level result semantics stay unchanged.
- No abstract-origin support, C++ scope expansion, symbol-table fallback, type-graph refactor,
  firmware edits, volatile workaround, Python/dependency changes, second backend or runtime.

## Evidence and risk bounds

Luna writes test-first real ELF byte fixtures using test-only Python builders; no dependency on
external ARM compiler, physical board, or proprietary project path in committed tests. Reuse the
existing test patterns; do not edit/remove `fixtures/dwarf/typed.elf` or its existing assertions.
One small test utility may construct ELF sections and DWARF abbreviation/info bytes. Do not add
a generic fixture framework. Required tests cover all four scenarios plus bool and integer flag
encodings, explicit overrides, invalid references and unchanged numeric bool rejection.

Focused suite: `test_dwarf.py`, the new declaration regression file, `test_debug_read.py`, and
`test_sampling.py`. These cover ingestion, provenance, typed reads and sampling without unrelated
Probe/hardware/release matrices. CPython3.12.10 / existing dependencies, external short basetemps,
no cache provider. Run complete relevant suite once before code return; preserve RED evidence and
clean only run-owned disposable output. Sol independently repeats this suite and exact ELF proof
from a clean detached worktree at returned final head; review complete accepted-base-to-final diff.

Commit tests/RED before product/GREEN; record exact boundaries. Commit implementation report
separately after CodeHead. Report stores base/CodeHead, not its own SHA, and separates original
physical failure, offline successful selection, synthetic memory and unexecuted physical retest.
Two unsuccessful implementation/review rounds require reconsidering the design, not more patching.
