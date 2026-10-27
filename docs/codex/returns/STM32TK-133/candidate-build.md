# v1.3.3 frozen candidate

Frozen source: `46ca09084bbe39f670714d19d7d55f9365ef06be`. Status: **LOCAL_CANDIDATE_NOT_QUALIFIED**.
Date: 2026-10-27. Primary independently verified the two Claude-executed official builds.
The user has authorized source/tag push and Latest after validation; unmet permanent gates
still require disposition for this specific candidate. No earlier exception is reused.

## Build identity and checks

- Both clean detached worktrees contained exact canonical Git bytes and no ignored build residue.
- Official offline builds exited 0 in 32.26 s and 30.97 s; all 13 filenames, sizes and SHA-256 values match.
- All 12 CHECKSUMS entries and the checksum file itself were verified. Manifest source/version are exact; public inventory is 52 MCP tools and 9 skills.
- Windows bundle was extracted with path/symlink/collision checks. Official `verify-bundle --json` exited 0.
- Frozen source differs from reviewed CodeHead `d281addbbdb70e36c270e24828868d7e936dc6e1` only by governance/evidence files; product/test bytes are unchanged.
- No installation, original-project change, hardware action or remote mutation occurred.
- Final installation and independent VS Code validation remain **USER_VALIDATION_PENDING**, owned by the user.

## Files

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| CHECKSUMS.sha256 | 1073 | `a71744ac8a602441bf49a47b20d04111f7d76cf99958d886d64ccaebcf698272` |
| LICENSE | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| THIRD-PARTY-NOTICES.md | 2615 | `241426e64abd43801dc97d0c2a3fcc6c39f17246329031c0a52a5e52149b7939` |
| compatibility.md | 2014 | `e3ceff749cfd97548ddc9a61fc80884c502b94ff07964596b4377010b355de13` |
| licenses.zip | 413750 | `1b6e46780391d74b146853f1306582bb5433c35193f370731135afc325ad9ad9` |
| monitor-assets.json | 970 | `0fe98bbd73abff784e9832c12a42a1b91cc0fda4bea3ce2d7d3f68c1a8b6bc4c` |
| release-manifest.json | 15814 | `5391dba36fb7bcb564116783e595a73118c9bbbf4e6418839a232808036c24ed` |
| sbom.spdx.json | 191430 | `4c405d1219296b9e6aa9d0549bac6209dd97bbfe3fcaeb8b17727e86b6788141` |
| stm32-toolkit-1.3.3-source.zip | 19562020 | `5e3251ea300a589a5f72c7ed0a2c08cb11d3c7905287792e577d32ecfd943645` |
| stm32-toolkit-1.3.3-windows-x86_64.zip | 116350730 | `52829b90bdd2ebf5b8dd61825ba7c423f5679597b23a35487bf3f8ca4c51378a` |
| stm32_monitor-1.3.3-py3-none-any.whl | 1556130 | `f2b960d18abc18445659c0f7f7e5fc29902e6c292c45f73fb464feb521f18ac7` |
| stm32_toolkit-1.3.3-py3-none-any.whl | 4241849 | `732c28ef502dbc89a7919f2b3be1ae46a23fe1781f89337968add915393f3714` |
| troubleshooting.md | 1737 | `48973953d6ae85e16a45cc2c41f65571697a496044a210fea95a43649b153710` |

## Qualification requiring explicit disposition

- toolkit-overall: 15211/18418 = 82.5877% (floor 90%, UNMET).
- toolkit-risk-core-v2: 14157/17176 = 82.4231% (floor 90%, UNMET).
- monitor-overall: 3292/3564 = 92.3681% (floor 90%, PASS).
- monitor-risk-core-v2: 3292/3564 = 92.3681% (floor 95%, UNMET).
- UI is 2938/3147 = 93.3588%, every positive-denominator source file meets 90%.
- Original full-file performance run retained one append failure: 124.9428 ms p95 against 50 ms. Exactly one controlled monitor-only comparison per version passed (old 21.4292 ms, candidate 19.5793 ms); cause of the original failure is not established. No relaxed threshold or full-file post-comparison rerun.
- Platform/historical-data skips remain. Native branch data reuse is bound to exact source bytes, not a single final-head full repository rerun; old arcs for changed sources were removed. The final single documentation assertion correction has targeted passing checks and reuses unchanged installer behavior results.
- Real CubeMX vendor generation is not verified (offline firmware package unavailable); only that external adapter is synthetic in the otherwise real GCC/new-project journey. No physical qualification is claimed.

See [version review](version-review.md), [source/run mapping](release-evidence.json) and the [permanent qualification contract](../../../testing/release-qualification.md).

Local raw evidence: `D:/codex-tmp/r133`. Build records `package-build-a.json` / `package-build-b.json`; native dispatcher `verify-package/summary.json`; canonical records `package-canonical-a.json` / `package-canonical-b.json`; exact asset and bundle record `frozen-package-verification.json`.
Verification record SHA-256: `ba32bdb5edd88fa305fdc0a490a4bce91186ce62b033de67da459f7eae6353e1`.
Qualification record SHA-256: `255f8a9f79794a465fbf1c3b17793ddbc88bf0dbff1d353daabb4c874f3008dd`.

Next step after candidate-specific qualification disposition: non-forced source/tag push, draft upload, server digest verification, Latest publication, then anonymous download/hash of all 13 files. Publication status in both READMEs and current guides must be updated only after observed success.
