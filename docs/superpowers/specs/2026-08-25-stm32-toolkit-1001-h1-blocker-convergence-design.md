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
- a source whose case-insensitive basename matches a canonical bare Standard Peripheral Library peripheral unit `stm32<family>xx_<peripheral>.c`, excluding names containing `_hal_` or `_ll_` and excluding `stm32<family>xx_it.c` and `system_stm32<family>xx.c`.

This `source` evidence plus the existing `define=USE_STDPERIPH_DRIVER` evidence selects SPL for the real project. The rule is based on source-set semantics, not directory or project names. HAL/LL evidence, mixed-framework evidence, a lone define, a lone source signature, or ambiguous qualified frameworks must continue to fail closed.

### 4.3 Tests and release impact

TDD tests must first reproduce the real XML nesting/listing MAP defect and SPL source-set ambiguity at the accepted base. GREEN tests cover core inspection, baseline capture, CLI/MCP parity, fallback MAP location, containment failures, HAL/LL conflict refusal, and no false selection from weak evidence. Run only the focused Keil/migration/workflow/CLI/MCP tests plus directly affected regression. Rebuild and verify one Windows candidate because Toolkit bytes change; no full release matrix is triggered.

## 5. Project portability correction contract

The project correction is not Toolkit product logic. It is one local Git change bound to a machine-readable proposal and a SHA-256 over the exact proposed P0-to-portability diff before apply. The standing user instruction authorizes the Sol primary to approve that exact digest without another interactive prompt. Any byte drift invalidates approval.

### 5.1 Encoding normalization

- Scope is exactly the 36 paths returned as `ARMCC_SOURCE_ENCODING_UNSUPPORTED` by the frozen plan.
- Every original file must fail strict UTF-8, pass strict GB18030 decoding, and round-trip byte-exactly through GB18030 before it is eligible.
- Re-encode the identical Unicode scalar sequence as UTF-8 without BOM. Preserve the decoded newline sequence; do not format, rename symbols, or change code/comments.
- Record path, original size/SHA-256, encoding, decoded-text digest, output size/SHA-256, and a proof that decoding the output as UTF-8 yields the identical scalar sequence.
- Any file failing these rules stops the correction; no replacement characters or fallback encodings are allowed.

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

## 8. Acceptance criteria

- Real inspect resolves `Project/OBJ/LWIP.axf` and `Project/LIST/LWIP.map`, captures their exact hashes, and selects SPL from two independent generic evidence categories.
- Focused Toolkit tests and independent complete-diff review pass without a new public option, agent logic, runtime, provider, backend, or controller.
- The project correction is exact-digest authorized, limited to the frozen 36 encodings plus one derived profile and one startup C file, and preserves original Keil inputs/historical outputs.
- Corrected public conversion/configuration applies only unchanged plans; two public builds are reproducible and all parent H1 gates pass, including vector/symbol/memory proof and a fully free `0x2002EFF0..0x20030000` interval.
- `testtime` and D4 behavior remain unedited, no mailbox exists, project and Toolkit worktrees are clean, campaign scratch is empty, remote state is unchanged, and no hardware operation has occurred.
