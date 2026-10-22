# STM32TK-120 documentation and local prequalification checkpoint

Date: 2026-10-22. This is a provisional evidence record, not a release verdict.

- Accepted base: `b80a712e1738ae6900f42bffc3ab6c80198654d1`.
- Documentation CodeHead before this report correction: `43cc9a17144e7e091b0daa1183391b7f078930d2`. The initial seven-file documentation commit was `45444fb1810320be4875b45ed0425b72c7deef6c` and was independently reviewed by the primary agent. An independent `release_review` finding identified that extraction into shared `C:\tools` could collide with the ZIP's outer `release/` directory; the version-specific BundleRoot correction was independently reviewed and integrated by the primary at `8c4760d670e448edc6adb13f4cc0c5347c87486b`. The seven-file recipient revision at `55fc8df0436b0be10d225eb4d06a9d68bc49d707` makes guidance valid before and after publication; primary acceptance is separate from this author report.
- Provisional package source: `d2c25706f87fc0c132e8cd1eeb774a32b6d9ebfa`, including the bounded Windows `SystemRoot` build correction. UI test-only source: `9d225d1519e41eee1ce4243497cb95769366bf9d`. These are separate inputs; no final integrated release CodeHead or downloadable asset hash is assigned.
- Specification and plan owner, integration reviewer and release disposition owner: primary conversation agent. Package/installation evidence owner: `build_v120`. Software evidence owner: `verify_v120`. UI test correction owner: `ui_release_tests`. Documentation implementer: `docs_v120`. Primary independently reviews the complete documentation difference and does not delegate acceptance to its author.
- Remote action: none in this checkpoint. No tag, Release, push, PR mutation or hardware access was performed by this implementer.

Local evidence is under `D:\codex-tmp\tk12022`:

| Layer and owner | Recorded result and evidence |
| --- | --- |
| Bounded Windows build correction, `fix_windows_build` | Original sanitized child process lacked `SystemRoot` and failed during pip SSL import. The whitelist correction retained the isolated/offline inputs; 76 release/security tests passed. See `diag/minenv-stderr.log`, `diag/systemroot-stdout.log` and `fix-run/release-security.log`. Primary independently reviewed the three-file fix and ran 7 focused checks; see `primary-review.json`. |
| Official candidate construction, `build_v120` | Two clean builds at `d2c25706f87fc0c132e8cd1eeb774a32b6d9ebfa` produced 13 byte-identical assets. Checksum, archive, bundle, 64-wheel closure, license and SBOM validation passed. See `build-pre-independent-compare.json` and `prequalification-summary.json`. These hashes identify only this provisional package, not the final recipient download. |
| Isolated final-position fresh install, `build_v120` | `Check` missing → `Bootstrap` → healthy 1.2.0 generation 1. `pip check`, Toolkit/Monitor launchers and PyOCD module/executable 0.45.1 passed. See `install-fresh` and `prequalification-summary.json`. |
| Isolated v1.0.1 upgrade, `build_v120` | Verified historical ZIP SHA256 `ed51a0e9773acc26010bfadae595fddbf99ba298080784a3d600509d861f1f8b`. v1.0.1 Bootstrap → v1.2.0 read-only Check repairable → authorized Repair → healthy generation 2. User marker hashes remained equal; the old runtime entered quarantine. See `install-upgrade` and `prequalification-summary.json`. |
| Installed loopback HTTP smoke, `build_v120` | Authenticated API/UI root 200, unauthenticated 401, wrong Host 403; service record removed and port closed after stop. No probe operation. See `install-fresh/http-smoke.json`. This is not interactive browser qualification. |
| Monitor Python, `verify_v120` | Full run: 1167 passed, 12 skipped, one `test_named_monitor_performance_acceptance` failure. History query p95 was 118.805 ms against a strict 100 ms requirement during concurrent work. See `verify/out/python-monitor/full.log`. A quiet repeat is pending; the failure is not converted to PASS. Native overall/risk-core-v2 coverage was 3161/3488 = 90.625%; the 95% risk-core gate is numerically **UNMET**. See `verify/out/python-monitor-summary.json`. |
| UI, `ui_release_tests` and primary | At exact test-only commit `9d225d1519e41eee1ce4243497cb95769366bf9d`, the full run passed 523 tests with one skip; native branch coverage was 2861/3068 and all 34 positive-denominator source files met 90%. Type checks, lint, build and distribution verification passed. See `ui-fix-run/coverage-commit.log`, `coverage-summary.json`, `coverage-check-commit.log` and the `*-commit.log` command logs. Primary independently reviewed the complete seven-file diff in a clean exact-head tree and ran 71 focused tests in 15.82 s, all passing. Final integrated release checks remain pending. |
| Toolkit Python, `verify_v120` | The original full attempt was **INCOMPLETE** with seven observed failures and no final JUnit or parent coverage. Five long-path cases and one CRLF case passed focused reruns after short-path/LF preflight; `in_memory_configure_and_build_fail_closed` remained unclassified. A corrected three-shard full matrix (6,476 nodes) on `8c4760d670e448edc6adb13f4cc0c5347c87486b` started at 23:17 local time and was pending; no full-suite PASS or coverage conclusion is assigned. |

Release qualification was **not accepted** at this checkpoint. The Monitor risk-core
threshold was unmet; the performance failure and Toolkit/final integrated checks were
unresolved. No v1.2.0 coverage exception had been approved at this checkpoint. The
earlier v1.0.1 exception and physical evidence do not transfer. Interactive browser,
IDE and hardware qualification had not been newly verified for v1.2.0 at this checkpoint.
Final package identity, later results, any approved exception and release disposition
belong to the actual
[v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0)
and subsequent master qualification records, not this provisional package's hashes.
