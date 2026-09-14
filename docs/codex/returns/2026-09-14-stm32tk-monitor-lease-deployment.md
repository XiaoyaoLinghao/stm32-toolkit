# Lease fix deployed and original physical evidence published

Deployment and existing-evidence verification **PASS**. User authorization: "开始部署，然后进行验证测试". Primary performed deployment and verification; Luna/max implementation and independent review remain as recorded in [the accepted correction](2026-09-14-stm32tk-monitor-physical-lease-link.md). Deployed source `0c375c03ab6afa4192a37d5732009b82845216a7` contains product code `72e9706c9cf60dc3204b351a98d3d01623125dd5`. No product code changed in this deployment, and no remote action occurred.

## Installed runtime

- Candidate Python: `D:\stm32tk-data\fault-controlled-20260911\candidates\lease-20260914\runtime\0.9.0\Scripts\python.exe`.
- Business DataRoot: `D:\stm32tk-data\fault-controlled-20260911`. Select that Python explicitly; default launchers based on the business root still select the older runtime. Preserve both previous installations.
- Candidate runtime-state: candidate root's `runtime\runtime-state.json`, SHA256 `bc361d020762a1e1393004ab10292a23fe655a36ce37d63e52935b71c9f4f8bf`.
- Release manifest SHA256 `7eb76e05d247b8e46bad089997b1dcab4611fa57dfc08e632586e42e11984c3d`.

Existing release builder used the retained closed build wheelhouse, with no dependency upgrades. Its first invocation stopped before creating the bundle: the new worktree still had persistent `core.autocrlf=true`, despite LF files created using a command-scoped override. Archive bytes failed the bootstrap trust anchor. Classification ENVIRONMENT; no installation/hardware or product change occurred. Correcting only the owned packaging worktree to `core.autocrlf=false` and `core.eol=lf` allowed the same builder to complete. Keep both results; this is not a product test failure or a repeated valid build.

Bundle verification passed. Existing setup Check missing -> Bootstrap exit0 -> Check exit0 produced bundle=ok, runtime=healthy, runtimeState=matching. All 145 installed Toolkit/Monitor package files match their verified wheels. The final installed `pyocd.exe --version` returned 0.45.1; this only checks the executable, with no probe access.

## Actual production verification

The new installed Python ran public `-I -B -m stm32_monitor physical publish` against the original business evidence/history, using saved exact argv. It returned exit0/OK. A fresh process then used public `load_monitor_run_reference` and `TestRunRepository.load` to authenticate the published reference and its original Target link.

- Original Target: `target-v2-53b0c81ffeb50ab65bd6c0ad815ad273`, retains `lease-203e4bda26ec46bd9b7424c26f36cfec`.
- Original Monitor: `6a8508ee-95ec-43f0-a638-73d37d7038c5`, retains `lease-8adfb28e758f48759ce46b91594d85f6`; sequences 0..300 exclusive.
- Published run-ref SHA256 `37e15560615974b49d041cd4386d3fbcbebaea76df395afd09581ae643739fc1`, exactly matches the previously accepted isolated verification.
- All 32 original evidence files remain byte-identical. Both old runtime-state files, firmware ELF and flash receipt match preimages. Firmware tracked tree is clean at `8755ba8fd0c678f32d7d23e7d827e84317026429`; existing generated build artifacts and backup are preserved.

The specific cross-operation lease publication blocker is resolved in the installed runtime and original evidence store. This is verification of existing physical evidence, not a newly executed hardware PASS. No probe enumeration/connection, flash, reset, sampling, source change, new timed attempt, Diagnostic resolution or FixVerification occurred. Original programming and 300-batch sampling PASS remain valid. P4/T10/Task11/Task12/VS10-A remain incomplete; next work is the prepared P4 repair and its corresponding bounded hardware/after-window verification.

## Retained evidence

Run root `D:\codex-tmp\t10-lease-deploy-20260914`: execution card/ledger, initial build rejection and correction record, successful build, bundle verification, setup before/bootstrap/after JSON and exits, installed-byte verification, final launcher result, publication argv/result/exit, fresh-load/hash verification, runtime binding and cleanup disposition. Bundle and clean LF checkout `D:\codex-tmp\t10-lease-pkg` remain for deployment provenance and handoff; temporary directory is empty. Previous policy-rejected cleanup was not retried. Existing consumed Monitor configs/markers and expired attempt were not rewritten.
