# v1.3.0 independent review and local delivery

Date:2026-10-24. Verdict: **ACCEPTED_WITH_FIXES for offline software and the local Release build**. This is not public publication or full release qualification.

Accepted base `6b4c13b6fa76f320503b14679c8eb7bfc712c9af`; frozen CodeHead `1e6ea849c21fb3786d60dba0254acb375d016a62`; implementation branch `codex/v1.3.0`. Artifacts identify this CodeHead. Subsequent report/status-only commits are intentionally outside that frozen source archive. No remote mutation was authorized or performed. Primary owns architecture/specification/orchestration/full-diff review/acceptance; local Claude Code CLI2.1.308, with the unchanged configured deepseek-v4.1-flash[1m] provider, owns implementation, tests, fixes and implementation reporting. No Codex-hosted implementation subagents or ownership override.

## Review scope

The complete accepted-base-to-CodeHead diff was reviewed in a separate clean checkout, reusing the independently accepted EXTERNAL-FIRMWARE review and inspecting every additional version, compatibility, installer, release, schema, inventory, test, skill and documentation change. The functional imported-firmware implementation is byte-for-byte unchanged from accepted feature4f002cd1479dc98c2dc9c48d7e75dddf896de2f2; only Toolkit version, legacy producer list and ninth skill change in Toolkit source during integration. The primary checked CLI/MCP signatures and real result fields against the documentation. Corrections replace pending49-tool language with52/9, reconcile installer expected names, bind setup hashes to actual archive bytes, distinguish published1.2 from local1.3, provide a matching1.3MCP launcher and use the actual `version` subcommand instead of `--version`. No blocking source finding remains. One blank line at EOF in test_external_firmware_routing.py569 is a retained nonblocking diff-check warning; no false claim of a completely clean whitespace check.

The source is1.3.0 across Toolkit/Monitor/plugin/UI/runtime launchers/release policy/schema. Monitor pins Toolkit==1.3.0. Historical1.2producer/runtime recognition remains explicit; no user's project or existing runtime was migrated. Protocol/schema numbers and third-party dependency pins remain unchanged. Earlier accepted preflight/diagnostics/probe discovery, snapshot builds, comment-copy skill, bounded startup and explicit memory-layout slices are included in this release source.

## Exact-source evidence

All rows below ran against CodeHead1e6ea849, on Windows with Python3.12.14, matching Toolkit/Monitor source paths, ARM GNU14.3.1 for the selected compiler fixtures, and isolated temporary/cache directories. CLI verification uses one supplied native PowerShell command per invocation, process-local native registration flags and strict empty MCP configuration. Actual tool events and JUnit are the authority. Details and exact commands: [test-results.json](test-results.json).

| Evidence owner / scope | Result |
| --- | --- |
| Claude CLI / version, generation, migration, snapshot, build, release and public contracts |755 passed|
| Claude CLI / Windows setup, legacy-runtime fake upgrades, launchers and plugin/docs contracts |63 passed|
| Claude CLI / external firmware, debug firmware, managed flash, hardware adapters, service/client/worker/backend/protocol |1061 passed|
| Claude CLI / Monitor affected version, CLI, runtime, models, service, exports and package boundaries |288 passed|
| Primary / independent clean-head feature, inventory, CLI version, archive anchor and release identity |59 passed|

The four CLI groups total2167 tests, zero failures/errors/skips. The59 independent checks are separate repeated evidence, not2167 additional distinct cases. Prior failed fixture/order runs and corrected ownership/source labels remain in EXTERNAL-FIRMWARE/review.md and D:/codex-tmp/fi24; they are not erased or retroactively relabeled. The pydantic-settings lifespan forward-reference warning remains nonfatal. Tests use fake/injected hardware; static inert preflight and import-blocked missing-dependency cases do not access a physical driver. Windows setup tests only create fake packages/runtimes in temporary directories, not a production install qualification.

## Build and artifact verification

Both official-builder runs used the same frozen commit, canonical raw Git blob bytes and the pinned offline wheelhouse. The primary verified all821 tracked files against raw Git blob hashes. Windows newline/stat behavior was resolved by materializing the existing committed bytes and refreshing the identical index; no source implementation, commit, global Git setting or persistent shell policy was changed. Build processes alone use core.autocrlf=false/core.eol=lf so archive and wheel bytes agree. Two product wheels use throwaway build environments; the existing installed runtime is unchanged.

Native build calls returned without console output. Their success is established by complete activated output, independent byte/hash/closure checks and a separate extracted-bundle official verification returning status=ok; silent CLI prose is not used as acceptance evidence. Both builds produced all13 files **byte-identically**. Independent verification covers12 checksum entries plus checksums-file equality, ZIP/wheel CRCs,821 source members,1138 exact bundle members,64 runtime wheels, every product-wheel payload's source binding, exact product metadata/dependency,52 tools/9 skills and7 Monitor assets. The official extracted verifier reports source1e6ea849 and manifestSHA256 `d36d7ef2344c1efd694d8b0573d2d33024f88948a605ddbbb394e4b9ecc1222c`.

All13 assets were copied to `D:/WorkSpace/STM32-Toolkit/dist/v1.3.0` and independently rehashed after copying. [artifact-verification.json](artifact-verification.json) records every filename, size and SHA256. Native build/verify commands and outputs are retained under `D:/codex-tmp/fi24` in build-a/b-command.txt, build-a/b.jsonl, verify-bundle-command.txt, verify-bundle.jsonl and verify-bundle-result.json. Reproduction uses tools/release/build_0900_artifacts.py build with this CodeHead, the recorded wheelhouse and a new external output directory.

## Qualification boundary

No original mobile-robot-controller project changes/build, physical probe discovery/attach/flash, existing runtime promotion, GitHub push/PR/tag/Release action occurred. Imported image software success does not prove a board runs, and imported receipts do not admit managed debug/Monitor/Target provenance. Full new-release coverage, real fresh installation/upgrade/rollback, interactive browser/IDE and physical qualification remain pending separate execution/authorization. Permanent gates remain unchanged and the1.2-only exception does not transfer. Native UV4 build backend, actual VS Code extension enumeration and migration baseline comparison remain product gaps; encoding/startup/memory support retains documented bounds.
