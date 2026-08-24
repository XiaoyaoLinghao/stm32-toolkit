# STM32TK-0902 VS09-B implementation report

## Ownership and frozen inputs

- Slice: STM32 Toolkit 0.9 VS09-B installation, upgrade, security, and release artifacts.
- Implementer: GPT-5.6-luna, reasoning effort `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent; this report does not issue a verdict.
- Accepted VS09-A base: `22bff0061e54e37eba22d892a3b8c34949c3b130`.
- Version accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Frozen specification: `4f91a92dcdd1a3b5a0efb2b535fb0274ee075d1b`.
- Frozen implementation plan: `d452d5e782d5829efacc9f961e4d4c0847ed1e76`.
- Correction-round-2 addendum: `2b15726c80c35237d769e3acb84e640df1721a84`.
- Branch/worktree: `codex/STM32TK-0902-INSTALL-UPGRADE-RELEASE` / `C:/tmp/stm32tk-0902-install-upgrade-release`.
- Product CodeHead, frozen before this report commit:
  `caae6bca5fc8da519f75b615bfa57c56dacae37d`.

The product retains one setup/runtime lifecycle and registration authority, exactly 48 MCP tools
and 8 Skills, and no controller/provider/backend, Agent-specific product logic, second runtime,
additional Python/platform target, CI, collaboration automation, hardware behavior, VS10, or
remote mutation.

## Product and test inventory

The complete accepted-base-to-Product-CodeHead product/test inventory is:

- `.gitattributes`, `LICENSE`, `README.md`, `README_zh-CN.md`;
- `bin/setup-stm32-env.ps1`;
- `schemas/stm32-release.schema.json`;
- `skills/setup-stm32-env/SKILL.md`;
- `tools/release/build_0900_artifacts.py`;
- `tools/release/release_0900_policy.json`;
- `tools/release/licenses/spdx/Apache-2.0.txt`, `BSD-3-Clause.txt`, `CC0-1.0.txt`,
  `MIT.txt`, `MPL-2.0.txt`, and `PSF-2.0.txt`;
- `tools/stm32-monitor/pyproject.toml` and `tools/stm32-monitor/tests/test_package_boundary.py`;
- `tools/stm32-toolkit/pyproject.toml`;
- `tools/stm32-toolkit/tests/release/test_0900_artifacts.py`;
- `tools/stm32-toolkit/tests/test_0900_security.py` and
  `tools/stm32-toolkit/tests/test_setup_runtime.py`.

Round-2 implementation commits before the report are `5224b0a648cf44c5e56932af89b3287b0c59a3a7`
(full canonical SPDX authority, setup-owned in-memory trust execution, and RED coverage),
`df1cd3e25abcbfe30ed1f2ba5b58a6640c8feed6` (bind anchor verification to archived source bytes),
and `caae6bca5fc8da519f75b615bfa57c56dacae37d` (refresh the final archived utility digest).

The bootstrap trust root is the externally checksummed setup script. It reads ordinary utility and
policy bytes, checks the frozen digests, and sends those retained bytes through the existing
bootstrap CPython process using an argument array and an in-memory launcher. The builder binds the
constants to the exact `git archive` bytes that become the extracted ToolkitRoot; this accounts for
Windows checkout filters and prevents a worktree hash from authorizing different extracted bytes.
The final archived digests are utility
`30f77206434d79d5ee8f912b754f75a4c43d24766c3b4f2c8d739b39957d13e0` and policy
`d5226dbd38a63e011d9a4456f9fbd89750244becef5ea49f99210affcebf7b66`.

## TDD evidence and classifications

Round-2 RED was recorded before the corresponding product fixes:

- canonical-authority tests failed because `licenseTextHashes` and source-controlled full texts
  were absent;
- the candidate-shaped setup utility replacement, policy swap, and changed-after-read probes
  showed attacker execution/marker creation before the trust fix;
- the archive-anchor test failed because setup constants matched filtered worktree bytes rather
  than the CRLF bytes emitted by `git archive`.

These were PRODUCT contract failures. Existing round-1 RED coverage for closed source/release
membership, exact manifest/wheel closure, provenance, marker parsing, license/SBOM structure, and
runtime-state acceptance remained in place. The first candidate build attempt was rejected as an
incomplete disposable input wheelhouse (`closed build backend is unavailable`); this was classified
ENVIRONMENT/INPUT, fixed by adding the exact offline `setuptools==84.0.0` and `wheel==0.48.0`
wheels, and did not relax product policy.

Final affected GREEN evidence:

- `py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q -p no:cacheprovider`
  — **36 passed**;
- `py -3.12 -m pytest tools/stm32-toolkit/tests/test_0900_security.py -q -p no:cacheprovider`
  — **27 passed**;
- the final trust-boundary subset of `test_setup_runtime.py` — **4 passed**;
- the earlier complete setup-runtime matrix completed with no failures; the final real-candidate
  Bootstrap/Check/Repair/refusal probes below exercised the same setup boundary at the frozen
  Product CodeHead;
- `py -3.12 -m py_compile tools/release/build_0900_artifacts.py` — exit 0;
- `git diff --check` — exit 0 for the final working tree.

An accidental broad full-Toolkit run was stopped by the parent after approximately 8.5 minutes and
4,445 disposable files because it exceeded the frozen affected matrix. It was interrupted,
out-of-scope verification with no result attribution; it is not a PASS or FAIL gate. Hardware,
physical-board, and other platform-only evidence remains deferred to the named later owner.

## Candidate reproducibility, schema, storage, and licenses

The exact disposable Windows CPython 3.12 binary wheelhouse was used only for input acquisition.
Final candidate build commands were offline/no-index and used the same wheelhouse for both builds.
The two final candidates had identical relative file lists, sizes, and SHA-256 values for all 13
files. Each candidate's `CHECKSUMS.sha256` independently verified **12/12** entries.

The retained self-contained candidate is:

`C:/tmp/p0902-final-candidate-vs09b-r2`

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `CHECKSUMS.sha256` | 1073 | `0dd47dfc15626cbfaa123125b669fd0c7460aa19bd2d614aea192418218dd34d` |
| `LICENSE` | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| `THIRD-PARTY-NOTICES.md` | 2615 | `c9a740027186fc46351903a24913ccbfbcaf4341c86ed5d782bfd47e3151f1ea` |
| `compatibility.md` | 1742 | `309159534892c68f938000c09177b1ad34a34594f690be2828c64ca6ea6fa439` |
| `licenses.zip` | 413750 | `d88d44c4381ac5ebcfd6529dd7c55480109e4ade29e6b9f6511153cecb2ba0ed` |
| `monitor-assets.json` | 975 | `e08692c6b519cc90c82cae2ce972ae9f9636ea6796196d6418fe44c4479403c6` |
| `release-manifest.json` | 15813 | `5224607a8b0de16647ed615ba9d36b050d0ba4b6bf49e00dc5ecbc6692e76d0b` |
| `sbom.spdx.json` | 191430 | `cc8bbeaf8f4a07cffb447166f78bac7d19f1179b022bd29e30073643bfcb5021` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 1244802 | `565ec5e1207aa48fa843f3a18788826aff01da00ac02757a45472ca7529e4151` |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 2510618 | `75c8b168813f3f6a061e8035d2f6c52e238cb7d2217df176b72c2c75be12b8fa` |
| `stm32-toolkit-0.9.0-source.zip` | 12911385 | `416475a37a9061f3126efb2921f70a310c79f9febd9306ee97da151a2dcb2e3d` |
| `stm32-toolkit-0.9.0-windows-x86_64.zip` | 98961682 | `e70f5367759e7581dbdfc9fd685d8a47fdb5e2e479afc009b5fef6180f558f3f` |
| `troubleshooting.md` | 675 | `86d99f7cdb22964ec039887aafc4bf41a9c0a22a5def8fa24418b52da097676` |

The manifest has schema `stm32-toolkit-release/1`, 64 normalized wheels (62 external plus Toolkit
and Monitor), six artifact entries, source commit `caae6bca5fc8da519f75b615bfa57c56dacae37d`,
and inventory 48/8. The extracted Windows bundle passed `verify-bundle` with manifest SHA
`5224607a8b0de16647ed615ba9d36b050d0ba4b6bf49e00dc5ecbc6692e76d0b` and utility SHA
`30f77206434d79d5ee8f912b754f75a4c43d24766c3b4f2c8d739b39957d13e0`.

The license archive has 86 members: 80 wheel-shipped license/NOTICE/COPYING materials plus six
complete source-controlled SPDX texts. The policy and source files bind these exact hashes:

| SPDX | SHA-256 | Bytes |
| --- | --- | ---: |
| Apache-2.0 | `240b8a39fdfd2bd3b3539c02e34466334884fc84b056b57f06e9da35323ecd97` | 11360 |
| BSD-3-Clause | `aad753d6c862eb1a2a10afd82583bcf9623a6b9a9866f74360dc1340f8d06f98` | 1461 |
| CC0-1.0 | `df8feba9f3469adec9c1c794633af3edb101f09e1641624ff78282f32ea410ea` | 6941 |
| MIT | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` | 1075 |
| MPL-2.0 | `4644cfa1be77f07944fcda50ab46d1df715e3ff41475936970c0208f72c4d06d` | 16728 |
| PSF-2.0 | `247e3814570d91389681031a3ce8e818eedd04f6e1176836fd78d71ee521d752` | 2426 |

The SBOM contains 491 unique authorities: 62 Python, 2 product, and 427 UI packages. Relationship
counts are `DESCRIBES=2`, `DEPENDS_ON=96`, and `GENERATED_FROM=427`; duplicate `(name,version)`
authority count is 0 and `NOASSERTION` license count is 0.

## Security and lifecycle integration evidence

The final candidate's fresh extracted root was tested with the standard-library ZIP extractor.
The following candidate-shaped probes failed closed before attacker execution, staging, or
quarantine:

- replaced extracted release utility: Check exit 0 with `bundle.status=invalid`; Bootstrap exit 2;
  both marker absent and staging absent;
- swapped extracted release policy: Bootstrap exit 2, staging absent;
- changed-after-read utility fixture: Bootstrap exit 2, staging absent.

Fresh offline install used a clean explicit project/data root with `PYTHONPATH`, `PYTHONHOME`,
`PIP_*`, and user-package variables removed. It produced:

- Bootstrap exit 0, managed CPython 3.12.10, Toolkit/Monitor 0.9.0, runtime-state schema 1,
  generation 1, and matching manifest/source identity;
- Check exit 0 with healthy runtime, valid bundle, and matching state;
- managed `pip check` exit 0 (`No broken requirements found`);
- doctor exit 0 with protocol `stm32-toolkit/1`, 48 MCP tools, 8 Skills, and Toolkit/Monitor 0.9.0.

A fresh 0.3.0 legacy profile was checked as broken and repaired offline. Repair exited 0, promoted
0.9.0, removed the legacy path, and preserved its marker in one timestamped `.quarantine` entry.
Separate recorded-state profiles refused a highest-installed 1.0.0 downgrade and a same-version
source/manifest conflict: both Bootstrap commands exited 2, created no `.staging` or
`.quarantine`, and left the state file byte-equivalent. Existing explicit project and Monitor
storage preservation/rollback behavior remains covered by the affected regression suite.

## Cleanup and local Git state

All disposable product p0902 candidates, extracted profiles, wheelhouse, basetemps, logs, failure
outputs, and generated test roots were removed after evidence capture. Exactly one named final
candidate remains at `C:/tmp/p0902-final-candidate-vs09b-r2`. Sol review roots
`C:/tmp/p0902-sol-r1-tamper`, `C:/tmp/p0902-sol-r2-bootstrap`, and its retained data/project roots
were preserved untouched.

The branch is clean, local, unpushed, and has no upstream. No push, PR, merge, tag, release,
remote branch deletion, authentication, upload, hardware, or other remote operation occurred.
This report is committed separately after the Product CodeHead and intentionally contains neither
its own commit SHA nor an acceptance verdict; the independent reviewer owns the complete-diff
review and final decision.
