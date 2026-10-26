# v1.3.2 frozen candidate: independent double build

Status: **LOCAL_CANDIDATE_NOT_QUALIFIED**. Software fixes and packaging are
complete; the current coverage/reuse limitations require candidate-specific
disposition before publication. The earlier v1.3.1 exception is not reused.

Frozen source: `acb71b9f39e8ae4799179b0cab088245c0a5ea5b`.
This differs from tested CodeHead `c1985337bb1b74eab38deb12509ace22f191ab07`
only in three primary-owned governance documents. Product/test bytes are unchanged.
The source archives and manifests bind the frozen source, not a later evidence
commit. [Software review](version-review.md) retains actual execution owners,
failures, fixes, platform skips and source-aware native branch reconciliation.

## Build and verification evidence

The primary ran the existing official `tools/release/build_0900_artifacts.py build`
twice, using clean independent worktrees `v132-review/STM32-Toolkit` and
`v132-package-review/STM32-Toolkit`, at the exact frozen source and verified offline
wheelhouse `D:/codex-tmp/fi24/wheelhouse`. Both commands exited 0. Each tree was
compared with exact Git-archive bytes before packaging; both required zero byte
restorations and had no ignored build residue. No package index or real runtime
installation was used.

Output roots: `D:/codex-tmp/r132/frozen-package-a` and `frozen-package-b`.
Both contain exactly 13 release files. Their names, lengths and SHA-256 hashes
match individually. Each CHECKSUMS file verifies the other 12 files, and the
CHECKSUMS files themselves also match. The manifests identify product 1.3.2,
the exact frozen source, 52 MCP tools and 9 Skills. Source-archive digests match.

The Windows bundle was safely extracted into
`D:/codex-tmp/r132/frozen-bundle/stm32-toolkit-1.3.2`. The separate worktree's
official `verify-bundle --toolkit-root <that directory> --json` exited 0.

Windows ZIP: **113,770,074 bytes**.
SHA-256: `1773a5e6b61a882bbd3d77a2a23902bd24f88ed296fb6e12dfccc03594c77f79`.

Machine-readable [candidate assets](candidate-assets.json) copy the primary's
run-local `D:/codex-tmp/r132/frozen-package-verification.json`, SHA-256
`f56d98749e4810d05c9e35c10147b0e1d4235d1d139e1515ac1474ed615423b4`.
That record also binds the exact native qualification JSON by SHA-256. Raw
commands, stdout, coverage, archive checks and original failed runs are retained
under `D:/codex-tmp/r132`; they are not presented as physical or IDE evidence.

## Outstanding qualification decision

Toolkit overall is 15381/17618 = 87.3028%; risk-core-v2 is 14310/16354 =
87.5015%, both below the permanent 90% floor. Monitor risk-core-v2 is
3227/3498 = 92.2527%, below 95%; its overall 90% gate passes. The complete
native denominator and frozen membership are retained.

Current affected groups pass with three native symlink cases deferred. Other
unchanged source uses explicitly bound historical evidence, including that old
matrix's 19 platform/historical-data skips. This is not a new final-head full
rerun. Applicable unchanged UI evidence is reused; it is not a fresh browser run.
Final installation and VS Code testing are user-owned and
**USER_VALIDATION_PENDING**. Setup's 45 isolated fixture cases passed, which does
not claim installation of this final package or physical upgrade/rollback.
No original project, installed runtime, global settings or hardware was modified.

The next decision is whether to accept these disclosed limits only for this
frozen candidate or continue work toward the permanent gates. GitHub Latest is
still v1.3.1; no v1.3.2 tag, release or remote write exists at this checkpoint.
