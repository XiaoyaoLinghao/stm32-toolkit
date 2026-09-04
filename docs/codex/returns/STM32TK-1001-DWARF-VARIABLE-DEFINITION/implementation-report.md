# STM32TK-1001 DWARF variable declaration/definition implementation report

Status: Task 2 implementation report for the reviewed Task 1 candidate. This
report records software and offline evidence; it does not claim a new physical
sample, a physical typed-variable pass, or complete temporary-output cleanup.

## Ownership, baseline, and candidate

- Module: VS10-A / H2 typed-variable observation.
- Implementer: GPT-5.6-luna, reasoning effort max.
- Independent reviewer and verification owner: GPT-5.6-sol.
- Branch: codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl.
- Accepted slice base: 472481232bfad99d4d298e0590035e88a6be7044.
- Accepted slice base tree: 043f373e538218a2c9e3fc65f21035de5bb70e93.
- Final code candidate (CodeHead): 677d8aa9d2b4b4bd949706c5191033a4cfd2be12.
- Final CodeHead tree: e1d207f9e5a2a4f3df1c803544e1c8fedd46269c.
- Governing specification:
  docs/superpowers/specs/2026-09-04-stm32-toolkit-1001-dwarf-variable-definition-design.md.
- Implementation plan:
  docs/superpowers/plans/2026-09-04-stm32-toolkit-1001-dwarf-variable-definition.md.
- Verification environment: Windows, CPython 3.12.10, existing pyelftools and
  pytest dependencies, with pytest cache provider disabled. No dependency was
  installed or changed.
- Sol independently reviewed the complete candidate in clean detached
  C:\tmp\dwr-review-0904. The final implementation worktree was clean.
- No push, pull, PR mutation, merge, tag, release, remote branch deletion,
  hardware operation, installation, or dependency change was performed.

The task execution checkout initially contained the later documentation head
7d1ac02b7af29a2ba2eac0b38854a60f8897067e. That is execution history, not the
accepted product base. The separately requested documentation commits and
source-location record remain outside the Task 1 product change.

## Frozen public behavior

The implementation keeps the existing DwarfCatalog, lookup, catalog-listing,
typed-read, and sampling APIs and adds no public type or backend. Its bounded
behavior is:

- Exact Python bool True and integer 1 declaration attributes identify
  declarations; False, 0, and absent attributes do not.
- Declaration DIEs are skipped before catalog-entry accounting.
- A concrete DW_TAG_variable may use one same-CU, one-hop
  DW_FORM_ref1/ref2/ref4/ref8/ref_udata DW_AT_specification to a variable
  declaration. The resolver validates the nonnegative CU-relative value,
  actual sequential DIE boundary, returned target offset/identity/tag/CU,
  declaration status, and absence of a further specification.
- A per-CU boundary index is built from one sequential DIE enumeration before
  specification resolution. Existing DIE-count and depth budgets remain in the
  enumeration path, and forward references remain valid. No recursive
  reference walk or new public limit was introduced.
- Direct definition name and type independently override inherited declaration
  attributes. A missing name or type inherits only from the validated
  declaration. The concrete DIE's location remains authoritative; declaration
  location and declaration status are not inherited.
- Existing lookup ambiguity, readable-region, type/location, provenance,
  per-item read, and sampling semantics remain in force. Invalid or unsupported
  specification references fail with DWARF_ELF_MALFORMED before a guessed
  address or target read. _integer_attribute and _location remain unchanged.

## Test-first chronology and review correction

The first implementation wave has an explicit process deviation. The actual
order was:

1. Tests and a test-only ELF fixture were authored untracked.
2. A first RED attempt exposed test setup defects (fixture PT_LOAD layout,
   malformed-case helper TypeError, and a disposable environment identity
   mismatch). Those were corrected in test-only code and are not product
   failures.
3. The valid unchanged-product RED ran with HEAD
   7d1ac02b7af29a2ba2eac0b38854a60f8897067e and produced 14 failed, 7 passed
   in 7.84 seconds.
4. Product editing of dwarf.py began before the required test-only commit.
   Focused GREEN eventually passed 26 tests, and only afterward the tests were
   committed as 9a662f13df0a4f44aeb97ff8793cbaa654a83c76. The first product
   candidate was c50ccffa84c0d6ea32d37c8658d512a81fc4c34c.
5. Sol review found a P2 safety issue in c50ccffa: a supported CU-relative
   reference could point inside an attribute payload and be interpreted via
   pyelftools as a forged variable target.

That deviation is not retroactively presented as compliant. The corrective
round restored the required local order:

1. New interior-payload and valid-forward-reference tests were run against
   unchanged c50ccffa. The RED result was 1 failed, 27 passed in 7.22 seconds;
   the sole intended failure was the interior-payload malformed-reference
   assertion.
2. Tests and fixture were committed first as
   dcb03de37960f567c620c11b5119e511a170a213.
3. The bounded product fix was then implemented in dwarf.py. Focused GREEN
   passed 28 tests, and the product-only revision commit is CodeHead
   677d8aa9d2b4b4bd949706c5191033a4cfd2be12.

## Implementer RED evidence

The first-wave valid RED command was:

~~~powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\tmp\dwd-red-0904 tools/stm32-toolkit/tests/test_dwarf_declarations.py
~~~

Its valid unchanged-product result was 14 failed, 7 passed in 7.84 seconds.
The failures were the expected pre-fix declaration filtering/resolution,
ambiguity, inheritance, malformed-reference, listing, read, and sampling
behaviors. The setup-only first attempt was 15 failed, 6 passed and is not
used as product evidence. Historical start/end timestamps for this first RED
were not captured by the command runner.

The corrective RED command was:

~~~powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\tmp\dwr-red-0904 tools/stm32-toolkit/tests/test_dwarf_declarations.py
~~~

It ran against unchanged product head
c50ccffa84c0d6ea32d37c8658d512a81fc4c34c, before revision test commit
dcb03de37960f567c620c11b5119e511a170a213. It ended exit code 1 with
1 failed, 27 passed in 7.22 seconds. Start was
2026-09-04T09:34:42.8439944+08:00 and end was
2026-09-04T09:34:51.1854196+08:00. The sole failure was
test_supported_reference_inside_die_payload_is_malformed with DID NOT RAISE;
the valid-forward-reference test and all previous cases passed. There were no
setup or import errors.

## Implementer GREEN and final software evidence

The corrective focused declaration suite passed 28 passed in 6.68 seconds,
exit code 0, from 2026-09-04T09:36:19.2897083+08:00 through
2026-09-04T09:36:27.0396587+08:00, using basetemp
C:\tmp\dwr-green-0904.

The affected four-file matrix was run once by the implementer with:

~~~powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\tmp\dwr-full-0904 tools/stm32-toolkit/tests/test_dwarf.py tools/stm32-toolkit/tests/test_dwarf_declarations.py tools/stm32-toolkit/tests/test_debug_read.py tools/stm32-toolkit/tests/test_sampling.py
~~~

The implementer result was session 87937, exit code 0, 188 passed in 101.66
seconds (0:01:41), from 2026-09-04T09:36:36.7201397+08:00 through
2026-09-04T09:38:19.5259674+08:00. No setup or product failures occurred.

Sol independently repeated the affected matrix from clean detached
C:\tmp\dwr-review-0904 at final CodeHead, using the exact source paths and
basetemp C:\tmp\dwr-sol-0904. Sol reported session 56166, exit code 0,
188 passed in 100.81 seconds. This is the independent verification result
against the exact reviewed CodeHead; no new test run was performed for this
report.

Sol's exact final verification command was:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='C:\tmp\dwr-review-0904\tools\stm32-toolkit\src;C:\tmp\dwr-review-0904\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' -q -p no:cacheprovider --basetemp C:\tmp\dwr-sol-0904 tools/stm32-toolkit/tests/test_dwarf_declarations.py tools/stm32-toolkit/tests/test_dwarf.py tools/stm32-toolkit/tests/test_debug_read.py tools/stm32-toolkit/tests/test_sampling.py
~~~

## Offline real-ELF cause and proof

The original physical public sample successfully bound the exact firmware, but
every returned testtime item had DWARF_SYMBOL_AMBIGUOUS: seven errors, zero
values, and thirteen dropped slots. Its top-level OK was not a typed-variable
PASS. The evidence is the physical evidence record
C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-testtime-sample-physical-20260904-01.json,
SHA256 18752506408c470bbc659debe39eea1c17367706a49356582d9a3a1baff3e6ee.
This is a physical failure record, not a physical success claim.

Sol's offline cause analysis against the separate verification replica found:

- DWARF declaration DIEs 0x179 and 0x148d use DW_FORM_flag_present, which
  pyelftools decodes as Python True. The old integer-only declaration check
  therefore retained both as location-less symbols.
- Concrete DIE 0x1649 uses DW_AT_specification DW_FORM_ref4, relative value
  1515 with CU offset 0xea2, to declaration 0x148d. It inherits name/type and
  has location expression [3,52,1,0,32], but the old parser dropped it for
  lacking a direct name.
- The ELF symtab independently contains one global testtime object at
  address 0x20000134 with size 4. All 232 specification references in this
  ELF are ordinary same-CU one-hop ref4 references; no symtab fallback or
  firmware edit is needed.

The exact offline proof at the implementer candidate, later independently
confirmed by Sol at CodeHead, loaded read-only:

C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math\build\arm-debug\LWIP.elf

The ELF SHA256 was
f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c.
Public DwarfCatalog.from_elf with project_root and
readable_regions=((0x20000000, 0x20030000),) then lookup(testtime) returned
address 0x20000134, size 4, signed False. Decoding the supplied offline bytes
(37, 0, 0, 0) returned 37. The proof asserted TARGET_READ=not-performed and
that no pyocd module was imported. The decoded 37 is synthetic/offline
evidence only, not a physical target value.

The implementer proof was captured from
2026-09-04T09:38:33.3076650+08:00 through
2026-09-04T09:38:34.6698149+08:00. Sol's independent proof used the same
ELF SHA and public selection at CodeHead. No target read, firmware mutation,
hardware action, or target import occurred.

## Synthetic connected-path evidence and boundaries

The committed declaration tests exercise the real catalog, read_variables, and
sample_variables paths with a test-only in-memory client seam. They verify
successful decoded items, exact request address/length
(0x20000134, 4), binding revalidation, per-item status, and two scheduled
samples. This is synthetic memory evidence and is not physical board
acceptance. A new real-board testtime sample remains unperformed and separately
authorized.

The committed test-only changes are:

- 9a662f13df0a4f44aeb97ff8793cbaa654a83c76 for the first declaration tests and
  fixture.
- dcb03de37960f567c620c11b5119e511a170a213 for interior-payload and
  forward-reference coverage.

The product changes are confined to
tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py. The two protected helper
functions _integer_attribute and _location are byte-for-byte unchanged from
accepted base. The final product commit is one-file product-only
677d8aa9d2b4b4bd949706c5191033a4cfd2be12. No existing dwarf fixture,
unrelated product module, test, specification, plan, or source-location
document was weakened or rewritten.

## User-requested original-source location note

The user-corrected original source location is:

D:\workspace\MR_Code\branches\stable

The location document records that Test-Path returned True, the directory is
not a Git repository, and no original-directory HEAD was recorded or inferred.
The earlier path D:\workspace\WDS\_CODE\branches\stable did not exist and was
superseded by the user correction. The source location is not the Toolkit
project root, and its correspondence to the ELF was not verified.

The bind/register/sample verification replica is separate:

C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math

Its recorded Git HEAD is cf273a18b4c757b4866793c94b25d5ceaad39925, its ELF is
build/arm-debug/LWIP.elf, its ELF SHA256 is
f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c, and its
recorded Build ID is a05dc376406721d497b0af451951420a583113eb298dd50d26eeb3ebdbfb8d44.
These paths, identities, and claims are kept separate. No original source
file was modified and no physical firmware was switched.

## Cleanup and residual evidence

Cleanup was attempted only for run-owned disposable output and was never
bypassed when the Windows execution policy rejected recursive removal before
execution. No source-controlled test, reusable fixture, user data, failure
evidence, external ELF, or review checkout was deleted.

Known Luna-owned residual basetemp roots:

- C:\tmp\dwd-red-0904
- C:\tmp\dwd-green-0904
- C:\tmp\dwd-full-0904
- C:\tmp\dwr-red-0904
- C:\tmp\dwr-green-0904
- C:\tmp\dwr-full-0904

The explicit Remove-Item -LiteralPath ... -Recurse -Force attempts for these
roots were rejected by policy before execution; the roots remain. The first
wave full root was observed with 8821 entries before its blocked cleanup.

Known Sol-owned residual roots and evidence:

- C:\tmp\dwd-red-sol-0904: native removal was rejected before execution.
- C:\tmp\dwd-red-review-0904: clean detached review checkout retained.
- C:\tmp\dwd-sol-0904: Sol matrix output retained.
- C:\tmp\dwd-review-0904: Sol review checkout retained.
- C:\tmp\dwr-sol-0904: final Sol matrix output retained.
- C:\tmp\dwr-review-0904: final Sol review checkout retained.

No claim is made that all temporary artifacts were removed. User-owned prior
oad roots were not touched.

## Report boundary and remaining gate

This tracked document contains only the implementation report. It does not
contain its own future commit SHA. The final code candidate and independent
software evidence are recorded above; the physical failure remains a failure,
synthetic memory remains synthetic, and the new physical retest remains
unperformed. Primary Sol review and any final release or hardware decision
remain outside this report's authority.
