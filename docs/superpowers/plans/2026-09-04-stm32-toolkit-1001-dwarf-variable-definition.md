# DWARF Variable Definition Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. One Luna/max implementer for this entire slice overrides fresh-owner-per-task guidance.

**Goal:** Resolve ordinary externally declared GCC variables from their concrete DWARF definition without weakening true-ambiguity or provenance protection.

**Architecture:** Keep the existing catalog/type graph/typed read path. Fix declaration recognition locally and select name/type owners from a bounded one-hop same-CU variable specification; always use the concrete location.

**Tech Stack:** Windows, CPython3.12.10, existing pyelftools/pytest8.4.2. No new dependencies.

## Global Constraints

- Accepted base `472481232bfad99d4d298e0590035e88a6be7044`.
- Governing spec: `docs/superpowers/specs/2026-09-04-stm32-toolkit-1001-dwarf-variable-definition-design.md`.
- One GPT-5.6-luna/max implementer; independent Sol reviewer. No hardware or remote operation.
- Only product `tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py` may change.
- `_integer_attribute` and `_location` remain byte-for-byte unchanged. No first-match/name/address
  deduplication. Unsupported specification shapes fail `DWARF_ELF_MALFORMED`.
- Same-CU one-hop reference to a variable declaration only; direct name/type override inherited
  attributes independently; concrete location only. Existing public errors and limits unchanged.
- No firmware change, no system/dependency install, no packaging/full-suite/CI/coverage matrix.
- Prior requested source-location note is a separate documentation change, not a test fixture.
- Work in verified existing isolated `C:\tmp\stm32tk-1001-legacy-hardware-impl`; preserve other worktrees.

## Task 1: Test-first declaration/definition ingestion and connected reads

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py`.
- Create: `tools/stm32-toolkit/tests/test_dwarf_declarations.py`.
- Optional test-only utility: `tools/stm32-toolkit/tests/dwarf_declaration_fixture.py`.
- Existing tests to run, not weaken: `test_dwarf.py`, `test_debug_read.py`, `test_sampling.py`.

**Interfaces:** consumes `DwarfCatalog.from_elf`, `.lookup`, catalog listing, existing typed-read and
sampling requests; produces the same public selections and values. No added public types.

- [ ] Read governing spec, `dwarf.py` ingestion/type ownership, `test_dwarf.py`, and the actual
  typed-read/sampling APIs. Read TDD and writing-good-tests skill reference before tests.
- [ ] Build a tiny valid ELF in test-only code with two CUs and a literal unsigned32 base type,
  typedef alias, declaration name `testtime`, one concrete specification definition at0x20000134.
  Encode flags with real `DW_FORM_flag_present` and `DW_FORM_flag`; use production pyelftools.
  Include a direct-definition variant and ambiguous two-definition variant. Reusable test assets
  belong to tracked test utilities, generated per-test bytes belong only in tmp_path.
- [ ] Write behavior tests. The central oracle must be literal, not derived from product helpers:

```python
catalog = DwarfCatalog.from_elf(elf_path, readable_regions=((0x20000000, 0x20030000),))
selected = catalog.lookup('testtime')
assert selected.address == 0x20000134
assert selected.byte_size == 4
assert selected.type.signed is False
assert selected.decode(bytes([37, 0, 0, 0])).value == 37
```

  Add catalog listing proof that only the concrete variable is exposed; declaration-only is
  NOT_FOUND; true duplicate concrete definitions remain AMBIGUOUS, including equal addresses.
  Test bool flags and integer flags, direct name/type precedence, no inherited location, malformed
  reference form/offset/target/self/chain, and ordinary numeric bool rejection. Invoke real
  `read_variables` and `sample_variables` using this catalog and only a memory/client test seam;
  assertions must check successful decoded item values and exact requested address/length.
  Do not change top-level OK behavior or sampling rate to make the test pass.
- [ ] Run the new file on unchanged product, capture expected failures, distinguish existing safety
  passes, and commit tests only. Stop for a test-design conflict; do not delete required assertions.

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\tmp\dwd-red-0904 tools/stm32-toolkit/tests/test_dwarf_declarations.py
git diff --check
git add -- tools/stm32-toolkit/tests/test_dwarf_declarations.py
# Add optional fixture helper only if created; never broad-stage.
git commit -m "test(vs10a): reproduce declared DWARF variable resolution"
```

- [ ] Implement the smallest fix after RED: private exact declaration predicate; private bounded
  specification resolver using reference form whitelist and CU/target validation; select direct
  or referenced attribute owner. Keep public lookup ambiguity policy and numeric/location helpers.
  Pseudocode prescribing the owner flow (not a new public API):

```python
if is_declaration(die):
    continue
specification = validated_variable_specification_or_none(die)
name_owner = die if 'DW_AT_name' in die.attributes else specification or die
type_owner = die if 'DW_AT_type' in die.attributes else specification or die
name = _name(name_owner, '')
# Existing name/entry-limit checks.
dwarf_type = type_graph.resolve_attribute(type_owner)
# Preserve existing error capture, parse location from die and its own cu.
```

- [ ] Rerun the new file GREEN, then full four-file matrix once. Use fresh short external roots
  `C:\tmp\dwd-green-0904` and `C:\tmp\dwd-full-0904`; identical Python/options above.
- [ ] Run offline exact external ELF selection against the known SHA in the spec. Assert literal
  address0x20000134/size4/unsigned and successful lookup; no real memory read, no target import.
  This proof is report evidence only and cannot become a path-dependent committed test.
- [ ] Review allowed paths; run `git diff --check`, `git diff --name-only`; ensure unchanged numeric
  and location helper bytes. Commit product only as `fix(vs10a): resolve declared DWARF variables`.
  Return exact RED/GREEN heads, test outputs, offline proof, cleanup and concerns in the ignored
  task report. No acceptance claim. Preserve minimum failure evidence, remove only owned outputs.

## Task 2: Accurate implementation report and final candidate

**Files:** create `docs/codex/returns/STM32TK-1001-DWARF-VARIABLE-DEFINITION/implementation-report.md`.
**Interfaces:** consumes reviewed Task1 commits and actor-attributed evidence; produces report-only
commit. No product/tests change. Same Luna owner, separate Sol report review.

- [ ] After Task1 review is accepted, record full base, spec/plan, exact RED and CodeHead/tree,
  frozen public behavior, original physical failure and offline cause/proof, four-file results,
  actor/environment and cleanup. Include source-location note as user-requested documentation.
- [ ] Do not repeat unchanged tests merely for report formatting. Record the existing valid
  evidence against exact CodeHead. No own report SHA, no physical PASS or invented target value.
- [ ] `git diff --check` and `git diff --name-only`; commit this report only. Return final head/tree
  and clean status. Main agent reviews complete base-to-final-head in fresh detached worktree.

## Final Sol verification and stop

Independently run the same four-file matrix once and exact external ELF offline lookup at final
source; use `C:\tmp\dwd-sol-0904` basetemp. Inspect all diff paths, safety/error behavior and report
lineage. Clean own temporary outputs, classify policy failures without bypass. Product/test pass
and complete review permit software acceptance only. Stop before a new physical testtime sample,
hardware change or remote action; the user has not authorized another such operation here.
