# STM32TK-120 v1.2.0 delivery execution record

## Published disposition — 2026-10-23

The user explicitly approved **USER_APPROVED_EXCEPTION** and Latest publication for only the frozen Windows x86_64 / CPython 3.12 v1.2.0 distribution, with the limits below disclosed. The package and `v1.2.0` tag source remain `99e7f000e3ceb773071037f8b8e30f05091ba6fb` (tree `a5cbe6a0c318fad1d7fe3c48c547d88a2ef679bb`). The accepted base and CodeHead before this final documentation-only report are `eeed95dd6678330bd70437f756520d2f68761309`. This later report commit is outside the frozen bundle, source ZIP and tag source; this report does not name its own final commit SHA. The human decision is recorded in `D:\codex-tmp\tk12022\user-v120-release-decision.json`, and the independently reviewed Release body in `independent-release-body-approved-review.json`.

The permanent qualification gates remain **UNMET**. Toolkit native overall/broad-core-v1 coverage was 12,653/14,336 = 88.2603% and risk-core-v2 was 11,756/13,202 = 89.0471%, below their 90% floors; Monitor risk-core-v2 was 3,161/3,488 = 90.625%, below its 95% floor. The complete 6,476-node Toolkit matrix at `8c4760d670e448edc6adb13f4cc0c5347c87486b` ended 6,436 passed, 25 skipped, 12 failed and 3 errors. Later 10 corrected tests, 3 fixture nodes and 2 quiet timing nodes passed focused checks, but no complete matrix was rerun after those corrections. Monitor's original concurrent history-query p95 failure (118.805 ms > 100 ms) remains recorded alongside a quiet repeat PASS (51.0939 ms). Interactive browser, IDE/probe and new physical-target qualification have no new v1.2.0 PASS. The one-version exception permits delivery of the exact fixed package with these limits; it is not ordinary gate acceptance, a change to permanent thresholds, a passing complete matrix or new hardware authority. Earlier exceptions do not transfer to v1.2.0, and this decision does not transfer to later versions or changes.

GitHub [Release v1.2.0](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0), ID `420935068`, was published at `2026-10-22T22:54:53Z` (`2026-10-23 06:54:53` Asia/Shanghai), with `draft=false`, `prerelease=false` and 13 assets. Both the tagged-release and Latest API lookups resolved to that ID. The `v1.2.0` Git tag directly targets `99e7f000e3ceb773071037f8b8e30f05091ba6fb`; primary confirmed it with `git ls-remote` and a locally fetched tag. The Release `target_commitish` is the same full commit. `remote-published-metadata.json` records the normalized published body matching the approved body, and `github-v120-published-latest.jpg` records the visible Latest/source display.

`build_v120` downloaded all 13 public assets with HTTP 200 into `D:\codex-tmp\tk12022\remote-public-download99` and verified every downloaded SHA256 against the frozen build, all 12 `CHECKSUMS.sha256` entries, the manifest's frozen source and SHA256 `06fbccd4045afedd07ccad8f00999585a711a59d3d43554058ab9887f5b6b0b3`, the 64-wheel closure, ZIP CRC and matching inside/outside copies (`remote-public-verification.json`, `remote-public-independent-hashes.json`). The API-reported 13 names, sizes and SHA256 digests also matched the frozen build. Primary independently rehashed all 13 public downloads and all 13 local dist files, confirming names, sizes and SHA256 without executing the downloads (`primary-public-download-review.json`). The public Windows ZIP SHA256 is `b64fb651fb53c38568ba875e518d2d6bd16de1bae81ec8c2045fb83756691c9f`; the source ZIP SHA256 is `3e8be8bfc3b52131a3023d0a5ea53dea7a1c2903fc11ce5fcb9715630a59e849`. The build, isolated fresh installation and official v1.0.1-to-frozen-v1.2.0 upgrade evidence remain in the checkpoint below; the public downloads were verified, not installed or executed again.

The user manually enabled the Edge ChatGPT extension's temporary file-URL access for the upload and was reminded to turn it off afterward. Closure has not been independently confirmed; that browser setting is not a product qualification gate. The following post-freeze checkpoint is historical: its statements that no exception, assets, tag or Latest existed describe the earlier state, not this published disposition. Its original measured results and failed gates remain retained.

# STM32TK-120 frozen-package execution checkpoint (historical)

Recorded 2026-10-23 after source/package freeze. Local package construction, fresh installation and the official v1.0.1-to-v1.2.0 upgrade passed their recorded checks. Release qualification remains **NOT_ACCEPTED** under the unchanged permanent gates; no v1.2.0 exception has been granted. A GitHub Release draft exists with no assets, tag or Latest publication. The primary conversation agent owns qualification, independent diff review and remote delivery.

## Fixed identities and document boundary

| Item | Identity or status |
| --- | --- |
| Post-freeze documentation accepted base and CodeHead before this report commit | `99e7f000e3ceb773071037f8b8e30f05091ba6fb` |
| Preparation accepted base | `b80a712e1738ae6900f42bffc3ab6c80198654d1` |
| Frozen package and intended `v1.2.0` tag source | `99e7f000e3ceb773071037f8b8e30f05091ba6fb` |
| Frozen tree | `a5cbe6a0c318fad1d7fe3c48c547d88a2ef679bb` |
| Distribution | Windows x86_64, CPython 3.12, product version 1.2.0 |
| Local evidence root | `D:\codex-tmp\tk12022` |
| Qualification on 2026-10-23 | **NOT_ACCEPTED**; no v1.2.0 coverage exception has been granted |
| GitHub Release draft | ID `420935068`, `tag_name=v1.2.0`, `target_commitish=99e7f000e3ceb773071037f8b8e30f05091ba6fb`, `draft=true`, assets `[]`; [draft URL](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/untagged-753c2405bef477f82162) |
| Actual tag, published Release and Latest | None at this checkpoint; a draft with `tag_name=v1.2.0` does not establish the tag or publication |

Any report or `docs/release-status.md` commit made after this freeze is a later documentation identity. It is **not** part of the bundle or source ZIP. If the `v1.2.0` tag is created, its target must be the frozen `99e7f000e3ceb773071037f8b8e30f05091ba6fb` source, excluding those later commits. Git records the report commit separately; this report must not contain its own final commit SHA.

## Final local artifact identity

`build_v120` owns the official build and installation evidence. `D:\codex-tmp\tk12022\final-publish-summary.json` and `publish-build-compare.json` record two clean LF official builds at the frozen source, with all 13 asset names, sizes and SHA256 values byte-identical. The 12 entries in `CHECKSUMS.sha256`, archive CRC, 64-wheel closure, license and SBOM checks passed. `publish-dist-copy-check.json` records the 13 verified local copies at `D:\WorkSpace\STM32-Toolkit\dist\v1.2.0`. Primary independently rehashed all 13 assets, recomputed all 12 checksum entries and checked both ZIP manifest copies against the frozen source; see `primary-publish-assets-review.json`. `release_review` independently rehashed all 13 dist assets and checked manifest/source binding; see `independent-release-notes-review.json`.

These are **locally verified frozen-package** identities. The draft Release had no assets at this checkpoint, so remote download identity was not verified:

| Local asset | SHA256 recorded by the frozen-source build |
| --- | --- |
| `stm32-toolkit-1.2.0-windows-x86_64.zip` | `b64fb651fb53c38568ba875e518d2d6bd16de1bae81ec8c2045fb83756691c9f` |
| `release-manifest.json` | `06fbccd4045afedd07ccad8f00999585a711a59d3d43554058ab9887f5b6b0b3` |
| `CHECKSUMS.sha256` | `17713cba5784e342bebc8869f315e2cfe09a71aaa45b19a059864f179cf26785` |
| `stm32-toolkit-1.2.0-source.zip` | `3e8be8bfc3b52131a3023d0a5ea53dea7a1c2903fc11ce5fcb9715630a59e849` |

The earlier `d2c25706f87fc0c132e8cd1eeb774a32b6d9ebfa` and `55649e81dca5621faacdfa0168b36f90e6178715` package hashes are superseded and must not be presented as the frozen download. The historical official v1.0.1-to-d2 upgrade remains separate provisional evidence; `final-publish-summary.json` correctly marks it **not** as `99e7f000` identity evidence. A new frozen-source upgrade has its own record below.

### Frozen-bundle installation and local service

`build_v120`'s final `final-publish-summary.json` records an isolated `99e7f000` fresh installation: `Check` missing → `Bootstrap` → `Check` healthy, generation 1, followed by `pip check`, Toolkit/Monitor 1.2.0 launchers and PyOCD module/executable 0.45.1 with exit 0. It also records loopback HTTP authenticated API/UI 200, unauthenticated 401, wrong Host 403, no probe operation, and service-record/port cleanup after stop. `release_review` confirmed the fresh-install and HTTP records bind to the frozen source and manifest; this was read-only review, not a second installation. Loopback HTTP does not establish interactive browser, IDE or hardware qualification.

`build_v120` completed a separate fresh-root official v1.0.1 → `99e7f000` single-`Repair` upgrade, recorded in `final-upgrade-summary.json`. The old official ZIP SHA256 was `ed51a0e9773acc26010bfadae595fddbf99ba298080784a3d600509d861f1f8b`. In `install-upgrade-publish`, old `Check` missing → old `Bootstrap` healthy 1.0.1 generation 1 → old `Check` healthy; the frozen 99e bundle's read-only `Check` then reported repairable, one `Repair` produced healthy 1.2.0 generation 2, and final `Check` reported healthy/matching without mutation. All six stage exits were 0. User marker SHA256 values stayed unchanged; the old runtime was no longer active, and exactly one quarantined 1.0.1 runtime retained its Python interpreter. Staging cleanup, `pip check`, Toolkit/Monitor 1.2.0 and PyOCD module/executable 0.45.1 checks passed. No existing service or hardware was accessed. The final source and manifest were `99e7f000e3ceb773071037f8b8e30f05091ba6fb` and `06fbccd4045afedd07ccad8f00999585a711a59d3d43554058ab9887f5b6b0b3`. Primary independently read all six raw stage JSON files and exits and checked live marker/quarantine identities (`primary-final-upgrade-review.json`, PASS); this was review, not re-execution. The earlier d2 upgrade remains preserved separately, and this run does not claim a failure/rollback matrix.

## Software and qualification evidence

| Layer and owner | Recorded evidence | Disposition |
| --- | --- | --- |
| Toolkit complete matrix, `verify_v120` | On integrated `8c4760d670e448edc6adb13f4cc0c5347c87486b`, all 6,476 unique nodes completed: 6,436 passed, 25 skipped, 12 failed, 3 fixture errors. All three shard processes exited 1; preserve their logs and JUnit. | **FAIL**, not a full-suite PASS. |
| Toolkit focused corrections, `fix_windows_build` / `verify_v120` | Final test-only correction focused native run: 10 passed. The three fixture nodes reran 3 passed; two quiet timing nodes reran 2 passed. Evidence: `verify\out\matrix\focused10`, `fixture-focus` and `quiet-timing`. | Focused checks **PASS**; they do not rewrite the original full matrix. |
| Toolkit native branches, `verify_v120` | `verify\out\matrix\final-exact\python-toolkit-summary.json`: overall/broad-core-v1 12,653/14,336 = 88.2603%; risk-core-v2 11,756/13,202 = 89.0471%; all 111 tracked source files mapped with no missing files or blob mismatches. `final-exact\binding.json` binds the focused tree to frozen `99e7f000` tree and records unchanged product source versus the matrix. | Overall 90% and risk-core-v2 90% gates **UNMET**. |
| Monitor Python, `verify_v120` | Original full run 1,167 passed, 12 skipped, one performance failure; history-query p95 118.805 ms exceeded 100 ms under concurrent load. Later quiet repeat passed at p95 51.0939 ms; preserve both results. Native overall/risk-core-v2 3,161/3,488 = 90.625%. | Overall 90% met; risk-core-v2 95% **UNMET**. Original performance failure remains recorded. |
| UI, `ui_release_tests` / primary | At exact test-only `9d225d1519e41eee1ce4243497cb95769366bf9d`: 523 passed, one skipped; native branches 2,861/3,068 and all 34 positive-denominator source files at least 90%; type checks, lint, build and distribution verification passed. See `ui-fix-run\*-commit.log` and `coverage-summary.json`. | UI gate **PASS** for its recorded source and inputs; final asset binding is a separate package check. |

The final Toolkit native summary is a measurement, **not** a passing qualification result. The full matrix failures and the focused corrections retain separate identities. Historical v1.0.0/v1.0.1 coverage exceptions do not transfer. On 2026-10-23, no user-approved version-specific exception resolved the v1.2.0 Toolkit or Monitor deficits. Interactive browser, IDE/probe and new physical-target qualification had no new v1.2.0 PASS; prior firmware and receipts cannot be rebound to the new exact runtime identity.

## Release disposition and remote state on 2026-10-23

The final `99e7f000` two-build, 13-asset local identity, fresh installation and isolated official v1.0.1-to-1.2.0 `Repair` upgrade passed their owner checks. Primary independently checked all 13 local asset hashes, 12 checksum entries and both ZIP manifest copies (`primary-publish-assets-review.json`), and independently read the six upgrade stage JSON/exits and marker/quarantine evidence (`primary-final-upgrade-review.json`). `release_review` separately rehashed the 13 dist assets (`independent-release-notes-review.json`). These checks do not change the full-matrix failure or unmet permanent Toolkit/Monitor coverage gates. The qualification disposition therefore remained **NOT_ACCEPTED**.

The primary asynchronously asked the user for a v1.2.0-only exception and Latest decision, disclosing the exact coverage deficits, the original complete-matrix failures, 15 separate Toolkit focused passes, the absence of a complete post-correction suite, and the unfinished interactive browser, IDE and hardware qualification. No user reply or v1.2.0 exception was recorded at this checkpoint. The permanent thresholds and historical version-specific exceptions were unchanged.

`github-draft-state.json` records GitHub Release draft `420935068` at [its canonical draft URL](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/untagged-753c2405bef477f82162): `tag_name=v1.2.0`, full `target_commitish=99e7f000e3ceb773071037f8b8e30f05091ba6fb`, `draft=true`, assets `[]`. Its body was updated at 2026-10-22 16:21:08 UTC with the final upgrade and healthy-requires-no-mutation setup guidance. A further 13-asset upload attempt hit the same Edge ChatGPT extension file-URL permission error; browser URL policy also rejected the internal extensions page. No workaround or upload succeeded. The user was asked to manually enable that permission for upload and manually disable it afterward. No `v1.2.0` tag, public Release, Latest designation or verified remote download existed at this checkpoint. The [versioned Release page](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) was not an available download.

This two-file documentation checkpoint follows the `99e7f000` package/source freeze. Its eventual Git commit is separate from the package and intended tag source and is intentionally not named inside this report.

No product code, qualification threshold, old release tag/asset or historical evidence is changed by this report. The 2026-10-22 pre-freeze record remains in [the implementation report](implementation-report.md); the corresponding dated checkpoint remains in [release status](../../../release-status.md).
