# Independent Keil-to-GCC delivery

Accepted local base: `b7895f771d9eeecab308af82124f487ed5d3bcbe`. Governing specification: 2026-10-26-gcc-delivery-contract.md. Primary owns design/review; Claude Code CLI owns product implementation/tests. Core content-identity work integrates separately. No original-project write, hardware, installed-runtime change, version change or remote publication.

## M1: independent delivery engine

Add a delivery planner/apply engine under migration/ using the existing Git-free ConversionAnalysis. Keep the historical low-level migration plan/apply decoding intact during this slice; M2 switches the public workflow to the new engine. Do not create a temporary Git repository, fake a SHA, or run Git as a prerequisite.

The source is an existing canonical directory, destination an explicitly named absolute disjoint directory whose parent exists. Reject source=destination, nesting either way, existing nonempty destination, links/reparse points and casefold collisions. Bind the exact destination and its absent/empty state into the plan ID, alongside selected Keil target, choices, source inventory and final output bytes. Git is optional metadata; the delivery plan does not need it.

Inventory the complete regular-file source tree, excluding .git directories/files explicitly. Preserve relative layout and licenses/headers/dependencies. Bound traversal depth, file count, per-file and aggregate bytes; report limits or unsupported links instead of silently omitting files. Do not guess external dependencies or copy outside source. Existing inspection diagnoses unresolved/out-of-root dependencies. Copied old output files do not count as a new successful GCC build.

Planning writes nothing. Analyze sources and overlay the reviewed source patches, generated startup and .stm32-project.json onto that inventory in memory. Render the complete CMake, toolchain, linker, presets, VS Code files and managed manifest using the existing generation validators/renderers, through a small new pure rendering seam if necessary; do not duplicate templates or hand-edit digest fields. Generated output collisions with copied source files must be explicit in the preview/diff. The originals remain untouched. Include hashes and sizes for all copied/generated/replaced outputs, source patch diffs and copied/excluded counts; do not return raw binary payloads.

Use a new conversion report schemaVersion 2 with sourceSnapshotSha256 and a content-based planId. It carries fixedSections/startup/include merges/ABI information as applicable; Git is absent unless explicitly recorded as optional metadata, never required for configure. Keep schemaVersion 1 report decoding strict for existing projects. Do not relax fixedSections/memory validation. The new renderer and normal subsequent configure/build must agree on the managed manifest and report.

Apply requires authorized=true plus the exact freshly recomputed plan ID. Revalidate inventory, options, destination ownership and output bytes; stage only in a newly created owned sibling of the destination, then publish a complete directory. Failures leave the source unchanged and do not expose a partial successful destination. Never overwrite a nonempty directory or delete unrelated files. Empty-destination state changes between plan/apply must be rejected. Recheck source snapshot before final publication; a concurrent source change invalidates the plan. Cleanup is bounded to owned staging, and cleanup failure is reported honestly.

The result reports output root, source/output snapshots, report path and that configuration was generated; `built`/`flashed` remain false. It directs the caller to bind the new root and use normal GCC build/flash. Output build inputs must not refer to the original absolute source or staging path.

Allowed M1 implementation: new migration/delivery.py (and one small value/helper module if needed), generation/configure.py pure rendering/report-schema support, migration/__init__.py exports, focused new test_migration_delivery.py and relevant existing generation/report tests. Do not edit CLI/MCP/workflows in M1. Existing conversion analysis and legacy apply behavior remain stable. Known supported UTF-8 fixtures are enough for this slice; encoding preparation and WFI intent are M3, not silently claimed solved.

M1 evidence: real no-Git source plan/apply; source byte hashes unchanged; destination complete; absence/empty/collision/nesting/reparse limits; plan drift, source/header change, write failure cleanup; copy inventory includes license and unlisted include headers; normal configure accepts output; real GCC build after copying ONLY output to a different isolated directory and making original unavailable. Tests own synthetic fixtures only. No real hardware, fake binaries as proof of real compilation, or modifications to user projects.

## M2: public workflow and guidance

Add explicit destination to keil convert CLI and MCP, and switch them to the delivery engine. Omission returns a clear destination-required diagnosis, never silently mutates the source. Keep preflight read-only and Git-free; remove Git from readiness requirements and offer the complete plan -> new output -> configure/build -> authorized flash journey. Retain all requested startup/layout/extra-region options, and bind optional explicit debug/editor configuration choices. Update CLI/MCP tests and VS Code skills; README stays short and bilingual.

## M3: source preparation and intended WFI return

Use declared per-file encoding and reviewed comment-only replacements in destination copies; include required headers, not just compile units. Reuse the existing normalization skill contract, do not guess charsets or rewrite original sources. A bounded explicit WFI normal-return choice belongs to the reviewed source plan (path/function plus existing content hashes), allowing a known void WFI-only wrapper to become ordinary GCC code that returns. No Keil disassembly prerequisite. Unknown asm and MSP/control-flow ambiguities remain diagnostics. Show the intended behavior change in the preview/report; no binary-equivalence claim.

M2/M3 receive narrower file/test lists at dispatch after M1 review. Final integration exercises migration and creation into independent no-Git GCC projects, with recording/fake probe admission and real GCC output validation. Physical and final user IDE validation remain separate.
