# v1.3.6 bounded implementation plan

Base: 37f69ca4acc2b879d4227a099384241ec39080f4.
Governing specification: ../specs/2026-10-30-v136-tool-evidence-design.md.
User approval: start repair, advance to v1.3.6, build/upload release and merge master.
Primary owns acceptance; local Claude CLI owns edits/tests. Exact dispatch task JSON
and raw native events live under D:/codex-tmp/v136-evidence, not product scope.

1. Migration presentation slice: delivery.py and test_armcc_float_abi.py only.
   Add deterministic PLAN/APPLY floatAbi and its warning using the existing resolver;
   do not change conversion report bytes or target selection unnecessarily.
2. Build evidence slice: bounded build identity/model/runner/helper/schema and related
   tests. Add optional ABI provenance and toolkitVersion; preserve exact field
   validation with explicit optional keys, readers, identity round-trip and presets.
   Primary reviews source before separately delegating exact-command verification.
3. Telemetry/documentation slice: existing tests and current user/architecture/
   changelog documentation. Lock null/value semantics, historical debug paths,
   source/report evidence and v1.3.5 publication link.
4. Version slice: active version authorities and affected existing version tests to
   1.3.6; current release/receiving documentation only. Coordinator supplies canonical
   hashes for existing Setup trust anchors after versioned inputs freeze. No broad
   history replacements or extra legacy recognition.
5. Integration: isolated short test roots, fixed verified Python/toolchain/dependency
   paths, exact commands and fresh JUnit/exit/source records. Group commands below
   native foreground budget when possible; coordinator reconciles already-started
   pending runs without reruns. Independent review uses exact final CodeHead.
6. Package: existing official builder, two clean canonical checkouts, complete cached
   pinned dependencies/backends and reproducibility verification; no current runtime
   installation. Record coverage/reuse/limitations honestly before publication.
7. Remote: fresh readback of master and v1.3.6 absence; non-force fast-forward
   integration (merge commit only if required and reviewed), new annotated tag,
   draft upload of exactly verified assets, final Release and anonymous byte checks.
   No existing asset replacement, force push, hidden credential access or new hardware.

Each bounded edit phase starts from a clean isolated source state and supplies exact
write/read sets; subsequent changes need their own task and source ledger. Correctable
review findings remain on the slice branch; after two nonconvergent rounds return to
design. Executed errors/denials keep their original disposition, no blanket retry.
Completion: reviewed code/tests/current docs, 1.3.6 reproducible artifacts, source
integrated into master and verified public Release, plus concise acceptance record.
