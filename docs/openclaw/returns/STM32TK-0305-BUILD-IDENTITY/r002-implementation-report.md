# STM32TK-0305-BUILD-IDENTITY r002 Implementation Report — Revision 5

Status: `IMPLEMENTED`
Module: `STM32TK-0305-BUILD-IDENTITY` / r002 / revision-5
Branch: `openclaw/STM32TK-0305-BUILD-IDENTITY/r002`
Accepted base commit: `e47eee0d374bd3a959fe555990b66a6163eb18b8` (exactly matches the work order; working tree clean at start)
Reviewed predecessor: `fd0a4c4a4043ca203bb45d8cc68d7ed03be48504` (the r002 revision-4 report commit)
Code head before this report commit: `6df31b5ae56e062a44a8c885e41fcce2543e6ee6`
Final branch head: supplied only in the return message and PR metadata
Work order: `docs/openclaw/modules/STM32TK-0305-BUILD-IDENTITY.md` (specification commit `cc2e4947aa692f940655c9ddf18ee8ab1f68c824`, `READY_FOR_OPENCLAW`, accepted base matches)

## 1. Revision verdict and scope

Codex returned `REVISION_REQUIRED` for the reviewed predecessor `fd0a4c4a…`. Codex's Windows
full suite on the predecessor was 1046 passed / 3 skipped with 93% branch coverage (its own
run, recorded as review evidence only), and Codex's real-toolchain gate with ARM GNU GCC
14.3.1 / binutils 2.44 on Windows:

1. **Real debug configure/build succeeded**, but the MAP validation then returned
   `BUILD_MAP_INVALID` / `outOfRegion`. Root cause: `parse_map` parsed every non-zero-size
   output section from the MAP text and could not distinguish `SHF_ALLOC` sections from
   non-allocated sections (`.debug_info`, `.debug_abbrev`, `.comment`, `.ARM.attributes`,
   …). Real GNU ld places non-alloc sections at VMA 0, which is outside every model region,
   so an otherwise valid real build was rejected.
2. **Release direct compile/link succeeded** when the fixture was built outside the MAP
   validation path, confirming the failure is the MAP allocation classification and not the
   toolchain or the generated CMake/linker configuration.

Fix in this round (confined to the four approved product/test paths plus this report):

- `build/map_file.py` adds the immutable internal `ElfSectionEvidence` (`name`, `address`,
  `size`, `alloc`) and a keyword-only `elf_sections` argument to `parse_map`. With evidence
  present, every non-zero MAP output section is classified from ELF flags, never from
  section names:
  - same-name ELF section with `SHF_ALLOC` → participates in VMA memory accounting; an
    explicit different LMA continues to participate in the corresponding region;
  - same-name ELF section without `SHF_ALLOC` → never counted in FLASH/RAM; real GNU ld may
    place it at VMA 0;
  - non-zero MAP section absent from the ELF evidence → fail closed (`BUILD_MAP_INVALID`,
    rule `unknown`);
  - MAP/ELF disagreement on VMA or size for a same-name `SHF_ALLOC` section →
    `BUILD_MAP_INVALID`, rules `address` / `size`;
  - every non-zero `SHF_ALLOC` ELF section must be uniquely matched in the MAP → missing
    fails closed with rule `missing`; duplicate evidence names fail closed with rule
    `duplicate` because unique matching is impossible;
  - zero-size rows continue to be ignored; duplicate/conflict/ambiguous/region
    mismatch/out-of-region/overflow rejections are unchanged; MAP interval-union, VMA+LMA,
    and FLASH/RAM/MEMORY overflow logic are unchanged.
- `build/identity.py` collects the evidence in `_inspect_elf` while the section loop runs:
  every non-zero section (alloc and non-alloc) contributes `(name, sh_addr, sh_size,
  SHF_ALLOC)`; the region-fit and fixed-section checks still apply only to `SHF_ALLOC`
  sections exactly as before. `ElfEvidence.sections` is internal validation data only — the
  public `FirmwareIdentity` / `BuildReport` / `OperationResult` protocols are byte-identical.
- `build/runner.py` validates the ELF (format, security, section attributes) **before**
  MAP memory accounting and passes `elf_evidence.sections` into `parse_map`. Error details
  remain stable and bounded (rule-only or rule + portable map path; no absolute paths,
  toolchain paths, MAP content, or exception text).
- Tests (RED commit `2c8b7f45…` then GREEN at the code head): real GNU ld style MAP with
  `.isr_vector`/`.text`/`.heap`/`.stack` counted and debug/comment rows at VMA 0 excluded;
  classification by ELF flags not names (`.debug_fake` with `SHF_ALLOC` still accounted /
  out-of-region, arbitrary-name non-alloc excluded); unknown MAP section rejected; address
  and size mismatch rejected; non-zero alloc ELF section missing from MAP rejected;
  non-alloc ELF sections absent from the MAP (GNU ld line wrapping) not required; interval
  union and LMA overflow hold with evidence; runner order proof (ELF validation first,
  evidence handed to MAP accounting); fake-CMake now emits deterministic ELF/MAP pairs whose
  VMA/size always agree, including the overflow defect (consistent evidence whose disjoint
  RAM LMAs overflow the writable region).

No schema, template (including `templates/cmake/CMakeLists.txt.j2` and its packaged copy),
minimal-gcc fixture, dependency, or lockfile was modified; no skip/xfail was added anywhere;
the 17 full-suite skips are the pre-existing accepted-base Windows-only skips, unchanged.
No commit was amended, rebased, cherry-picked, or force-pushed; `master`, the specification
commit, the r001 branch, and PR #5 were not touched.

## 2. Changed-path inventory (revision diff `fd0a4c4a…` → code head `6df31b5a…`)

| Status | Path | Purpose |
|---|---|---|
| M | `tools/stm32-toolkit/src/stm32_toolkit/build/map_file.py` | immutable `ElfSectionEvidence`; `parse_map(..., *, elf_sections)` allocation classification with stable `unknown`/`missing`/`address`/`size`/`duplicate` failures |
| M | `tools/stm32-toolkit/src/stm32_toolkit/build/identity.py` | collect deterministic alloc/non-alloc section evidence during ELF validation; `ElfEvidence.sections` internal field |
| M | `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py` | ELF validation before MAP accounting; pass ELF section evidence into `parse_map` |
| M | `tools/stm32-toolkit/tests/test_build_map.py` | RED/GREEN classification tests (real GNU ld style, flags-not-names, unknown/address/size/missing/duplicate, zero-size, union + LMA overflow with evidence) |
| M | `tools/stm32-toolkit/tests/test_firmware_identity.py` | ELF evidence classification test (alloc vs non-alloc, frozen tuples) |
| M | `tools/stm32-toolkit/tests/test_build_runner.py` | deterministic ELF/MAP evidence pairs in the fake CMake; runner order proof; runner-level unknown/address/size/missing-section/overflow/debug-MAP tests |
| M | `docs/openclaw/returns/STM32TK-0305-BUILD-IDENTITY/r002-implementation-report.md` | this report (report-only final commit) |

`git diff --check fd0a4c4a…...HEAD` is silent and `git diff --name-status fd0a4c4a…...HEAD`
lists exactly these seven paths and nothing else. No commit was amended, rebased,
cherry-picked, or force-pushed; `master`, the specification commit, the r001 branch, and
PR #5 were not touched.

## 3. Public contracts delivered

- Types/signatures: unchanged public contracts — `BuildRequest`, `MemoryUsage`,
  `FirmwareIdentity`, `BuildReport`, `run_build`, `OperationResult[BuildReport]` are
  byte-identical; `ElfEvidence.sections` (internal, `tuple[ElfSectionEvidence, …]`) is added
  as validation-only data; `parse_map(text, regions, path=None, *, elf_sections=None)`
  gains an optional evidence argument with unchanged default behavior.
- Commands/events/configuration/schemas: none changed (no schema, template, dependency,
  lockfile, or fixture change).
- External interfaces: `NONE` — no CLI/MCP/plugin surface changed.

## 4. Environment-separated verification (this revision round)

OpenClaw environment: Linux x86_64 (`Linux 7.0.0-22-generic`); CPython 3.10.11
(`/home/openclaw/coding/venvs/tk0302`, outside the repository); jsonschema 4.23.0, mcp 1.27.0,
pyelftools 0.33, Jinja2 3.1.6, pytest 8.3.5, pytest-cov 6.0.0. All commands ran with
`PYTHONPATH` set to the checked-out branch tree (`tools/stm32-toolkit/src`) from the
repository root on branch `openclaw/STM32TK-0305-BUILD-IDENTITY/r002` at code head
`6df31b5a…`; the report commit follows separately.

| Gate/command | Evidence owner | Environment | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| MAP/ELF/runner focused gate: `python -m pytest tools/stm32-toolkit/tests/test_build_map.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_build_runner.py -q` | OpenClaw | Linux; CPython 3.10.11 | code head | 0 | 206 passed, 0 failed (188 prior + 18 new classification/order/evidence tests) | PASS |
| `python -m pytest tools/stm32-toolkit/tests/test_process.py -q --durations=10` | OpenClaw | same | code head | 0 | 26 passed, 0 skipped, 0 failed; slowest 3.01 s (bounded polls, no 60 s wait) | PASS |
| fake-CMake target: `python -m pytest tools/stm32-toolkit/tests/test_build_runner.py -q -k "fake_cmake_launcher_reaches_the_python_double or run_build_success_debug_publishes_exact_evidence or launch_failure_returns_configure_failed"` | OpenClaw | same | code head | 0 | 3 passed (launcher probe, exact-evidence success, launch failure) | PASS |
| 5-file focused gate: `python -m pytest tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_build_map.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_context.py -q` | OpenClaw | same | code head | 0 | 269 passed, 0 skipped, 0 failed | PASS |
| Full suite: `python -m pytest tools/stm32-toolkit/tests -q` | OpenClaw | same | code head | 0 | 1067 collected; 1050 passed, 17 skipped (pre-existing accepted-base Windows-only skips; no new skip/xfail), 0 failures/errors | PASS |
| Branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` (clean `.coverage`) | OpenClaw | same | code head | 0 | **93% TOTAL** (6137 stmts, 407 miss; 2022 branches, 159 miss); build.model 100%, build.map_file 98%, build.identity 95%, build.runner 93%, process 91% — every new build/process module ≥90% | PASS |
| Compile: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | code head | 0 | silent | PASS |
| Revision diff hygiene/scope: `git diff --check fd0a4c4a…...HEAD`, `git diff --name-status fd0a4c4a…...HEAD` | OpenClaw | same | code head | 0 | silent; exactly the §2 inventory | PASS |
| Working tree: `git status --short` | OpenClaw | same | code head | 0 | empty before the report commit | PASS |
| Windows full suite and 93% branch coverage on the reviewed predecessor | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | `fd0a4c4a` | 0 | 1046 passed / 3 skipped, 93% coverage (Codex review evidence on the predecessor, not an OpenClaw run) | PASS (Codex review evidence) |
| Real debug configure/build of `minimal-gcc` on the reviewed predecessor | Codex | Windows; CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1/binutils 2.44 | `fd0a4c4a` | 0 (configure/build) | configure and build succeeded; the MAP validation then returned `BUILD_MAP_INVALID`/`outOfRegion` because non-alloc `.debug_*`/`.comment`/`.ARM.attributes` rows at VMA 0 were misclassified as MCU memory | FAIL (rejection evidence) |
| Release direct compile/link of `minimal-gcc` on the reviewed predecessor | Codex | same | `fd0a4c4a` | 0 | direct compile/link of the release preset succeeded, isolating the failure to the MAP allocation classification | PASS (Codex review evidence) |
| Windows focused/full on the returned head, real process-tree timeout (`taskkill /T`, `CREATE_NEW_PROCESS_GROUP`), `msvcrt.locking`, replace/fsync publication | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | returned head | — | the ELF-backed classification is pure Python with exact-byte fixtures and the fake-CMake evidence pairs are host-independent, but the full Windows suite must be re-run by Codex on the returned head | `DEFERRED_TO_CODEX` |
| Real CMake 4.3.1 + Ninja 1.13.2 + ARM GNU 14.3.1/binutils 2.44 debug+release builds of the `minimal-gcc` fixture | Codex | Windows; CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1 | returned head | — | both presets must exit 0 with valid MAP/ELF/identity now that non-alloc sections are classified from the ELF; OpenClaw verifies the runner end-to-end with the hit-proven fake toolchain only | `DEFERRED_TO_CODEX` |
| Visual/hardware | N/A | N/A | — | — | `NOT_APPLICABLE` — no UI or hardware access | N/A |

Attribution rules are honored: every `PASS` row is an OpenClaw run with its own observed exit
and result; the Codex Windows predecessor runs (1046 passed / 3 skipped / 93%, the real
debug configure/build success followed by `BUILD_MAP_INVALID`, and the release direct
compile/link success) are recorded only as the review evidence they are, never as an
OpenClaw PASS; the two Codex gates on the returned head are recorded only as
`DEFERRED_TO_CODEX`.

## 5. Security, privacy, performance, accessibility, and compatibility

- Security/robustness: MAP classification is fail-closed in both directions — a non-zero MAP
  section absent from the validated ELF (`unknown`), a non-zero `SHF_ALLOC` ELF section
  absent from the MAP (`missing`), MAP/ELF VMA (`address`) or size (`size`) disagreement,
  and ambiguous duplicate evidence names (`duplicate`) all reject the build. Non-alloc
  sections are excluded by ELF flags only, never by a name whitelist, and VMA 0 is never
  special-cased; a `.debug_fake` section marked `SHF_ALLOC` is still accounted or rejected
  out-of-region. ELF format/security/section-attribute validation strictly precedes MAP
  memory accounting in the production path.
- Privacy/redaction: new error details are stable single-word rules plus the optional
  portable map path; no absolute path, toolchain install path, MAP content, exception text,
  environment, username, or credential is added anywhere.
- Performance: classification is a single linear pass over MAP rows plus a name-indexed
  lookup and a linear missing-scan over evidence; no timing assertions were added and the
  4 MiB MAP / 1000-input budgets from the work order are unchanged.
- Accessibility/input checks: `NOT_APPLICABLE` — no UI.
- Compatibility: CPython 3.10+, Windows/Linux; the evidence path uses only frozen
  dataclasses and pyelftools 0.33 section-header fields already read by the validated ELF
  stage; the fake-CMake evidence pairs use exact bytes and portable paths and run
  identically on Windows.

## 6. Blockers and residual risks

- Blockers: `NONE`.
- Residual risks:
  1. Windows focused/full on the returned head (including the real process-tree timeout,
     `msvcrt.locking`, and replace/fsync publication) remains Codex's gate. The new
     classification is pure Python over exact-byte fixtures and the deterministic ELF/MAP
     evidence pairs are host-independent, but has not been executed on Windows here.
  2. Real CMake/Ninja/ARM GNU debug+release builds of `minimal-gcc` remain Codex's gate.
     The fix directly addresses the observed rejection (non-alloc sections at VMA 0), but a
     real MAP may present additional GNU ld row shapes (for example further orphan or
     synthetic output sections); any such shape is handled fail-closed by the `unknown`
     rule and would surface as a stable `BUILD_MAP_INVALID` rather than a mis-accounting.
  3. The real-toolchain gate is the only place a real `.heap`/`.stack` section pairing
     (named in the work order regression list) is exercised; OpenClaw covers the same
     classification with synthetic `.heap`/`.stack` rows in `test_build_map.py`.
- Follow-up recommendation: unchanged from the reviewed predecessor (later CLI/MCP modules
  may consume `stm32_toolkit.build.run_build`).

## 7. Author checklist

- [x] Accepted base and code head are full SHAs (`e47eee0d374bd3a959fe555990b66a6163eb18b8`,
      `6df31b5ae56e062a44a8c885e41fcce2543e6ee6`); reviewed predecessor
      `fd0a4c4a4043ca203bb45d8cc68d7ed03be48504` recorded.
- [x] Final head is returned out of band after this report commit (PR metadata + return
      message); this report contains no self-referential final SHA and no moving commit
      totals or volatile file counts.
- [x] Revision diff contains exactly the three approved product paths, the three approved
      test paths, and this report; no schema, template (root or packaged), fixture,
      dependency, lockfile, `test_process.py`, or `test_context.py` change; no skip/xfail
      added; no fixed sleeps or 60 s natural-exit waits introduced (slowest test 3.01 s,
      bounded polls only).
- [x] The P0 rejection class (real ARM MAP misclassifying non-alloc ELF sections as MCU
      memory) is fixed by ELF-backed allocation classification; the Codex predecessor
      evidence (1046 passed / 3 skipped / 93%, debug configure/build success then
      `BUILD_MAP_INVALID`, release direct compile/link success) is recorded in §1 and §4 as
      review evidence only.
- [x] Every required OpenClaw gate has direct observed evidence on the code head (focused
      206 passed; `test_process.py` 26 passed / 0 skipped, slowest 3.01 s; fake-CMake 3
      passed; 5-file 269 passed / 0 skipped; full 1067 collected / 1050 passed / 17
      pre-existing skips / 0 failures; branch coverage 93% overall with map_file 98%,
      identity 95%, runner 93%, process 91% — every new build/process module ≥90%;
      compileall; both diff checks; clean status).
- [x] Other-environment gates are accurately attributed or deferred (Codex Windows
      predecessor evidence recorded as review evidence only; Windows suite/process-tree/lock
      and real ARM toolchain builds `DEFERRED_TO_CODEX`; visual `NOT_APPLICABLE`).
- [x] No credentials, private data, caches, build output, or temp projects are committed
      (venv outside the repository; `.coverage`/`__pycache__`/`.pytest_cache` ignored).
- [x] Overall status `IMPLEMENTED`: complete suite exits 0 on CPython 3.10.11 (1050 passed,
      17 pre-existing skips), branch coverage 93% with every new build/process module ≥90%,
      Windows and real-toolchain gates `DEFERRED_TO_CODEX`.
