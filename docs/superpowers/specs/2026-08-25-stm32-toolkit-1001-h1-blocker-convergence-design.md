# STM32TK-1001 H1 blocker convergence design

**Status:** frozen correction design  
**Parent slice:** VS10-A `STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP`  
**Accepted Toolkit base:** `12d0d3be1f59a5ed44b84a1244575cb853b97173`  
**Project P0:** `e7b2408fb615748ca5d67a2006f31e2377a09942` / tree `c953083eb371171df5f48fe041aea48e7bdc6b76`  
**Specification owner/reviewer:** GPT-5.6-sol primary  
**Implementation owner:** the existing single GPT-5.6-luna/max VS10-A implementer  
**Remote authority:** none  
**Hardware authority:** none for this correction

## 1. Triggering evidence

The first real H1 pass used the exact installed 0.9.0 candidate and explicit project root against `Project/LWIP.uvprojx`, `Target 1`. Public `keil inspect` returned `OK` and selected `STM32F429ZGTx`, but reported every output path as null and `baseline.available=false`, despite unchanged P0 files `Project/OBJ/LWIP.axf` and `Project/LIST/LWIP.map`. Public convert dry-run returned plan `4736c6c63b067153d51481cca7f43c1c3c677ccd6a595e9e54eec4f399fc5e7c`, zero patches, and exactly 38 blockers: one framework selection, 36 non-UTF-8 sources, and one included ARMCC startup assembly.

The evidence is frozen under `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence` as `inspection.json`, `task-6-keil-convert-dry-run.stdout`, and `task-6-inspect-convert-classification.json`. No apply, configure, build, project edit, or hardware operation occurred.

## 2. User scenarios and non-goals

### Runnable scenarios

1. A Keil project whose output fields are in the standard `TargetCommonOption` location is inspected through CLI or MCP, and its existing AXF and listing-directory MAP are captured as the real baseline.
2. A legacy SPL project with `USE_STDPERIPH_DRIVER`, `misc.c`, and canonical bare `stm32*xx_<peripheral>.c` driver sources is selected as SPL without accepting HAL/LL conflicts or a project-name special case.
3. The named P0 project receives one digest-bound portability correction: strict GB18030-to-UTF-8 normalization for exactly the 36 rejected source files plus a derived GCC-only uvprojx and project-owned C startup. The original uvprojx, ARMCC startup, historical outputs, and D4/test logic remain preserved.
4. The corrected Toolkit candidate reruns public inspect, guarded conversion/configuration, and two reproducible builds, producing P1c only if all H1 memory, vector, symbol, and future-mailbox-range checks pass.

### Non-goals

- No generic ARMASM translator, arbitrary Keil compatibility layer, encoding auto-detection/rewrite in Toolkit, startup generator backend, new runtime, MCP registration, controller, provider, backend, Agent logic, Python version, CI, or collaboration automation.
- No implicit framework selection from one weak clue, no `--framework` public option, and no project-specific string such as `STM32F4_FWLIB` in product logic.
- No modification of the original `Project/LWIP.uvprojx`, `Startup_config/startup_stm32f429_439xx.s`, historical Keil AXF/MAP/HEX/logs, golden tree, or Toolkit release artifacts in place.
- No mailbox reservation, v2 emitter, D4 behavior edit, `testtime` volatile edit, Probe open, attach, reset, flash, read, or hardware PASS.

## 3. Considered approaches

### A. Minimal generic inspector correction plus project-owned portability profile — selected

Fix the two narrow generic inspection defects, then keep encoding and startup conversion explicitly project-owned and digest-bound. This preserves Toolkit's conservative refusal to rewrite unknown encodings or ARM assembly while allowing the real project to reach the existing guarded public workflow.

### B. Add CLI/MCP framework, encoding, and startup override parameters — rejected

This expands multiple public schemas, Skills, inventory, authorization, and compatibility surfaces for one real-project migration. It would require broader release verification and creates a long-lived conversion policy surface not justified by VS10-A.

### C. Bypass public conversion with private modules or handwritten CMake — rejected

This would evade the product behavior being accepted, break plan/digest guarantees, and create untraceable build evidence.

## 4. Toolkit correction contract

### 4.1 Standard Keil output locations

`inspect_keil` reads `OutputDirectory`, `OutputName`, and `ListingPath` from the already-selected `TargetCommonOption`, not directly from `TargetOption`.

- AXF path: `<OutputDirectory>/<OutputName>.axf` when both fields exist.
- MAP path: `<ListingPath>/<OutputName>.map` when `ListingPath` exists; otherwise fall back to `<OutputDirectory>/<OutputName>.map`.
- All current containment, absolute-path, traversal, duplicate, file-size, and read-only guarantees remain unchanged.
- A missing field remains `null`; the parser must not search the filesystem or guess a basename.
- CLI, MCP, and core must expose the same corrected normalized inspection and baseline.

### 4.2 Conservative SPL source-set evidence

Framework selection keeps the existing two-distinct-evidence-category rule. A new generic `source` evidence item for SPL is emitted only when the included source set contains both:

- a source whose case-insensitive basename is `misc.c`; and
- an ASCII-only source basename whose lowercase form is exactly one of these 29 real STM32F4 Standard Peripheral Library units: `stm32f4xx_adc.c`, `stm32f4xx_can.c`, `stm32f4xx_crc.c`, `stm32f4xx_cryp.c`, `stm32f4xx_dac.c`, `stm32f4xx_dbgmcu.c`, `stm32f4xx_dcmi.c`, `stm32f4xx_dma.c`, `stm32f4xx_dma2d.c`, `stm32f4xx_exti.c`, `stm32f4xx_flash.c`, `stm32f4xx_fmc.c`, `stm32f4xx_fsmc.c`, `stm32f4xx_gpio.c`, `stm32f4xx_hash.c`, `stm32f4xx_i2c.c`, `stm32f4xx_iwdg.c`, `stm32f4xx_ltdc.c`, `stm32f4xx_pwr.c`, `stm32f4xx_rcc.c`, `stm32f4xx_rng.c`, `stm32f4xx_rtc.c`, `stm32f4xx_sai.c`, `stm32f4xx_sdio.c`, `stm32f4xx_spi.c`, `stm32f4xx_syscfg.c`, `stm32f4xx_tim.c`, `stm32f4xx_usart.c`, or `stm32f4xx_wwdg.c`.

This `source` evidence plus the existing `define=USE_STDPERIPH_DRIVER` evidence selects SPL for the real project. The rule is based on source-set semantics, not directory or project names. HAL/LL evidence, mixed-framework evidence, a lone define, a lone source signature, or ambiguous qualified frameworks must continue to fail closed.

The matcher must not form a family/peripheral cross-product and must not use Unicode-aware case folding. Unknown families, nonexistent family/peripheral combinations, interrupt/system units, HAL/LL units, and Unicode-confusable basenames remain non-evidence.

### 4.3 Tests and release impact

TDD tests must first reproduce the real XML nesting/listing MAP defect and SPL source-set ambiguity at the accepted base. GREEN tests cover core inspection, baseline capture, CLI/MCP parity, fallback MAP location, containment failures, HAL/LL conflict refusal, and no false selection from weak evidence. Run only the focused Keil/migration/workflow/CLI/MCP tests plus directly affected regression. Rebuild and verify one Windows candidate because Toolkit bytes change; no full release matrix is triggered.

### 4.4 ARM linker image-component program-size fallback

The corrected public inspect reached the real contained `Project/LIST/LWIP.map` and exposed a second generic Keil MAP format. This ARM linker output has no `Program Size: Code=...` line. It instead contains an `Image component sizes` section with this exact six-number totals layout:

```text
Code  (inc. data)  RO Data  RW Data  ZI Data  Debug
62772       5540      1004     1576   406440  534601   Grand Totals
```

The parenthesized `inc. data` value is a subset of Code, not RO Data. For the real baseline the public `KeilProgramSize` is therefore Code `62772`, RO Data `1004`, RW Data `1576`, and ZI Data `406440`; its existing derived values are ROM `65352` and RAM `408016`.

The MAP parser keeps the existing bounded UTF-8/size/overflow contract and adds one fail-closed fallback:

- the existing `Program Size` form remains authoritative when present;
- otherwise require the exact `Image component sizes` section, the exact ordered `Code (inc. data) / RO Data / RW Data / ZI Data / Debug` header semantics, and exactly one `Grand Totals` row with six unsigned decimal values;
- map columns 1/3/4/5 to Code/RO/RW/ZI and ignore columns 2/6 only after validation;
- require `Total RO Size` to equal Code + RO Data and `Total RW Size` to equal RW Data + ZI Data; these two cross-checks are mandatory for the fallback;
- reject missing headers/totals/cross-checks, malformed or overflowing values, multiple component totals, cross-check mismatches, or a component tuple that conflicts with a present `Program Size` tuple using the existing stable `KEIL_MAP_INVALID` envelope and bounded rule names.

This is generic ARM linker evidence parsing. It must not recognize the project name, output basename, object list, absolute path, or the real numeric values specially. No public model, schema, CLI, MCP, error code, output-path rule, framework rule, or baseline lifecycle changes.

## 5. Project portability correction contract

The project correction is not Toolkit product logic. It is one local Git change bound to a machine-readable proposal and a SHA-256 over the exact proposed P0-to-portability diff before apply. The standing user instruction authorizes the Sol primary to approve that exact digest without another interactive prompt. Any byte drift invalidates approval.

### 5.1 Encoding normalization

- Scope is exactly the 36 paths returned as `ARMCC_SOURCE_ENCODING_UNSUPPORTED` by the frozen plan.
- All 36 originals must fail strict UTF-8. The 34 files that pass strict GB18030 must round-trip byte-exactly through GB18030, then be re-encoded from the identical Unicode scalar sequence as UTF-8 without BOM. Preserve decoded newline characters; do not format, rename symbols, or change code/comments.
- P0, intake, and golden bytes prove that two files contain pre-existing comment corruption rather than a second usable source encoding:
  - `USER/usart2_rs485_1/usart2_rs485_1.c`, 4785 bytes, SHA-256 `6814388ad93a854a0f5af1ae1396dbb1356be85e977caf96ca7f59772ffb6be2`, has twelve one-byte GB18030 failures: `F3@1704`, `F3@1765`, `FC@1770`, `F9@1830`, `E8@1832`, `ED@1893`, `F3@1899`, `EA@1901`, `E9@1957`, `E0@1959`, `EA@2008`, and `F3@2172`.
  - `USER/usart5_rs485_2/usart5_rs485_2.c`, 4856 bytes, SHA-256 `f5c8e277733c4bf776e5df6403f6839f7e2253ff698cd1e31d8ca8f5a9c9a9ad`, has one one-byte failure, `F3@2217`.
- Those thirteen bytes are eligible for one reversible project-owned recovery only when every path, size, SHA-256, offset, byte value, and error length matches the list above; every error is inside a physical line matching `^[ \t]*//`, and no affected line ends in a continuation backslash. Decode all valid spans as strict GB18030 and render each invalid byte in the comment as the literal ASCII text `\xHH`. Do not guess the lost Chinese character, use a replacement character, or select a fallback codec.
- The recovered output must be strict UTF-8 without BOM. Valid decoded spans and newline characters remain identical; each escape plus the closed recovery manifest makes every corrupt source byte reversible. A line-level proof must show that the affected lines contain no C tokens before the full-line comment and that all other token-bearing text has identical Unicode scalars.
- Record path, original size/SHA-256, conversion mode (`strict-gb18030` or `gb18030-with-comment-byte-escapes`), decoded-text or valid-span digest, recovery events where applicable, output size/SHA-256, newline proof, and strict UTF-8 output proof.
- Any drift from the exact 34-path strict set or the two pinned recovery inputs stops the correction. Toolkit product logic receives no encoding detector, repair rule, project path, or special case.

### 5.2 Derived GCC Keil profile

- Preserve `Project/LWIP.uvprojx` byte-for-byte.
- Create `Project/LWIP.gcc.uvprojx` as a deterministic derived copy. Its only semantic XML change is in the selected `Target 1` source list: replace the included ARMCC startup entry with `Migration/startup_stm32f429xx.c` and the correct C file type/name. All device, memory, defines, include paths, source order apart from the one replacement, output settings, and target options remain equal.
- Public inspect/convert for the corrected campaign uses `Project/LWIP.gcc.uvprojx`; the original profile remains the provenance baseline.

### 5.3 Project-owned C startup

`Migration/startup_stm32f429xx.c` owns only GCC reset/vector portability:

- initial SP is the documented SRAM1 top `0x20030000` for P1c;
- vector entries, order, reserved slots, and handler names exactly match the original included ARMCC F429/439 startup;
- the vector table is retained in `.isr_vector` and exposes `Reset_Handler` as Thumb code;
- reset copies `.data` from `_sidata` to `_sdata.._edata`, zeros `_sbss.._ebss`, calls `SystemInit`, then `main`, and does not silently return;
- all otherwise undefined interrupt handlers are weak aliases to one non-returning default handler, while project strong handlers such as `TIM3_IRQHandler` override them;
- it contains no mailbox, target-test, diagnostic, D4, monitor, or hardware-control behavior.

Static project tests compare the derived profile and C vector sequence against the original ARMCC DCD sequence, verify exactly one startup input, compile the startup with the frozen GCC flags, and prove the original profile/startup hashes unchanged.

## 6. Corrected H1 lifecycle

1. Luna/max implements the Toolkit correction with RED/GREEN tests and commits it on the existing VS10-A implementation branch.
2. Sol reviews the complete `12d0d3be..CodeHead` diff in a clean worktree and runs only focused affected tests. No project correction starts before `ACCEPTED`.
3. Build and verify a replacement 0.9.0 campaign candidate from the accepted CodeHead. Because secure runtime state must reject different bytes under the same version, do not invoke upgrade/repair over the old 0.9.0 runtime. Preserve its state/manifest/package hashes, verify no process uses it, retire only the exact campaign-managed `data/runtime` tree, and bootstrap the replacement into a fresh `data/runtime`. The old candidate identity remains evidence but is no longer current.
4. Rerun inspect on unchanged P0. Require real AXF/MAP baseline and `framework=spl`. Rerun convert dry-run and require that only the 36 encoding and one ARMCC assembly blockers remain.
5. Luna/max constructs the project portability proposal in scratch, records its exact diff digest, and returns it without changing P0. Sol verifies scope and authorizes only that digest under the standing user direction.
6. Apply the exact proposal, commit the local portability input, rerun inspect/convert dry-run, and require zero blockers. Apply only the unchanged conversion plan, then guarded configure.
7. Build twice and run the parent specification's complete H1 comparison. The final stage is named P1c because real H1 evidence triggered a project portability correction; P1 is recorded as unavailable before correction, not falsely passed.
8. Only an H1-clean P1c may enter Task 7. Any new product/project defect stops before hardware.

## 7. Error, evidence, and cleanup semantics

Existing stable public error envelopes and plan drift rejection remain unchanged. Failures use the parent classification taxonomy. The formal evidence adds:

- `h1-correction-red.json`
- `toolkit-correction.json`
- replacement candidate/runtime records
- `portability-proposal.json`
- `portability-authorization.json`
- `portability-correction.json`
- derived-profile/vector equivalence evidence
- corrected inspect/conversion/configuration/build and memory-comparison records

No evidence may label fixture, static, replay, or no-hardware results as physical PASS. Temporary candidate worktrees, proposal scratch, basetemps, and build intermediates are removed only after required formal evidence is preserved. The campaign retains the old and replacement candidate identities needed to explain evidence invalidation; there is still one active managed runtime and one public Toolkit behavior path.

### 7.1 One-time closed-input recovery after classified absence

Task 3 preflight proved the retained 64-wheel runtime wheelhouse does not contain the two previously pinned build-backend wheels. A read-only search of the approved local cache roots also found no copy. This is an `ENVIRONMENT` blocker, not a product failure, and permits exactly one bounded recovery before Task 3 resumes:

- acquire only `setuptools-84.0.0-py3-none-any.whl` from `https://files.pythonhosted.org/packages/95/9c/c510029fc6ef33a6275cd2c5d3cecd6613dfd6aa401d57c54f1c18852ccf/setuptools-84.0.0-py3-none-any.whl` and `wheel-0.48.0-py3-none-any.whl` from `https://files.pythonhosted.org/packages/2e/29/69cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449/wheel-0.48.0-py3-none-any.whl`, the exact official artifact URLs published by PyPI;
- write them only into a new run-scoped recovery directory under campaign `scratch`, with redirects disabled and no package resolver, index search, dependency resolution, installation, or alternate source;
- require respectively `(size=818216, sha256=51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670)` and `(size=33320, sha256=3217dcc807155e45eb462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab)` before either file may enter the closed build wheelhouse;
- record source URL, TLS request result, filename, size, SHA-256, acquisition time, and the prior local-cache miss in formal evidence;
- if either request, filename, size, or digest differs, remove the two exact run-scoped downloads and stop without build/runtime/project/hardware mutation.

This recovery does not expand supported dependencies or authorize general network acquisition. After verified copy-in, the build still consumes the same frozen 66-wheel set and all original member/trust-anchor equality gates apply. The recovery directory is removed after evidence is preserved.

### 7.2 Independent-transport diagnosis after the first recovery mismatch

The first bounded recovery fetched both expected sizes through Windows curl/Schannel after the redirect-disabled .NET client failed before bytes. Setuptools matched. The wheel response had SHA-256 `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`, differing at hex index 16 from the frozen and official PyPI digest `3217dcc807155e45eb462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`. Ordinal comparison independently confirmed the mismatch; the bytes were rejected and removed before build or runtime mutation.

The source-of-truth hash is not relaxed. To distinguish a reproducible source/environment rewrite from a transient Schannel/curl transfer defect, exactly one diagnostic retry is permitted for `wheel-0.48.0-py3-none-any.whl`:

- use the frozen CPython 3.12.10 interpreter's standard-library `urllib.request` over its OpenSSL TLS stack, with a redirect handler that rejects every redirect and the same exact official artifact URL;
- stream only to a new exact run-scoped campaign scratch directory; require HTTP 200, final URL equality, `Content-Length=33320`, downloaded size 33320, a valid ZIP central directory/CRC test, and SHA-256 `3217dcc807155e45eb462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`;
- record Python/OpenSSL versions, response headers needed for provenance, timestamps, size/hash, the first-attempt mismatch, and official PyPI metadata digest in formal evidence; do not log secrets or unrelated headers;
- if any gate fails or the digest again differs, preserve minimum diagnostic evidence, remove the exact scratch download, and stop before candidate/runtime/project/hardware mutation;
- if every gate passes, classify the first response as a transient/environmental transport-integrity failure, combine the verified diagnostic wheel with a fresh exact recovery of the already-passing setuptools artifact under the same CPython transport and gates, then admit only those two verified bytes to the temporary 66-wheel closed set and resume Task 3.

Section 7.2 itself authorizes no third request, mirror, resolver, index search, alternate version, hash update, or acceptance of mismatched bytes. Section 7.3 separately supersedes only the request-count boundary for its one final evidence-only diagnosis; every other prohibition remains in force.

### 7.3 Final multi-digest source-identity diagnosis

The independent OpenSSL retry reproduced the same valid 33320-byte ZIP and the same SHA mismatch. Its response ETag equals PyPI's published MD5 `75e4bbe15fefadbb91258c5e79b38aa3`, while the exact official artifact URL path embeds PyPI's published BLAKE2b-256 `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449`. Response claims are not sufficient to change a trust anchor, so one final evidence-only request is permitted to hash the actual bytes under both independent algorithms.

Use the same CPython 3.12.10/OpenSSL direct request, exact URL, redirect rejection, response/size/ZIP gates, and new exact run-scoped scratch root. Retain the file until Sol reconciles these actual-byte digests:

- SHA-256 against both the published value and the two prior observed values;
- BLAKE2b-256 against the exact official URL path and PyPI JSON;
- MD5 against the ETag and PyPI JSON, as corroborating legacy evidence only;
- ZIP member list, per-member CRC test, and wheel `RECORD` self-consistency.

No candidate/runtime/project/hardware action follows this request automatically. Luna returns the retained file and formal evidence to Sol. Sol may authorize a corrected SHA-256 anchor only if the actual bytes reproduce the prior observed SHA, match the official BLAKE2b-256 exactly, match the official MD5 exactly, pass all archive/RECORD checks, and the response identity/status/length gates remain exact. BLAKE2b is the independent strong identity anchor; MD5 alone can never authorize the correction. Any other result removes the exact scratch file after minimum evidence is preserved and blocks VS10-A. No further request for this wheel is allowed.

### 7.4 Accepted corrected wheel identity anchor

The final retained bytes passed every Section 7.3 gate. Sol independently recomputed all three file digests and all 20 `RECORD` rows. The accepted identity tuple for this one artifact is therefore:

- file: `wheel-0.48.0-py3-none-any.whl`, size 33320;
- corrected actual-byte SHA-256: `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`;
- official URL/PyPI BLAKE2b-256 strong anchor: `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449`;
- corroborating official MD5/ETag: `75e4bbe15fefadbb91258c5e79b38aa3`.

The PyPI JSON SHA-256 `3217dcc807155e45eb462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab` remains preserved as the rejected inconsistent metadata value; it must not be silently overwritten in diagnostic evidence. The correction is authorized only because the actual bytes match the independent official BLAKE2b strong anchor, reproduce across three direct requests and two TLS stacks, match the official MD5, and pass ZIP/RECORD integrity. It is not a policy to prefer downloaded bytes over published hashes.

Sol writes a single-use machine-readable authorization after this design and plan reach the implementation branch. It binds the retained wheel path and all three accepted digests, diagnostic-evidence digest, current clean Toolkit CodeHead, unchanged campaign P0/runtime identities, and the exact Task 3 continuation. Luna may then execute Task 3 Step 5 onward: copy the already-retained wheel into the temporary closed set, make the one already-authorized setuptools request, and continue only if every frozen tuple and 66-member equality gate passes. Any drift invalidates the authorization before mutation.

### 7.5 Candidate invalidation after the real MAP format defect

The candidate and fresh runtime at Toolkit CodeHead `171a46060225479a6031c2499cbb6298e4b83d6a` passed all package/runtime gates but failed the first unchanged-P0 public inspect with `KEIL_MAP_INVALID` because Section 4.4 was not implemented. They remain valid evidence for their bytes but are not H1-eligible and cannot be patched in place.

After the Section 4.4 product correction is independently accepted, preserve the current candidate/extracted/runtime state identity and build a new candidate under distinct campaign paths `runtime/mapfix-candidate` and `runtime/mapfix-candidate-extracted`. The current managed runtime remains the only active runtime until the new candidate passes all verification. Because the two backend wheel bytes were correctly cleaned after their prior one-time build, one new bounded acquisition of each exact official artifact is permitted for this invalidation-triggered rebuild, using the accepted identities from Sections 7.1 and 7.4: setuptools SHA-256 `51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`; wheel corrected SHA-256 `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab` plus BLAKE2b-256 `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449`. The same direct-URL, redirect-rejection, filename/size, ZIP, no-resolver/index/dependency, 66-member, source-binding, trust-anchor, candidate, and cleanup gates apply.

After the map-fix candidate is verified, preserve the `171a4606...` runtime lineage, prove no process uses it, retire only the exact campaign `data/runtime`, and fresh-bootstrap the new candidate. Do not use same-version upgrade/repair. The final unchanged-P0 inspect/dry-run must capture the real AXF/MAP hashes, produce the exact Section 4.4 sizes, select SPL, and return exactly the frozen 37 portability blockers before Task 4 begins.

## 8. Acceptance criteria

- Real inspect resolves `Project/OBJ/LWIP.axf` and `Project/LIST/LWIP.map`, captures their exact hashes, and selects SPL from two independent generic evidence categories.
- Real MAP fallback reports Code `62772`, RO Data `1004`, RW Data `1576`, ZI Data `406440`, derived ROM `65352`, and RAM `408016`, with RO/RW total cross-checks passing.
- Focused Toolkit tests and independent complete-diff review pass without a new public option, agent logic, runtime, provider, backend, or controller.
- The project correction is exact-digest authorized, limited to the frozen 36 encodings plus one derived profile and one startup C file, and preserves original Keil inputs/historical outputs.
- Corrected public conversion/configuration applies only unchanged plans; two public builds are reproducible and all parent H1 gates pass, including vector/symbol/memory proof and a fully free `0x2002EFF0..0x20030000` interval.
- `testtime` and D4 behavior remain unedited, no mailbox exists, project and Toolkit worktrees are clean, campaign scratch is empty, remote state is unchanged, and no hardware operation has occurred.
