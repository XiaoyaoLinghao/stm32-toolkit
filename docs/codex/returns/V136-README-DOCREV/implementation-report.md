# v1.3.6 archive README documentation revision — 2026-10-31

**ACCEPTED_WITH_FIXES / FOUR_REVISED_ASSETS_PUBLICLY_VERIFIED.**

The original v1.3.6 Windows/source ZIPs retained pre-publication README text even
though master had been updated after packaging. This was a real archive documentation
defect, not a firmware or tool invocation defect. The user explicitly selected updating
v1.3.6 documentation attachments/checksums, preserving the tag and recording the revision.

## Source and ownership

Primary Codex owns specification, bounded plan, orchestration, complete independent
review and acceptance. Local Claude Code CLI, retaining the configured
`deepseek-v4.1-flash[1m]` route, owns both README edits and the master-only existing-test
adjustment. Native inventories matched, both edit audits were accepted, and no
Codex implementation fallback occurred.

Original archive/tag base: `b00cbc4edee191712dd6da7e1beb073ff4a74f28`.
Documentation archive source: `d3a82a0d03e1c71691654423e5f79ec842f168a9`.
Master integration base: `2606eb7b1fd3f105c3d5442f417d47fdb06acb8f`.
Reviewed master CodeHead before this report: `1652aa73f66b9da063d4d5d61ee6d9e27d761827`.
The report does not contain its own commit SHA. Subsequent authorized push and
remote readback are retained separately in run-local delivery evidence.

The archive source differs from the original tag in exactly `README.md` and
`README_zh-CN.md`. Both now state v1.3.6 is published, use `/releases/latest`, link
the corrected pinned v1.3.6 receiving guide, and identify v1.3.5 guidance as historical.
The revised source commit is recorded honestly in the existing manifest schema.
The tag stays unchanged; GitHub automatic tag archives still represent that old tag.
Use the uploaded source ZIP for the revised README.

## Verification and delivery

Two independent archive assemblies from the same reviewed inputs are byte-identical.
All 1152 source files were compared: only the two README payloads differ. All 64
product/dependency wheel files (128 copies across the bundle's two release trees)
are byte-identical. Runtime code, bootstrap, schemas, version authorities, SDK pin,
frequency, authorization, identity and lease contracts remain unchanged. Nine external
assets, including wheels, SBOM and licenses, retain both original bytes and GitHub asset IDs.
SBOM continues to describe the unchanged original runtime/wheels.

The separately delegated existing official command
`build_0900_artifacts.py verify-bundle --toolkit-root <independent-extraction> --json`
returned `status=ok`, `productVersion=1.3.6`, and the documentation source SHA above.
Inventory, native harmless PowerShell smoke and main command all matched; CLI and
dispatcher exited0. The native tool supplied no numeric exit, retained as null.

At the reviewed master CodeHead, the single affected existing test
`test_plugin_layout.py::test_readmes_are_concise_and_distinguish_published_and_local_contracts`
passed: fresh JUnit1passed/0failed/0errors/0skipped, actual test subprocess exit0,
all tracked source hashes unchanged, accepted native delegation audit. Its existing
checksum filename prohibition now applies to command blocks, allowing the explicitly
requested revision metadata in prose while retaining every other landing-page assertion.
Primary independently reviewed the complete three-file master diff and both archive
README blobs in clean exact-head trees. Diff checks passed. No full-suite or hardware
rerun is claimed; the original source-bound runtime evidence remains historical.

GitHub Release429783935 remains public Latest v1.3.6. Authorized `gh release upload
--clobber` replaced exactly four attachments and `gh release edit --notes-file` added
the bilingual revision note while retaining the original publication record and old hash.
Every gh command exited0. Server metadata matches all13 expected digests, unchanged
asset IDs were checked, and the four changed files were anonymously downloaded with
HTTP200 and exact byte counts/SHA-256. The downloaded Windows ZIP's README and
manifest were inspected again.

Current Windows ZIP SHA-256:
`acd94c641130c36e10692d36d2e18e4a5a2479fc2fda7fdac18433166dcbabad`

Changed attachments: Windows ZIP, source ZIP, `release-manifest.json`,
`CHECKSUMS.sha256`. Exact commands, digests, source/asset member counts and audit
results are in [evidence.json](evidence.json).

## Retained limits and abnormal preparation records

The coordinator's first two preparation checks failed before any archive assembly:
first an archive-only LF override was incorrectly applied to `git status`, then the
LF override produced unrelated differences from the original archive's normal Git
filters. Both scripts/results were retained. After explicit user authorization
“允许这一次有界重试”, the corrected ordinary Git archive invocation assembled the
revision successfully once; no failed record is relabeled PASS. A local merge also
initially lacked committer identity; the already approved command-only Codex identity
was used, without modifying persistent Git settings. Expected README merge conflicts
were resolved by selecting the exact reviewed Claude blobs.

Synthetic-state checks confirm original manifest -> `matching`, revised manifest ->
`source-conflict`. Existing v1.3.6 installations need no reinstall or runtime Repair;
this identity guard is preserved, not bypassed. The shell reported exits0/1, while
native Python numeric exits were not separately captured and are not invented.
No installed runtime or hardware was accessed. Other bundled prose remains its original
build-time snapshot; the README and Release note identify current online instructions.
Permanent unmet coverage gates, original candidate-specific exception boundaries and
recipient installation/IDE/MCP limits remain unchanged.
